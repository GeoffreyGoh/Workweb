"""Closing a receivable (closing pembayaran piutang) and the customer statement.

Two rules carry the money risk here and both are tested from several angles:
a receivable cannot be closed while anything is still owed, and voiding a
payment must put a closed receivable back on the outstanding list rather than
letting the debt vanish.
"""

from datetime import date, timedelta

from conftest import dec


def pay(client, headers, so, amount=None):
    """Record a payment; defaults to settling the invoice in full."""
    response = client.post("/receipts", headers=headers, json={
        "sales_order_id": so["id"],
        "amount": float(amount if amount is not None else dec(so["total"])),
    })
    assert response.status_code == 201, response.text
    return response.json()


def settled(client, headers, confirmed_order, **kwargs):
    so = confirmed_order(headers, **kwargs)
    pay(client, headers, so)
    return so


class TestClosing:
    def test_a_settled_invoice_can_be_closed(self, client, budi, confirmed_order):
        so = settled(client, budi, confirmed_order)
        closed = client.post(f"/sales-orders/{so['id']}/close-receivable",
                             headers=budi, json={}).json()
        assert closed["is_closed"] is True
        assert closed["receivable_closed_at"] == f"{date.today()}"
        assert closed["receivable_closed_by_name"] == "Budi Santoso"

    def test_closing_while_money_is_owed_is_refused(self, client, budi,
                                                    confirmed_order):
        so = confirmed_order(budi)
        pay(client, budi, so, dec(so["total"]) / 2)
        response = client.post(f"/sales-orders/{so['id']}/close-receivable",
                               headers=budi, json={})
        assert response.status_code == 409
        assert "still outstanding" in response.json()["detail"]

    def test_an_unpaid_invoice_cannot_be_closed(self, client, budi, confirmed_order):
        so = confirmed_order(budi)
        response = client.post(f"/sales-orders/{so['id']}/close-receivable",
                               headers=budi, json={})
        assert response.status_code == 409
        assert so["so_no"] in response.json()["detail"]

    def test_the_closing_date_can_be_backdated(self, client, budi, confirmed_order):
        """The money often lands before anyone gets to the screen."""
        so = settled(client, budi, confirmed_order)
        yesterday = date.today() - timedelta(days=1)
        closed = client.post(f"/sales-orders/{so['id']}/close-receivable",
                             headers=budi,
                             json={"closed_at": f"{yesterday}"}).json()
        assert closed["receivable_closed_at"] == f"{yesterday}"

    def test_the_note_is_kept(self, client, budi, confirmed_order):
        so = settled(client, budi, confirmed_order)
        closed = client.post(f"/sales-orders/{so['id']}/close-receivable",
                             headers=budi,
                             json={"note": "Transfer BCA, checked by finance"}).json()
        assert closed["receivable_close_note"] == "Transfer BCA, checked by finance"

    def test_closing_twice_is_refused(self, client, budi, confirmed_order):
        so = settled(client, budi, confirmed_order)
        client.post(f"/sales-orders/{so['id']}/close-receivable", headers=budi, json={})
        response = client.post(f"/sales-orders/{so['id']}/close-receivable",
                               headers=budi, json={})
        assert response.status_code == 409
        assert "already closed" in response.json()["detail"]

    def test_a_cancelled_invoice_has_no_receivable(self, client, budi,
                                                   make_sales_order):
        so = make_sales_order(budi)
        client.patch(f"/sales-orders/{so['id']}/status",
                     json={"status": "cancelled"}, headers=budi)
        response = client.post(f"/sales-orders/{so['id']}/close-receivable",
                               headers=budi, json={})
        assert response.status_code == 409
        assert "cancelled" in response.json()["detail"]

    def test_missing_invoice_is_404(self, client, budi):
        assert client.post("/sales-orders/9999/close-receivable",
                           headers=budi, json={}).status_code == 404

    def test_someone_elses_invoice_is_403(self, client, budi, sari, confirmed_order):
        so = settled(client, budi, confirmed_order)
        assert client.post(f"/sales-orders/{so['id']}/close-receivable",
                           headers=sari, json={}).status_code == 403

    def test_an_admin_may_close_anyones(self, client, budi, admin, confirmed_order):
        so = settled(client, budi, confirmed_order)
        assert client.post(f"/sales-orders/{so['id']}/close-receivable",
                           headers=admin, json={}).status_code == 200


