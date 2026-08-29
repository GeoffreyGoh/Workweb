"""Quotation creation, editing, numbering and status rules."""

from datetime import date

import pytest

from conftest import dec


class TestCreate:
    def test_server_computes_every_total(self, client, budi, make_quotation):
        q = make_quotation(budi)
        assert dec(q["subtotal"]) == dec("3100000.00")
        assert dec(q["discount_amount"]) == dec("1085000.00")
        assert dec(q["netto"]) == dec("2015000.00")
        assert dec(q["ppn_amount"]) == dec("221650.00")
        assert dec(q["total"]) == dec("2236650.00")
        assert dec(q["total_qty"]) == dec("9.00")

    def test_client_supplied_totals_are_ignored(self, client, budi, customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "subtotal": 1, "discount_amount": 0, "netto": 1,
            "ppn_amount": 1, "total": 1, "total_qty": 999,
            "items": [{"product_id": products["unit"].id, "quantity": 2}],
        })
        q = response.json()
        assert dec(q["subtotal"]) == dec("100000.00")   # 2 x 50,000
        assert dec(q["total_qty"]) == dec("2.00")
        assert dec(q["total"]) != dec("1")

    def test_defaults_to_35_percent_discount(self, client, budi, customer, products):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["unit"].id, "quantity": 1}],
        }).json()
        assert dec(q["discount_percent"]) == dec("35.00")

    def test_discount_stays_editable(self, client, budi, make_quotation):
        q = make_quotation(budi, discount_percent=12.5)
        assert dec(q["discount_percent"]) == dec("12.50")
        assert dec(q["discount_amount"]) == dec("387500.00")  # 12.5% of 3,100,000

    def test_new_quotations_start_as_draft(self, client, budi, make_quotation):
        assert make_quotation(budi)["status"] == "draft"

    def test_status_cannot_be_forced_on_create(self, client, budi, make_quotation):
        assert make_quotation(budi, status="approved")["status"] == "draft"

    def test_records_the_creator(self, client, budi, users, make_quotation):
        q = make_quotation(budi)
        assert q["created_by"] == users["budi"]
        assert q["created_by_name"] == "Budi Santoso"

    def test_customer_details_are_snapshotted(self, client, budi, customer, make_quotation):
        q = make_quotation(budi)
        assert q["address"] == customer.address
        assert q["payment_terms"] == customer.payment_terms
        assert q["nik_npwp"] == customer.nik_npwp

    def test_explicit_header_values_beat_the_customer_master(self, client, budi,
                                                             customer, products):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "address": "Site address, not billing",
            "items": [{"product_id": products["unit"].id, "quantity": 1}],
        }).json()
        assert q["address"] == "Site address, not billing"

    def test_line_snapshots_survive_a_later_product_rename(self, client, budi, db,
                                                          make_quotation, products):
        q = make_quotation(budi)
        import models
        db.query(models.Product).filter(models.Product.id == products["sqm"].id).update(
            {"name": "Renamed Later", "unit_price": dec("999999")})
        db.commit()
        fetched = client.get(f"/quotations/{q['id']}", headers=budi).json()
        assert fetched["items"][0]["product_name"] == "Roller Blind"
        assert dec(fetched["items"][0]["unit_price"]) == dec("400000.00")

    def test_unknown_customer_is_422(self, client, budi, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": 9999,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 422
        assert "customer" in response.json()["detail"].lower()

    def test_unknown_product_is_422(self, client, budi, customer):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": 4242, "quantity": 1}]})
        assert response.status_code == 422
        assert "4242" in response.json()["detail"]

    def test_a_quotation_with_no_lines_is_allowed_but_zero(self, client, budi, customer):
        q = client.post("/quotations", headers=budi,
                        json={"customer_id": customer.id, "items": []}).json()
        assert dec(q["total"]) == dec("0.00")


class TestValidation:
    def test_oversize_width_is_rejected(self, client, budi, customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["sqm"].id, "quantity": 1,
                       "width_cm": 350, "height_cm": 100}]})
        assert response.status_code == 422
        assert "exceeds the maximum" in response.json()["detail"]

    def test_missing_height_on_a_sqm_product_is_rejected(self, client, budi,
                                                         customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["sqm"].id, "quantity": 1, "width_cm": 100}]})
        assert response.status_code == 422
        assert "height_cm is required" in response.json()["detail"]

    def test_error_identifies_the_offending_line(self, client, budi, customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [
                {"product_id": products["unit"].id, "quantity": 1},
                {"product_id": products["unit"].id, "quantity": 1},
                {"product_id": products["sqm"].id, "quantity": 1,
                 "width_cm": 999, "height_cm": 100},
            ]})
        assert response.status_code == 422
        assert "Line 3" in response.json()["detail"]

    def test_zero_quantity_is_rejected(self, client, budi, customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["unit"].id, "quantity": 0}]})
        assert response.status_code == 422

    def test_discount_above_100_is_rejected(self, client, budi, customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "discount_percent": 101,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 422

    def test_negative_discount_is_rejected(self, client, budi, customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "discount_percent": -5,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 422

    def test_a_failed_create_leaves_nothing_behind(self, client, budi, customer, products):
        client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["sqm"].id, "quantity": 1,
                       "width_cm": 999, "height_cm": 100}]})
        assert client.get("/quotations", headers=budi).json() == []


