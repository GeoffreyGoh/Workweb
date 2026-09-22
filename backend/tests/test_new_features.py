"""Installation cost, TOP/DP, component options, report filters,
purchase-order splitting and the delivery schedule."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

import models
import pricing
from conftest import dec


# ------------------------------------------------------- installation cost
class TestInstallationCost:
    def test_lands_inside_the_ppn_base(self):
        """Installation is a taxable service - leaving it out of the PPN base
        would under-collect the tax."""
        lines = [{
            "line_total": Decimal("1000000.00"),
            "line_discount_amt": Decimal("0.00"),
            "quantity": Decimal("1"),
        }]
        totals = pricing.compute_totals(lines, Decimal("11"), Decimal("500000"))
        assert totals["netto"] == dec("1000000.00")
        assert totals["installation_cost"] == dec("500000.00")
        assert totals["ppn_amount"] == dec("165000.00")   # 11% of 1,500,000
        assert totals["total"] == dec("1665000.00")

    def test_defaults_to_zero(self):
        lines = [{"line_total": Decimal("100"), "line_discount_amt": Decimal("0"),
                  "quantity": Decimal("1")}]
        totals = pricing.compute_totals(lines, Decimal("0"))
        assert totals["installation_cost"] == dec("0.00")
        assert totals["total"] == dec("100.00")

    def test_negative_is_rejected(self):
        with pytest.raises(pricing.PricingError, match="cannot be negative"):
            pricing.compute_totals([], Decimal("11"), Decimal("-1"))

    def test_quotation_carries_it(self, client, budi, customer, products):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "discount_percent": 0, "ppn_percent": 11,
            "installation_cost": 750000,
            "items": [{"product_id": products["unit"].id, "quantity": 20}],
        }).json()
        assert dec(q["installation_cost"]) == dec("750000.00")
        assert dec(q["netto"]) == dec("1000000.00")
        assert dec(q["ppn_amount"]) == dec("192500.00")   # 11% of 1,750,000
        assert dec(q["total"]) == dec("1942500.00")

    def test_client_cannot_send_a_negative(self, client, budi, customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "installation_cost": -5,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 422

    def test_survives_conversion_to_a_sales_order(self, client, budi, customer,
                                                  products):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "installation_cost": 250000,
            "items": [{"product_id": products["unit"].id, "quantity": 4}]}).json()
        client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"}, headers=budi)
        so = client.post(f"/sales-orders/from-quotation/{q['id']}", headers=budi).json()
        assert dec(so["installation_cost"]) == dec("250000.00")
        assert dec(so["total"]) == dec(q["total"])


# ------------------------------------------------------------- TOP / DP
class TestDownPayment:
    def test_percentage_and_balance(self):
        dp, balance = pricing.compute_dp(Decimal("1665000"), 50)
        assert dp == dec("832500.00")
        assert balance == dec("832500.00")

    def test_blank_means_no_dp_agreed(self):
        dp, balance = pricing.compute_dp(Decimal("1000"), None)
        assert dp == dec("0.00")
        assert balance == dec("1000.00")

    def test_out_of_range_is_rejected(self):
        with pytest.raises(pricing.PricingError, match="between 0 and 100"):
            pricing.compute_dp(Decimal("1000"), 101)

    def test_dp_plus_balance_always_equals_total(self):
        for percent in (0, 1, 33.33, 50, 99.99, 100):
            dp, balance = pricing.compute_dp(Decimal("1234567.89"), percent)
            assert dp + balance == dec("1234567.89")

    def test_quotation_exposes_amount_and_balance(self, client, budi, customer,
                                                  products):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "discount_percent": 0, "ppn_percent": 0,
            "dp_percent": 40,
            "items": [{"product_id": products["unit"].id, "quantity": 20}]}).json()
        assert dec(q["total"]) == dec("1000000.00")
        assert dec(q["dp_percent"]) == dec("40.00")
        assert dec(q["dp_amount"]) == dec("400000.00")
        assert dec(q["dp_balance"]) == dec("600000.00")

    def test_dp_recalculates_when_the_total_changes(self, client, budi, customer,
                                                    products):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "discount_percent": 0, "ppn_percent": 0,
            "dp_percent": 50,
            "items": [{"product_id": products["unit"].id, "quantity": 20}]}).json()
        updated = client.put(f"/quotations/{q['id']}", headers=budi, json={
            "customer_id": customer.id, "discount_percent": 0, "ppn_percent": 0,
            "dp_percent": 50,
            "items": [{"product_id": products["unit"].id, "quantity": 40}]}).json()
        assert dec(updated["total"]) == dec("2000000.00")
        assert dec(updated["dp_amount"]) == dec("1000000.00")

    def test_carries_to_the_sales_order(self, client, budi, customer, products):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "dp_percent": 30,
            "items": [{"product_id": products["unit"].id, "quantity": 4}]}).json()
        client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"}, headers=budi)
        so = client.post(f"/sales-orders/from-quotation/{q['id']}", headers=budi).json()
        assert dec(so["dp_percent"]) == dec("30.00")
        assert dec(so["dp_amount"]) == dec(q["dp_amount"])

    def test_above_100_is_rejected_by_the_api(self, client, budi, customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "dp_percent": 120,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 422


# ------------------------------------------------------- component options
@pytest.fixture()
def fabric_with_options(db, products):
    product = products["sqm"]
    product.options.extend([
        models.ProductOption(option_group="Roller", option_name="Standard Roll",
                             is_available=True),
        models.ProductOption(option_group="Roller", option_name="Reverse Roll",
                             is_available=True),
        models.ProductOption(option_group="Roman", option_name="Classic",
                             is_available=False),   # the chart says "x"
    ])
    db.commit()
    return product


class TestComponentOptions:
    def test_only_available_options_are_offered(self, client, budi,
                                                fabric_with_options):
        options = client.get(f"/products/{fabric_with_options.id}/options",
                             headers=budi).json()
        names = {o["option_name"] for o in options}
        assert names == {"Standard Roll", "Reverse Roll"}
        assert "Classic" not in names

    def test_unavailable_can_be_asked_for_explicitly(self, client, budi,
                                                     fabric_with_options):
        options = client.get(
            f"/products/{fabric_with_options.id}/options?include_unavailable=true",
            headers=budi).json()
        assert len(options) == 3
        assert any(o["option_name"] == "Classic" and not o["is_available"]
                   for o in options)

    def test_product_detail_hides_unavailable(self, client, budi, fabric_with_options):
        product = client.get(f"/products/{fabric_with_options.id}", headers=budi).json()
        assert {o["option_name"] for o in product["options"]} == {
            "Standard Roll", "Reverse Roll"}

    def test_choice_is_stored_on_the_line(self, client, budi, customer,
                                          fabric_with_options):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": fabric_with_options.id, "quantity": 1,
                       "width_cm": 100, "height_cm": 100,
                       "component_options": "Roller: Standard Roll | Rail: Flat"}]}).json()
        assert q["items"][0]["component_options"] == "Roller: Standard Roll | Rail: Flat"

    def test_choice_survives_conversion(self, client, budi, customer,
                                        fabric_with_options):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": fabric_with_options.id, "quantity": 1,
                       "width_cm": 100, "height_cm": 100,
                       "component_options": "Roller: Reverse Roll"}]}).json()
        client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"}, headers=budi)
        so = client.post(f"/sales-orders/from-quotation/{q['id']}", headers=budi).json()
        assert so["items"][0]["component_options"] == "Roller: Reverse Roll"

    def test_missing_product_is_404(self, client, budi):
        assert client.get("/products/9999/options", headers=budi).status_code == 404


# ------------------------------------------------------- sales report filters
class TestReportFilters:
    def live_order(self, client, headers, make_sales_order, **kwargs):
        so = make_sales_order(headers, **kwargs)
        client.patch(f"/sales-orders/{so['id']}/status",
                     json={"status": "confirmed"}, headers=headers)
        return client.get(f"/sales-orders/{so['id']}", headers=headers).json()

    def test_breakdown_by_salesperson(self, client, budi, sari, users,
                                      make_quotation, make_sales_order):
        make_quotation(budi)
        make_quotation(budi)
        make_quotation(sari)
        self.live_order(client, budi, make_sales_order)

        report = client.get("/reports/sales", headers=budi).json()
        by_name = {u["created_by_name"]: u for u in report["by_user"]}
        assert by_name["Budi Santoso"]["quotation_count"] == 2
        assert by_name["Budi Santoso"]["order_count"] == 1
        assert by_name["Sari Dewi"]["quotation_count"] == 1
        assert by_name["Sari Dewi"]["order_count"] == 0

    def test_filter_to_one_salesperson(self, client, budi, sari, users,
                                       make_quotation):
        make_quotation(budi)
        make_quotation(sari)
        report = client.get(f"/reports/sales?created_by={users['sari']}",
                            headers=budi).json()
        assert report["quotation_count"] == 1
        assert [u["created_by_name"] for u in report["by_user"]] == ["Sari Dewi"]

    def test_filter_by_company(self, client, budi, customer, customer2,
                               make_quotation):
        make_quotation(budi)
        make_quotation(budi, customer_id=customer2.id)
        report = client.get(f"/reports/sales?customer_id={customer2.id}",
                            headers=budi).json()
        assert report["quotation_count"] == 1
        assert [c["customer_name"] for c in report["by_customer"]] in (
            [], [customer2.name])

    def test_both_filters_together(self, client, budi, sari, users, customer2,
                                   make_quotation):
        make_quotation(budi, customer_id=customer2.id)
        make_quotation(sari, customer_id=customer2.id)
        make_quotation(budi)
        report = client.get(
            f"/reports/sales?customer_id={customer2.id}&created_by={users['budi']}",
            headers=budi).json()
        assert report["quotation_count"] == 1

    def test_per_user_conversion_rate(self, client, budi, make_quotation,
                                      make_sales_order):
        for _ in range(4):
            make_quotation(budi)
        self.live_order(client, budi, make_sales_order)
        report = client.get("/reports/sales", headers=budi).json()
        assert dec(report["by_user"][0]["conversion_rate"]) == dec("25.00")

    def test_financial_report_filters_too(self, client, budi, sari, admin, users,
                                          make_sales_order):
        """Only an admin gets the unfiltered view to compare against - a normal
        user's report is already scoped to themselves."""
        self.live_order(client, budi, make_sales_order)
        self.live_order(client, sari, make_sales_order)
        everyone = client.get("/reports/financial", headers=admin).json()
        just_budi = client.get(f"/reports/financial?created_by={users['budi']}",
                               headers=admin).json()
        assert len(everyone["by_order"]) == 2
        assert len(just_budi["by_order"]) == 1
        assert dec(just_budi["revenue"]) < dec(everyone["revenue"])

    def test_a_users_own_report_already_equals_the_filtered_one(
            self, client, budi, sari, users, make_sales_order):
        self.live_order(client, budi, make_sales_order)
        self.live_order(client, sari, make_sales_order)
        unfiltered = client.get("/reports/financial", headers=budi).json()
        filtered = client.get(f"/reports/financial?created_by={users['budi']}",
                              headers=budi).json()
        assert dec(unfiltered["revenue"]) == dec(filtered["revenue"])