class TestReopening:
    def test_reopening_clears_the_closure(self, client, budi, confirmed_order):
        so = settled(client, budi, confirmed_order)
        client.post(f"/sales-orders/{so['id']}/close-receivable", headers=budi, json={})
        reopened = client.post(f"/sales-orders/{so['id']}/reopen-receivable",
                               headers=budi).json()
        assert reopened["is_closed"] is False
        assert reopened["receivable_closed_at"] is None
        assert reopened["receivable_close_note"] is None

    def test_reopening_one_that_is_not_closed_is_refused(self, client, budi,
                                                         confirmed_order):
        so = confirmed_order(budi)
        response = client.post(f"/sales-orders/{so['id']}/reopen-receivable",
                               headers=budi)
        assert response.status_code == 409
        assert "not closed" in response.json()["detail"]

    def test_voiding_a_payment_reopens_the_receivable(self, client, budi,
                                                      confirmed_order):
        """Otherwise voiding a receipt would quietly erase the debt."""
        so = confirmed_order(budi)
        receipt = pay(client, budi, so)
        client.post(f"/sales-orders/{so['id']}/close-receivable", headers=budi, json={})

        assert client.delete(f"/receipts/{receipt['id']}",
                             headers=budi).status_code == 204
        after = client.get(f"/sales-orders/{so['id']}", headers=budi).json()
        assert after["is_closed"] is False
        assert dec(after["balance_due"]) == dec(so["total"])

    def test_voiding_one_of_several_payments_still_reopens(self, client, budi,
                                                           confirmed_order):
        so = confirmed_order(budi)
        half = dec(so["total"]) / 2
        first = pay(client, budi, so, half)
        pay(client, budi, so, dec(so["total"]) - half)
        client.post(f"/sales-orders/{so['id']}/close-receivable", headers=budi, json={})

        client.delete(f"/receipts/{first['id']}", headers=budi)
        after = client.get(f"/sales-orders/{so['id']}", headers=budi).json()
        assert after["is_closed"] is False


class TestReceivableFilter:
    def test_open_and_closed_split_the_list(self, client, budi, confirmed_order):
        open_so = confirmed_order(budi)
        closed_so = settled(client, budi, confirmed_order)
        client.post(f"/sales-orders/{closed_so['id']}/close-receivable",
                    headers=budi, json={})

        open_ids = [r["id"] for r in
                    client.get("/sales-orders?receivable=open", headers=budi).json()]
        closed_ids = [r["id"] for r in
                      client.get("/sales-orders?receivable=closed", headers=budi).json()]

        assert open_so["id"] in open_ids and closed_so["id"] not in open_ids
        assert closed_so["id"] in closed_ids and open_so["id"] not in closed_ids

    def test_no_filter_returns_both(self, client, budi, confirmed_order):
        open_so = confirmed_order(budi)
        closed_so = settled(client, budi, confirmed_order)
        client.post(f"/sales-orders/{closed_so['id']}/close-receivable",
                    headers=budi, json={})
        ids = [r["id"] for r in client.get("/sales-orders", headers=budi).json()]
        assert {open_so["id"], closed_so["id"]} <= set(ids)


