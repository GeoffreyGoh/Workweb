"""Generate a year of realistic transactions for demos and training.

    python seed.py --demo

Documents are built through the real pricing and numbering modules rather than
by inserting rows, so every total, discount and document number is exactly what
the application itself would produce.

Deals are spread across the last ten months so the monthly report has something
to draw, and purchase costs are set as a share of order value so the margin
report shows plausible figures instead of noise.

Everything here is fiction: the customers, suppliers and staff are invented.
"""

import calendar
import random
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

import models
import numbering
import pricing

# Fixed seed: two people running this get the same database.
rng = random.Random(20260810)

TODAY = date.today()


# --------------------------------------------------------------------- dates
def months_ago(count: int, day: int = 1) -> date:
    """A date `count` months back, clamped to a valid day of that month."""
    year = TODAY.year + (TODAY.month - 1 - count) // 12
    month = (TODAY.month - 1 - count) % 12 + 1
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def at(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour, rng.randint(0, 59)))


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------- scenarios
# (product code, qty, width_cm, height_cm) - width/height ignored for per_unit
DEALS = [
    dict(
        month=9, day=6, customer="CUST-003", user="budi", discount=35,
        surveyor="Agus Prasetyo", note="Renovasi 24 kamar lantai 3-4.",
        lines=[("RB-BO-01", 24, 180, 240), ("TRK-DBL-AL", 24, 200, None),
               ("INS-STD", 24, None, None)],
        quotation="converted", order="completed",
        purchases=[("SUP-001", 0.42), ("SUP-002", 0.14)],
        deliveries=[1.0], payments=[0.5, 0.5],
    ),
    dict(
        month=8, day=14, customer="CUST-001", user="sari", discount=35,
        note="Kantor pusat lantai 8.",
        lines=[("RB-SS-05", 18, 150, 220), ("VB-ALU-25", 6, 120, 150),
               ("INS-STD", 24, None, None)],
        quotation="converted", order="completed",
        purchases=[("SUP-001", 0.38), ("SUP-002", 0.18)],
        deliveries=[1.0], payments=[0.3, 0.7],
    ),
    dict(
        month=7, day=3, customer="CUST-005", user="budi", discount=30,
        note="Rumah pribadi, 2 lantai.",
        lines=[("CT-BLK-01", 6, 300, 280), ("CT-SHR-01", 6, 300, 280),
               ("TRK-DBL-AL", 6, 320, None), ("INS-STD", 6, None, None)],
        quotation="converted", order="completed",
        purchases=[("SUP-001", 0.46)],
        deliveries=[1.0], payments=[0.5, 0.5],
    ),
    dict(
        month=6, day=21, customer="CUST-004", user="sari", discount=40,
        note="Show unit tower B - 3 tipe unit.",
        lines=[("RB-DIM-01", 45, 160, 200), ("VRT-FB-89", 12, 240, 260),
               ("INS-STD", 57, None, None), ("SRV-DELIV", 2, None, None)],
        quotation="converted", order="completed",
        purchases=[("SUP-001", 0.40), ("SUP-002", 0.12), ("SUP-005", 0.05)],
        deliveries=[0.6, 0.4], payments=[0.4, 0.6],
    ),
    dict(
        month=5, day=9, customer="CUST-007", user="agus", discount=35,
        note="Ruang rawat inap lantai 2. Bahan wipe-clean.",
        lines=[("VRT-PVC-89", 32, 200, 240), ("INS-STD", 32, None, None),
               ("SRV-REMOVE", 32, None, None)],
        quotation="converted", order="completed",
        purchases=[("SUP-001", 0.44)],
        deliveries=[1.0], payments=[1.0],
    ),
    dict(
        month=4, day=17, customer="CUST-006", user="budi", discount=25,
        note="Proyek residensial klien studio.",
        lines=[("CT-RMN-01", 8, 140, 180), ("RB-ZEB-01", 10, 160, 200),
               ("INS-STD", 18, None, None)],
        quotation="converted", order="completed",
        purchases=[("SUP-001", 0.48)],
        deliveries=[1.0], payments=[0.5, 0.5],
    ),
    dict(
        month=3, day=11, customer="CUST-010", user="sari", discount=35,
        note="Restoran cabang BSD.",
        lines=[("VB-WD-50", 9, 120, 160), ("CT-LIN-01", 4, 280, 300),
               ("ROD-WD-28", 4, 300, None), ("INS-STD", 13, None, None)],
        quotation="converted", order="delivered",
        purchases=[("SUP-004", 0.40), ("SUP-001", 0.14)],
        deliveries=[1.0], payments=[0.5],
    ),
    dict(
        month=2, day=5, customer="CUST-003", user="budi", discount=35,
        note="Lanjutan renovasi - lantai 5.",
        lines=[("RB-BO-02", 20, 180, 240), ("MTR-TUB-45", 20, None, None),
               ("MTR-HUB-WIFI", 2, None, None), ("INS-HIGH", 20, None, None)],
        quotation="converted", order="in_production",
        purchases=[("SUP-003", 0.34), ("SUP-001", 0.20)],
        deliveries=[], payments=[0.5],
    ),
    dict(
        month=1, day=19, customer="CUST-008", user="agus", discount=30,
        note="Ruang meeting dan ruang tunggu.",
        lines=[("VB-ALU-16", 7, 110, 140), ("RB-SS-03", 5, 150, 190),
               ("INS-STD", 12, None, None)],
        quotation="converted", order="confirmed",
        purchases=[("SUP-002", 0.30), ("SUP-001", 0.16)],
        deliveries=[0.5], payments=[0.5],
    ),
    dict(
        month=1, day=26, customer="CUST-009", user="budi", discount=30,
        note="Rumah tinggal - kamar utama dan ruang keluarga.",
        lines=[("CT-BLK-01", 4, 260, 270), ("TRK-MTR-01", 4, 280, None),
               ("MTR-TUB-45", 4, None, None), ("INS-STD", 4, None, None)],
        quotation="converted", order="confirmed",
        purchases=[("SUP-003", 0.32), ("SUP-001", 0.18)],
        deliveries=[], payments=[],
    ),
    dict(
        month=0, day=4, customer="CUST-001", user="sari", discount=35,
        note="Perluasan lantai 9.",
        lines=[("RB-SS-05", 14, 150, 220), ("INS-STD", 14, None, None)],
        quotation="converted", order="draft",
        purchases=[], deliveries=[], payments=[],
    ),

    # ------------------------------------------- quotations that stalled
    dict(month=2, day=22, customer="CUST-004", user="sari", discount=40,
         note="Menunggu keputusan owner.",
         lines=[("RB-DIM-01", 60, 160, 200), ("INS-STD", 60, None, None)],
         quotation="sent"),
    dict(month=1, day=8, customer="CUST-006", user="budi", discount=25,
         note="Revisi ke-2, menunggu approval klien.",
         lines=[("CT-RMN-01", 12, 140, 180), ("INS-STD", 12, None, None)],
         quotation="approved"),
    dict(month=0, day=2, customer="CUST-002", user="agus", discount=30,
         lines=[("VB-ALU-25", 8, 130, 160), ("INS-STD", 8, None, None)],
         quotation="sent"),
    dict(month=0, day=7, customer="CUST-007", user="sari", discount=35,
         note="Penawaran awal, ukuran belum final.",
         lines=[("VRT-PVC-89", 18, 200, 240), ("SRV-SURVEY", 1, None, None)],
         quotation="draft"),
    dict(month=0, day=9, customer="CUST-005", user="budi", discount=30,
         lines=[("RB-ZEB-01", 5, 150, 190), ("INS-STD", 5, None, None)],
         quotation="draft"),
    dict(month=3, day=28, customer="CUST-009", user="agus", discount=30,
         note="Klien membatalkan, pindah rumah.",
         lines=[("CT-SHR-01", 6, 250, 260), ("INS-STD", 6, None, None)],
         quotation="cancelled"),
]

