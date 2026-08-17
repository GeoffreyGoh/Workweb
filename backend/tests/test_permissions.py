"""The two-role model.

Everyone sees everything. A normal user may only change what they created;
an admin may change anything. That is the whole rule.
"""

import pytest


class TestSharedVisibility:
    def test_a_user_sees_documents_created_by_others(
            self, client, budi, sari, make_quotation, make_sales_order,
            make_purchase_order):
        make_quotation(budi)
        make_sales_order(budi)
        make_purchase_order(budi)

        assert len(client.get("/quotations", headers=sari).json()) == 1
        assert len(client.get("/sales-orders", headers=sari).json()) == 1
        assert len(client.get("/purchase-orders", headers=sari).json()) == 1

    def test_a_user_can_open_someone_elses_document(self, client, budi, sari,
                                                    make_quotation):
        q = make_quotation(budi)
        response = client.get(f"/quotations/{q['id']}", headers=sari)
        assert response.status_code == 200
        assert response.json()["quotation_no"] == q["quotation_no"]

    def test_list_shows_who_created_each_row(self, client, budi, sari, make_quotation):
        make_quotation(budi)
        row = client.get("/quotations", headers=sari).json()[0]
        assert row["created_by_name"] == "Budi Santoso"

    def test_mine_only_narrows_sales_orders_to_the_caller(self, client, budi, sari,
                                                          make_sales_order):
        mine = make_sales_order(sari)
        make_sales_order(budi)
        rows = client.get("/sales-orders?mine_only=true", headers=sari).json()
        assert [r["id"] for r in rows] == [mine["id"]]


class TestCanEditFlag:
    def test_own_rows_are_flagged_editable(self, client, budi, make_quotation):
        make_quotation(budi)
        assert client.get("/quotations", headers=budi).json()[0]["can_edit"] is True

    def test_other_peoples_rows_are_flagged_read_only(self, client, budi, sari,
                                                      make_quotation):
        make_quotation(budi)
        assert client.get("/quotations", headers=sari).json()[0]["can_edit"] is False

    def test_admin_can_edit_everything(self, client, budi, admin, make_quotation):
        make_quotation(budi)
        assert client.get("/quotations", headers=admin).json()[0]["can_edit"] is True

    @pytest.mark.parametrize("path,factory", [
        ("/sales-orders", "make_sales_order"),
        ("/purchase-orders", "make_purchase_order"),
    ])
    def test_flag_is_present_on_orders_too(self, client, budi, sari, admin,
                                           path, factory, request):
        request.getfixturevalue(factory)(budi)
        assert client.get(path, headers=budi).json()[0]["can_edit"] is True
        assert client.get(path, headers=sari).json()[0]["can_edit"] is False
        assert client.get(path, headers=admin).json()[0]["can_edit"] is True


class TestQuotationOwnership:
    def test_stranger_cannot_edit(self, client, budi, sari, make_quotation):
        q = make_quotation(budi)
        response = client.put(f"/quotations/{q['id']}", headers=sari,
                              json={"customer_id": q["customer_id"], "items": []})
        assert response.status_code == 403
        assert "created by someone else" in response.json()["detail"]

    def test_stranger_cannot_change_status(self, client, budi, sari, make_quotation):
        q = make_quotation(budi)
        response = client.patch(f"/quotations/{q['id']}/status",
                                json={"status": "sent"}, headers=sari)
        assert response.status_code == 403

    def test_stranger_cannot_delete(self, client, budi, sari, make_quotation):
        q = make_quotation(budi)
        assert client.delete(f"/quotations/{q['id']}", headers=sari).status_code == 403

    def test_a_refused_edit_changes_nothing(self, client, budi, sari, make_quotation):
        q = make_quotation(budi)
        client.put(f"/quotations/{q['id']}", headers=sari,
                   json={"customer_id": q["customer_id"], "items": []})
        after = client.get(f"/quotations/{q['id']}", headers=budi).json()
        assert len(after["items"]) == 3
        assert after["total"] == q["total"]

    def test_owner_can_edit(self, client, budi, make_quotation):
        q = make_quotation(budi)
        response = client.put(f"/quotations/{q['id']}", headers=budi,
                              json={"customer_id": q["customer_id"], "items": []})
        assert response.status_code == 200

    def test_admin_can_edit_another_users_quotation(self, client, budi, admin,
                                                    make_quotation):
        q = make_quotation(budi)
        response = client.put(f"/quotations/{q['id']}", headers=admin,
                              json={"customer_id": q["customer_id"],
                                    "discount_percent": 10, "items": []})
        assert response.status_code == 200
        assert response.json()["discount_percent"] == "10.00"

    def test_admin_can_change_another_users_status(self, client, budi, admin,
                                                   make_quotation):
        q = make_quotation(budi)
        response = client.patch(f"/quotations/{q['id']}/status",
                                json={"status": "sent"}, headers=admin)
        assert response.status_code == 200

    def test_admin_can_delete_another_users_draft(self, client, budi, admin,
                                                  make_quotation):
        q = make_quotation(budi)
        assert client.delete(f"/quotations/{q['id']}", headers=admin).status_code == 204