class TestStatement:
    def url(self, customer, extra=""):
        return f"/reports/statement/{customer.id}{extra}"

    def test_totals_add_up(self, client, budi, customer, confirmed_order):
        first = confirmed_order(budi)
        second = confirmed_order(budi)
        pay(client, budi, first, 1000)

        body = client.get(self.url(customer), headers=budi).json()
        assert dec(body["invoiced"]) == dec(first["total"]) + dec(second["total"])
        assert dec(body["paid"]) == dec("1000.00")
        assert dec(body["outstanding"]) == dec(body["invoiced"]) - dec("1000.00")
        assert body["customer_name"] == customer.name

    def test_open_invoice_count_ignores_settled_ones(self, client, budi, customer,
                                                     confirmed_order):
        confirmed_order(budi)
        settled(client, budi, confirmed_order)
        body = client.get(self.url(customer), headers=budi).json()
        assert body["open_invoice_count"] == 1

    def test_payments_carry_a_running_balance(self, client, budi, customer,
                                              confirmed_order):
        so = confirmed_order(budi)
        pay(client, budi, so, 1000)
        pay(client, budi, so, 2500)

        body = client.get(self.url(customer), headers=budi).json()
        balances = [dec(p["running_balance"]) for p in body["payments"]]
        assert balances == [dec(so["total"]) - dec("1000.00"),
                            dec(so["total"]) - dec("3500.00")]

    def test_a_closed_receivable_still_shows_but_stops_counting(
            self, client, budi, customer, confirmed_order):
        so = settled(client, budi, confirmed_order)
        client.post(f"/sales-orders/{so['id']}/close-receivable", headers=budi, json={})

        body = client.get(self.url(customer), headers=budi).json()
        row = next(i for i in body["invoices"] if i["id"] == so["id"])
        assert row["is_closed"] is True
        assert dec(body["outstanding"]) == dec("0.00")

    def test_open_only_hides_what_is_settled(self, client, budi, customer,
                                             confirmed_order):
        owing = confirmed_order(budi)
        paid_off = settled(client, budi, confirmed_order)

        body = client.get(self.url(customer, "?open_only=true"), headers=budi).json()
        ids = [i["id"] for i in body["invoices"]]
        assert ids == [owing["id"]]
        assert paid_off["id"] not in ids

    def test_drafts_and_cancellations_are_not_a_debt(self, client, budi, customer,
                                                     make_sales_order,
                                                     confirmed_order):
        live = confirmed_order(budi)
        make_sales_order(budi)                       # still draft
        scrapped = make_sales_order(budi)
        client.patch(f"/sales-orders/{scrapped['id']}/status",
                     json={"status": "cancelled"}, headers=budi)

        body = client.get(self.url(customer), headers=budi).json()
        assert [i["id"] for i in body["invoices"]] == [live["id"]]
        assert dec(body["invoiced"]) == dec(live["total"])

    def test_another_customers_invoices_stay_out(self, client, budi, customer,
                                                 customer2, confirmed_order):
        mine = confirmed_order(budi)
        confirmed_order(budi, customer_id=customer2.id)
        body = client.get(self.url(customer), headers=budi).json()
        assert [i["id"] for i in body["invoices"]] == [mine["id"]]

    def test_the_company_filter_narrows_both_sides(self, client, budi, customer,
                                                   companies, confirmed_order):
        gb = confirmed_order(budi)
        mj = confirmed_order(budi, company_id=companies["MJ"].id)
        pay(client, budi, mj, 500)

        body = client.get(self.url(customer, f"?company_id={companies['GB'].id}"),
                          headers=budi).json()
        assert [i["id"] for i in body["invoices"]] == [gb["id"]]
        assert body["payments"] == []
        assert body["company_name"] == "PT Graha Blinds Nusantara"

    def test_the_date_window_is_respected(self, client, budi, customer, db,
                                          confirmed_order):
        import models
        old = confirmed_order(budi)
        db.query(models.SalesOrder).filter(models.SalesOrder.id == old["id"]).update(
            {"order_date": date.today() - timedelta(days=400)})
        db.commit()

        body = client.get(self.url(customer), headers=budi).json()
        assert [i["id"] for i in body["invoices"]] == []

    def test_unknown_customer_is_404(self, client, budi):
        assert client.get("/reports/statement/9999", headers=budi).status_code == 404

    def test_it_needs_a_login(self, client, customer):
        assert client.get(self.url(customer)).status_code == 401
