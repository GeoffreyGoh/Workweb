"""Purchase orders and the supplier master."""

from datetime import date

from conftest import dec


class TestCreate:
    def test_numbering(self, client, budi, make_purchase_order):
        po = make_purchase_order(budi)
        assert po["po_no"] == f"PO-GB-{date.today():%Y%m}-001"

    def test_totals_are_subtotal_plus_ppn(self, client, budi, make_purchase_order):
        po = make_purchase_order(budi, items=[
            {"description": "Fabric", "unit": "roll", "quantity": 4, "unit_price": 250000},
            {"description": "Tube", "unit": "pcs", "quantity": 10, "unit_price": 50000},
        ])
        assert dec(po["subtotal"]) == dec("1500000.00")
        assert dec(po["ppn_amount"]) == dec("165000.00")
        assert dec(po["total"]) == dec("1665000.00")
        assert dec(po["total_qty"]) == dec("14.00")

    def test_no_trade_discount_field(self, client, budi, make_purchase_order):
        assert "discount_percent" not in make_purchase_order(budi)

    def test_free_text_materials_need_no_product(self, client, budi,
                                                 make_purchase_order):
        po = make_purchase_order(budi, items=[
            {"description": "Assorted brackets, mixed sizes", "quantity": 30,
             "unit_price": 7500}])
        assert po["items"][0]["product_id"] is None
        assert po["items"][0]["description"] == "Assorted brackets, mixed sizes"

    def test_a_line_may_reference_a_product(self, client, budi, products,
                                            make_purchase_order):
        po = make_purchase_order(budi, items=[
            {"product_id": products["sqm"].id, "description": "Restock",
             "quantity": 2, "unit_price": 100}])
        assert po["items"][0]["product_id"] == products["sqm"].id

    def test_unknown_product_is_rejected(self, client, budi, supplier):
        response = client.post("/purchase-orders", headers=budi, json={
            "supplier_id": supplier.id,
            "items": [{"product_id": 9999, "description": "x",
                       "quantity": 1, "unit_price": 1}]})
        assert response.status_code == 422

    def test_unknown_supplier_is_422(self, client, budi):
        response = client.post("/purchase-orders", headers=budi, json={
            "supplier_id": 9999,
            "items": [{"description": "x", "quantity": 1, "unit_price": 1}]})
        assert response.status_code == 422
        assert "supplier" in response.json()["detail"].lower()

    def test_unit_defaults_to_pcs(self, client, budi, make_purchase_order):
        po = make_purchase_order(budi, items=[
            {"description": "Thing", "quantity": 1, "unit_price": 100}])
        assert po["items"][0]["unit"] == "pcs"

    def test_description_is_required(self, client, budi, supplier):
        response = client.post("/purchase-orders", headers=budi, json={
            "supplier_id": supplier.id,
            "items": [{"quantity": 1, "unit_price": 100}]})
        assert response.status_code == 422

    def test_blank_description_is_rejected(self, client, budi, supplier):
        response = client.post("/purchase-orders", headers=budi, json={
            "supplier_id": supplier.id,
            "items": [{"description": "", "quantity": 1, "unit_price": 100}]})
        assert response.status_code == 422

    def test_zero_quantity_is_rejected(self, client, budi, supplier):
        response = client.post("/purchase-orders", headers=budi, json={
            "supplier_id": supplier.id,
            "items": [{"description": "x", "quantity": 0, "unit_price": 100}]})
        assert response.status_code == 422

    def test_negative_price_is_rejected(self, client, budi, supplier):
        response = client.post("/purchase-orders", headers=budi, json={
            "supplier_id": supplier.id,
            "items": [{"description": "x", "quantity": 1, "unit_price": -5}]})
        assert response.status_code == 422


class TestSalesOrderLink:
    def test_unlinked_by_default(self, client, budi, make_purchase_order):
        po = make_purchase_order(budi)
        assert po["sales_order_id"] is None
        assert po["so_no"] is None

    def test_can_be_linked(self, client, budi, make_sales_order, make_purchase_order):
        so = make_sales_order(budi)
        po = make_purchase_order(budi, sales_order_id=so["id"])
        assert po["sales_order_id"] == so["id"]
        assert po["so_no"] == so["so_no"]

    def test_unknown_sales_order_is_422(self, client, budi, supplier):
        response = client.post("/purchase-orders", headers=budi, json={
            "supplier_id": supplier.id, "sales_order_id": 9999,
            "items": [{"description": "x", "quantity": 1, "unit_price": 1}]})
        assert response.status_code == 422
        assert "sales_order_id" in response.json()["detail"]

    def test_filter_by_sales_order(self, client, budi, make_sales_order,
                                   make_purchase_order):
        so = make_sales_order(budi)
        linked = make_purchase_order(budi, sales_order_id=so["id"])
        make_purchase_order(budi)
        rows = client.get(f"/purchase-orders?sales_order_id={so['id']}",
                          headers=budi).json()
        assert [r["id"] for r in rows] == [linked["id"]]