class TestSalesOrderOwnership:
    def test_stranger_cannot_edit(self, client, budi, sari, make_sales_order):
        so = make_sales_order(budi)
        response = client.put(f"/sales-orders/{so['id']}", headers=sari,
                              json={"customer_id": so["customer_id"], "items": []})
        assert response.status_code == 403

    def test_stranger_cannot_change_status(self, client, budi, sari, make_sales_order):
        so = make_sales_order(budi)
        response = client.patch(f"/sales-orders/{so['id']}/status",
                                json={"status": "confirmed"}, headers=sari)
        assert response.status_code == 403

    def test_admin_can(self, client, budi, admin, make_sales_order):
        so = make_sales_order(budi)
        response = client.patch(f"/sales-orders/{so['id']}/status",
                                json={"status": "confirmed"}, headers=admin)
        assert response.status_code == 200


class TestPurchaseOrderOwnership:
    def test_stranger_cannot_edit(self, client, budi, sari, supplier,
                                  make_purchase_order):
        po = make_purchase_order(budi)
        response = client.put(f"/purchase-orders/{po['id']}", headers=sari,
                              json={"supplier_id": supplier.id, "items": []})
        assert response.status_code == 403

    def test_admin_can_edit(self, client, budi, admin, supplier, make_purchase_order):
        po = make_purchase_order(budi)
        response = client.put(f"/purchase-orders/{po['id']}", headers=admin, json={
            "supplier_id": supplier.id,
            "items": [{"description": "Changed", "quantity": 1, "unit_price": 1000}]})
        assert response.status_code == 200


class TestReceiptOwnership:
    def test_stranger_cannot_void(self, client, budi, sari, confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": 1000}).json()
        assert client.delete(f"/receipts/{receipt['id']}", headers=sari).status_code == 403

    def test_owner_can_void(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": 1000}).json()
        assert client.delete(f"/receipts/{receipt['id']}", headers=budi).status_code == 204

    def test_admin_can_void_anyones(self, client, budi, admin, confirmed_order):
        so = confirmed_order(budi)
        receipt = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": 1000}).json()
        assert client.delete(f"/receipts/{receipt['id']}", headers=admin).status_code == 204


class TestSharedMasterData:
    """Only quotations are protected - master data is everyone's."""

    def test_a_normal_user_may_add_a_product(self, client, budi):
        response = client.post("/products", headers=budi, json={
            "code": "NEW-1", "name": "New Product",
            "price_unit": "per_unit", "unit_price": 1000})
        assert response.status_code == 201

    def test_a_normal_user_may_add_a_customer(self, client, budi):
        response = client.post("/customers", headers=budi,
                               json={"code": "C-NEW", "name": "New Customer"})
        assert response.status_code == 201

    def test_a_normal_user_may_add_a_supplier(self, client, budi):
        response = client.post("/suppliers", headers=budi,
                               json={"code": "S-NEW", "name": "New Supplier"})
        assert response.status_code == 201

    def test_a_normal_user_may_read_the_financial_report(self, client, budi):
        assert client.get("/reports/financial", headers=budi).status_code == 200


class TestOrphanedDocuments:
    def test_a_document_with_no_creator_is_admin_only(self, client, budi, admin,
                                                      make_quotation, db):
        """Imported/legacy rows have created_by NULL and must not fall to anyone."""
        import models
        q = make_quotation(budi)
        db.query(models.Quotation).filter(models.Quotation.id == q["id"]).update(
            {"created_by": None})
        db.commit()

        assert client.put(f"/quotations/{q['id']}", headers=budi,
                          json={"customer_id": q["customer_id"],
                                "items": []}).status_code == 403
        assert client.put(f"/quotations/{q['id']}", headers=admin,
                          json={"customer_id": q["customer_id"],
                                "items": []}).status_code == 200
