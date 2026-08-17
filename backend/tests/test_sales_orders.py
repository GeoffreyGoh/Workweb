"""Sales orders, and converting a quotation into one."""

from datetime import date

from conftest import dec


class TestConversion:
    def convert(self, client, headers, quotation_id):
        return client.post(f"/sales-orders/from-quotation/{quotation_id}", headers=headers)

    def approved(self, client, headers, make_quotation):
        q = make_quotation(headers)
        client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"},
                     headers=headers)
        client.patch(f"/quotations/{q['id']}/status", json={"status": "approved"},
                     headers=headers)
        return q

    def test_totals_carry_across_untouched(self, client, budi, make_quotation):
        q = self.approved(client, budi, make_quotation)
        so = self.convert(client, budi, q["id"]).json()
        for field in ("subtotal", "discount_amount", "netto", "ppn_amount",
                      "total", "total_qty"):
            assert dec(so[field]) == dec(q[field]), field

    def test_lines_carry_across_untouched(self, client, budi, make_quotation):
        q = self.approved(client, budi, make_quotation)
        so = self.convert(client, budi, q["id"]).json()
        assert len(so["items"]) == len(q["items"])
        for line, source in zip(so["items"], q["items"]):
            assert line["product_code"] == source["product_code"]
            assert dec(line["line_total"]) == dec(source["line_total"])
            assert dec(line["measure"]) == dec(source["measure"])

    def test_conversion_survives_a_later_price_rise(self, client, budi, db,
                                                    make_quotation, products):
        """The customer accepted these numbers - a price change must not reprice."""
        q = self.approved(client, budi, make_quotation)
        import models
        db.query(models.Product).update({"unit_price": dec("9999999")})
        db.commit()
        so = self.convert(client, budi, q["id"]).json()
        assert dec(so["total"]) == dec(q["total"])

    def test_quotation_becomes_converted(self, client, budi, make_quotation):
        q = self.approved(client, budi, make_quotation)
        self.convert(client, budi, q["id"])
        assert client.get(f"/quotations/{q['id']}",
                          headers=budi).json()["status"] == "converted"

    def test_link_back_to_the_quotation_is_kept(self, client, budi, make_quotation):
        q = self.approved(client, budi, make_quotation)
        so = self.convert(client, budi, q["id"]).json()
        assert so["quotation_id"] == q["id"]
        assert so["quotation_no"] == q["quotation_no"]

    def test_converting_twice_is_refused(self, client, budi, make_quotation):
        q = self.approved(client, budi, make_quotation)
        first = self.convert(client, budi, q["id"]).json()
        second = self.convert(client, budi, q["id"])
        assert second.status_code == 409
        assert first["so_no"] in second.json()["detail"]

    def test_a_draft_quotation_cannot_convert(self, client, budi, make_quotation):
        q = make_quotation(budi)
        response = self.convert(client, budi, q["id"])
        assert response.status_code == 409
        assert "approved or sent" in response.json()["detail"]

    def test_a_sent_quotation_can_convert(self, client, budi, make_quotation):
        q = make_quotation(budi)
        client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"}, headers=budi)
        assert self.convert(client, budi, q["id"]).status_code == 201

    def test_anyone_may_convert_anyones_quotation(self, client, budi, sari,
                                                  make_quotation):
        """Converting creates a new document, it does not edit the old one."""
        q = self.approved(client, budi, make_quotation)
        response = self.convert(client, sari, q["id"])
        assert response.status_code == 201
        assert response.json()["created_by_name"] == "Sari Dewi"

    def test_missing_quotation_is_404(self, client, budi):
        assert self.convert(client, budi, 9999).status_code == 404

    def test_deleting_the_order_releases_the_quotation(self, client, budi,
                                                       make_quotation):
        q = self.approved(client, budi, make_quotation)
        so = self.convert(client, budi, q["id"]).json()
        assert client.delete(f"/sales-orders/{so['id']}", headers=budi).status_code == 204
        assert client.get(f"/quotations/{q['id']}",
                          headers=budi).json()["status"] == "approved"

    def test_a_converted_quotation_cannot_be_deleted(self, client, budi, admin,
                                                     make_quotation):
        q = self.approved(client, budi, make_quotation)
        self.convert(client, budi, q["id"])
        response = client.delete(f"/quotations/{q['id']}", headers=admin)
        # Blocked by the draft-only rule, which fires before the SO check.
        assert response.status_code == 409
        assert client.get(f"/quotations/{q['id']}", headers=admin).status_code == 200

    def test_a_draft_quotation_with_an_order_is_still_protected(self, client, budi,
                                                               admin, db,
                                                               make_quotation):
        """Backstop: even if a quotation is forced back to draft, an order that
        was raised from it must keep the quotation alive."""
        import models
        q = self.approved(client, budi, make_quotation)
        self.convert(client, budi, q["id"])
        db.query(models.Quotation).filter(models.Quotation.id == q["id"]).update(
            {"status": "draft"})
        db.commit()

        response = client.delete(f"/quotations/{q['id']}", headers=admin)
        assert response.status_code == 409
        assert "sales order" in response.json()["detail"]


