"""Delivery notes (Surat Jalan) - partial deliveries and the over-delivery rule."""

from datetime import date

import pytest

from conftest import dec


@pytest.fixture()
def order(client, budi, confirmed_order, products):
    """A confirmed order with three lines of known quantities."""
    return confirmed_order(budi, items=[
        {"product_id": products["sqm"].id, "quantity": 10,
         "width_cm": 200, "height_cm": 100},
        {"product_id": products["meter"].id, "quantity": 4, "width_cm": 250},
        {"product_id": products["unit"].id, "quantity": 6},
    ])


def line_ids(client, headers, so_id):
    detail = client.get(f"/sales-orders/{so_id}", headers=headers).json()
    return [item["id"] for item in detail["items"]]


class TestOutstanding:
    def test_nothing_delivered_yet(self, client, budi, order):
        body = client.get(f"/delivery-notes/outstanding/{order['id']}",
                          headers=budi).json()
        assert body["so_no"] == order["so_no"]
        assert body["fully_delivered"] is False
        assert [dec(line["ordered"]) for line in body["lines"]] == [
            dec("10.00"), dec("4.00"), dec("6.00")]
        assert [dec(line["delivered"]) for line in body["lines"]] == [dec("0.00")] * 3

    def test_carries_the_sizes_for_the_installer(self, client, budi, order):
        body = client.get(f"/delivery-notes/outstanding/{order['id']}",
                          headers=budi).json()
        assert dec(body["lines"][0]["width_cm"]) == dec("200.00")
        assert dec(body["lines"][0]["height_cm"]) == dec("100.00")

    def test_reflects_a_partial_delivery(self, client, budi, order):
        ids = line_ids(client, budi, order["id"])
        client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 4}]})

        body = client.get(f"/delivery-notes/outstanding/{order['id']}",
                          headers=budi).json()
        first = body["lines"][0]
        assert dec(first["delivered"]) == dec("4.00")
        assert dec(first["outstanding"]) == dec("6.00")
        assert body["fully_delivered"] is False

    def test_fully_delivered_once_everything_has_gone(self, client, budi, order):
        client.post(f"/delivery-notes/from-sales-order/{order['id']}", headers=budi)
        body = client.get(f"/delivery-notes/outstanding/{order['id']}",
                          headers=budi).json()
        assert body["fully_delivered"] is True
        assert all(dec(line["outstanding"]) == dec("0.00") for line in body["lines"])

    def test_missing_order_is_404(self, client, budi):
        assert client.get("/delivery-notes/outstanding/9999",
                          headers=budi).status_code == 404


class TestCreateFromOrder:
    def test_drafts_everything_outstanding(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        assert note["status"] == "draft"
        assert len(note["items"]) == 3
        assert [dec(i["quantity"]) for i in note["items"]] == [
            dec("10.00"), dec("4.00"), dec("6.00")]
        assert dec(note["total_qty"]) == dec("20.00")

    def test_numbering_uses_the_sj_prefix(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        assert note["sj_no"] == f"SJ-GB-{date.today():%Y%m}-001"

    def test_copies_the_delivery_address(self, client, budi, customer, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        assert note["deliver_to"] == customer.name
        assert note["deliver_address"] == customer.address

    def test_links_back_to_the_order(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        assert note["sales_order_id"] == order["id"]
        assert note["so_no"] == order["so_no"]

    def test_only_the_remainder_goes_on_the_second_note(self, client, budi, order):
        ids = line_ids(client, budi, order["id"])
        client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 4}]})

        second = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                             headers=budi).json()
        by_line = {i["sales_order_item_id"]: dec(i["quantity"]) for i in second["items"]}
        assert by_line[ids[0]] == dec("6.00")
        assert by_line[ids[1]] == dec("4.00")

    def test_refused_when_nothing_is_left(self, client, budi, order):
        client.post(f"/delivery-notes/from-sales-order/{order['id']}", headers=budi)
        response = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                               headers=budi)
        assert response.status_code == 409
        assert "already been delivered" in response.json()["detail"]

    def test_a_draft_order_cannot_be_delivered(self, client, budi, make_sales_order):
        so = make_sales_order(budi)
        response = client.post(f"/delivery-notes/from-sales-order/{so['id']}",
                               headers=budi)
        assert response.status_code == 409
        assert "Confirm the invoice" in response.json()["detail"]

    def test_a_cancelled_order_cannot_be_delivered(self, client, budi, order):
        client.patch(f"/sales-orders/{order['id']}/status",
                     json={"status": "cancelled"}, headers=budi)
        response = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                               headers=budi)
        assert response.status_code == 409

    def test_unknown_order_is_422(self, client, budi):
        assert client.post("/delivery-notes/from-sales-order/9999",
                           headers=budi).status_code == 422


