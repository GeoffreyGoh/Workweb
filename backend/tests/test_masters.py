"""Product and customer master data, plus document numbering."""

from datetime import date

import pytest

import models
import numbering
from conftest import dec


class TestProducts:
    def test_create_and_read_back(self, client, admin, budi):
        created = client.post("/products", headers=admin, json={
            "code": "NEW-1", "name": "Vertical Blind", "category": "Blind",
            "price_unit": "per_sqm", "unit_price": 275000,
            "min_width_cm": 50, "max_width_cm": 400,
        }).json()
        fetched = client.get(f"/products/{created['id']}", headers=budi).json()
        assert fetched["name"] == "Vertical Blind"
        assert dec(fetched["unit_price"]) == dec("275000.00")
        assert dec(fetched["max_width_cm"]) == dec("400.00")

    def test_duplicate_code_is_409(self, client, admin, products):
        response = client.post("/products", headers=admin, json={
            "code": "RB-SQM", "name": "Clash", "price_unit": "per_unit",
            "unit_price": 1})
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_invalid_price_unit_is_422(self, client, admin):
        response = client.post("/products", headers=admin, json={
            "code": "BAD", "name": "Bad", "price_unit": "per_banana", "unit_price": 1})
        assert response.status_code == 422

    def test_negative_price_is_422(self, client, admin):
        response = client.post("/products", headers=admin, json={
            "code": "BAD", "name": "Bad", "price_unit": "per_unit", "unit_price": -1})
        assert response.status_code == 422

    def test_search_matches_code_or_name(self, client, budi, products):
        assert len(client.get("/products?q=Roller", headers=budi).json()) == 1
        assert len(client.get("/products?q=RB-SQM", headers=budi).json()) == 1
        assert client.get("/products?q=zzz", headers=budi).json() == []

    def test_partial_update_leaves_other_fields_alone(self, client, admin, products):
        updated = client.put(f"/products/{products['sqm'].id}", headers=admin,
                             json={"unit_price": 450000}).json()
        assert dec(updated["unit_price"]) == dec("450000.00")
        assert updated["name"] == "Roller Blind"
        assert dec(updated["max_width_cm"]) == dec("300.00")

    def test_inactive_products_are_hidden_by_default(self, client, admin, budi,
                                                     products):
        client.put(f"/products/{products['sqm'].id}", headers=admin,
                   json={"is_active": False})
        codes = [p["code"] for p in client.get("/products", headers=budi).json()]
        assert "RB-SQM" not in codes
        all_codes = [p["code"] for p in
                     client.get("/products?active_only=false", headers=budi).json()]
        assert "RB-SQM" in all_codes

    def test_results_are_sorted_by_name(self, client, budi, products):
        names = [p["name"] for p in client.get("/products", headers=budi).json()]
        assert names == sorted(names)

    def test_limit_is_capped(self, client, budi):
        assert client.get("/products?limit=99999", headers=budi).status_code == 422

    def test_missing_product_is_404(self, client, budi):
        assert client.get("/products/9999", headers=budi).status_code == 404


class TestCustomers:
    def test_create_and_read_back(self, client, budi):
        created = client.post("/customers", headers=budi, json={
            "code": "C-NEW", "name": "Toko Tirai", "phone": "0812",
            "payment_terms": "COD"}).json()
        fetched = client.get(f"/customers/{created['id']}", headers=budi).json()
        assert fetched["name"] == "Toko Tirai"
        assert fetched["payment_terms"] == "COD"

    def test_duplicate_code_is_409(self, client, budi, customer):
        response = client.post("/customers", headers=budi,
                               json={"code": customer.code, "name": "Clash"})
        assert response.status_code == 409

    def test_name_is_required(self, client, budi):
        assert client.post("/customers", headers=budi,
                           json={"code": "X"}).status_code == 422

    def test_blank_name_is_rejected(self, client, budi):
        assert client.post("/customers", headers=budi,
                           json={"code": "X", "name": ""}).status_code == 422

    def test_search_matches_code_or_name(self, client, budi, customer):
        assert len(client.get("/customers?q=Graha", headers=budi).json()) == 1
        assert len(client.get("/customers?q=CUST-001", headers=budi).json()) == 1

    def test_update(self, client, budi, customer):
        updated = client.put(f"/customers/{customer.id}", headers=budi,
                             json={"phone": "021-0000"}).json()
        assert updated["phone"] == "021-0000"
        assert updated["name"] == customer.name

    def test_editing_a_customer_does_not_rewrite_past_quotations(
            self, client, budi, customer, make_quotation):
        """Documents keep a snapshot, so history stays truthful."""
        q = make_quotation(budi)
        client.put(f"/customers/{customer.id}", headers=budi,
                   json={"address": "Moved to a new office"})
        after = client.get(f"/quotations/{q['id']}", headers=budi).json()
        assert after["address"] == "Jl. Sudirman No. 45, Jakarta"

    def test_missing_customer_is_404(self, client, budi):
        assert client.get("/customers/9999", headers=budi).status_code == 404


