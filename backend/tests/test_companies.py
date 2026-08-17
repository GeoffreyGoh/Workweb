"""Three entities sharing one catalogue.

What is shared: products, customers, suppliers, staff.
What is not: the letterhead, the bank account, and the document numbering.
"""

from datetime import date

import pytest

import models
from conftest import dec


class TestCompanyMaster:
    def test_everyone_can_read_the_list(self, client, budi, companies):
        rows = client.get("/companies", headers=budi).json()
        assert {c["code"] for c in rows} == {"GB", "MJ"}

    def test_inactive_companies_are_hidden(self, client, admin, companies, db):
        companies["MJ"].is_active = False
        db.commit()
        assert {c["code"] for c in client.get("/companies", headers=admin).json()} == {"GB"}
        assert len(client.get("/companies?active_only=false", headers=admin).json()) == 2

    def test_only_an_admin_may_change_a_letterhead(self, client, budi, companies):
        """It appears on every document that entity has ever printed."""
        response = client.put(f"/companies/{companies['GB'].id}", headers=budi,
                              json={"name": "Renamed By A User"})
        assert response.status_code == 403

    def test_admin_can_update(self, client, admin, companies):
        updated = client.put(f"/companies/{companies['GB'].id}", headers=admin,
                             json={"bank_account": "5555555555"}).json()
        assert updated["bank_account"] == "5555555555"
        assert updated["name"] == "PT Graha Blinds Nusantara"

    def test_duplicate_code_is_409(self, client, admin, companies):
        response = client.post("/companies", headers=admin,
                               json={"code": "GB", "name": "Clash"})
        assert response.status_code == 409

    def test_missing_company_is_404(self, client, budi):
        assert client.get("/companies/9999", headers=budi).status_code == 404


class TestChoosingTheCompany:
    def test_defaults_to_the_users_own_company(self, client, budi, customer,
                                               products, companies):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]}).json()
        assert q["company_id"] == companies["GB"].id
        assert q["company_code"] == "GB"

    def test_an_explicit_choice_wins(self, client, budi, customer, products,
                                     companies):
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "company_id": companies["MJ"].id,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]}).json()
        assert q["company_code"] == "MJ"
        assert q["company_name"] == "PT Mitra Jendela Indah"

    def test_unknown_company_is_rejected(self, client, budi, customer, products):
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "company_id": 9999,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 422
        assert "company" in response.json()["detail"].lower()

    def test_an_inactive_company_cannot_issue(self, client, budi, customer,
                                              products, companies, db):
        companies["MJ"].is_active = False
        db.commit()
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id, "company_id": companies["MJ"].id,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 422
        assert "no longer active" in response.json()["detail"]

    def test_user_with_no_default_must_choose(self, client, budi, customer,
                                              products, users, db):
        db.query(models.User).filter(models.User.username == "budi").update(
            {"default_company_id": None})
        db.commit()
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 422
        assert "Choose which company" in response.json()["detail"]

    def test_single_company_install_needs_no_choice(self, client, budi, customer,
                                                    products, companies, users, db):
        """A one-entity business should never see a company picker."""
        db.query(models.User).update({"default_company_id": None})
        companies["MJ"].is_active = False
        db.commit()
        response = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 201
        assert response.json()["company_code"] == "GB"

    def test_the_company_cannot_be_changed_after_issue(self, client, budi, customer,
                                                       products, companies):
        """The number encodes the company, so reassigning would break it."""
        q = client.post("/quotations", headers=budi, json={
            "customer_id": customer.id,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]}).json()
        response = client.put(f"/quotations/{q['id']}", headers=budi, json={
            "customer_id": customer.id, "company_id": companies["MJ"].id,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]})
        assert response.status_code == 409
        assert "Create a new quotation" in response.json()["detail"]


