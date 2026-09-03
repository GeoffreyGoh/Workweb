"""PDF generation, and the rupiah-in-words helper printed on receipts."""

import base64
import re
import zlib
from decimal import Decimal

import pytest

import pdf


def _decode_stream(raw: bytes) -> bytes:
    """Undo whatever filters ReportLab applied to a content stream.

    It writes `/Filter [ /ASCII85Decode /FlateDecode ]`, so the bytes are
    ASCII85 first and Flate underneath. Fall back gracefully so the helper
    keeps working if compression settings change.
    """
    candidate = raw.strip()
    if candidate.endswith(b"~>"):
        candidate = candidate[:-2]
    try:
        candidate = base64.a85decode(candidate)
    except ValueError:
        candidate = raw
    try:
        return zlib.decompress(candidate)
    except zlib.error:
        return candidate


def pdf_text(data: bytes) -> str:
    """Pull readable text out of a ReportLab PDF.

    Text is drawn as `(string) Tj` or as `[(a) -1 (b)] TJ` arrays.
    """
    chunks = [
        _decode_stream(match.group(1))
        for match in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S)
    ]
    blob = b"\n".join(chunks).decode("latin-1")

    pieces = []
    for match in re.finditer(r"\[(.*?)\]\s*TJ|\((.*?)\)\s*Tj", blob, re.S):
        if match.group(1) is not None:            # TJ array
            pieces.append("".join(re.findall(r"\((.*?)\)", match.group(1), re.S)))
        else:                                      # simple Tj
            pieces.append(match.group(2))

    # PDF string escapes: \( \) \\ and octal for non-ASCII
    text = " ".join(pieces)
    return text.replace(r"\(", "(").replace(r"\)", ")").replace("\\\\", "\\")


# ------------------------------------------------------------------ helpers
class TestWholeRupiah:
    @pytest.mark.parametrize("value,expected", [
        ("0", 0), ("0.4", 0), ("0.5", 1), ("1.49", 1), ("1.5", 2),
        ("2559271.50", 2559272), ("12345.50", 12346), ("2.5", 3), ("3.5", 4),
    ])
    def test_rounds_half_away_from_zero(self, value, expected):
        # 2.5 -> 3 and 3.5 -> 4 prove this is not Python's default half-even
        assert pdf.whole_rupiah(value) == expected

    def test_figure_and_words_always_agree(self):
        for value in ["2559271.50", "12345.50", "0.5", "1500000", "999999.99"]:
            figure = pdf.fmt_money(value, "IDR").replace(",", "")
            words_from = pdf.whole_rupiah(value)
            assert figure == str(words_from)

    def test_non_idr_keeps_two_decimals(self):
        assert pdf.fmt_money("1234.5", "USD") == "1,234.50"

    def test_idr_has_no_decimals(self):
        assert pdf.fmt_money("1234.5", "IDR") == "1,235"


class TestTerbilang:
    @pytest.mark.parametrize("number,expected", [
        (0, "nol"),
        (1, "satu"),
        (10, "sepuluh"),
        (11, "sebelas"),
        (12, "dua belas"),
        (19, "sembilan belas"),
        (20, "dua puluh"),
        (21, "dua puluh satu"),
        (100, "seratus"),
        (101, "seratus satu"),
        (110, "seratus sepuluh"),
        (200, "dua ratus"),
        (1000, "seribu"),
        (1001, "seribu satu"),
        (1100, "seribu seratus"),
        (2000, "dua ribu"),
        (15000, "lima belas ribu"),
        (100000, "seratus ribu"),
        (1000000, "satu juta"),
        (1500000, "satu juta lima ratus ribu"),
        (1000000000, "satu miliar"),
        (1250000000, "satu miliar dua ratus lima puluh juta"),
    ])
    def test_known_values(self, number, expected):
        assert pdf.terbilang(number) == expected

    def test_round_numbers_have_no_stray_nol(self):
        for number in (1000, 1500000, 2000000, 15000, 100000):
            assert "nol" not in pdf.terbilang(number)

    def test_no_double_spaces(self):
        for number in (1500000, 1000000000, 1001, 2559272):
            assert "  " not in pdf.terbilang(number)

    def test_negative(self):
        assert pdf.terbilang(-5).startswith("minus ")

    def test_handles_trillions(self):
        assert "triliun" in pdf.terbilang(2_000_000_000_000)


