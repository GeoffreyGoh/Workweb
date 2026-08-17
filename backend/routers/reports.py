"""Sales and financial reporting.

Both reports work off netto (pre-PPN) figures. PPN is collected on behalf of
the tax office and passed through, so including it would inflate both revenue
and cost and distort the margin.

Cost comes from purchase orders. A PO linked to a sales order is attributed to
that order; unlinked POs still count toward total cost for the period but
cannot be broken down per order.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
import pricing
import schemas
from database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])

# Cancelled documents never happened, as far as reporting is concerned.
LIVE_SO_STATUSES = ("confirmed", "in_production", "delivered", "completed")
LIVE_PO_STATUSES = ("sent", "received")

ZERO = Decimal("0.00")


def _default_range(date_from: Optional[date], date_to: Optional[date]):
    """Default to the last 12 months, inclusive of today."""
    today = date.today()
    end = date_to or today
    start = date_from or (end - timedelta(days=365))
    return start, end


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if not denominator:
        return ZERO
    return pricing.money(numerator * 100 / denominator)


@router.get("/sales", response_model=schemas.SalesReport)
def sales_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    company_id: Optional[int] = Query(None, description="Filter to one company"),
    created_by: Optional[int] = Query(None, description="Filter to one salesperson"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Quotation activity, order intake, and what is selling.

    Filterable by customer (the company being sold to) and by the member of
    staff who raised the documents.
    """
    start, end = _default_range(date_from, date_to)

    q_query = db.query(models.Quotation).filter(
        models.Quotation.quotation_date >= start,
        models.Quotation.quotation_date <= end,
        models.Quotation.status != "cancelled",
    )
    so_query = db.query(models.SalesOrder).filter(
        models.SalesOrder.order_date >= start,
        models.SalesOrder.order_date <= end,
        models.SalesOrder.status.in_(LIVE_SO_STATUSES),
    )
    if customer_id:
        q_query = q_query.filter(models.Quotation.customer_id == customer_id)
        so_query = so_query.filter(models.SalesOrder.customer_id == customer_id)
    if created_by:
        q_query = q_query.filter(models.Quotation.created_by == created_by)
        so_query = so_query.filter(models.SalesOrder.created_by == created_by)
    if company_id:
        q_query = q_query.filter(models.Quotation.company_id == company_id)
        so_query = so_query.filter(models.SalesOrder.company_id == company_id)

    quotations = q_query.all()
    orders = so_query.all()

    buckets = defaultdict(
        lambda: {"quotation_count": 0, "quotation_value": ZERO,
                 "order_count": 0, "order_value": ZERO}
    )
    for quotation in quotations:
        b = buckets[f"{quotation.quotation_date:%Y-%m}"]
        b["quotation_count"] += 1
        b["quotation_value"] += quotation.netto
    for order in orders:
        b = buckets[f"{order.order_date:%Y-%m}"]
        b["order_count"] += 1
        b["order_value"] += order.netto

    by_customer = defaultdict(lambda: {"count": 0, "value": ZERO, "customer": None})
    for order in orders:
        entry = by_customer[order.customer_id]
        entry["count"] += 1
        entry["value"] += order.netto
        entry["customer"] = order.customer

    by_product = defaultdict(lambda: {"name": "", "qty": ZERO, "measure": ZERO, "value": ZERO})
    for order in orders:
        for line in order.items:
            entry = by_product[line.product_code]
            entry["name"] = line.product_name
            entry["qty"] += line.quantity
            entry["measure"] += line.measure
            entry["value"] += line.line_net

    by_user = defaultdict(
        lambda: {"quotations": 0, "quotation_value": ZERO,
                 "orders": 0, "order_value": ZERO, "name": None}
    )
    for quotation in quotations:
        entry = by_user[quotation.created_by]
        entry["quotations"] += 1
        entry["quotation_value"] += quotation.netto
        if quotation.creator:
            entry["name"] = quotation.creator.full_name
    for order in orders:
        entry = by_user[order.created_by]
        entry["orders"] += 1
        entry["order_value"] += order.netto
        if order.creator:
            entry["name"] = order.creator.full_name

    status_query = db.query(
        models.Quotation.status, func.count(models.Quotation.id)
    ).filter(
        models.Quotation.quotation_date >= start,
        models.Quotation.quotation_date <= end,
    )
    if company_id:
        status_query = status_query.filter(models.Quotation.company_id == company_id)
    status_counts = dict(status_query.group_by(models.Quotation.status).all())

    company = db.get(models.Company, company_id) if company_id else None

    quotation_value = pricing.money(sum((q.netto for q in quotations), ZERO))
    order_value = pricing.money(sum((o.netto for o in orders), ZERO))

    return schemas.SalesReport(
        date_from=start,
        date_to=end,
        company_id=company_id,
        company_name=company.name if company else None,
        quotation_count=len(quotations),
        quotation_value=quotation_value,
        order_count=len(orders),
        order_value=order_value,
        conversion_rate=_pct(Decimal(len(orders)), Decimal(len(quotations) or 0)),
        by_period=[
            schemas.PeriodBucket(
                period=period,
                quotation_count=v["quotation_count"],
                quotation_value=pricing.money(v["quotation_value"]),
                order_count=v["order_count"],
                order_value=pricing.money(v["order_value"]),
            )
            for period, v in sorted(buckets.items())
        ],
        by_customer=sorted(
            (
                schemas.CustomerSales(
                    customer_id=cid,
                    customer_code=v["customer"].code if v["customer"] else None,
                    customer_name=v["customer"].name if v["customer"] else f"#{cid}",
                    order_count=v["count"],
                    order_value=pricing.money(v["value"]),
                )
                for cid, v in by_customer.items()
            ),
            key=lambda c: c.order_value,
            reverse=True,
        ),
        by_product=sorted(
            (
                schemas.ProductSales(
                    product_code=code,
                    product_name=v["name"],
                    quantity=pricing.money(v["qty"]),
                    measure=pricing.money(v["measure"]),
                    value=pricing.money(v["value"]),
                )
                for code, v in by_product.items()
            ),
            key=lambda p: p.value,
            reverse=True,
        ),
        by_user=sorted(
            (
                schemas.UserSales(
                    created_by=user_id,
                    created_by_name=v["name"] or "Unassigned",
                    quotation_count=v["quotations"],
                    quotation_value=pricing.money(v["quotation_value"]),
                    order_count=v["orders"],
                    order_value=pricing.money(v["order_value"]),
                    conversion_rate=_pct(Decimal(v["orders"]),
                                         Decimal(v["quotations"] or 0)),
                )
                for user_id, v in by_user.items()
            ),
            key=lambda u: u.order_value,
            reverse=True,
        ),
        by_status=status_counts,
    )