class TestNumberingIsPerCompany:
    def make(self, client, headers, customer, products, company_id=None):
        payload = {"customer_id": customer.id,
                   "items": [{"product_id": products["unit"].id, "quantity": 1}]}
        if company_id:
            payload["company_id"] = company_id
        return client.post("/quotations", headers=headers, json=payload).json()

    def test_number_carries_the_company_code(self, client, budi, customer, products):
        q = self.make(client, budi, customer, products)
        assert q["quotation_no"] == f"Q-GB-{date.today():%Y%m}-001"

    def test_each_company_counts_from_one(self, client, budi, customer, products,
                                          companies):
        first_gb = self.make(client, budi, customer, products)
        first_mj = self.make(client, budi, customer, products, companies["MJ"].id)
        second_gb = self.make(client, budi, customer, products)

        month = f"{date.today():%Y%m}"
        assert first_gb["quotation_no"] == f"Q-GB-{month}-001"
        assert first_mj["quotation_no"] == f"Q-MJ-{month}-001"
        assert second_gb["quotation_no"] == f"Q-GB-{month}-002"

    def test_one_companys_documents_do_not_advance_anothers(self, client, budi,
                                                            customer, products,
                                                            companies):
        for _ in range(5):
            self.make(client, budi, customer, products)
        mj = self.make(client, budi, customer, products, companies["MJ"].id)
        assert mj["quotation_no"].endswith("-001")

    def test_downstream_documents_inherit_the_code(self, client, budi, customer,
                                                   products, companies):
        q = self.make(client, budi, customer, products, companies["MJ"].id)
        client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"},
                     headers=budi)
        so = client.post(f"/sales-orders/from-quotation/{q['id']}", headers=budi).json()
        assert so["company_code"] == "MJ"
        assert so["so_no"].startswith("SO-MJ-")

        client.patch(f"/sales-orders/{so['id']}/status", json={"status": "confirmed"},
                     headers=budi)
        note = client.post(f"/delivery-notes/from-sales-order/{so['id']}",
                           headers=budi).json()
        assert note["sj_no"].startswith("SJ-MJ-")

        receipt = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": 1000}).json()
        assert receipt["receipt_no"].startswith("RCP-MJ-")
        assert receipt["company_code"] == "MJ"


class TestFilteringByCompany:
    @pytest.fixture()
    def two_companies_of_work(self, client, budi, customer, products, companies):
        made = {}
        for code in ("GB", "MJ"):
            q = client.post("/quotations", headers=budi, json={
                "customer_id": customer.id, "company_id": companies[code].id,
                "items": [{"product_id": products["unit"].id, "quantity": 2}]}).json()
            client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"},
                         headers=budi)
            so = client.post(f"/sales-orders/from-quotation/{q['id']}",
                             headers=budi).json()
            client.patch(f"/sales-orders/{so['id']}/status",
                         json={"status": "confirmed"}, headers=budi)
            note = client.post(f"/delivery-notes/from-sales-order/{so['id']}",
                               headers=budi).json()
            receipt = client.post("/receipts", headers=budi, json={
                "sales_order_id": so["id"], "amount": 500}).json()
            made[code] = dict(quotation=q, sales_order=so, note=note, receipt=receipt)
        return made

    @pytest.mark.parametrize("path,key", [
        ("/quotations", "quotation_no"),
        ("/sales-orders", "so_no"),
        ("/delivery-notes", "sj_no"),
        ("/receipts", "receipt_no"),
    ])
    def test_every_list_filters_by_company(self, client, budi, companies,
                                           two_companies_of_work, path, key):
        everything = client.get(path, headers=budi).json()
        assert len(everything) == 2

        only_mj = client.get(f"{path}?company_id={companies['MJ'].id}",
                             headers=budi).json()
        assert len(only_mj) == 1
        assert "-MJ-" in only_mj[0][key]

    def test_purchase_orders_filter_by_company(self, client, budi, supplier,
                                               companies):
        for code in ("GB", "MJ"):
            client.post("/purchase-orders", headers=budi, json={
                "supplier_id": supplier.id, "company_id": companies[code].id,
                "items": [{"description": "x", "quantity": 1, "unit_price": 100}]})
        rows = client.get(f"/purchase-orders?company_id={companies['MJ'].id}",
                          headers=budi).json()
        assert len(rows) == 1
        assert rows[0]["company_code"] == "MJ"

    def test_lists_carry_the_company_name(self, client, budi, two_companies_of_work):
        row = client.get("/quotations", headers=budi).json()[0]
        assert row["company_name"] in ("PT Graha Blinds Nusantara",
                                       "PT Mitra Jendela Indah")

    def test_sales_report_filters_by_company(self, client, budi, companies,
                                             two_companies_of_work):
        both = client.get("/reports/sales", headers=budi).json()
        assert both["quotation_count"] == 2

        one = client.get(f"/reports/sales?company_id={companies['MJ'].id}",
                         headers=budi).json()
        assert one["quotation_count"] == 1
        assert one["company_name"] == "PT Mitra Jendela Indah"

    def test_financial_report_filters_by_company(self, client, budi, companies,
                                                 two_companies_of_work):
        both = client.get("/reports/financial", headers=budi).json()
        one = client.get(f"/reports/financial?company_id={companies['GB'].id}",
                         headers=budi).json()
        assert len(one["by_order"]) == 1
        assert dec(one["revenue"]) < dec(both["revenue"])

    def test_schedule_filters_by_company(self, client, budi, companies,
                                         two_companies_of_work):
        board = client.get(
            f"/delivery-notes/schedule/board?company_id={companies['MJ'].id}",
            headers=budi).json()
        stops = [s for day in board["days"] for s in day["stops"]]
        assert stops and all("-MJ-" in s["sj_no"] for s in stops)