# ---------------------------------------------------------------- documents
@pytest.fixture()
def full_chain(client, budi, products, customer, make_quotation, make_purchase_order):
    """One of every document, all hanging off a single sales order."""
    q = make_quotation(budi)
    so = client.post("/sales-orders", headers=budi, json={
        "customer_id": customer.id, "discount_percent": 35, "ppn_percent": 11,
        "items": [
            {"product_id": products["sqm"].id, "quantity": 3,
             "width_cm": 200, "height_cm": 100},
            {"product_id": products["unit"].id, "quantity": 4},
        ]}).json()
    client.patch(f"/sales-orders/{so['id']}/status",
                 json={"status": "confirmed"}, headers=budi)
    po = make_purchase_order(budi, sales_order_id=so["id"])
    receipt = client.post("/receipts", headers=budi, json={
        "sales_order_id": so["id"], "amount": float(so["total"]),
        "payment_method": "transfer", "reference": "BCA/123"}).json()
    note = client.post(f"/delivery-notes/from-sales-order/{so['id']}",
                       headers=budi).json()
    client.put(f"/delivery-notes/{note['id']}", headers=budi, json={
        "vehicle_no": "B 1234 XYZ", "driver_name": "Pak Joko"})
    note = client.get(f"/delivery-notes/{note['id']}", headers=budi).json()
    return {"quotation": q, "sales_order": so, "purchase_order": po,
            "receipt": receipt, "delivery_note": note}


PATHS = {
    "quotation": "/documents/quotations/{id}.pdf",
    "sales_order": "/documents/sales-orders/{id}.pdf",
    "purchase_order": "/documents/purchase-orders/{id}.pdf",
    "receipt": "/documents/receipts/{id}.pdf",
    "delivery_note": "/documents/delivery-notes/{id}.pdf",
}


class TestDocumentEndpoints:
    @pytest.mark.parametrize("kind", list(PATHS))
    def test_returns_a_real_pdf(self, client, budi, full_chain, kind):
        path = PATHS[kind].format(id=full_chain[kind]["id"])
        response = client.get(path, headers=budi)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")
        assert response.content.rstrip().endswith(b"%%EOF")
        assert len(response.content) > 1000

    @pytest.mark.parametrize("kind", list(PATHS))
    def test_previews_inline_by_default(self, client, budi, full_chain, kind):
        path = PATHS[kind].format(id=full_chain[kind]["id"])
        disposition = client.get(path, headers=budi).headers["content-disposition"]
        assert disposition.startswith("inline;")

    @pytest.mark.parametrize("kind", list(PATHS))
    def test_download_flag_attaches(self, client, budi, full_chain, kind):
        path = PATHS[kind].format(id=full_chain[kind]["id"]) + "?download=1"
        disposition = client.get(path, headers=budi).headers["content-disposition"]
        assert disposition.startswith("attachment;")

    def test_filename_is_the_document_number(self, client, budi, full_chain):
        response = client.get(
            PATHS["quotation"].format(id=full_chain["quotation"]["id"]), headers=budi)
        assert full_chain["quotation"]["quotation_no"] in \
            response.headers["content-disposition"]

    @pytest.mark.parametrize("kind", list(PATHS))
    def test_requires_authentication(self, client, full_chain, kind):
        path = PATHS[kind].format(id=full_chain[kind]["id"])
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("kind", list(PATHS))
    def test_missing_document_is_404(self, client, budi, full_chain, kind):
        assert client.get(PATHS[kind].format(id=9999), headers=budi).status_code == 404

    def test_a_quotation_with_no_lines_is_refused(self, client, budi, customer):
        empty = client.post("/quotations", headers=budi,
                            json={"customer_id": customer.id, "items": []}).json()
        response = client.get(PATHS["quotation"].format(id=empty["id"]), headers=budi)
        assert response.status_code == 409
        assert "no line items" in response.json()["detail"]

    def test_anyone_may_print_anyones_document(self, client, sari, full_chain):
        path = PATHS["quotation"].format(id=full_chain["quotation"]["id"])
        assert client.get(path, headers=sari).status_code == 200


