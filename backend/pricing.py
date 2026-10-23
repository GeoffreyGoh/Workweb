"""Quotation pricing and validation.

Everything the client sends about money is advisory only - the API recomputes
line measures, line totals, discounts, PPN and the grand total from the
product master and the submitted dimensions.

Totals model (matches the legacy quotation screen):

    line_total      = measure * unit_price          (gross, per line)
    line_discount   = line_total * effective_pct    (line override, else header %)
    line_net        = line_total - line_discount
    subtotal        = sum(line_total)
    discount_amount = sum(line_discount)
    netto           = subtotal - discount_amount
    ppn_amount      = netto * ppn_percent
    total           = netto + ppn_amount
"""

import math
from decimal import ROUND_HALF_UP, ROUND_UP, Decimal

CENT = Decimal("0.01")
FOUR = Decimal("0.0001")
HALF = Decimal("0.5")

# per_sqm_min1m  - blinds/shades priced by area, each side floored at 1m
#                  before multiplying (client formula sheet, "RUMUS BLINDS").
# per_curtain_panel - curtains priced by fabric consumption in running
#                  metres, derived from the number of 0.6m-wide panels needed
#                  to cover the window (client formula sheet, "RUMUS GORDEN").
PRICE_UNITS = (
    "per_sqm", "per_unit", "per_meter",
    "per_sqm_min1m", "per_curtain_panel",
)


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def measure4(value) -> Decimal:
    return Decimal(str(value)).quantize(FOUR, rounding=ROUND_HALF_UP)


class PricingError(ValueError):
    """Raised when a line fails validation; surfaced as HTTP 422."""


def validate_dimensions(product, width_cm, height_cm, line_no: int) -> None:
    """Check width/height against the product's allowed range.

    Only dimensions the product actually prices on are required. A NULL bound
    on the product means "no limit on that side".
    """
    needs_width = product.price_unit in (
        "per_sqm", "per_meter", "per_sqm_min1m", "per_curtain_panel",
    )
    needs_height = product.price_unit in ("per_sqm", "per_sqm_min1m", "per_curtain_panel")

    def fail(msg):
        raise PricingError(f"Line {line_no} ({product.code}): {msg}")

    if needs_width:
        if width_cm is None or width_cm <= 0:
            fail("width_cm is required and must be greater than 0")
        if product.min_width_cm is not None and width_cm < product.min_width_cm:
            fail(f"width {width_cm} cm is below the minimum {product.min_width_cm} cm")
        if product.max_width_cm is not None and width_cm > product.max_width_cm:
            fail(f"width {width_cm} cm exceeds the maximum {product.max_width_cm} cm")

    if needs_height:
        if height_cm is None or height_cm <= 0:
            fail("height_cm is required and must be greater than 0")
        if product.min_height_cm is not None and height_cm < product.min_height_cm:
            fail(f"height {height_cm} cm is below the minimum {product.min_height_cm} cm")
        if product.max_height_cm is not None and height_cm > product.max_height_cm:
            fail(f"height {height_cm} cm exceeds the maximum {product.max_height_cm} cm")


def compute_measure(price_unit: str, quantity, width_cm, height_cm, fabric_width_cm=None) -> Decimal:
    """Billable quantity for a line, in the product's pricing unit.

    `fabric_width_cm` only matters for per_curtain_panel (the roll width of
    the specific curtain fabric); every other unit ignores it.
    """
    quantity = Decimal(str(quantity))

    if price_unit == "per_sqm":
        sqm = (Decimal(str(width_cm)) / 100) * (Decimal(str(height_cm)) / 100)
        return measure4(sqm * quantity)
    if price_unit == "per_meter":
        return measure4((Decimal(str(width_cm)) / 100) * quantity)
    if price_unit == "per_unit":
        return measure4(quantity)

    if price_unit == "per_sqm_min1m":
        # "RUMUS BLINDS": both width and height are floored at 1m / 100cm
        # before multiplying, even if the real measurement is smaller. A
        # 75cm-wide blind is billed as if it were 100cm wide.
        width_m = max(Decimal(str(width_cm)), Decimal("100")) / 100
        height_m = max(Decimal(str(height_cm)), Decimal("100")) / 100
        return measure4(width_m * height_m * quantity)

    if price_unit == "per_curtain_panel":
        # "RUMUS GORDEN": panels = width / 0.6m, rounded UP to a whole panel.
        # A wider fabric roll (280cm vs 140cm) covers two panels at once, so
        # halve the panel count (still rounded up) when fabric_width_cm=280.
        width_cm_d = Decimal(str(width_cm))
        panels = math.ceil(width_cm_d / Decimal("60"))
        if fabric_width_cm is not None and Decimal(str(fabric_width_cm)) >= 280:
            panels = math.ceil(Decimal(str(panels)) / 2)
        panels = Decimal(panels)

        # metres = (height + 30cm seam allowance) x panels + 40cm for the belt/strap,
        # then rounded UP to the nearest half metre (matches both worked examples:
        # 15.76 -> 16m, and 8.08 -> 8.5m).
        height_m = Decimal(str(height_cm)) / 100
        raw_metres = (height_m + Decimal("0.3")) * panels + Decimal("0.4")
        rounded = (raw_metres / HALF).to_integral_value(rounding=ROUND_UP) * HALF
        return measure4(rounded * quantity)

    raise PricingError(f"Unknown price_unit '{price_unit}'")


