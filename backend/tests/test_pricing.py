"""Unit tests for the pricing engine - no HTTP, no database."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

import pricing


def product(**kwargs):
    defaults = dict(
        id=1, code="P1", name="Product", price_unit="per_sqm",
        unit_price=Decimal("400000"),
        min_width_cm=None, max_width_cm=None,
        min_height_cm=None, max_height_cm=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def item(**kwargs):
    defaults = dict(
        quantity=Decimal("1"), width_cm=None, height_cm=None,
        unit_price=None, line_discount_pct=None, description=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ------------------------------------------------------------- measurement
class TestMeasure:
    def test_per_sqm_converts_cm_to_square_metres(self):
        # 200cm x 100cm = 2m x 1m = 2 sqm, times 3 units
        assert pricing.compute_measure("per_sqm", 3, 200, 100) == Decimal("6.0000")

    def test_per_meter_uses_width_only(self):
        assert pricing.compute_measure("per_meter", 2, 250, None) == Decimal("5.0000")

    def test_per_unit_ignores_dimensions(self):
        assert pricing.compute_measure("per_unit", 7, 999, 999) == Decimal("7.0000")

    def test_fractional_sizes_keep_four_decimals(self):
        # 135cm x 87cm = 1.35 x 0.87 = 1.1745 sqm
        assert pricing.compute_measure("per_sqm", 1, 135, 87) == Decimal("1.1745")

    def test_unknown_unit_is_rejected(self):
        with pytest.raises(pricing.PricingError, match="Unknown price_unit"):
            pricing.compute_measure("per_furlong", 1, 100, 100)


# -------------------------------------------------------------- validation
class TestDimensionValidation:
    def test_width_below_minimum(self):
        with pytest.raises(pricing.PricingError, match="below the minimum"):
            pricing.validate_dimensions(product(min_width_cm=Decimal("40")), 30, 100, 1)

    def test_width_above_maximum(self):
        with pytest.raises(pricing.PricingError, match="exceeds the maximum"):
            pricing.validate_dimensions(product(max_width_cm=Decimal("300")), 350, 100, 1)

    def test_height_below_minimum(self):
        with pytest.raises(pricing.PricingError, match="below the minimum"):
            pricing.validate_dimensions(product(min_height_cm=Decimal("40")), 100, 20, 1)

    def test_height_above_maximum(self):
        with pytest.raises(pricing.PricingError, match="exceeds the maximum"):
            pricing.validate_dimensions(product(max_height_cm=Decimal("400")), 100, 500, 1)

    def test_boundaries_are_inclusive(self):
        p = product(min_width_cm=Decimal("40"), max_width_cm=Decimal("300"),
                    min_height_cm=Decimal("40"), max_height_cm=Decimal("400"))
        pricing.validate_dimensions(p, Decimal("40"), Decimal("40"), 1)
        pricing.validate_dimensions(p, Decimal("300"), Decimal("400"), 1)

    def test_null_bound_means_no_limit(self):
        pricing.validate_dimensions(product(), Decimal("99999"), Decimal("99999"), 1)

    def test_per_sqm_requires_both_dimensions(self):
        with pytest.raises(pricing.PricingError, match="height_cm is required"):
            pricing.validate_dimensions(product(), 150, None, 1)
        with pytest.raises(pricing.PricingError, match="width_cm is required"):
            pricing.validate_dimensions(product(), None, 150, 1)

    def test_per_meter_requires_width_but_not_height(self):
        p = product(price_unit="per_meter")
        pricing.validate_dimensions(p, 150, None, 1)
        with pytest.raises(pricing.PricingError, match="width_cm is required"):
            pricing.validate_dimensions(p, None, None, 1)

    def test_per_unit_requires_neither(self):
        pricing.validate_dimensions(product(price_unit="per_unit"), None, None, 1)

    def test_zero_dimension_is_rejected(self):
        with pytest.raises(pricing.PricingError, match="greater than 0"):
            pricing.validate_dimensions(product(), 0, 100, 1)

    def test_message_names_the_line_and_product(self):
        with pytest.raises(pricing.PricingError, match=r"Line 7 \(ABC\)"):
            pricing.validate_dimensions(
                product(code="ABC", max_width_cm=Decimal("100")), 200, 100, 7
            )


# ------------------------------------------------------------ line pricing
class TestPriceLine:
    def test_uses_the_product_price_when_none_given(self):
        line = pricing.price_line(product(), item(quantity=3, width_cm=200, height_cm=100),
                                  Decimal("35"), 1)
        assert line["measure"] == Decimal("6.0000")
        assert line["unit_price"] == Decimal("400000.00")
        assert line["line_total"] == Decimal("2400000.00")

    def test_manual_unit_price_overrides_the_master(self):
        line = pricing.price_line(
            product(), item(quantity=1, width_cm=100, height_cm=100,
                            unit_price=Decimal("123456")), Decimal("0"), 1)
        assert line["unit_price"] == Decimal("123456.00")
        assert line["line_total"] == Decimal("123456.00")

    def test_zero_unit_price_override_is_honoured(self):
        # A giveaway line must not silently fall back to the master price.
        line = pricing.price_line(
            product(), item(quantity=1, width_cm=100, height_cm=100,
                            unit_price=Decimal("0")), Decimal("0"), 1)
        assert line["unit_price"] == Decimal("0.00")
        assert line["line_total"] == Decimal("0.00")

    def test_header_discount_applies_when_no_override(self):
        line = pricing.price_line(product(), item(quantity=1, width_cm=100, height_cm=100),
                                  Decimal("35"), 1)
        assert line["line_total"] == Decimal("400000.00")
        assert line["line_discount_amt"] == Decimal("140000.00")
        assert line["line_net"] == Decimal("260000.00")

    def test_line_override_beats_the_header(self):
        line = pricing.price_line(
            product(), item(quantity=1, width_cm=100, height_cm=100,
                            line_discount_pct=Decimal("10")), Decimal("35"), 1)
        assert line["line_discount_amt"] == Decimal("40000.00")

    def test_zero_line_discount_is_not_treated_as_missing(self):
        line = pricing.price_line(
            product(), item(quantity=1, width_cm=100, height_cm=100,
                            line_discount_pct=Decimal("0")), Decimal("35"), 1)
        assert line["line_discount_amt"] == Decimal("0.00")
        assert line["line_net"] == line["line_total"]

    def test_quantity_must_be_positive(self):
        with pytest.raises(pricing.PricingError, match="quantity must be greater than 0"):
            pricing.price_line(product(), item(quantity=0, width_cm=100, height_cm=100),
                               Decimal("35"), 1)

    def test_discount_outside_0_100_is_rejected(self):
        with pytest.raises(pricing.PricingError, match="between 0 and 100"):
            pricing.price_line(
                product(), item(quantity=1, width_cm=100, height_cm=100,
                                line_discount_pct=Decimal("140")), Decimal("35"), 1)

    def test_snapshots_the_product_details(self):
        line = pricing.price_line(product(code="XYZ", name="Snapshot Me"),
                                  item(quantity=1, width_cm=100, height_cm=100),
                                  Decimal("0"), 3)
        assert (line["product_code"], line["product_name"], line["line_no"]) == (
            "XYZ", "Snapshot Me", 3)


# ----------------------------------------------------------------- rollups
class TestTotals:
    def build(self, header_discount="35", line_discounts=(None, None, None)):
        specs = [
            (product(), item(quantity=3, width_cm=200, height_cm=100,
                             line_discount_pct=line_discounts[0])),
            (product(price_unit="per_meter", unit_price=Decimal("100000")),
             item(quantity=2, width_cm=250, line_discount_pct=line_discounts[1])),
            (product(price_unit="per_unit", unit_price=Decimal("50000")),
             item(quantity=4, line_discount_pct=line_discounts[2])),
        ]
        return [
            pricing.price_line(p, i, Decimal(header_discount), n)
            for n, (p, i) in enumerate(specs, start=1)
        ]

    def test_totals_chain(self):
        totals = pricing.compute_totals(self.build(), Decimal("11"))
        # 2,400,000 + 500,000 + 200,000
        assert totals["subtotal"] == Decimal("3100000.00")
        assert totals["discount_amount"] == Decimal("1085000.00")
        assert totals["netto"] == Decimal("2015000.00")
        assert totals["ppn_amount"] == Decimal("221650.00")
        assert totals["total"] == Decimal("2236650.00")
        assert totals["total_qty"] == Decimal("9.00")

    def test_netto_is_subtotal_less_discount(self):
        totals = pricing.compute_totals(self.build(), Decimal("11"))
        assert totals["netto"] == totals["subtotal"] - totals["discount_amount"]
        assert totals["total"] == totals["netto"] + totals["ppn_amount"]

    def test_line_override_changes_the_rollup(self):
        totals = pricing.compute_totals(self.build(line_discounts=(None, None, "0")),
                                        Decimal("11"))
        assert totals["discount_amount"] == Decimal("1015000.00")
        assert totals["netto"] == Decimal("2085000.00")
        assert totals["total"] == Decimal("2314350.00")

    def test_zero_ppn(self):
        totals = pricing.compute_totals(self.build(), Decimal("0"))
        assert totals["ppn_amount"] == Decimal("0.00")
        assert totals["total"] == totals["netto"]

    def test_hundred_percent_discount_zeroes_the_net(self):
        totals = pricing.compute_totals(self.build(header_discount="100"), Decimal("11"))
        assert totals["discount_amount"] == totals["subtotal"]
        assert totals["netto"] == Decimal("0.00")
        assert totals["total"] == Decimal("0.00")

    def test_empty_document_totals_zero(self):
        totals = pricing.compute_totals([], Decimal("11"))
        assert totals["subtotal"] == Decimal("0.00")
        assert totals["total"] == Decimal("0.00")
        assert totals["total_qty"] == Decimal("0.00")

    def test_awkward_percentages_stay_self_consistent(self):
        line = pricing.price_line(
            product(unit_price=Decimal("333333.33")),
            item(quantity=1, width_cm=100, height_cm=100), Decimal("33.33"), 1)
        assert line["line_total"] == Decimal("333333.33")
        assert line["line_discount_amt"] == Decimal("111100.00")
        # net must always be exactly total - discount, never re-derived
        assert line["line_net"] == line["line_total"] - line["line_discount_amt"]

    def test_half_cent_rounds_up_not_to_even(self):
        # 100.00 x 12.345% = 12.345 exactly.
        # ROUND_HALF_UP -> 12.35;  Python's default half-even -> 12.34.
        line = pricing.price_line(
            product(price_unit="per_unit", unit_price=Decimal("100")),
            item(quantity=1, line_discount_pct=Decimal("12.345")), Decimal("0"), 1)
        assert line["line_discount_amt"] == Decimal("12.35")
        assert line["line_net"] == Decimal("87.65")


# ------------------------------------------------------- purchase pricing
class TestPurchasePricing:
    def po_item(self, **kwargs):
        defaults = dict(product_id=None, description="Fabric", unit="roll",
                        quantity=Decimal("4"), unit_price=Decimal("250000"))
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_line_is_quantity_times_price(self):
        line = pricing.price_purchase_line(self.po_item(), 1)
        assert line["line_total"] == Decimal("1000000.00")

    def test_defaults_the_unit(self):
        assert pricing.price_purchase_line(self.po_item(unit=None), 1)["unit"] == "pcs"

    def test_quantity_must_be_positive(self):
        with pytest.raises(pricing.PricingError, match="greater than 0"):
            pricing.price_purchase_line(self.po_item(quantity=Decimal("0")), 1)

    def test_negative_price_is_rejected(self):
        with pytest.raises(pricing.PricingError, match="cannot be negative"):
            pricing.price_purchase_line(self.po_item(unit_price=Decimal("-1")), 1)

    def test_totals_have_no_trade_discount(self):
        lines = [
            pricing.price_purchase_line(self.po_item(), 1),
            pricing.price_purchase_line(
                self.po_item(quantity=Decimal("2"), unit_price=Decimal("500000")), 2),
        ]
        totals = pricing.compute_purchase_totals(lines, Decimal("11"))
        assert totals["subtotal"] == Decimal("2000000.00")
        assert totals["ppn_amount"] == Decimal("220000.00")
        assert totals["total"] == Decimal("2220000.00")
        assert totals["total_qty"] == Decimal("6.00")
        assert "discount_amount" not in totals
