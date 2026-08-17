"""Delivery notes (Surat Jalan).

A sales order can go out in several trips, so each delivery is its own
numbered document drawing down the ordered quantities. The rule that matters
is that you cannot deliver more of a line than was ordered.

Cancelled notes release their quantities; every other status holds them, so a
draft note reserves stock and two people cannot promise the same goods twice.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import auth
import models
import numbering
import schemas
from database import get_db

router = APIRouter(prefix="/delivery-notes", tags=["delivery notes"])

EDITABLE_STATUSES = {"draft", "issued"}

ALLOWED_TRANSITIONS = {
    "draft": {"issued", "cancelled"},
    "issued": {"delivered", "draft", "cancelled"},
    "delivered": {"issued"},
    "cancelled": {"draft"},
}

# A cancelled note has released its goods; the rest still hold them.
COMMITTED_STATUSES = ("draft", "issued", "delivered")

ZERO = Decimal("0.00")


def _qty(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _show(value) -> str:
    """Quantity for a human: 10 rather than 10.00, but 2.5 stays 2.5.

    Decimal ignores the `g` format spec the way floats honour it, so trim
    the zeros explicitly.
    """
    text = f"{Decimal(str(value or 0)):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


# ------------------------------------------------------------------ helpers
def _delivered_by_line(db: Session, sales_order_id: int, exclude_note_id=None) -> dict:
    """Quantity already committed per sales order line.

    `exclude_note_id` leaves the note being edited out of the tally, so
    re-saving it does not count its own quantities against itself.
    """
    query = (
        db.query(models.DeliveryNoteItem)
        .join(models.DeliveryNote)
        .filter(
            models.DeliveryNote.sales_order_id == sales_order_id,
            models.DeliveryNote.status.in_(COMMITTED_STATUSES),
        )
    )
    if exclude_note_id is not None:
        query = query.filter(models.DeliveryNote.id != exclude_note_id)

    totals = {}
    for item in query.all():
        totals[item.sales_order_item_id] = totals.get(
            item.sales_order_item_id, ZERO
        ) + Decimal(str(item.quantity))
    return totals


def outstanding_lines(db: Session, so: models.SalesOrder, exclude_note_id=None):
    """What is still waiting to go out, line by line."""
    delivered = _delivered_by_line(db, so.id, exclude_note_id)
    lines = []
    for item in so.items:
        already = _qty(delivered.get(item.id, ZERO))
        ordered = _qty(item.quantity)
        lines.append(
            schemas.OutstandingLine(
                sales_order_item_id=item.id,
                line_no=item.line_no,
                product_code=item.product_code,
                product_name=item.product_name,
                description=item.description,
                width_cm=item.width_cm,
                height_cm=item.height_cm,
                ordered=ordered,
                delivered=already,
                outstanding=_qty(ordered - already),
            )
        )
    return lines


def _to_out(note: models.DeliveryNote) -> schemas.DeliveryNoteOut:
    out = schemas.DeliveryNoteOut.model_validate(note)
    so = note.sales_order
    if so:
        out.so_no = so.so_no
        out.po_reference = so.po_reference
        if so.customer:
            out.customer_name = so.customer.name
            out.customer_code = so.customer.code
    if note.creator:
        out.created_by_name = note.creator.full_name
    if note.company:
        out.company_name = note.company.name
        out.company_code = note.company.code
    out.total_qty = _qty(sum((Decimal(str(i.quantity)) for i in note.items), ZERO))
    return out


def _apply_items(db: Session, note: models.DeliveryNote, items) -> None:
    """Replace the note's lines, refusing to over-deliver any order line."""
    so = note.sales_order or db.get(models.SalesOrder, note.sales_order_id)
    by_id = {item.id: item for item in so.items}
    already = _delivered_by_line(db, so.id, exclude_note_id=note.id)

    if not items:
        raise HTTPException(status_code=422, detail="A delivery note needs at least one line")

    wanted = {}
    for position, line in enumerate(items, start=1):
        order_line = by_id.get(line.sales_order_item_id)
        if not order_line:
            raise HTTPException(
                status_code=422,
                detail=f"Line {position}: that line is not on sales order {so.so_no}",
            )
        wanted[line.sales_order_item_id] = wanted.get(
            line.sales_order_item_id, ZERO
        ) + Decimal(str(line.quantity))

    for order_line_id, requested in wanted.items():
        order_line = by_id[order_line_id]
        remaining = _qty(Decimal(str(order_line.quantity)) - already.get(order_line_id, ZERO))
        if _qty(requested) > remaining:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{order_line.product_code}: only {_show(remaining)} of "
                    f"{_show(order_line.quantity)} left to deliver, "
                    f"but {_show(requested)} was entered"
                ),
            )

    note.items.clear()
    for position, line in enumerate(items, start=1):
        order_line = by_id[line.sales_order_item_id]
        note.items.append(
            models.DeliveryNoteItem(
                line_no=position,
                sales_order_item_id=order_line.id,
                product_code=order_line.product_code,
                product_name=order_line.product_name,
                description=line.description or order_line.description,
                width_cm=order_line.width_cm,
                height_cm=order_line.height_cm,
                quantity=Decimal(str(line.quantity)),
                unit=line.unit or "pcs",
            )
        )