class TestStatusFlow:
    def test_draft_to_sent_to_received(self, client, budi, make_purchase_order):
        po = make_purchase_order(budi)
        for target in ("sent", "received"):
            response = client.patch(f"/purchase-orders/{po['id']}/status",
                                    json={"status": target}, headers=budi)
            assert response.status_code == 200
            assert response.json()["status"] == target

    def test_cannot_receive_a_draft(self, client, budi, make_purchase_order):
        po = make_purchase_order(budi)
        response = client.patch(f"/purchase-orders/{po['id']}/status",
                                json={"status": "received"}, headers=budi)
        assert response.status_code == 409

    def test_received_orders_are_locked_for_editing(self, client, budi, supplier,
                                                    make_purchase_order):
        po = make_purchase_order(budi)
        for target in ("sent", "received"):
            client.patch(f"/purchase-orders/{po['id']}/status",
                         json={"status": target}, headers=budi)
        response = client.put(f"/purchase-orders/{po['id']}", headers=budi,
                              json={"supplier_id": supplier.id, "items": []})
        assert response.status_code == 409

    def test_only_drafts_can_be_deleted(self, client, budi, make_purchase_order):
        po = make_purchase_order(budi)
        assert client.delete(f"/purchase-orders/{po['id']}", headers=budi).status_code == 204
        other = make_purchase_order(budi)
        client.patch(f"/purchase-orders/{other['id']}/status",
                     json={"status": "sent"}, headers=budi)
        assert client.delete(f"/purchase-orders/{other['id']}",
                             headers=budi).status_code == 409


class TestUpdate:
    def test_editing_reprices(self, client, budi, supplier, make_purchase_order):
        po = make_purchase_order(budi)
        updated = client.put(f"/purchase-orders/{po['id']}", headers=budi, json={
            "supplier_id": supplier.id, "ppn_percent": 11,
            "items": [{"description": "Cheaper", "quantity": 1, "unit_price": 100000}]}).json()
        assert dec(updated["subtotal"]) == dec("100000.00")
        assert dec(updated["ppn_amount"]) == dec("11000.00")
        assert len(updated["items"]) == 1

    def test_number_is_stable(self, client, budi, supplier, make_purchase_order):
        po = make_purchase_order(budi)
        updated = client.put(f"/purchase-orders/{po['id']}", headers=budi,
                             json={"supplier_id": supplier.id, "items": []}).json()
        assert updated["po_no"] == po["po_no"]


class TestSuppliers:
    def test_create_and_read(self, client, budi):
        created = client.post("/suppliers", headers=budi, json={
            "code": "SUP-NEW", "name": "New Vendor", "phone": "021-1", }).json()
        fetched = client.get(f"/suppliers/{created['id']}", headers=budi).json()
        assert fetched["name"] == "New Vendor"

    def test_duplicate_code_is_409(self, client, budi, supplier):
        response = client.post("/suppliers", headers=budi,
                               json={"code": supplier.code, "name": "Clash"})
        assert response.status_code == 409

    def test_search_by_name_and_code(self, client, budi, supplier):
        assert len(client.get("/suppliers?q=Tekstil", headers=budi).json()) == 1
        assert len(client.get("/suppliers?q=SUP-001", headers=budi).json()) == 1
        assert client.get("/suppliers?q=nothing", headers=budi).json() == []

    def test_update(self, client, budi, supplier):
        updated = client.put(f"/suppliers/{supplier.id}", headers=budi,
                             json={"phone": "021-9999"}).json()
        assert updated["phone"] == "021-9999"
        assert updated["name"] == supplier.name  # untouched

    def test_inactive_suppliers_are_hidden_by_default(self, client, budi, supplier):
        client.put(f"/suppliers/{supplier.id}", headers=budi, json={"is_active": False})
        assert client.get("/suppliers", headers=budi).json() == []
        assert len(client.get("/suppliers?active_only=false", headers=budi).json()) == 1

    def test_missing_supplier_is_404(self, client, budi):
        assert client.get("/suppliers/9999", headers=budi).status_code == 404