class TestOverDeliveryGuard:
    def test_cannot_deliver_more_than_ordered(self, client, budi, order):
        ids = line_ids(client, budi, order["id"])
        response = client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 11}]})
        assert response.status_code == 422
        assert "only 10 of 10 left" in response.json()["detail"]

    def test_cannot_exceed_across_several_notes(self, client, budi, order):
        ids = line_ids(client, budi, order["id"])
        body = {"sales_order_id": order["id"],
                "items": [{"sales_order_item_id": ids[0], "quantity": 6}]}
        assert client.post("/delivery-notes", headers=budi, json=body).status_code == 201
        second = client.post("/delivery-notes", headers=budi, json=body)
        assert second.status_code == 422
        assert "only 4 of 10 left" in second.json()["detail"]

    def test_delivering_the_exact_remainder_is_fine(self, client, budi, order):
        ids = line_ids(client, budi, order["id"])
        client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 6}]})
        response = client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 4}]})
        assert response.status_code == 201

    def test_duplicate_lines_are_summed_before_checking(self, client, budi, order):
        """Splitting one order line over two rows must not dodge the limit."""
        ids = line_ids(client, budi, order["id"])
        response = client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [
                {"sales_order_item_id": ids[0], "quantity": 6},
                {"sales_order_item_id": ids[0], "quantity": 6},
            ]})
        assert response.status_code == 422

    def test_a_line_from_another_order_is_rejected(self, client, budi, order,
                                                   confirmed_order, products):
        other = confirmed_order(budi, items=[
            {"product_id": products["unit"].id, "quantity": 5}])
        stranger = line_ids(client, budi, other["id"])[0]
        response = client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": stranger, "quantity": 1}]})
        assert response.status_code == 422
        assert "not on invoice" in response.json()["detail"]

    def test_zero_quantity_is_rejected(self, client, budi, order):
        ids = line_ids(client, budi, order["id"])
        response = client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 0}]})
        assert response.status_code == 422

    def test_an_empty_note_is_rejected(self, client, budi, order):
        response = client.post("/delivery-notes", headers=budi,
                               json={"sales_order_id": order["id"], "items": []})
        assert response.status_code == 422
        assert "at least one line" in response.json()["detail"]

    def test_a_cancelled_note_releases_its_quantities(self, client, budi, order):
        ids = line_ids(client, budi, order["id"])
        note = client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 10}]}).json()

        client.patch(f"/delivery-notes/{note['id']}/status",
                     json={"status": "cancelled"}, headers=budi)

        body = client.get(f"/delivery-notes/outstanding/{order['id']}",
                          headers=budi).json()
        assert dec(body["lines"][0]["outstanding"]) == dec("10.00")
        again = client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 10}]})
        assert again.status_code == 201

    def test_a_draft_note_still_holds_its_quantities(self, client, budi, order):
        """Two people must not be able to promise the same goods."""
        ids = line_ids(client, budi, order["id"])
        client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 10}]})
        response = client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 1}]})
        assert response.status_code == 422


