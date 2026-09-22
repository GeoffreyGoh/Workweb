"""Sales and financial reporting.

Both reports work on netto (pre-PPN) figures, and only on documents that have
actually committed - draft and cancelled ones do not count.
"""

from datetime import date, timedelta

from conftest import dec


def live_order(client, headers, make_sales_order, **kwargs):
    """A sales order in a state the reports count."""
    so = make_sales_order(headers, **kwargs)
    client.patch(f"/sales-orders/{so['id']}/status",
                 json={"status": "confirmed"}, headers=headers)
    return client.get(f"/sales-orders/{so['id']}", headers=headers).json()


def live_po(client, headers, make_purchase_order, **kwargs):
    po = make_purchase_order(headers, **kwargs)
    client.patch(f"/purchase-orders/{po['id']}/status",
                 json={"status": "sent"}, headers=headers)
    return client.get(f"/purchase-orders/{po['id']}", headers=headers).json()


class TestSalesReport:
    def test_empty_period_is_all_zeroes(self, client, budi):
        r = client.get("/reports/sales", headers=budi).json()
        assert r["quotation_count"] == 0
        assert dec(r["order_value"]) == dec("0.00")
        assert dec(r["conversion_rate"]) == dec("0.00")
        assert r["by_period"] == []

    def test_counts_quotations_and_orders(self, client, budi, make_quotation,
                                          make_sales_order):
        make_quotation(budi)
        make_quotation(budi)
        so = live_order(client, budi, make_sales_order)
        r = client.get("/reports/sales", headers=budi).json()
        assert r["quotation_count"] == 2
        assert r["order_count"] == 1
        assert dec(r["order_value"]) == dec(so["netto"])

    def test_values_are_netto_not_gross(self, client, budi, make_quotation):
        q = make_quotation(budi)
        r = client.get("/reports/sales", headers=budi).json()
        assert dec(r["quotation_value"]) == dec(q["netto"])
        assert dec(r["quotation_value"]) != dec(q["total"])

    def test_conversion_rate(self, client, budi, make_quotation, make_sales_order):
        for _ in range(4):
            make_quotation(budi)
        live_order(client, budi, make_sales_order)
        r = client.get("/reports/sales", headers=budi).json()
        assert dec(r["conversion_rate"]) == dec("25.00")

    def test_draft_orders_do_not_count(self, client, budi, make_sales_order):
        make_sales_order(budi)  # left as draft
        r = client.get("/reports/sales", headers=budi).json()
        assert r["order_count"] == 0

    def test_cancelled_quotations_do_not_count(self, client, budi, make_quotation):
        q = make_quotation(budi)
        client.patch(f"/quotations/{q['id']}/status",
                     json={"status": "cancelled"}, headers=budi)
        r = client.get("/reports/sales", headers=budi).json()
        assert r["quotation_count"] == 0

    def test_breakdown_by_customer(self, client, budi, customer, customer2,
                                   make_sales_order):
        live_order(client, budi, make_sales_order)
        live_order(client, budi, make_sales_order, customer_id=customer2.id)
        r = client.get("/reports/sales", headers=budi).json()
        names = {row["customer_name"] for row in r["by_customer"]}
        assert names == {customer.name, customer2.name}

    def test_customers_are_ranked_by_value(self, client, budi, customer2, products,
                                           make_sales_order):
        live_order(client, budi, make_sales_order,
                   items=[{"product_id": products["unit"].id, "quantity": 1}])
        live_order(client, budi, make_sales_order, customer_id=customer2.id,
                   items=[{"product_id": products["unit"].id, "quantity": 100}])
        r = client.get("/reports/sales", headers=budi).json()
        values = [dec(row["order_value"]) for row in r["by_customer"]]
        assert values == sorted(values, reverse=True)

    def test_breakdown_by_product(self, client, budi, products, make_sales_order):
        live_order(client, budi, make_sales_order, items=[
            {"product_id": products["unit"].id, "quantity": 4},
            {"product_id": products["meter"].id, "quantity": 2, "width_cm": 250},
        ])
        r = client.get("/reports/sales", headers=budi).json()
        by_code = {row["product_code"]: row for row in r["by_product"]}
        assert dec(by_code["INS-U"]["quantity"]) == dec("4.00")
        assert dec(by_code["TRK-M"]["measure"]) == dec("5.00")

    def test_product_quantities_accumulate_across_orders(self, client, budi, products,
                                                         make_sales_order):
        for _ in range(3):
            live_order(client, budi, make_sales_order,
                       items=[{"product_id": products["unit"].id, "quantity": 2}])
        r = client.get("/reports/sales", headers=budi).json()
        assert dec(r["by_product"][0]["quantity"]) == dec("6.00")

    def test_status_census(self, client, budi, make_quotation):
        make_quotation(budi)
        sent = make_quotation(budi)
        client.patch(f"/quotations/{sent['id']}/status",
                     json={"status": "sent"}, headers=budi)
        r = client.get("/reports/sales", headers=budi).json()
        assert r["by_status"] == {"draft": 1, "sent": 1}

    def test_period_buckets_are_monthly_and_sorted(self, client, budi, db,
                                                   make_quotation):
        import models
        make_quotation(budi)
        old = make_quotation(budi)
        db.query(models.Quotation).filter(models.Quotation.id == old["id"]).update(
            {"quotation_date": date.today() - timedelta(days=60)})
        db.commit()
        r = client.get("/reports/sales", headers=budi).json()
        periods = [row["period"] for row in r["by_period"]]
        assert periods == sorted(periods)
        assert len(periods) >= 2

    def test_date_range_excludes_older_documents(self, client, budi, db,
                                                 make_quotation):
        import models
        q = make_quotation(budi)
        db.query(models.Quotation).filter(models.Quotation.id == q["id"]).update(
            {"quotation_date": date(2020, 1, 15)})
        db.commit()
        assert client.get("/reports/sales", headers=budi).json()["quotation_count"] == 0
        wide = client.get("/reports/sales?date_from=2020-01-01&date_to=2020-12-31",
                          headers=budi).json()
        assert wide["quotation_count"] == 1

    def test_filter_by_customer(self, client, budi, customer2, make_quotation):
        make_quotation(budi)
        make_quotation(budi, customer_id=customer2.id)
        r = client.get(f"/reports/sales?customer_id={customer2.id}", headers=budi).json()
        assert r["quotation_count"] == 1