# Purchase orders not tied to any one job - stock, consumables, overheads.
STANDING_PURCHASES = [
    dict(month=6, day=12, supplier="SUP-005", user="agus", total=4_850_000,
         materials=[("Bracket set assorted, stok gudang", "set", 120),
                    ("Rantai kontrol 1.5m", "pcs", 200)]),
    dict(month=4, day=8, supplier="SUP-006", user="agus", total=2_940_000,
         materials=[("Karton pelindung roll", "roll", 60),
                    ("Bubble wrap 50cm x 100m", "roll", 25)]),
    dict(month=1, day=15, supplier="SUP-005", user="budi", total=3_600_000,
         materials=[("Bracket set assorted, stok gudang", "set", 90),
                    ("Sekrup dan fischer, mixed", "box", 40)]),
]

DRIVERS = ["Pak Joko Susilo", "Pak Slamet Riyadi", "Pak Dedi Kurniawan"]
PLATES = ["B 9021 KXA", "B 1745 TRD", "B 2288 QLM"]
RECIPIENTS = ["Ibu Rina", "Pak Bambang", "Ibu Sri Wahyuni", "Pak Deni"]
BANKS = ["BCA", "Mandiri", "BNI", "BRI"]


# ------------------------------------------------------------------ builders
def _line_item(quantity, width, height):
    return SimpleNamespace(
        quantity=Decimal(str(quantity)),
        width_cm=Decimal(str(width)) if width is not None else None,
        height_cm=Decimal(str(height)) if height is not None else None,
        unit_price=None, line_discount_pct=None, description=None,
    )