def _fill_from_order(note: models.DeliveryNote, so: models.SalesOrder) -> None:
    defaults = {
        "deliver_to": so.deliver_to or (so.customer.name if so.customer else None),
        "deliver_address": so.deliver_address or so.address,
        "phone": so.phone,
    }
    for field, value in defaults.items():
        if not getattr(note, field):
            setattr(note, field, value)


def _load_order(db: Session, sales_order_id: int) -> models.SalesOrder:
    so = db.get(models.SalesOrder, sales_order_id)
    if not so:
        raise HTTPException(status_code=422, detail="Unknown sales_order_id")
    if so.status in ("draft", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Confirm the sales order before delivering it (it is '{so.status}')",
        )
    return so


# ------------------------------------------------------------------- routes
@router.get("", response_model=List[schemas.DeliveryNoteListOut])
def list_delivery_notes(
    status_filter: Optional[str] = Query(None, alias="status"),
    sales_order_id: Optional[int] = None,
    company_id: Optional[int] = None,
    q: Optional[str] = Query(None, description="Search by SJ number"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.DeliveryNote)
    if status_filter:
        query = query.filter(models.DeliveryNote.status == status_filter)
    if sales_order_id:
        query = query.filter(models.DeliveryNote.sales_order_id == sales_order_id)
    if company_id:
        query = query.filter(models.DeliveryNote.company_id == company_id)
    if q:
        query = query.filter(models.DeliveryNote.sj_no.like(f"%{q}%"))
    if date_from:
        query = query.filter(models.DeliveryNote.delivery_date >= date_from)
    if date_to:
        query = query.filter(models.DeliveryNote.delivery_date <= date_to)

    rows = query.order_by(models.DeliveryNote.id.desc()).offset(offset).limit(limit).all()

    results = []
    for row in rows:
        item = schemas.DeliveryNoteListOut.model_validate(row)
        if row.sales_order:
            item.so_no = row.sales_order.so_no
            if row.sales_order.customer:
                item.customer_name = row.sales_order.customer.name
        if row.creator:
            item.created_by_name = row.creator.full_name
        if row.company:
            item.company_name = row.company.name
            item.company_code = row.company.code
        item.line_count = len(row.items)
        item.total_qty = _qty(sum((Decimal(str(i.quantity)) for i in row.items), ZERO))
        item.can_edit = auth.is_admin(current_user) or row.created_by == current_user.id
        results.append(item)
    return results


@router.get("/outstanding/{sales_order_id}", response_model=schemas.SalesOrderDeliveryStatus)
def delivery_status(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """What is left to deliver on an order - drives the 'new Surat Jalan' form."""
    so = db.get(models.SalesOrder, sales_order_id)
    if not so:
        raise HTTPException(status_code=404, detail="Sales order not found")
    lines = outstanding_lines(db, so)
    return schemas.SalesOrderDeliveryStatus(
        sales_order_id=so.id,
        so_no=so.so_no,
        fully_delivered=all(line.outstanding <= 0 for line in lines) and bool(lines),
        lines=lines,
    )


@router.get("/{note_id}", response_model=schemas.DeliveryNoteOut)
def get_delivery_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    note = db.get(models.DeliveryNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Delivery note not found")
    return _to_out(note)


@router.post(
    "/from-sales-order/{sales_order_id}",
    response_model=schemas.DeliveryNoteOut,
    status_code=status.HTTP_201_CREATED,
)
def create_from_sales_order(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Draft a Surat Jalan for everything still outstanding on the order."""
    so = _load_order(db, sales_order_id)
    remaining = [line for line in outstanding_lines(db, so) if line.outstanding > 0]
    if not remaining:
        raise HTTPException(
            status_code=409,
            detail=f"Everything on {so.so_no} has already been delivered",
        )

    note = models.DeliveryNote(
        sales_order_id=so.id,
        company_id=so.company_id,      # goods go out under the order's entity
        delivery_date=date.today(),
        status="draft",
        created_by=current_user.id,
    )
    _fill_from_order(note, so)
    _apply_items(db, note, [
        schemas.DeliveryNoteItemIn(
            sales_order_item_id=line.sales_order_item_id, quantity=line.outstanding
        )
        for line in remaining
    ])

    numbering.allocate(
        db, note, models.DeliveryNote.sj_no,
        numbering.scoped(numbering.PREFIXES["delivery_note"],
                         so.company.code if so.company else None),
        note.delivery_date,
    )
    db.refresh(note)
    return _to_out(note)


@router.post("", response_model=schemas.DeliveryNoteOut, status_code=status.HTTP_201_CREATED)
def create_delivery_note(
    payload: schemas.DeliveryNoteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Create a partial delivery with explicit quantities."""
    so = _load_order(db, payload.sales_order_id)

    note = models.DeliveryNote(
        **payload.model_dump(exclude={"items", "sales_order_id", "company_id"})
    )
    note.sales_order_id = so.id
    note.company_id = so.company_id
    note.delivery_date = payload.delivery_date or date.today()
    note.status = "draft"
    note.created_by = current_user.id
    _fill_from_order(note, so)
    _apply_items(db, note, payload.items)

    numbering.allocate(
        db, note, models.DeliveryNote.sj_no,
        numbering.scoped(numbering.PREFIXES["delivery_note"],
                         so.company.code if so.company else None),
        note.delivery_date,
    )
    db.refresh(note)
    return _to_out(note)


@router.put("/{note_id}", response_model=schemas.DeliveryNoteOut)
def update_delivery_note(
    note_id: int,
    payload: schemas.DeliveryNoteUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    note = db.get(models.DeliveryNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Delivery note not found")
    auth.require_owner_or_admin(current_user, note, "delivery note")
    if note.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"A '{note.status}' delivery note can no longer be edited",
        )

    changes = payload.model_dump(exclude={"items"}, exclude_unset=True)
    changes.pop("company_id", None)
    for field, value in changes.items():
        setattr(note, field, value)

    items = payload.items if payload.items is not None else [
        schemas.DeliveryNoteItemIn(
            sales_order_item_id=line.sales_order_item_id,
            quantity=line.quantity,
            unit=line.unit,
            description=line.description,
        )
        for line in note.items
    ]
    _apply_items(db, note, items)

    db.commit()
    db.refresh(note)
    return _to_out(note)


@router.patch("/{note_id}/status", response_model=schemas.DeliveryNoteOut)
def change_status(
    note_id: int,
    payload: schemas.DeliveryNoteStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    note = db.get(models.DeliveryNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Delivery note not found")
    auth.require_owner_or_admin(current_user, note, "delivery note")

    allowed = ALLOWED_TRANSITIONS.get(note.status, set())
    if payload.status != note.status and payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move a delivery note from '{note.status}' to '{payload.status}'",
        )

    # Reinstating a cancelled note must not overshoot what is left on the order.
    if note.status == "cancelled" and payload.status != "cancelled":
        _apply_items(db, note, [
            schemas.DeliveryNoteItemIn(
                sales_order_item_id=line.sales_order_item_id,
                quantity=line.quantity,
                unit=line.unit,
                description=line.description,
            )
            for line in note.items
        ])

    note.status = payload.status
    if payload.status == "delivered":
        note.received_by = payload.received_by or note.received_by
        note.received_at = payload.received_at or date.today()

    db.commit()
    db.refresh(note)
    return _to_out(note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_delivery_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    note = db.get(models.DeliveryNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Delivery note not found")
    auth.require_owner_or_admin(current_user, note, "delivery note")
    if note.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Only a draft delivery note can be deleted - cancel it instead",
        )
    db.delete(note)
    db.commit()


SLOT_ORDER = {"morning": 0, "afternoon": 1, "evening": 2, None: 3}


@router.get("/schedule/board", response_model=schemas.DeliverySchedule)
def schedule(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    driver: Optional[str] = None,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """The delivery run sheet: what goes out, when, on which vehicle.

    Defaults to the coming fortnight. Notes still sitting in draft with a date
    in the past are surfaced as overdue rather than quietly dropped off the
    end of the board.
    """
    start = date_from or date.today()
    end = date_to or (start + timedelta(days=14))

    query = db.query(models.DeliveryNote).filter(
        models.DeliveryNote.status != "cancelled",
        models.DeliveryNote.delivery_date >= start,
        models.DeliveryNote.delivery_date <= end,
    )
    if driver:
        query = query.filter(models.DeliveryNote.driver_name.like(f"%{driver}%"))
    if company_id:
        query = query.filter(models.DeliveryNote.company_id == company_id)
    notes = query.all()

    # Anything undelivered and already past its date, however far back.
    overdue = (
        db.query(models.DeliveryNote)
        .filter(
            models.DeliveryNote.status.in_(("draft", "issued")),
            models.DeliveryNote.delivery_date < start,
        )
        .all()
    )

    def to_stop(note):
        stop = schemas.ScheduleStop.model_validate(note)
        if note.sales_order:
            stop.so_no = note.sales_order.so_no
            if note.sales_order.customer:
                stop.customer_name = note.sales_order.customer.name
        stop.line_count = len(note.items)
        stop.total_qty = _qty(
            sum((Decimal(str(i.quantity)) for i in note.items), ZERO)
        )
        stop.can_edit = auth.is_admin(current_user) or note.created_by == current_user.id
        return stop

    by_day = {}
    for note in notes + overdue:
        by_day.setdefault(note.delivery_date, []).append(note)

    today = date.today()
    days = []
    for day in sorted(by_day):
        stops = sorted(
            by_day[day],
            key=lambda n: (SLOT_ORDER.get(n.time_slot, 3), n.sj_no),
        )
        days.append(
            schemas.ScheduleDay(
                delivery_date=day,
                is_today=day == today,
                is_overdue=day < today
                and any(n.status in ("draft", "issued") for n in stops),
                stop_count=len(stops),
                total_qty=_qty(
                    sum(
                        (Decimal(str(i.quantity)) for n in stops for i in n.items),
                        ZERO,
                    )
                ),
                stops=[to_stop(n) for n in stops],
            )
        )

    # Confirmed orders with goods outstanding and no delivery note at all.
    scheduled_orders = {n.sales_order_id for n in notes + overdue}
    pending = (
        db.query(models.SalesOrder)
        .filter(
            models.SalesOrder.status.in_(("confirmed", "in_production")),
            ~models.SalesOrder.id.in_(scheduled_orders or [0]),
        )
        .all()
    )
    unscheduled = []
    for so in pending:
        lines = outstanding_lines(db, so)
        if any(line.outstanding > 0 for line in lines):
            unscheduled.append(
                schemas.ScheduleStop(
                    id=0,
                    sj_no="-",
                    status="unscheduled",
                    so_no=so.so_no,
                    customer_name=so.customer.name if so.customer else None,
                    deliver_to=so.deliver_to,
                    deliver_address=so.deliver_address,
                    phone=so.phone,
                    total_qty=_qty(sum((line.outstanding for line in lines), ZERO)),
                    line_count=sum(1 for line in lines if line.outstanding > 0),
                )
            )

    return schemas.DeliverySchedule(
        date_from=start, date_to=end, days=days, unscheduled=unscheduled
    )