class TestLetterheadPerCompany:
    def build(self, client, headers, customer, products, company):
        q = client.post("/quotations", headers=headers, json={
            "customer_id": customer.id, "company_id": company.id,
            "items": [{"product_id": products["unit"].id, "quantity": 1}]}).json()
        return q

    def test_each_document_prints_its_own_company(self, client, budi, customer,
                                                  products, companies):
        from test_pdf import pdf_text

        for code in ("GB", "MJ"):
            q = self.build(client, budi, customer, products, companies[code])
            response = client.get(f"/documents/quotations/{q['id']}.pdf", headers=budi)
            assert response.status_code == 200
            text = pdf_text(response.content)

            mine = companies[code]
            other = companies["MJ" if code == "GB" else "GB"]
            assert mine.name in text
            assert mine.npwp in text
            assert mine.bank_account in text
            # and crucially, not the other entity's details
            assert other.npwp not in text
            assert other.bank_account not in text

    def test_receipt_prints_the_entity_that_was_paid(self, client, budi, customer,
                                                     products, companies):
        from test_pdf import pdf_text

        q = self.build(client, budi, customer, products, companies["MJ"])
        client.patch(f"/quotations/{q['id']}/status", json={"status": "sent"},
                     headers=budi)
        so = client.post(f"/sales-orders/from-quotation/{q['id']}", headers=budi).json()
        client.patch(f"/sales-orders/{so['id']}/status", json={"status": "confirmed"},
                     headers=budi)
        receipt = client.post("/receipts", headers=budi, json={
            "sales_order_id": so["id"], "amount": 1000}).json()

        response = client.get(f"/documents/receipts/{receipt['id']}.pdf", headers=budi)
        text = pdf_text(response.content)
        assert companies["MJ"].name in text
        assert companies["GB"].npwp not in text

    def test_signatory_comes_from_the_company(self, client, budi, customer,
                                              products, companies):
        from test_pdf import pdf_text

        q = self.build(client, budi, customer, products, companies["MJ"])
        response = client.get(f"/documents/quotations/{q['id']}.pdf", headers=budi)
        assert companies["MJ"].signatory in pdf_text(response.content)   # "Direktur"