def _price(products, lines, discount, ppn=Decimal("11")):
    priced = [
        pricing.price_line(products[code], _line_item(qty, w, h), Decimal(str(discount)), n)
        for n, (code, qty, w, h) in enumerate(lines, start=1)
    ]
    return priced, pricing.compute_totals(priced, ppn)


def _allocate(total, shares):
    """Split a target amount across shares, giving the remainder to the last."""
    amounts = [money(Decimal(str(total)) * Decimal(str(s))) for s in shares[:-1]]
    amounts.append(money(Decimal(str(total)) - sum(amounts, Decimal("0"))))
    return amounts


def build_quotation(db, deal, customers, products, users):
    customer = customers[deal["customer"]]
    priced, totals = _price(products, deal["lines"], deal["discount"])
    when = months_ago(deal["month"], deal["day"])

    quotation = models.Quotation(
        quotation_date=when,
        status=deal["quotation"],
        customer_id=customer.id,
        nik_npwp=customer.nik_npwp,
        surveyor=deal.get("surveyor"),
        address=customer.address,
        deliver_to=customer.deliver_to or customer.name,
        deliver_address=customer.deliver_address or customer.address,
        phone=customer.phone,
        email=customer.email,
        currency="IDR",
        price_group=customer.price_group,
        payment_terms=customer.payment_terms,
        discount_percent=Decimal(str(deal["discount"])),
        ppn_percent=Decimal("11"),
        notes=deal.get("note"),
        created_by=users[deal["user"]].id,
        created_at=at(when, 9),
        updated_at=at(when, 9),
    )
    if deal["quotation"] in ("sent", "approved", "converted"):
        quotation.last_follow_up = when + timedelta(days=rng.randint(2, 9))

    for line in priced:
        quotation.items.append(models.QuotationItem(**line))
    for field, value in totals.items():
        setattr(quotation, field, value)

    numbering.allocate(db, quotation, models.Quotation.quotation_no,
                       numbering.PREFIXES["quotation"], when)
    return quotation


def build_sales_order(db, deal, quotation, customers, users):
    customer = customers[deal["customer"]]
    when = months_ago(deal["month"], deal["day"]) + timedelta(days=rng.randint(3, 12))

    so = models.SalesOrder(
        quotation_id=quotation.id,
        customer_id=customer.id,
        order_date=when,
        delivery_date=when + timedelta(days=rng.randint(14, 28)),
        status=deal["order"],
        nik_npwp=quotation.nik_npwp,
        surveyor=quotation.surveyor,
        address=quotation.address,
        deliver_to=quotation.deliver_to,
        deliver_address=quotation.deliver_address,
        phone=quotation.phone,
        email=quotation.email,
        currency="IDR",
        price_group=quotation.price_group,
        payment_terms=quotation.payment_terms,
        po_reference=f"PO/{customer.code[-3:]}/{when:%m%y}/{rng.randint(10, 99)}"
        if customer.price_group == "PROJECT" else None,
        discount_percent=quotation.discount_percent,
        ppn_percent=quotation.ppn_percent,
        notes=quotation.notes,
        created_by=users[deal["user"]].id,
        created_at=at(when, 11),
        updated_at=at(when, 11),
    )

    # Copy the accepted lines verbatim - no repricing.
    for line in quotation.items:
        so.items.append(models.SalesOrderItem(
            line_no=line.line_no, product_id=line.product_id,
            product_code=line.product_code, product_name=line.product_name,
            price_unit=line.price_unit, description=line.description,
            quantity=line.quantity, width_cm=line.width_cm, height_cm=line.height_cm,
            measure=line.measure, unit_price=line.unit_price,
            line_discount_pct=line.line_discount_pct, line_total=line.line_total,
            line_discount_amt=line.line_discount_amt, line_net=line.line_net,
        ))
    for field in ("subtotal", "discount_amount", "netto", "ppn_amount",
                  "total", "total_qty"):
        setattr(so, field, getattr(quotation, field))

    numbering.allocate(db, so, models.SalesOrder.so_no,
                       numbering.PREFIXES["sales_order"], when)
    return so