class TestNumbering:
    def test_format_is_q_yyyymm_seq(self, client, budi, make_quotation):
        q = make_quotation(budi)
        assert q["quotation_no"] == f"Q-GB-{date.today():%Y%m}-001"

    def test_numbers_increment(self, client, budi, make_quotation):
        numbers = [make_quotation(budi)["quotation_no"] for _ in range(3)]
        assert numbers == [f"Q-GB-{date.today():%Y%m}-{n:03d}" for n in (1, 2, 3)]

    def test_numbers_are_unique_across_users(self, client, budi, sari, make_quotation):
        numbers = {make_quotation(budi)["quotation_no"],
                   make_quotation(sari)["quotation_no"],
                   make_quotation(budi)["quotation_no"]}
        assert len(numbers) == 3


class TestUpdate:
    def test_editing_reprices_from_scratch(self, client, budi, make_quotation, products):
        q = make_quotation(budi)
        updated = client.put(f"/quotations/{q['id']}", headers=budi, json={
            "customer_id": q["customer_id"], "discount_percent": 50, "ppn_percent": 11,
            "items": [{"product_id": products["unit"].id, "quantity": 4}],
        }).json()
        assert dec(updated["subtotal"]) == dec("200000.00")
        assert dec(updated["discount_amount"]) == dec("100000.00")
        assert len(updated["items"]) == 1

    def test_changing_only_the_discount_reprices_existing_lines(self, client, budi,
                                                                make_quotation):
        q = make_quotation(budi)
        updated = client.put(f"/quotations/{q['id']}", headers=budi, json={
            "customer_id": q["customer_id"], "discount_percent": 0, "ppn_percent": 11,
        }).json()
        assert dec(updated["subtotal"]) == dec("3100000.00")
        assert dec(updated["discount_amount"]) == dec("0.00")
        assert dec(updated["netto"]) == dec("3100000.00")
        assert len(updated["items"]) == 3

    def test_the_number_never_changes_on_edit(self, client, budi, make_quotation):
        q = make_quotation(budi)
        updated = client.put(f"/quotations/{q['id']}", headers=budi,
                             json={"customer_id": q["customer_id"], "items": []}).json()
        assert updated["quotation_no"] == q["quotation_no"]

    def test_a_sent_quotation_is_still_editable(self, client, budi, make_quotation,
                                                products):
        """A sent quotation is still being negotiated - the customer asks for a
        different fabric and the same document is revised."""
        q = make_quotation(budi)
        client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"}, headers=budi)

        response = client.put(f"/quotations/{q['id']}", headers=budi, json={
            "customer_id": q["customer_id"], "discount_percent": 0, "ppn_percent": 0,
            "items": [{"product_id": products["unit"].id, "quantity": 3}]})
        assert response.status_code == 200
        assert dec(response.json()["total"]) == dec("150000.00")

    def test_revising_a_sent_quotation_keeps_it_sent(self, client, budi,
                                                     make_quotation):
        q = make_quotation(budi)
        client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"}, headers=budi)
        updated = client.put(f"/quotations/{q['id']}", headers=budi,
                             json={"customer_id": q["customer_id"], "items": []}).json()
        assert updated["status"] == "sent"
        assert updated["quotation_no"] == q["quotation_no"]

    @pytest.mark.parametrize("status", ["approved", "converted", "cancelled"])
    def test_locked_once_it_leaves_negotiation(self, client, budi, admin, db,
                                               make_quotation, status):
        """Past 'sent' a sales order may depend on the figures, so it locks."""
        import models
        q = make_quotation(budi)
        db.query(models.Quotation).filter(models.Quotation.id == q["id"]).update(
            {"status": status})
        db.commit()

        response = client.put(f"/quotations/{q['id']}", headers=admin,
                              json={"customer_id": q["customer_id"], "items": []})
        assert response.status_code == 409
        assert "no longer be edited" in response.json()["detail"]

    def test_editing_a_missing_quotation_is_404(self, client, budi, customer):
        response = client.put("/quotations/9999", headers=budi,
                              json={"customer_id": customer.id, "items": []})
        assert response.status_code == 404


