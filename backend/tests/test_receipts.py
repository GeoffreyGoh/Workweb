"""Receipts - payments recorded against an invoice."""

from datetime import date

from conftest import dec


class TestCreate:
    def test_numbering(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi,
                              json={"sales_order_id": so["id"], "amount": 1000}).json()
        assert receipt["receipt_no"] == f"RCP-GB-{date.today():%Y%m}-001"

    def test_defaults_to_today(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi,
                              json={"sales_order_id": so["id"], "amount": 1000}).json()
        assert receipt["receipt_date"] == date.today().isoformat()

    def test_received_from_defaults_to_the_customer(self, client, budi, customer,
                                                    confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi,
                              json={"sales_order_id": so["id"], "amount": 1000}).json()
        assert receipt["received_from"] == customer.name

    def test_records_who_took_the_payment(self, client, budi, users, confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi,
                              json={"sales_order_id": so["id"], "amount": 1000}).json()
        assert receipt["created_by"] == users["budi"]
        assert receipt["created_by_name"] == "Budi Santoso"

    def test_carries_the_order_and_customer(self, client, budi, customer,
                                            confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi,
                              json={"sales_order_id": so["id"], "amount": 1000}).json()
        assert receipt["so_no"] == so["so_no"]
        assert receipt["customer_name"] == customer.name


class TestGuards:
    def test_cannot_pay_a_draft_order(self, client, budi, make_sales_order):
        so = make_sales_order(budi)
        response = client.post("/receipts", headers=budi,
                               json={"sales_order_id": so["id"], "amount": 1000})
        assert response.status_code == 409
        assert "Confirm the invoice" in response.json()["detail"]

    def test_cannot_pay_a_cancelled_order(self, client, budi, make_sales_order):
        so = make_sales_order(budi)
        client.patch(f"/sales-orders/{so['id']}/status",
                     json={"status": "cancelled"}, headers=budi)
        response = client.post("/receipts", headers=budi,
                               json={"sales_order_id": so["id"], "amount": 1000})
        assert response.status_code == 409

    def test_overpayment_is_refused(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        response = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": float(dec(so["total"]) + 1)})
        assert response.status_code == 422
        assert "exceeds the outstanding balance" in response.json()["detail"]

    def test_paying_the_exact_balance_is_allowed(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        response = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": float(so["total"])})
        assert response.status_code == 201

    def test_instalments_cannot_exceed_the_total(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        half = float(dec(so["total"]) / 2)
        assert client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": half}).status_code == 201
        assert client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": half}).status_code == 201
        # a third instalment has nothing left to pay
        third = client.post("/receipts", headers=budi,
                            json={"sales_order_id": so["id"], "amount": 1})
        assert third.status_code == 422

    def test_zero_amount_is_rejected(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        response = client.post("/receipts", headers=budi,
                               json={"sales_order_id": so["id"], "amount": 0})
        assert response.status_code == 422

    def test_negative_amount_is_rejected(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        response = client.post("/receipts", headers=budi,
                               json={"sales_order_id": so["id"], "amount": -500})
        assert response.status_code == 422

    def test_unknown_order_is_422(self, client, budi):
        response = client.post("/receipts", headers=budi,
                               json={"sales_order_id": 9999, "amount": 100})
        assert response.status_code == 422

    def test_unknown_payment_method_is_422(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        response = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": 100, "payment_method": "goats"})
        assert response.status_code == 422


class TestVoiding:
    def test_voiding_restores_the_balance(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi,
                              json={"sales_order_id": so["id"], "amount": 5000}).json()
        client.delete(f"/receipts/{receipt['id']}", headers=budi)
        after = client.get(f"/sales-orders/{so['id']}", headers=budi).json()
        assert dec(after["amount_paid"]) == dec("0.00")
        assert dec(after["balance_due"]) == dec(so["total"])

    def test_room_is_freed_for_a_new_payment(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        full = float(so["total"])
        first = client.post("/receipts", headers=budi,
                            json={"sales_order_id": so["id"], "amount": full}).json()
        client.delete(f"/receipts/{first['id']}", headers=budi)
        again = client.post("/receipts", headers=budi,
                            json={"sales_order_id": so["id"], "amount": full})
        assert again.status_code == 201

    def test_cannot_void_against_a_completed_order(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": float(so["total"])}).json()
        for target in ("in_production", "delivered", "completed"):
            client.patch(f"/sales-orders/{so['id']}/status",
                         json={"status": target}, headers=budi)
        response = client.delete(f"/receipts/{receipt['id']}", headers=budi)
        assert response.status_code == 409
        assert "Reopen the invoice" in response.json()["detail"]

    def test_missing_receipt_is_404(self, client, budi):
        assert client.delete("/receipts/9999", headers=budi).status_code == 404


class TestListing:
    def test_filter_by_sales_order(self, client, budi, confirmed_order):
        first = confirmed_order(budi)
        second = confirmed_order(budi)
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": first["id"], "amount": 100})
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": second["id"], "amount": 200})
        rows = client.get(f"/receipts?sales_order_id={first['id']}", headers=budi).json()
        assert len(rows) == 1
        assert dec(rows[0]["amount"]) == dec("100.00")

    def test_everyone_sees_all_receipts(self, client, budi, sari, confirmed_order):
        so = confirmed_order(budi)
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": so["id"], "amount": 100})
        assert len(client.get("/receipts", headers=sari).json()) == 1

    def test_date_range_filter(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": so["id"], "amount": 100})
        today = date.today().isoformat()
        assert len(client.get(f"/receipts?date_from={today}", headers=budi).json()) == 1
        assert client.get("/receipts?date_to=2000-01-01", headers=budi).json() == []

    def test_receipts_are_immutable(self, client, budi, confirmed_order):
        """There is deliberately no PUT - correcting means void and reissue."""
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi,
                              json={"sales_order_id": so["id"], "amount": 100}).json()
        response = client.put(f"/receipts/{receipt['id']}", headers=budi,
                              json={"amount": 999999})
        assert response.status_code == 405