MATERIALS = {
    "SUP-001": [("Kain blackout 3 pass, roll 280cm", "roll"),
                ("Kain sunscreen 5%, roll 250cm", "roll"),
                ("Kain vitrase, roll 300cm", "roll")],
    "SUP-002": [("Profil aluminium rail double", "btg"),
                ("Tabung roller 38mm", "pcs"),
                ("Bottom bar aluminium", "btg")],
    "SUP-003": [("Tubular motor 45mm", "pcs"),
                ("Remote 15 channel", "pcs"),
                ("Bracket motor", "set")],
    "SUP-004": [("Slat kayu basswood 50mm", "m2"),
                ("Batang kayu 28mm, finishing walnut", "btg")],
    "SUP-005": [("Bracket set assorted", "set"),
                ("Rantai kontrol 1.5m", "pcs")],
    "SUP-006": [("Karton pelindung roll", "roll"),
                ("Bubble wrap 50cm x 100m", "roll")],
}


def build_purchase_order(db, supplier, target_cost, when, user, sales_order=None,
                         explicit=None):
    po = models.PurchaseOrder(
        supplier_id=supplier.id,
        sales_order_id=sales_order.id if sales_order else None,
        order_date=when,
        expected_date=when + timedelta(days=rng.randint(5, 14)),
        status="received" if when < TODAY - timedelta(days=30) else "sent",
        currency="IDR",
        payment_terms=supplier.payment_terms,
        ppn_percent=Decimal("11"),
        created_by=user.id,
        created_at=at(when, 14),
        updated_at=at(when, 14),
    )

    if explicit:
        rows = [(desc, unit, qty, None) for desc, unit, qty in explicit]
        amounts = _allocate(target_cost, [1 / len(rows)] * len(rows))
    else:
        catalogue = MATERIALS[supplier.code]
        picked = catalogue[: min(len(catalogue), rng.randint(2, len(catalogue)))]
        rows = [(desc, unit, rng.randint(4, 30), None) for desc, unit in picked]
        weights = [rng.uniform(0.8, 1.2) for _ in rows]
        total_weight = sum(weights)
        amounts = _allocate(target_cost, [w / total_weight for w in weights])

    priced = []
    for position, ((description, unit, quantity, _), amount) in enumerate(
            zip(rows, amounts), start=1):
        # Round the unit price to a sensible figure, then let quantity carry it.
        unit_price = money(
            (Decimal(str(amount)) / Decimal(str(quantity))).quantize(Decimal("1000"),
                                                                     rounding=ROUND_HALF_UP)
        )
        if unit_price <= 0:
            unit_price = money(1000)
        priced.append(pricing.price_purchase_line(
            SimpleNamespace(product_id=None, description=description, unit=unit,
                            quantity=Decimal(str(quantity)), unit_price=unit_price),
            position,
        ))

    for line in priced:
        po.items.append(models.PurchaseOrderItem(**line))
    for field, value in pricing.compute_purchase_totals(priced, po.ppn_percent).items():
        setattr(po, field, value)

    numbering.allocate(db, po, models.PurchaseOrder.po_no,
                       numbering.PREFIXES["purchase_order"], when)
    return po


def build_delivery_note(db, so, fraction, when, user, final):
    note = models.DeliveryNote(
        sales_order_id=so.id,
        delivery_date=when,
        status="delivered",
        deliver_to=so.deliver_to,
        deliver_address=so.deliver_address,
        phone=so.phone,
        vehicle_no=rng.choice(PLATES),
        driver_name=rng.choice(DRIVERS),
        received_by=rng.choice(RECIPIENTS),
        received_at=when,
        created_by=user.id,
        created_at=at(when, 8),
        updated_at=at(when, 8),
    )

    position = 0
    for line in so.items:
        ordered = Decimal(str(line.quantity))
        already = sum(
            (Decimal(str(i.quantity))
             for existing in so.delivery_notes for i in existing.items
             if i.sales_order_item_id == line.id),
            Decimal("0"),
        )
        remaining = ordered - already
        if remaining <= 0:
            continue

        if final:
            quantity = remaining
        else:
            quantity = ordered * Decimal(str(fraction))
            # Blinds ship as whole units - half a blind is not a thing.
            if ordered == ordered.to_integral_value():
                quantity = quantity.to_integral_value(rounding=ROUND_HALF_UP)
            quantity = max(quantity, Decimal("1"))
        quantity = money(min(quantity, remaining))
        if quantity <= 0:
            continue
        position += 1
        note.items.append(models.DeliveryNoteItem(
            line_no=position,
            sales_order_item_id=line.id,
            product_code=line.product_code,
            product_name=line.product_name,
            description=line.description,
            width_cm=line.width_cm,
            height_cm=line.height_cm,
            quantity=quantity,
            unit="pcs",
        ))

    if not note.items:
        return None
    numbering.allocate(db, note, models.DeliveryNote.sj_no,
                       numbering.PREFIXES["delivery_note"], when)
    return note