# ------------------------------------------------ purchase order per supplier
@pytest.fixture()
def two_suppliers(db, supplier):
    second = models.Supplier(code="SUP-002", name="CV Aluminium Jaya",
                             payment_terms="14 days")
    db.add(second)
    db.commit()
    db.refresh(second)
    return supplier, second


class TestPurchaseOrderSplit:
    def order_with_suppliers(self, client, db, headers, customer, products,
                             two_suppliers):
        fabric_supplier, metal_supplier = two_suppliers
        products["sqm"].supplier_id = fabric_supplier.id
        products["meter"].supplier_id = metal_supplier.id
        products["unit"].supplier_id = None      # a service, nobody supplies it
        db.commit()

        so = client.post("/sales-orders", headers=headers, json={
            "customer_id": customer.id,
            "items": [
                {"product_id": products["sqm"].id, "quantity": 2,
                 "width_cm": 200, "height_cm": 100},
                {"product_id": products["meter"].id, "quantity": 3, "width_cm": 250},
                {"product_id": products["unit"].id, "quantity": 5},
            ]}).json()
        client.patch(f"/sales-orders/{so['id']}/status",
                     json={"status": "confirmed"}, headers=headers)
        return so

    def test_preview_groups_by_supplier(self, client, budi, db, customer, products,
                                        two_suppliers):
        so = self.order_with_suppliers(client, db, budi, customer, products,
                                       two_suppliers)
        preview = client.get(f"/purchase-orders/split/{so['id']}", headers=budi).json()
        assert len(preview["groups"]) == 2
        assert {g["supplier_name"] for g in preview["groups"]} == {
            "PT Tekstil Nusantara", "CV Aluminium Jaya"}
        assert all(len(g["lines"]) == 1 for g in preview["groups"])

    def test_preview_lists_lines_with_no_supplier(self, client, budi, db, customer,
                                                  products, two_suppliers):
        so = self.order_with_suppliers(client, db, budi, customer, products,
                                       two_suppliers)
        preview = client.get(f"/purchase-orders/split/{so['id']}", headers=budi).json()
        assert [line["product_code"] for line in preview["unassigned"]] == ["INS-U"]

    def test_creates_one_po_per_supplier(self, client, budi, db, customer, products,
                                         two_suppliers):
        so = self.order_with_suppliers(client, db, budi, customer, products,
                                       two_suppliers)
        created = client.post(f"/purchase-orders/split/{so['id']}", headers=budi).json()
        assert len(created) == 2
        assert len({po["po_no"] for po in created}) == 2
        assert all(po["sales_order_id"] == so["id"] for po in created)
        assert all(po["status"] == "draft" for po in created)

    def test_each_po_only_holds_its_suppliers_lines(self, client, budi, db, customer,
                                                    products, two_suppliers):
        so = self.order_with_suppliers(client, db, budi, customer, products,
                                       two_suppliers)
        created = client.post(f"/purchase-orders/split/{so['id']}", headers=budi).json()
        for po in created:
            assert len(po["items"]) == 1
            if po["supplier_name"] == "PT Tekstil Nusantara":
                assert "Roller Blind" in po["items"][0]["description"]
            else:
                assert "Curtain Track" in po["items"][0]["description"]

    def test_quantity_follows_the_billable_measure(self, client, budi, db, customer,
                                                   products, two_suppliers):
        """2 blinds of 2m x 1m need 4 m2 of fabric, not 2 pieces."""
        so = self.order_with_suppliers(client, db, budi, customer, products,
                                       two_suppliers)
        created = client.post(f"/purchase-orders/split/{so['id']}", headers=budi).json()
        fabric = next(p for p in created if p["supplier_name"] == "PT Tekstil Nusantara")
        assert dec(fabric["items"][0]["quantity"]) == dec("4.00")
        assert fabric["items"][0]["unit"] == "m2"

    def test_unassigned_lines_are_not_dumped_on_a_supplier(self, client, budi, db,
                                                           customer, products,
                                                           two_suppliers):
        so = self.order_with_suppliers(client, db, budi, customer, products,
                                       two_suppliers)
        created = client.post(f"/purchase-orders/split/{so['id']}", headers=budi).json()
        descriptions = [i["description"] for po in created for i in po["items"]]
        assert not any("Installation" in d for d in descriptions)

    def test_refused_when_no_product_has_a_supplier(self, client, budi,
                                                    confirmed_order):
        so = confirmed_order(budi)
        response = client.post(f"/purchase-orders/split/{so['id']}", headers=budi)
        assert response.status_code == 409
        assert "default supplier" in response.json()["detail"]

    def test_draft_order_cannot_be_split(self, client, budi, db, customer, products,
                                         two_suppliers, make_sales_order):
        products["unit"].supplier_id = two_suppliers[0].id
        db.commit()
        so = make_sales_order(budi)
        response = client.post(f"/purchase-orders/split/{so['id']}", headers=budi)
        assert response.status_code == 409

    def test_missing_order_is_404(self, client, budi):
        assert client.post("/purchase-orders/split/9999", headers=budi).status_code == 404