class TestQuotationContent:
    @pytest.fixture()
    def text(self, client, budi, full_chain):
        response = client.get(
            PATHS["quotation"].format(id=full_chain["quotation"]["id"]), headers=budi)
        return pdf_text(response.content)

    def test_carries_the_issuing_company(self, text, companies):
        """Three entities share the system, so the letterhead must come from
        the document's own company, not a global constant."""
        assert companies["GB"].name in text

    def test_shows_the_quotation_number(self, text, full_chain):
        assert full_chain["quotation"]["quotation_no"] in text

    def test_titled_as_a_sales_quotation(self, text):
        assert "SALES QUOTATION" in text

    def test_names_the_customer(self, text, customer):
        assert customer.name in text

    def test_lists_the_products(self, text):
        assert "Roller Blind" in text
        assert "RB-SQM" in text

    def test_shows_dimensions(self, text):
        assert "200 x 100" in text

    def test_shows_the_totals(self, text):
        assert "Sub Total" in text
        assert "TOTAL" in text
        assert "3,100,000" in text      # subtotal
        assert "2,236,650" in text      # grand total

    def test_labels_the_discount_percentage(self, text):
        assert "Discount (35%)" in text

    def test_includes_terms_and_bank_details(self, text):
        from company import COMPANY
        assert "TERMS" in text
        assert COMPANY["bank_account"] in text

    def test_has_a_signature_block(self, text):
        assert "Customer Acceptance" in text


class TestInvoiceContent:
    """The document the customer is billed on - it must say Invoice, not
    Sales Order, and it must carry an INV- number."""

    @pytest.fixture()
    def text(self, client, budi, full_chain):
        response = client.get(
            PATHS["sales_order"].format(id=full_chain["sales_order"]["id"]),
            headers=budi)
        return pdf_text(response.content)

    def test_titled_as_an_invoice(self, text):
        assert "INVOICE" in text
        assert "SALES ORDER" not in text

    def test_shows_the_invoice_number(self, text, full_chain):
        so_no = full_chain["sales_order"]["so_no"]
        assert so_no.startswith("INV-")
        assert so_no in text

    def test_carries_the_issuing_company(self, text, companies):
        assert companies["GB"].name in text

    def test_names_the_customer(self, text, customer):
        assert customer.name in text

    def test_shows_the_totals(self, text):
        assert "TOTAL" in text


class TestReceiptContent:
    @pytest.fixture()
    def text(self, client, budi, full_chain):
        response = client.get(
            PATHS["receipt"].format(id=full_chain["receipt"]["id"]), headers=budi)
        return pdf_text(response.content)

    def test_titled_as_a_receipt(self, text):
        assert "RECEIPT / KWITANSI" in text

    def test_shows_the_receipt_number(self, text, full_chain):
        assert full_chain["receipt"]["receipt_no"] in text

    def test_references_the_sales_order(self, text, full_chain):
        assert full_chain["sales_order"]["so_no"] in text

    def test_spells_out_the_amount(self, text):
        assert "Terbilang" in text
        assert "rupiah" in text

    def test_words_match_the_figure(self, client, budi, full_chain):
        """The number printed and the number spelled out must be the same."""
        amount = Decimal(full_chain["receipt"]["amount"])
        response = client.get(
            PATHS["receipt"].format(id=full_chain["receipt"]["id"]), headers=budi)
        text = pdf_text(response.content)
        assert pdf.fmt_money(amount, "IDR") in text
        assert pdf.terbilang(pdf.whole_rupiah(amount)) in text

    def test_shows_the_running_balance(self, text):
        assert "Balance Due" in text
        assert "Paid to date" in text


