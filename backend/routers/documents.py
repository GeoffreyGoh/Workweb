"""PDF endpoints.

Each returns an inline PDF so the browser can preview it in a tab; the
frontend adds ?download=1 when the user wants a file on disk instead.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
import pdf as pdf_builder
import pricing
from database import get_db

router = APIRouter(prefix="/documents", tags=["documents"])


def _pdf_response(data: bytes, filename: str, download: bool) -> Response:
    disposition = "attachment" if download else "inline"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/quotations/{quotation_id}.pdf")
def quotation_pdf(
    quotation_id: int,
    download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    quotation = db.get(models.Quotation, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if not quotation.items:
        raise HTTPException(status_code=409, detail="This quotation has no line items")
    return _pdf_response(
        pdf_builder.quotation_pdf(quotation),
        f"{quotation.quotation_no}.pdf",
        download,
    )


@router.get("/sales-orders/{so_id}.pdf")
def sales_order_pdf(
    so_id: int,
    download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    so = db.get(models.SalesOrder, so_id)
    if not so:
        raise HTTPException(status_code=404, detail="Sales order not found")
    if not so.items:
        raise HTTPException(status_code=409, detail="This sales order has no line items")
    return _pdf_response(pdf_builder.sales_order_pdf(so), f"{so.so_no}.pdf", download)


@router.get("/purchase-orders/{po_id}.pdf")
def purchase_order_pdf(
    po_id: int,
    download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    po = db.get(models.PurchaseOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if not po.items:
        raise HTTPException(status_code=409, detail="This purchase order has no line items")
    return _pdf_response(pdf_builder.purchase_order_pdf(po), f"{po.po_no}.pdf", download)


@router.get("/delivery-notes/{note_id}.pdf")
def delivery_note_pdf(
    note_id: int,
    download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    note = db.get(models.DeliveryNote, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Delivery note not found")
    if not note.items:
        raise HTTPException(status_code=409, detail="This delivery note has no line items")
    return _pdf_response(
        pdf_builder.delivery_note_pdf(note), f"{note.sj_no}.pdf", download
    )


@router.get("/receipts/{receipt_id}.pdf")
def receipt_pdf(
    receipt_id: int,
    download: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    receipt = db.get(models.Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")

    # "Paid to date" means up to and including this receipt, so a reprinted
    # old receipt still shows the balance as it stood when it was issued.
    paid = db.query(func.sum(models.Receipt.amount)).filter(
        models.Receipt.sales_order_id == receipt.sales_order_id,
        models.Receipt.id <= receipt.id,
    ).scalar() or Decimal("0")
    paid = pricing.money(paid)
    balance = pricing.money(receipt.sales_order.total - paid) if receipt.sales_order else paid

    return _pdf_response(
        pdf_builder.receipt_pdf(receipt, paid, balance),
        f"{receipt.receipt_no}.pdf",
        download,
    )