class TestEditing:
    def test_a_note_does_not_count_against_itself(self, client, budi, order):
        """Re-saving the same quantities must not trip the over-delivery guard."""
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        response = client.put(f"/delivery-notes/{note['id']}", headers=budi, json={
            "driver_name": "Pak Joko",
            "items": [{"sales_order_item_id": i["sales_order_item_id"],
                       "quantity": float(i["quantity"])} for i in note["items"]],
        })
        assert response.status_code == 200
        assert response.json()["driver_name"] == "Pak Joko"

    def test_header_only_edit_keeps_the_lines(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        updated = client.put(f"/delivery-notes/{note['id']}", headers=budi,
                             json={"vehicle_no": "B 1234 XYZ"}).json()
        assert updated["vehicle_no"] == "B 1234 XYZ"
        assert len(updated["items"]) == 3

    def test_reducing_a_line_frees_the_difference(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        first = note["items"][0]
        client.put(f"/delivery-notes/{note['id']}", headers=budi, json={
            "items": [{"sales_order_item_id": first["sales_order_item_id"],
                       "quantity": 3}]})
        body = client.get(f"/delivery-notes/outstanding/{order['id']}",
                          headers=budi).json()
        assert dec(body["lines"][0]["outstanding"]) == dec("7.00")

    def test_a_delivered_note_is_locked(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        for target in ("issued", "delivered"):
            client.patch(f"/delivery-notes/{note['id']}/status",
                         json={"status": target}, headers=budi)
        response = client.put(f"/delivery-notes/{note['id']}", headers=budi,
                              json={"driver_name": "Too late"})
        assert response.status_code == 409
        assert "no longer be edited" in response.json()["detail"]

    def test_missing_note_is_404(self, client, budi):
        assert client.put("/delivery-notes/9999", headers=budi,
                          json={"driver_name": "x"}).status_code == 404


class TestStatusFlow:
    def test_draft_issued_delivered(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        for target in ("issued", "delivered"):
            response = client.patch(f"/delivery-notes/{note['id']}/status",
                                    json={"status": target}, headers=budi)
            assert response.status_code == 200
            assert response.json()["status"] == target

    def test_delivering_records_who_signed(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        client.patch(f"/delivery-notes/{note['id']}/status",
                     json={"status": "issued"}, headers=budi)
        done = client.patch(f"/delivery-notes/{note['id']}/status", headers=budi,
                            json={"status": "delivered",
                                  "received_by": "Ibu Rina"}).json()
        assert done["received_by"] == "Ibu Rina"
        assert done["received_at"] == date.today().isoformat()

    def test_cannot_skip_straight_to_delivered(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        response = client.patch(f"/delivery-notes/{note['id']}/status",
                                json={"status": "delivered"}, headers=budi)
        assert response.status_code == 409

    def test_unknown_status_is_422(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        assert client.patch(f"/delivery-notes/{note['id']}/status",
                            json={"status": "teleported"},
                            headers=budi).status_code == 422

    def test_reinstating_a_cancelled_note_rechecks_capacity(self, client, budi, order):
        """While it was cancelled someone else may have shipped the goods."""
        ids = line_ids(client, budi, order["id"])
        note = client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 10}]}).json()
        client.patch(f"/delivery-notes/{note['id']}/status",
                     json={"status": "cancelled"}, headers=budi)

        # someone else ships the lot in the meantime
        client.post("/delivery-notes", headers=budi, json={
            "sales_order_id": order["id"],
            "items": [{"sales_order_item_id": ids[0], "quantity": 10}]})

        response = client.patch(f"/delivery-notes/{note['id']}/status",
                                json={"status": "draft"}, headers=budi)
        assert response.status_code == 422
        assert "left to deliver" in response.json()["detail"]


class TestDeletion:
    def test_a_draft_can_be_deleted(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        assert client.delete(f"/delivery-notes/{note['id']}",
                             headers=budi).status_code == 204

    def test_deleting_releases_the_quantities(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        client.delete(f"/delivery-notes/{note['id']}", headers=budi)
        body = client.get(f"/delivery-notes/outstanding/{order['id']}",
                          headers=budi).json()
        assert dec(body["lines"][0]["outstanding"]) == dec("10.00")

    def test_an_issued_note_cannot_be_deleted(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        client.patch(f"/delivery-notes/{note['id']}/status",
                     json={"status": "issued"}, headers=budi)
        response = client.delete(f"/delivery-notes/{note['id']}", headers=budi)
        assert response.status_code == 409
        assert "cancel it instead" in response.json()["detail"]


class TestListing:
    def test_filter_by_sales_order(self, client, budi, order, confirmed_order,
                                   products):
        client.post(f"/delivery-notes/from-sales-order/{order['id']}", headers=budi)
        other = confirmed_order(budi, items=[
            {"product_id": products["unit"].id, "quantity": 2}])
        client.post(f"/delivery-notes/from-sales-order/{other['id']}", headers=budi)

        rows = client.get(f"/delivery-notes?sales_order_id={order['id']}",
                          headers=budi).json()
        assert len(rows) == 1
        assert rows[0]["so_no"] == order["so_no"]

    def test_row_summary_fields(self, client, budi, customer, order):
        client.post(f"/delivery-notes/from-sales-order/{order['id']}", headers=budi)
        row = client.get("/delivery-notes", headers=budi).json()[0]
        assert row["line_count"] == 3
        assert dec(row["total_qty"]) == dec("20.00")
        assert row["customer_name"] == customer.name

    def test_filter_by_status(self, client, budi, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        client.patch(f"/delivery-notes/{note['id']}/status",
                     json={"status": "issued"}, headers=budi)
        assert len(client.get("/delivery-notes?status=issued", headers=budi).json()) == 1
        assert client.get("/delivery-notes?status=draft", headers=budi).json() == []

    def test_everyone_sees_all_notes(self, client, budi, sari, order):
        client.post(f"/delivery-notes/from-sales-order/{order['id']}", headers=budi)
        rows = client.get("/delivery-notes", headers=sari).json()
        assert len(rows) == 1
        assert rows[0]["can_edit"] is False

    def test_missing_note_is_404(self, client, budi):
        assert client.get("/delivery-notes/9999", headers=budi).status_code == 404


class TestOwnership:
    def test_stranger_cannot_edit(self, client, budi, sari, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        response = client.put(f"/delivery-notes/{note['id']}", headers=sari,
                              json={"driver_name": "Nope"})
        assert response.status_code == 403

    def test_stranger_cannot_change_status(self, client, budi, sari, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        assert client.patch(f"/delivery-notes/{note['id']}/status",
                            json={"status": "issued"},
                            headers=sari).status_code == 403

    def test_admin_can(self, client, budi, admin, order):
        note = client.post(f"/delivery-notes/from-sales-order/{order['id']}",
                           headers=budi).json()
        assert client.patch(f"/delivery-notes/{note['id']}/status",
                            json={"status": "issued"},
                            headers=admin).status_code == 200