@router.get("/financial", response_model=schemas.FinancialReport)
def financial_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    company_id: Optional[int] = None,
    created_by: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Revenue against purchase cost, and the gross margin that falls out."""
    start, end = _default_range(date_from, date_to)

    so_query = db.query(models.SalesOrder).filter(
        models.SalesOrder.order_date >= start,
        models.SalesOrder.order_date <= end,
        models.SalesOrder.status.in_(LIVE_SO_STATUSES),
    )
    if customer_id:
        so_query = so_query.filter(models.SalesOrder.customer_id == customer_id)
    if created_by:
        so_query = so_query.filter(models.SalesOrder.created_by == created_by)
    if company_id:
        so_query = so_query.filter(models.SalesOrder.company_id == company_id)
    orders = so_query.all()
    po_query = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.order_date >= start,
        models.PurchaseOrder.order_date <= end,
        models.PurchaseOrder.status.in_(LIVE_PO_STATUSES),
    )
    if company_id:
        po_query = po_query.filter(models.PurchaseOrder.company_id == company_id)
    if customer_id or created_by:
        # Narrowed to a subset of orders, so only the cost attributed to those
        # orders is meaningful; unlinked overheads belong to nobody.
        po_query = po_query.filter(
            models.PurchaseOrder.sales_order_id.in_([o.id for o in orders] or [0])
        )
    purchase_orders = po_query.all()

    revenue = pricing.money(sum((o.netto for o in orders), ZERO))
    cost = pricing.money(sum((p.subtotal for p in purchase_orders), ZERO))

    cost_by_order = defaultdict(lambda: {"cost": ZERO, "count": 0})
    cost_unlinked = ZERO
    for po in purchase_orders:
        if po.sales_order_id:
            entry = cost_by_order[po.sales_order_id]
            entry["cost"] += po.subtotal
            entry["count"] += 1
        else:
            cost_unlinked += po.subtotal

    periods = defaultdict(lambda: {"revenue": ZERO, "cost": ZERO})
    for order in orders:
        periods[f"{order.order_date:%Y-%m}"]["revenue"] += order.netto
    for po in purchase_orders:
        periods[f"{po.order_date:%Y-%m}"]["cost"] += po.subtotal

    by_order = []
    for order in orders:
        entry = cost_by_order.get(order.id, {"cost": ZERO, "count": 0})
        order_cost = pricing.money(entry["cost"])
        profit = pricing.money(order.netto - order_cost)
        by_order.append(
            schemas.OrderMargin(
                sales_order_id=order.id,
                so_no=order.so_no,
                customer_name=order.customer.name if order.customer else "",
                order_date=order.order_date,
                revenue=pricing.money(order.netto),
                cost=order_cost,
                gross_profit=profit,
                margin_pct=_pct(profit, order.netto),
                po_count=entry["count"],
            )
        )
    by_order.sort(key=lambda o: o.order_date, reverse=True)

    order_ids = [o.id for o in orders]
    collected = ZERO
    if order_ids:
        collected = pricing.money(
            db.query(func.sum(models.Receipt.amount))
            .filter(models.Receipt.sales_order_id.in_(order_ids))
            .scalar()
            or 0
        )
    invoiced = pricing.money(sum((o.total for o in orders), ZERO))

    gross_profit = pricing.money(revenue - cost)

    company = db.get(models.Company, company_id) if company_id else None
    return schemas.FinancialReport(
        date_from=start,
        date_to=end,
        company_id=company_id,
        company_name=company.name if company else None,
        revenue=revenue,
        cost=cost,
        gross_profit=gross_profit,
        margin_pct=_pct(gross_profit, revenue),
        cost_linked=pricing.money(cost - cost_unlinked),
        cost_unlinked=pricing.money(cost_unlinked),
        collected=collected,
        outstanding=pricing.money(invoiced - collected),
        by_period=[
            schemas.FinancialPeriod(
                period=period,
                revenue=pricing.money(v["revenue"]),
                cost=pricing.money(v["cost"]),
                gross_profit=pricing.money(v["revenue"] - v["cost"]),
                margin_pct=_pct(v["revenue"] - v["cost"], v["revenue"]),
            )
            for period, v in sorted(periods.items())
        ],
        by_order=by_order,
    )