def resolve_option_price(product, component_options: str):
    """Look up a per-mechanism price override from the chosen component(s).

    `component_options` is the "Group: Name | Group2: Name2" string the line
    editor builds (see frontend/js/line-editor.js readComponents). Only a
    match against one of the product's loaded ProductOption rows with a
    non-NULL unit_price counts - everything else falls back to the product's
    own price, which is the existing behaviour.
    """
    if not component_options:
        return None
    chosen = {}
    for part in component_options.split("|"):
        bits = part.split(":")
        if len(bits) == 2:
            chosen[bits[0].strip()] = bits[1].strip()
    for option in getattr(product, "options", []) or []:
        if chosen.get(option.option_group) == option.option_name and option.unit_price is not None:
            return option.unit_price
    return None


def price_line(product, item, header_discount_pct: Decimal, line_no: int) -> dict:
    """Validate and price one line item.

    `item` carries quantity/width_cm/height_cm/line_discount_pct and optionally
    a unit_price override; `product` supplies the fallback price and limits.
    """
    quantity = Decimal(str(item.quantity))
    if quantity <= 0:
        raise PricingError(f"Line {line_no} ({product.code}): quantity must be greater than 0")

    validate_dimensions(product, item.width_cm, item.height_cm, line_no)

    measure = compute_measure(
        product.price_unit, quantity, item.width_cm, item.height_cm,
        fabric_width_cm=getattr(product, "fabric_width_cm", None),
    )

    # Precedence: explicit manual override > the selected option's own price
    # (e.g. Panel Glide "Classic" prices differently from "Villa") > the
    # product's base price.
    option_price = resolve_option_price(product, getattr(item, "component_options", None))
    if item.unit_price is not None:
        unit_price = money(item.unit_price)
    elif option_price is not None:
        unit_price = money(option_price)
    else:
        unit_price = money(product.unit_price)

    effective_pct = (
        Decimal(str(item.line_discount_pct))
        if item.line_discount_pct is not None
        else Decimal(str(header_discount_pct))
    )
    if effective_pct < 0 or effective_pct > 100:
        raise PricingError(f"Line {line_no}: discount must be between 0 and 100")

    line_total = money(measure * unit_price)
    line_discount_amt = money(line_total * effective_pct / 100)
    line_net = money(line_total - line_discount_amt)

    return {
        "line_no": line_no,
        "product_id": product.id,
        "product_code": product.code,
        "product_name": product.name,
        "price_unit": product.price_unit,
        "description": item.description,
        "quantity": quantity,
        "width_cm": item.width_cm,
        "height_cm": item.height_cm,
        "measure": measure,
        "unit_price": unit_price,
        "line_discount_pct": item.line_discount_pct,
        "line_total": line_total,
        "line_discount_amt": line_discount_amt,
        "line_net": line_net,
    }


def price_purchase_line(item, line_no: int) -> dict:
    """Price one purchase-order line.

    Raw materials have no dimensions and no product master to validate
    against - quantity x unit price in whatever unit the supplier quotes.
    """
    quantity = Decimal(str(item.quantity))
    if quantity <= 0:
        raise PricingError(f"Line {line_no}: quantity must be greater than 0")

    unit_price = money(item.unit_price)
    if unit_price < 0:
        raise PricingError(f"Line {line_no}: unit price cannot be negative")

    return {
        "line_no": line_no,
        "product_id": item.product_id,
        "description": item.description,
        "unit": item.unit or "pcs",
        "quantity": quantity,
        "unit_price": unit_price,
        "line_total": money(quantity * unit_price),
    }


def compute_purchase_totals(priced_lines, ppn_percent) -> dict:
    """Purchase orders carry no trade discount - subtotal, PPN, total."""
    subtotal = money(sum((line["line_total"] for line in priced_lines), Decimal("0")))
    ppn_amount = money(subtotal * Decimal(str(ppn_percent)) / 100)
    total_qty = Decimal(str(sum((line["quantity"] for line in priced_lines), Decimal("0"))))

    return {
        "subtotal": subtotal,
        "ppn_amount": ppn_amount,
        "total": money(subtotal + ppn_amount),
        "total_qty": total_qty.quantize(CENT),
    }


def compute_dp(total, dp_percent):
    """The down payment (TOP) the customer pays up front.

    Returns (dp_amount, balance). A blank or zero percentage means no DP was
    agreed, which is different from a DP of nothing: dp_amount is 0 and the
    whole total is due on the normal terms.
    """
    total = money(total)
    if dp_percent in (None, ""):
        return money(0), total
    percent = Decimal(str(dp_percent))
    if percent < 0 or percent > 100:
        raise PricingError("DP percent must be between 0 and 100")
    dp_amount = money(total * percent / 100)
    return dp_amount, money(total - dp_amount)


def compute_totals(priced_lines, ppn_percent, installation_cost=0) -> dict:
    """Roll priced lines up into the quotation header totals.

    Installation is a job-level charge that lands after the trade discount and
    before PPN. It is a service and therefore taxable, so it belongs in the PPN
    base - leaving it out would under-collect the tax:

        subtotal -> discount -> netto -> + installation -> PPN -> total
    """
    subtotal = money(sum((line["line_total"] for line in priced_lines), Decimal("0")))
    discount_amount = money(
        sum((line["line_discount_amt"] for line in priced_lines), Decimal("0"))
    )
    netto = money(subtotal - discount_amount)

    installation = money(installation_cost or 0)
    if installation < 0:
        raise PricingError("Installation cost cannot be negative")

    taxable = money(netto + installation)
    ppn_amount = money(taxable * Decimal(str(ppn_percent)) / 100)
    total = money(taxable + ppn_amount)
    total_qty = Decimal(str(sum((line["quantity"] for line in priced_lines), Decimal("0"))))

    return {
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "netto": netto,
        "installation_cost": installation,
        "ppn_amount": ppn_amount,
        "total": total,
        "total_qty": total_qty.quantize(CENT),
    }