class TestNumbering:
    def test_prefix_map(self):
        assert numbering.PREFIXES == {
            "quotation": "Q", "sales_order": "INV",
            "purchase_order": "PO", "receipt": "RCP",
            "delivery_note": "SJ",
        }

    def test_company_code_scopes_the_prefix(self):
        assert numbering.scoped("Q", "GB") == "Q-GB"
        assert numbering.scoped("SO", "mj") == "SO-MJ"
        # No company (single-entity install) leaves the prefix alone.
        assert numbering.scoped("Q", None) == "Q"

    def test_first_number_of_a_month(self, db):
        number = numbering.next_number(db, models.Quotation.quotation_no, "Q",
                                       date(2026, 8, 1))
        assert number == "Q-202608-001"

    def test_sequence_continues_from_the_highest(self, db, customer, companies):
        for seq in (1, 2, 3):
            db.add(models.Quotation(
                quotation_no=f"Q-202608-{seq:03d}", quotation_date=date(2026, 8, 5),
                customer_id=customer.id,
                                company_id=companies["GB"].id))
        db.commit()
        assert numbering.next_number(db, models.Quotation.quotation_no, "Q",
                                     date(2026, 8, 9)) == "Q-202608-004"

    def test_each_month_restarts_at_one(self, db, customer, companies):
        db.add(models.Quotation(quotation_no="Q-202607-009",
                                quotation_date=date(2026, 7, 20),
                                customer_id=customer.id,
                                company_id=companies["GB"].id))
        db.commit()
        assert numbering.next_number(db, models.Quotation.quotation_no, "Q",
                                     date(2026, 8, 1)) == "Q-202608-001"

    def test_document_types_have_independent_sequences(self, client, budi,
                                                       make_quotation,
                                                       make_sales_order,
                                                       make_purchase_order):
        month = f"{date.today():%Y%m}"
        assert make_quotation(budi)["quotation_no"] == f"Q-GB-{month}-001"
        assert make_sales_order(budi)["so_no"] == f"INV-GB-{month}-001"
        assert make_purchase_order(budi)["po_no"] == f"PO-GB-{month}-001"

    def test_a_malformed_existing_number_does_not_crash(self, db, customer, companies):
        db.add(models.Quotation(quotation_no="Q-202608-XYZ",
                                quotation_date=date(2026, 8, 5),
                                customer_id=customer.id,
                                company_id=companies["GB"].id))
        db.commit()
        assert numbering.next_number(db, models.Quotation.quotation_no, "Q",
                                     date(2026, 8, 9)) == "Q-202608-001"

    def test_sequence_pads_to_three_digits(self, db, customer, companies):
        db.add(models.Quotation(quotation_no="Q-202608-099",
                                quotation_date=date(2026, 8, 5),
                                customer_id=customer.id,
                                company_id=companies["GB"].id))
        db.commit()
        assert numbering.next_number(db, models.Quotation.quotation_no, "Q",
                                     date(2026, 8, 9)) == "Q-202608-100"


class TestMoneyPrecision:
    """The Dec type stores money as text on SQLite; make sure nothing is lost."""

    def test_large_rupiah_amounts_survive_a_round_trip(self, client, admin, budi,
                                                       customer):
        big = client.post("/products", headers=admin, json={
            "code": "BIG", "name": "Big Ticket", "price_unit": "per_unit",
            "unit_price": "987654321.99"}).json()
        assert dec(big["unit_price"]) == dec("987654321.99")

        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "discount_percent": 0, "ppn_percent": 0,
            "items": [{"product_id": big["id"], "quantity": 1}]}).json()
        assert dec(q["total"]) == dec("987654321.99")

    def test_fractional_measures_do_not_drift(self, client, budi, customer, products):
        # 135 x 87 cm = 1.1745 sqm at 400,000 = 469,800
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "discount_percent": 0, "ppn_percent": 0,
            "items": [{"product_id": products["sqm"].id, "quantity": 1,
                       "width_cm": 135, "height_cm": 87}]}).json()
        assert dec(q["items"][0]["measure"]) == dec("1.1745")
        assert dec(q["subtotal"]) == dec("469800.00")

    @pytest.mark.parametrize("amount", ["0.01", "1234.56", "99999999.99"])
    def test_receipt_amounts_round_trip_exactly(self, client, budi, confirmed_order,
                                                products, amount):
        so = confirmed_order(budi, items=[
            {"product_id": products["unit"].id, "quantity": 4000}])  # 200,000,000 gross
        receipt = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": amount}).json()
        assert dec(receipt["amount"]) == dec(amount)