class TestStatus:
    def test_happy_path(self, client, budi, make_quotation):
        q = make_quotation(budi)
        for target in ("sent", "approved"):
            response = client.patch(f"/quotations/{q['id']}/status",
                                    json={"status": target}, headers=budi)
            assert response.status_code == 200
            assert response.json()["status"] == target

    def test_sending_stamps_the_follow_up_date(self, client, budi, make_quotation):
        q = make_quotation(budi)
        sent = client.patch(f"/quotations/{q['id']}/status",
                            json={"status": "sent"}, headers=budi).json()
        assert sent["last_follow_up"] == date.today().isoformat()

    def test_illegal_jump_is_refused(self, client, budi, make_quotation):
        q = make_quotation(budi)
        response = client.patch(f"/quotations/{q['id']}/status",
                                json={"status": "converted"}, headers=budi)
        assert response.status_code == 409
        assert "Cannot move" in response.json()["detail"]

    def test_unknown_status_is_422(self, client, budi, make_quotation):
        q = make_quotation(budi)
        response = client.patch(f"/quotations/{q['id']}/status",
                                json={"status": "banana"}, headers=budi)
        assert response.status_code == 422

    def test_cancelled_can_be_reopened_as_draft(self, client, budi, make_quotation):
        q = make_quotation(budi)
        client.patch(f"/quotations/{q['id']}/status",
                     json={"status": "cancelled"}, headers=budi)
        response = client.patch(f"/quotations/{q['id']}/status",
                                json={"status": "draft"}, headers=budi)
        assert response.status_code == 200


class TestListAndFilters:
    def test_everyone_sees_every_quotation(self, client, budi, sari, make_quotation):
        make_quotation(budi)
        make_quotation(sari)
        assert len(client.get("/quotations", headers=sari).json()) == 2
        assert len(client.get("/quotations", headers=budi).json()) == 2

    def test_filter_by_status(self, client, budi, make_quotation):
        first = make_quotation(budi)
        make_quotation(budi)
        client.patch(f"/quotations/{first['id']}/status",
                     json={"status": "sent"}, headers=budi)
        sent = client.get("/quotations?status=sent", headers=budi).json()
        assert [q["id"] for q in sent] == [first["id"]]

    def test_filter_by_customer(self, client, budi, customer2, make_quotation, products):
        make_quotation(budi)
        other = make_quotation(budi, customer_id=customer2.id)
        rows = client.get(f"/quotations?customer_id={customer2.id}", headers=budi).json()
        assert [q["id"] for q in rows] == [other["id"]]

    def test_search_by_number(self, client, budi, make_quotation):
        q = make_quotation(budi)
        rows = client.get(f"/quotations?q={q['quotation_no'][-3:]}", headers=budi).json()
        assert q["id"] in [r["id"] for r in rows]

    def test_date_range(self, client, budi, make_quotation):
        make_quotation(budi)
        today = date.today().isoformat()
        assert len(client.get(f"/quotations?date_from={today}", headers=budi).json()) == 1
        assert client.get("/quotations?date_to=2000-01-01", headers=budi).json() == []

    def test_newest_first(self, client, budi, make_quotation):
        ids = [make_quotation(budi)["id"] for _ in range(3)]
        listed = [q["id"] for q in client.get("/quotations", headers=budi).json()]
        assert listed == sorted(ids, reverse=True)

    def test_detail_includes_lines(self, client, budi, make_quotation):
        q = make_quotation(budi)
        detail = client.get(f"/quotations/{q['id']}", headers=budi).json()
        assert len(detail["items"]) == 3
        assert [i["line_no"] for i in detail["items"]] == [1, 2, 3]

    def test_missing_quotation_is_404(self, client, budi):
        assert client.get("/quotations/9999", headers=budi).status_code == 404