class TestPurchaseOrderContent:
    @pytest.fixture()
    def text(self, client, budi, full_chain):
        response = client.get(
            PATHS["purchase_order"].format(id=full_chain["purchase_order"]["id"]),
            headers=budi)
        return pdf_text(response.content)

    def test_titled_as_a_purchase_order(self, text):
        assert "PURCHASE ORDER" in text

    def test_names_the_supplier(self, text, supplier):
        assert supplier.name in text

    def test_lists_the_materials(self, text):
        assert "Fabric roll" in text

    def test_delivers_to_our_own_address(self, text, companies):
        assert companies["GB"].address in text


class TestDeliveryNoteContent:
    @pytest.fixture()
    def text(self, client, budi, full_chain):
        response = client.get(
            PATHS["delivery_note"].format(id=full_chain["delivery_note"]["id"]),
            headers=budi)
        return pdf_text(response.content)

    def test_titled_surat_jalan(self, text):
        assert "SURAT JALAN" in text

    def test_shows_its_own_number(self, text, full_chain):
        assert full_chain["delivery_note"]["sj_no"] in text

    def test_references_the_sales_order(self, text, full_chain):
        assert full_chain["sales_order"]["so_no"] in text

    def test_shows_where_it_is_going(self, text, customer):
        assert customer.name in text

    def test_lists_the_goods(self, text):
        assert "Roller Blind" in text
        assert "RB-SQM" in text

    def test_shows_sizes_for_the_installer(self, text):
        assert "200 x 100" in text

    def test_shows_quantities_and_the_total(self, text):
        assert "Total Barang" in text

    def test_shows_the_vehicle_and_driver(self, text):
        assert "B 1234 XYZ" in text
        assert "Pak Joko" in text

    def test_has_a_three_way_signature_block(self, text):
        assert "Pengemudi" in text      # driver
        assert "Penerima" in text       # recipient
        assert "Hormat kami" in text    # sender

    def test_signature_labels_render_as_markup_not_literal_tags(self, text):
        assert "<br/>" not in text
        assert "Sender" in text and "Driver" in text and "Received by" in text

    def test_carries_the_goods_received_wording(self, text):
        assert "Barang telah diterima" in text

    def test_never_shows_prices(self, client, budi, full_chain):
        """A Surat Jalan travels with the goods - the driver and the person
        signing for them must not be handed the customer's pricing."""
        response = client.get(
            PATHS["delivery_note"].format(id=full_chain["delivery_note"]["id"]),
            headers=budi)
        text = pdf_text(response.content)

        so = full_chain["sales_order"]
        for amount in (so["subtotal"], so["netto"], so["total"], so["discount_amount"]):
            formatted = pdf.fmt_money(amount, "IDR")
            assert formatted not in text, f"{formatted} leaked onto the Surat Jalan"

        for word in ("Sub Total", "PPN", "Discount", "Harga", "TOTAL"):
            assert word not in text, f"'{word}' should not appear on a Surat Jalan"


class TestEscaping:
    def test_ampersands_in_names_do_not_corrupt_the_pdf(self, client, budi, db,
                                                        make_quotation):
        """ReportLab paragraphs are mini-HTML - unescaped & or < would throw."""
        import models
        db.add(models.Customer(code="C-AMP", name="Smith & Sons <Interiors>"))
        db.commit()
        row = db.query(models.Customer).filter(models.Customer.code == "C-AMP").first()

        q = make_quotation(budi, customer_id=row.id)
        response = client.get(PATHS["quotation"].format(id=q["id"]), headers=budi)
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF-")


class TestLongDocuments:
    def test_many_lines_paginate_without_error(self, client, budi, customer, products):
        items = [{"product_id": products["unit"].id, "quantity": 1,
                  "description": f"Line item number {n}"} for n in range(60)]
        q = client.post("/quotations", headers=budi,
                        json={"customer_id": customer.id, "items": items}).json()
        response = client.get(PATHS["quotation"].format(id=q["id"]), headers=budi)
        assert response.status_code == 200
        assert response.content.count(b"/Type /Page") > 1  # spilled onto page 2