# -------------------------------------------------------- delivery schedule
class TestDeliverySchedule:
    def note_on(self, client, headers, so, when, slot=None):
        note = client.post(f"/delivery-notes/from-sales-order/{so['id']}",
                           headers=headers).json()
        client.put(f"/delivery-notes/{note['id']}", headers=headers, json={
            "delivery_date": when.isoformat(), "time_slot": slot,
            "driver_name": "Pak Joko"})
        return client.get(f"/delivery-notes/{note['id']}", headers=headers).json()

    def test_groups_by_day(self, client, budi, confirmed_order):
        today = date.today()
        self.note_on(client, budi, confirmed_order(budi), today)
        self.note_on(client, budi, confirmed_order(budi), today + timedelta(days=2))

        board = client.get("/delivery-notes/schedule/board", headers=budi).json()
        assert [d["delivery_date"] for d in board["days"]] == [
            today.isoformat(), (today + timedelta(days=2)).isoformat()]
        assert board["days"][0]["is_today"] is True

    def test_orders_stops_by_time_slot(self, client, budi, confirmed_order):
        today = date.today()
        self.note_on(client, budi, confirmed_order(budi), today, "evening")
        self.note_on(client, budi, confirmed_order(budi), today, "morning")
        board = client.get("/delivery-notes/schedule/board", headers=budi).json()
        slots = [s["time_slot"] for s in board["days"][0]["stops"]]
        assert slots == ["morning", "evening"]

    def test_day_totals(self, client, budi, confirmed_order, products):
        today = date.today()
        so = confirmed_order(budi, items=[
            {"product_id": products["unit"].id, "quantity": 7}])
        self.note_on(client, budi, so, today)
        board = client.get("/delivery-notes/schedule/board", headers=budi).json()
        assert board["days"][0]["stop_count"] == 1
        assert dec(board["days"][0]["total_qty"]) == dec("7.00")

    def test_cancelled_notes_are_off_the_board(self, client, budi, confirmed_order):
        note = self.note_on(client, budi, confirmed_order(budi), date.today())
        client.patch(f"/delivery-notes/{note['id']}/status",
                     json={"status": "cancelled"}, headers=budi)
        board = client.get("/delivery-notes/schedule/board", headers=budi).json()
        assert board["days"] == []

    def test_overdue_undelivered_notes_are_surfaced(self, client, budi, db,
                                                    confirmed_order):
        note = self.note_on(client, budi, confirmed_order(budi), date.today())
        db.query(models.DeliveryNote).filter(
            models.DeliveryNote.id == note["id"]).update(
                {"delivery_date": date.today() - timedelta(days=10)})
        db.commit()
        board = client.get("/delivery-notes/schedule/board", headers=budi).json()
        assert board["days"][0]["is_overdue"] is True

    def test_orders_awaiting_a_surat_jalan_are_listed(self, client, budi,
                                                      confirmed_order):
        so = confirmed_order(budi)
        board = client.get("/delivery-notes/schedule/board", headers=budi).json()
        assert [s["so_no"] for s in board["unscheduled"]] == [so["so_no"]]

    def test_fully_scheduled_orders_drop_off_the_unscheduled_list(
            self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        self.note_on(client, budi, so, date.today())
        board = client.get("/delivery-notes/schedule/board", headers=budi).json()
        assert board["unscheduled"] == []

    def test_filter_by_driver(self, client, budi, confirmed_order):
        self.note_on(client, budi, confirmed_order(budi), date.today())
        assert client.get("/delivery-notes/schedule/board?driver=Joko",
                          headers=budi).json()["days"]
        assert client.get("/delivery-notes/schedule/board?driver=Nobody",
                          headers=budi).json()["days"] == []

    def test_defaults_to_a_fortnight(self, client, budi):
        board = client.get("/delivery-notes/schedule/board", headers=budi).json()
        span = date.fromisoformat(board["date_to"]) - date.fromisoformat(
            board["date_from"])
        assert span.days == 14

    def test_requires_authentication(self, client, users):
        assert client.get("/delivery-notes/schedule/board").status_code == 401


class TestUsersEndpoint:
    def test_lists_active_staff(self, client, budi, users):
        rows = client.get("/users", headers=budi).json()
        names = {u["username"] for u in rows}
        assert {"admin", "budi", "sari"} <= names
        assert "gone" not in names          # deactivated

    def test_never_leaks_password_hashes(self, client, budi, users):
        assert all("password_hash" not in u for u in client.get("/users",
                                                                headers=budi).json())

    def test_requires_authentication(self, client, users):
        assert client.get("/users").status_code == 401