class TestDirectCreate:
    def test_numbering(self, client, budi, make_sales_order):
        so = make_sales_order(budi)
        assert so["so_no"] == f"SO-GB-{date.today():%Y%m}-001"

    def test_priced_like_a_quotation(self, client, budi, make_sales_order, products):
        so = make_sales_order(budi, items=[
            {"product_id": products["sqm"].id, "quantity": 3,
             "width_cm": 200, "height_cm": 100},
            {"product_id": products["meter"].id, "quantity": 2, "width_cm": 250},
            {"product_id": products["unit"].id, "quantity": 4},
        ])
        assert dec(so["subtotal"]) == dec("3100000.00")
        assert dec(so["total"]) == dec("2236650.00")

    def test_starts_as_draft_with_no_quotation(self, client, budi, make_sales_order):
        so = make_sales_order(budi)
        assert so["status"] == "draft"
        assert so["quotation_id"] is None

    def test_dimension_rules_still_apply(self, client, budi, customer, products):
        response = client.post("/sales-orders", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["sqm"].id, "quantity": 1,
                       "width_cm": 999, "height_cm": 100}]})
        assert response.status_code == 422

    def test_customer_details_are_copied(self, client, budi, customer, make_sales_order):
        so = make_sales_order(budi)
        assert so["address"] == customer.address
        assert so["payment_terms"] == customer.payment_terms


class TestStatusFlow:
    def test_full_lifecycle(self, client, budi, make_sales_order):
        so = make_sales_order(budi)
        for target in ("confirmed", "in_production", "delivered"):
            response = client.patch(f"/sales-orders/{so['id']}/status",
                                    json={"status": target}, headers=budi)
            assert response.status_code == 200, response.text
            assert response.json()["status"] == target

    def test_cannot_skip_a_stage(self, client, budi, make_sales_order):
        so = make_sales_order(budi)
        response = client.patch(f"/sales-orders/{so['id']}/status",
                                json={"status": "delivered"}, headers=budi)
        assert response.status_code == 409

    def test_completed_is_terminal(self, client, budi, make_sales_order):
        so = make_sales_order(budi, items=[])
        for target in ("confirmed", "in_production", "delivered", "completed"):
            client.patch(f"/sales-orders/{so['id']}/status",
                         json={"status": target}, headers=budi)
        response = client.patch(f"/sales-orders/{so['id']}/status",
                                json={"status": "draft"}, headers=budi)
        assert response.status_code == 409

    def test_cannot_complete_while_money_is_outstanding(self, client, budi,
                                                        confirmed_order):
        so = confirmed_order(budi)
        for target in ("in_production", "delivered"):
            client.patch(f"/sales-orders/{so['id']}/status",
                         json={"status": target}, headers=budi)
        response = client.patch(f"/sales-orders/{so['id']}/status",
                                json={"status": "completed"}, headers=budi)
        assert response.status_code == 409
        assert "outstanding" in response.json()["detail"]

    def test_can_complete_once_paid_in_full(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": so["id"], "amount": float(so["total"])})
        for target in ("in_production", "delivered", "completed"):
            response = client.patch(f"/sales-orders/{so['id']}/status",
                                    json={"status": target}, headers=budi)
        assert response.status_code == 200
        assert response.json()["status"] == "completed"


class TestEditing:
    def test_draft_and_confirmed_are_editable(self, client, budi, make_sales_order,
                                              products):
        so = make_sales_order(budi)
        body = {"customer_id": so["customer_id"],
                "items": [{"product_id": products["unit"].id, "quantity": 2}]}
        assert client.put(f"/sales-orders/{so['id']}", headers=budi,
                          json=body).status_code == 200
        client.patch(f"/sales-orders/{so['id']}/status",
                     json={"status": "confirmed"}, headers=budi)
        assert client.put(f"/sales-orders/{so['id']}", headers=budi,
                          json=body).status_code == 200

    def test_in_production_is_locked(self, client, budi, make_sales_order):
        so = make_sales_order(budi)
        for target in ("confirmed", "in_production"):
            client.patch(f"/sales-orders/{so['id']}/status",
                         json={"status": target}, headers=budi)
        response = client.put(f"/sales-orders/{so['id']}", headers=budi,
                              json={"customer_id": so["customer_id"], "items": []})
        assert response.status_code == 409
        assert "no longer be edited" in response.json()["detail"]


class TestPaymentTracking:
    def test_unpaid_order_shows_the_full_balance(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        assert dec(so["amount_paid"]) == dec("0.00")
        assert dec(so["balance_due"]) == dec(so["total"])

    def test_balance_falls_as_payments_arrive(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        total = dec(so["total"])
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": so["id"], "amount": float(total / 2)})
        after = client.get(f"/sales-orders/{so['id']}", headers=budi).json()
        assert dec(after["amount_paid"]) == (total / 2).quantize(dec("0.01"))
        assert dec(after["balance_due"]) == total - dec(after["amount_paid"])

    def test_list_rows_carry_the_balance(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": so["id"], "amount": 1000})
        row = client.get("/sales-orders", headers=budi).json()[0]
        assert dec(row["amount_paid"]) == dec("1000.00")
        assert dec(row["balance_due"]) == dec(so["total"]) - dec("1000.00")


class TestDeletion:
    def test_only_drafts_can_be_deleted(self, client, budi, make_sales_order):
        so = make_sales_order(budi)
        client.patch(f"/sales-orders/{so['id']}/status",
                     json={"status": "confirmed"}, headers=budi)
        assert client.delete(f"/sales-orders/{so['id']}", headers=budi).status_code == 409

    def test_an_order_with_receipts_is_protected(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": so["id"], "amount": 500})
        client.patch(f"/sales-orders/{so['id']}/status",
                     json={"status": "draft"}, headers=budi)
        response = client.delete(f"/sales-orders/{so['id']}", headers=budi)
        assert response.status_code == 409
        assert "receipts" in response.json()["detail"]

    def test_an_order_referenced_by_a_po_is_protected(self, client, budi,
                                                      make_sales_order,
                                                      make_purchase_order):
        so = make_sales_order(budi)
        make_purchase_order(budi, sales_order_id=so["id"])
        response = client.delete(f"/sales-orders/{so['id']}", headers=budi)
        assert response.status_code == 409
        assert "purchase order" in response.json()["detail"]