class TestFinancialReport:
    def test_empty_period(self, client, budi):
        r = client.get("/reports/financial", headers=budi).json()
        assert dec(r["revenue"]) == dec("0.00")
        assert dec(r["cost"]) == dec("0.00")
        assert dec(r["margin_pct"]) == dec("0.00")   # no divide-by-zero

    def test_revenue_less_cost_is_gross_profit(self, client, budi, make_sales_order,
                                               make_purchase_order):
        so = live_order(client, budi, make_sales_order)
        po = live_po(client, budi, make_purchase_order, sales_order_id=so["id"])
        r = client.get("/reports/financial", headers=budi).json()
        assert dec(r["revenue"]) == dec(so["netto"])
        assert dec(r["cost"]) == dec(po["subtotal"])
        assert dec(r["gross_profit"]) == dec(so["netto"]) - dec(po["subtotal"])

    def test_margin_percentage(self, client, budi, products, make_sales_order,
                               make_purchase_order):
        # netto 1,000,000 revenue against 750,000 cost -> 25% margin
        so = live_order(client, budi, make_sales_order, discount_percent=0, items=[
            {"product_id": products["unit"].id, "quantity": 20}])   # 20 x 50,000
        live_po(client, budi, make_purchase_order, sales_order_id=so["id"], items=[
            {"description": "materials", "quantity": 1, "unit_price": 750000}])
        r = client.get("/reports/financial", headers=budi).json()
        assert dec(r["revenue"]) == dec("1000000.00")
        assert dec(r["cost"]) == dec("750000.00")
        assert dec(r["gross_profit"]) == dec("250000.00")
        assert dec(r["margin_pct"]) == dec("25.00")

    def test_both_sides_exclude_ppn(self, client, budi, admin, make_sales_order,
                                    make_purchase_order):
        so = live_order(client, budi, make_sales_order)
        po = live_po(client, budi, make_purchase_order)
        r = client.get("/reports/financial", headers=admin).json()
        assert dec(r["revenue"]) != dec(so["total"])      # total includes PPN
        assert dec(r["cost"]) != dec(po["total"])

    def test_linked_cost_is_attributed_to_the_order(self, client, budi,
                                                    make_sales_order,
                                                    make_purchase_order):
        so = live_order(client, budi, make_sales_order)
        po = live_po(client, budi, make_purchase_order, sales_order_id=so["id"])
        r = client.get("/reports/financial", headers=budi).json()
        row = next(o for o in r["by_order"] if o["sales_order_id"] == so["id"])
        assert dec(row["cost"]) == dec(po["subtotal"])
        assert row["po_count"] == 1
        assert dec(r["cost_unlinked"]) == dec("0.00")

    def test_unlinked_cost_counts_in_the_total_but_not_per_order(
            self, client, budi, admin, make_sales_order, make_purchase_order):
        """Whole-business view: unlinked overhead belongs to nobody, so only
        an admin's unscoped report can show it."""
        so = live_order(client, budi, make_sales_order)
        stray = live_po(client, budi, make_purchase_order)   # no sales_order_id
        r = client.get("/reports/financial", headers=admin).json()
        assert dec(r["cost"]) == dec(stray["subtotal"])
        assert dec(r["cost_unlinked"]) == dec(stray["subtotal"])
        row = next(o for o in r["by_order"] if o["sales_order_id"] == so["id"])
        assert dec(row["cost"]) == dec("0.00")
        assert row["po_count"] == 0

    def test_linked_plus_unlinked_equals_total_cost(self, client, budi, admin,
                                                    make_sales_order,
                                                    make_purchase_order):
        so = live_order(client, budi, make_sales_order)
        live_po(client, budi, make_purchase_order, sales_order_id=so["id"])
        live_po(client, budi, make_purchase_order)
        r = client.get("/reports/financial", headers=admin).json()
        assert dec(r["cost_linked"]) + dec(r["cost_unlinked"]) == dec(r["cost"])

    def test_several_pos_on_one_order_add_up(self, client, budi, make_sales_order,
                                             make_purchase_order):
        so = live_order(client, budi, make_sales_order)
        a = live_po(client, budi, make_purchase_order, sales_order_id=so["id"])
        b = live_po(client, budi, make_purchase_order, sales_order_id=so["id"], items=[
            {"description": "extra", "quantity": 1, "unit_price": 111000}])
        r = client.get("/reports/financial", headers=budi).json()
        row = next(o for o in r["by_order"] if o["sales_order_id"] == so["id"])
        assert dec(row["cost"]) == dec(a["subtotal"]) + dec(b["subtotal"])
        assert row["po_count"] == 2

    def test_draft_purchase_orders_are_not_cost_yet(self, client, budi, admin,
                                                    make_sales_order,
                                                    make_purchase_order):
        live_order(client, budi, make_sales_order)
        make_purchase_order(budi)   # left as draft
        r = client.get("/reports/financial", headers=admin).json()
        assert dec(r["cost"]) == dec("0.00")

    def test_cancelled_purchase_orders_are_excluded(self, client, budi, admin,
                                                    make_sales_order,
                                                    make_purchase_order):
        live_order(client, budi, make_sales_order)
        po = make_purchase_order(budi)
        client.patch(f"/purchase-orders/{po['id']}/status",
                     json={"status": "cancelled"}, headers=budi)
        r = client.get("/reports/financial", headers=admin).json()
        assert dec(r["cost"]) == dec("0.00")

    def test_negative_margin_is_reported_honestly(self, client, budi, products,
                                                  make_sales_order,
                                                  make_purchase_order):
        so = live_order(client, budi, make_sales_order, items=[
            {"product_id": products["unit"].id, "quantity": 1}])
        live_po(client, budi, make_purchase_order, sales_order_id=so["id"], items=[
            {"description": "expensive", "quantity": 1, "unit_price": 10000000}])
        r = client.get("/reports/financial", headers=budi).json()
        assert dec(r["gross_profit"]) < 0
        assert dec(r["margin_pct"]) < 0

    def test_collected_and_outstanding(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        half = float(dec(so["total"]) / 2)
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": so["id"], "amount": half})
        r = client.get("/reports/financial", headers=budi).json()
        assert dec(r["collected"]) == dec(half)
        assert dec(r["outstanding"]) == dec(so["total"]) - dec(half)

    def test_outstanding_clears_on_full_payment(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        client.post("/receipts", headers=budi,
                    json={"sales_order_id": so["id"], "amount": float(so["total"])})
        r = client.get("/reports/financial", headers=budi).json()
        assert dec(r["outstanding"]) == dec("0.00")

    def test_monthly_rows_are_self_consistent(self, client, budi, make_sales_order,
                                              make_purchase_order):
        so = live_order(client, budi, make_sales_order)
        live_po(client, budi, make_purchase_order, sales_order_id=so["id"])
        r = client.get("/reports/financial", headers=budi).json()
        for row in r["by_period"]:
            assert dec(row["gross_profit"]) == dec(row["revenue"]) - dec(row["cost"])

    def test_orders_are_listed_newest_first(self, client, budi, make_sales_order):
        for _ in range(3):
            live_order(client, budi, make_sales_order)
        r = client.get("/reports/financial", headers=budi).json()
        dates = [row["order_date"] for row in r["by_order"]]
        assert dates == sorted(dates, reverse=True)

    def test_defaults_to_the_last_twelve_months(self, client, budi):
        r = client.get("/reports/financial", headers=budi).json()
        span = date.fromisoformat(r["date_to"]) - date.fromisoformat(r["date_from"])
        assert span.days == 365


class TestFinancialReportIsScopedToTheCaller:
    """Revenue, cost and margin across the whole business is the admin's
    view. A normal user sees the orders they raised and nothing else."""

    def test_a_user_sees_only_their_own_revenue(self, client, budi, sari,
                                                make_sales_order):
        mine = live_order(client, budi, make_sales_order)
        live_order(client, sari, make_sales_order)
        r = client.get("/reports/financial", headers=budi).json()
        assert dec(r["revenue"]) == dec(mine["netto"])

    def test_an_admin_sees_everyones_revenue(self, client, budi, sari, admin,
                                             make_sales_order):
        a = live_order(client, budi, make_sales_order)
        b = live_order(client, sari, make_sales_order)
        r = client.get("/reports/financial", headers=admin).json()
        assert dec(r["revenue"]) == dec(a["netto"]) + dec(b["netto"])

    def test_a_users_invoice_list_excludes_colleagues_orders(
            self, client, budi, sari, make_sales_order):
        mine = live_order(client, budi, make_sales_order)
        theirs = live_order(client, sari, make_sales_order)
        rows = client.get("/reports/financial", headers=budi).json()["by_order"]
        ids = [row["sales_order_id"] for row in rows]
        assert ids == [mine["id"]]
        assert theirs["id"] not in ids

    def test_a_user_does_not_see_a_colleagues_margin(self, client, sari, budi,
                                                     make_sales_order,
                                                     make_purchase_order):
        so = live_order(client, sari, make_sales_order)
        live_po(client, sari, make_purchase_order, sales_order_id=so["id"])
        r = client.get("/reports/financial", headers=budi).json()
        assert dec(r["revenue"]) == dec("0.00")
        assert dec(r["cost"]) == dec("0.00")

    def test_collected_and_outstanding_are_scoped_too(self, client, budi, sari,
                                                      confirmed_order):
        """The money columns must follow the same rule as the revenue ones."""
        theirs = confirmed_order(sari)
        client.post("/receipts", headers=sari,
                    json={"sales_order_id": theirs["id"], "amount": 500000})
        r = client.get("/reports/financial", headers=budi).json()
        assert dec(r["collected"]) == dec("0.00")
        assert dec(r["outstanding"]) == dec("0.00")

    def test_asking_for_a_colleague_by_name_is_refused(self, client, budi, users):
        response = client.get(f"/reports/financial?created_by={users['sari']}",
                              headers=budi)
        assert response.status_code == 403
        assert "your own figures" in response.json()["detail"]

    def test_asking_for_your_own_id_is_fine(self, client, budi, users):
        response = client.get(f"/reports/financial?created_by={users['budi']}",
                              headers=budi)
        assert response.status_code == 200

    def test_an_admin_may_still_filter_to_one_salesperson(self, client, budi, sari,
                                                          admin, make_sales_order):
        mine = live_order(client, budi, make_sales_order)
        live_order(client, sari, make_sales_order)
        r = client.get(f"/reports/financial?created_by={mine['created_by']}",
                       headers=admin).json()
        assert dec(r["revenue"]) == dec(mine["netto"])

    def test_the_payload_says_whose_figures_these_are(self, client, budi, users):
        r = client.get("/reports/financial", headers=budi).json()
        assert r["scoped_to_user_id"] == users["budi"]
        assert r["scoped_to_user_name"] == "Budi Santoso"
        assert r["is_whole_business"] is False

    def test_an_admins_report_is_labelled_whole_business(self, client, admin):
        r = client.get("/reports/financial", headers=admin).json()
        assert r["is_whole_business"] is True
        assert r["scoped_to_user_id"] is None

    def test_an_admin_filtering_is_not_labelled_whole_business(self, client, admin,
                                                               users):
        r = client.get(f"/reports/financial?created_by={users['budi']}",
                       headers=admin).json()
        assert r["is_whole_business"] is False
        assert r["scoped_to_user_name"] == "Budi Santoso"