def build_receipt(db, so, amount, when, user, method="transfer"):
    receipt = models.Receipt(
        sales_order_id=so.id,
        receipt_date=when,
        amount=money(amount),
        payment_method=method,
        reference=f"{rng.choice(BANKS)} {when:%Y%m%d}/{rng.randint(1000, 9999)}"
        if method == "transfer" else None,
        received_from=so.customer.name if so.customer else None,
        created_by=user.id,
        created_at=at(when, 15),
    )
    numbering.allocate(db, receipt, models.Receipt.receipt_no,
                       numbering.PREFIXES["receipt"], when)
    return receipt


# ---------------------------------------------------------------- entry point
def generate(db, force: bool = False):
    if db.query(models.Quotation).first() and not force:
        print("Demo transactions already present - skipping.")
        print("Use `python seed.py --demo --reset` to rebuild from scratch.")
        return

    users = {u.username: u for u in db.query(models.User).all()}
    customers = {c.code: c for c in db.query(models.Customer).all()}
    suppliers = {s.code: s for s in db.query(models.Supplier).all()}
    products = {p.code: p for p in db.query(models.Product).all()}

    counts = dict(quotations=0, orders=0, purchases=0, deliveries=0, receipts=0)

    for deal in sorted(DEALS, key=lambda d: (-d["month"], d["day"])):
        user = users[deal["user"]]
        quotation = build_quotation(db, deal, customers, products, users)
        counts["quotations"] += 1

        if deal["quotation"] != "converted":
            continue

        so = build_sales_order(db, deal, quotation, customers, users)
        counts["orders"] += 1

        live = so.status not in ("draft", "cancelled")

        for supplier_code, share in deal.get("purchases", []):
            when = so.order_date + timedelta(days=rng.randint(1, 6))
            build_purchase_order(db, suppliers[supplier_code],
                                 money(so.netto * Decimal(str(share))),
                                 when, user, sales_order=so)
            counts["purchases"] += 1

        if live:
            fractions = deal.get("deliveries", [])
            # Only sweep up the remainder when the deal is meant to be fully
            # delivered. A lone [0.5] means half has gone and half is still
            # outstanding, which is the state the Surat Jalan screen is for.
            completes = abs(sum(fractions) - 1.0) < 1e-9
            for index, fraction in enumerate(fractions):
                when = so.order_date + timedelta(days=rng.randint(12, 30) + index * 9)
                if when > TODAY:
                    when = TODAY - timedelta(days=1)
                note = build_delivery_note(
                    db, so, fraction, when, user,
                    final=completes and index == len(fractions) - 1,
                )
                if note:
                    counts["deliveries"] += 1

            paid = Decimal("0")
            for index, share in enumerate(deal.get("payments", [])):
                amount = money(so.total * Decimal(str(share)))
                if paid + amount > so.total:
                    amount = money(so.total - paid)
                if amount <= 0:
                    continue
                when = so.order_date + timedelta(days=rng.randint(2, 20) + index * 21)
                if when > TODAY:
                    when = TODAY - timedelta(days=1)
                build_receipt(db, so, amount, when, user,
                              method="cash" if amount < 3_000_000 else "transfer")
                paid += amount
                counts["receipts"] += 1

    for standing in STANDING_PURCHASES:
        when = months_ago(standing["month"], standing["day"])
        build_purchase_order(
            db, suppliers[standing["supplier"]], standing["total"], when,
            users[standing["user"]],
            explicit=[(desc, unit, qty) for desc, unit, qty in standing["materials"]],
        )
        counts["purchases"] += 1

    db.commit()

    print("Demo transactions created:")
    print(f"  {counts['quotations']:>3} quotations")
    print(f"  {counts['orders']:>3} sales orders")
    print(f"  {counts['purchases']:>3} purchase orders")
    print(f"  {counts['deliveries']:>3} delivery notes (Surat Jalan)")
    print(f"  {counts['receipts']:>3} receipts")
    print(f"  spread over {months_ago(9):%b %Y} to {TODAY:%b %Y}")
