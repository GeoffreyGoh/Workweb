"""PDF documents: quotation, invoice, purchase order, receipt.

One shared letterhead and one shared visual language, built with ReportLab
(pure Python - no GTK/Cairo system libraries, so it behaves the same on the
Windows dev machine and the Linux droplet).

Company details and the logo come from company.py.
"""

from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from company import COMPANY as FALLBACK_COMPANY
from company import ASSETS_DIR, QUOTATION_TERMS as FALLBACK_TERMS, logo_file


def identity(document):
    """The letterhead for whichever company issued this document.

    Three entities share the system, so the letterhead cannot be a module
    constant. Falls back to company.py when a document predates the companies
    table, which keeps old documents printable.
    """
    company = getattr(document, "company", None)
    if company is None:
        return dict(FALLBACK_COMPANY), list(FALLBACK_TERMS), logo_file()

    # The company row is authoritative. Merging it over the placeholder
    # defaults would mean that clearing an unknown NPWP silently reprints the
    # sample one - a fake tax number on a real invoice is worse than none.
    details = {
        field: (getattr(company, field, None) or "")
        for field in ("name", "tagline", "address", "city", "phone", "email",
                      "website", "npwp", "bank_name", "bank_account",
                      "bank_holder", "signatory")
    }

    terms = list(FALLBACK_TERMS)
    if company.quotation_terms:
        terms = [t for t in company.quotation_terms.split("|") if t.strip()]

    logo = None
    if company.logo_filename:
        candidate = ASSETS_DIR / company.logo_filename
        if candidate.is_file():
            logo = candidate
    if logo is None:
        # Convention: assets/logo_GB.png, falling back to the shared logo.
        candidate = ASSETS_DIR / f"logo_{company.code}.png"
        logo = candidate if candidate.is_file() else logo_file()

    return details, terms, logo

NAVY = colors.HexColor("#12294A")
BRASS = colors.HexColor("#C08B3E")
GREY = colors.HexColor("#556579")
LIGHT = colors.HexColor("#F5F7FA")
BORDER = colors.HexColor("#D3DAE4")

_base = getSampleStyleSheet()

S = {
    "company": ParagraphStyle("company", parent=_base["Normal"], fontName="Helvetica-Bold",
                              fontSize=15, textColor=NAVY, leading=18),
    "tagline": ParagraphStyle("tagline", parent=_base["Normal"], fontName="Helvetica-Oblique",
                              fontSize=8, textColor=BRASS, leading=11),
    "small": ParagraphStyle("small", parent=_base["Normal"], fontSize=7.5,
                            textColor=GREY, leading=10.5),
    "title": ParagraphStyle("title", parent=_base["Normal"], fontName="Helvetica-Bold",
                            fontSize=15, textColor=NAVY, leading=18),
    "label": ParagraphStyle("label", parent=_base["Normal"], fontName="Helvetica-Bold",
                            fontSize=7, textColor=GREY, leading=10),
    "body": ParagraphStyle("body", parent=_base["Normal"], fontSize=8.5, leading=12),
    "bodyb": ParagraphStyle("bodyb", parent=_base["Normal"], fontName="Helvetica-Bold",
                            fontSize=8.5, leading=12),
    "cell": ParagraphStyle("cell", parent=_base["Normal"], fontSize=8, leading=10.5),
    "cellb": ParagraphStyle("cellb", parent=_base["Normal"], fontName="Helvetica-Bold",
                            fontSize=8, leading=10.5),
    "right": ParagraphStyle("right", parent=_base["Normal"], fontSize=8,
                            leading=10.5, alignment=TA_RIGHT),
    "centre": ParagraphStyle("centre", parent=_base["Normal"], fontSize=8,
                             leading=11, alignment=TA_CENTER),
    "terms": ParagraphStyle("terms", parent=_base["Normal"], fontSize=7.5,
                            textColor=GREY, leading=11),
}


# --------------------------------------------------------------- formatting
def whole_rupiah(value) -> int:
    """Round to whole rupiah, half away from zero.

    Figures and the spelled-out 'terbilang' on a receipt must come from this
    one function - if they disagree by a rupiah the document is disputable.
    Python's own .0f formatting rounds half-to-even, which is not what an
    Indonesian receipt is expected to do.
    """
    return int(Decimal(str(value or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def fmt_money(value, currency="IDR") -> str:
    if currency == "IDR":
        return f"{whole_rupiah(value):,}"
    return f"{Decimal(str(value or 0)):,.2f}"


def fmt_num(value) -> str:
    value = Decimal(str(value or 0))
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return text or "0"


def fmt_date(value) -> str:
    return value.strftime("%d %b %Y") if value else "-"


def _esc(value) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ------------------------------------------------------------- shared parts
def letterhead(company=None, logo=None):
    """Logo (if supplied) plus company details, with a brass rule underneath."""
    company = company or FALLBACK_COMPANY
    logo = logo if logo is not None else logo_file()
    if logo:
        image = Image(str(logo))
        ratio = image.imageWidth / float(image.imageHeight or 1)
        image.drawHeight = 16 * mm
        image.drawWidth = min(16 * mm * ratio, 55 * mm)
        left = image
    else:
        left = Paragraph(_esc(company["name"]), S["company"])

    # Blank fields are omitted rather than printed as empty labels: a line
    # reading "Tel" with no number looks like a fault on a customer document.
    lines = [_esc(company.get("address")), _esc(company.get("city"))]
    contact = []
    if company.get("phone"):
        contact.append(f"Tel {_esc(company['phone'])}")
    if company.get("email"):
        contact.append(_esc(company["email"]))
    if contact:
        lines.append(" &nbsp;|&nbsp; ".join(contact))
    if company.get("npwp"):
        lines.append(f"NPWP {_esc(company['npwp'])}")

    right = Paragraph("<br/>".join(line for line in lines if line), S["small"])

    header = Table([[left, right]], colWidths=[95 * mm, 75 * mm])
    header.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )

    parts = [header]
    if logo and company.get("tagline"):
        parts.append(Paragraph(_esc(company["tagline"]), S["tagline"]))

    rule = Table([[""]], colWidths=[170 * mm], rowHeights=[2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRASS)]))
    parts += [Spacer(1, 4), rule, Spacer(1, 9)]
    return parts


def title_block(title: str, fields):
    """Document title on the left, key/value pairs on the right."""
    rows = [
        [Paragraph(_esc(k), S["label"]), Paragraph(f"<b>{_esc(v)}</b>", S["cell"])]
        for k, v in fields
    ]
    meta = Table(rows, colWidths=[26 * mm, 42 * mm])
    meta.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ])
    )

    block = Table([[Paragraph(title, S["title"]), meta]], colWidths=[102 * mm, 68 * mm])
    block.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    return [block, Spacer(1, 9)]


def party_block(left_title, left_lines, right_title, right_lines):
    """The two grey 'to' panels, e.g. Bill To / Deliver To."""
    def panel(title, lines):
        text = "<br/>".join(_esc(line) for line in lines if line)
        return [
            Paragraph(_esc(title), S["label"]),
            Spacer(1, 2),
            Paragraph(text or "-", S["cell"]),
        ]

    table = Table([[panel(left_title, left_lines), panel(right_title, right_lines)]],
                  colWidths=[85 * mm, 85 * mm])
    table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    return [table, Spacer(1, 10)]


def items_table(headers, rows, col_widths, numeric_from=3):
    table = Table([headers] + rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("ALIGN", (numeric_from, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, BORDER),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    return table


def totals_block(pairs, currency):
    """Right-aligned summary. The last pair is emphasised as the grand total."""
    rows = []
    for i, (label, value) in enumerate(pairs):
        last = i == len(pairs) - 1
        style = S["cellb"] if last else S["cell"]
        rows.append([
            Paragraph(_esc(label), style),
            Paragraph(f"{currency} {value}", ParagraphStyle(
                "v", parent=style, alignment=TA_RIGHT)),
        ])

    table = Table(rows, colWidths=[42 * mm, 38 * mm])
    table.setStyle(
        TableStyle([
            ("LINEABOVE", (0, len(rows) - 1), (-1, len(rows) - 1), 1, NAVY),
            ("TEXTCOLOR", (0, len(rows) - 1), (-1, len(rows) - 1), NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ])
    )

    wrapper = Table([["", table]], colWidths=[90 * mm, 80 * mm])
    wrapper.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return wrapper


def signature_block(left_label, right_label, signatory=None):
    def cell(label, name):
        return [
            Paragraph(_esc(label), S["centre"]),
            Spacer(1, 22 * mm),
            Paragraph(f"( {_esc(name or '_' * 22)} )", S["centre"]),
        ]

    table = Table([[cell(left_label, None), cell(right_label, signatory)]],
                  colWidths=[85 * mm, 85 * mm])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def _footer(canvas, doc, company=None):
    company = company or FALLBACK_COMPANY
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(GREY)
    footer_text = company["name"]
    if company.get("website"):
        footer_text += f" | {company['website']}"
    canvas.drawString(20 * mm, 11 * mm, footer_text)
    canvas.drawRightString(190 * mm, 11 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _render(story, company=None) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=22 * mm,
    )
    def footer(canvas, document):
        _footer(canvas, document, company)

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _dimension_text(line) -> str:
    if line.price_unit == "per_sqm" and line.width_cm and line.height_cm:
        return f"{fmt_num(line.width_cm)} x {fmt_num(line.height_cm)}"
    if line.price_unit == "per_meter" and line.width_cm:
        return f"{fmt_num(line.width_cm)}"
    return "-"


UNIT_LABEL = {"per_sqm": "m2", "per_meter": "m", "per_unit": "pcs"}


# ------------------------------------------------------------------ documents
def _sales_document(doc, title, number_label, number, date_label, date_value,
                    extra_fields, company=None, logo=None):
    """Shared body for quotations and invoices - identical line structure."""
    currency = doc.currency
    story = letterhead(company, logo)

    fields = [(number_label, number), (date_label, fmt_date(date_value))]
    fields += extra_fields
    story += title_block(title, fields)

    customer = doc.customer
    story += party_block(
        "CUSTOMER",
        [
            customer.name if customer else "",
            doc.address,
            f"Tel {doc.phone}" if doc.phone else None,
            doc.email,
            f"NPWP {doc.nik_npwp}" if doc.nik_npwp else None,
        ],
        "DELIVER TO",
        [doc.deliver_to, doc.deliver_address],
    )

    headers = [
        Paragraph("#", S["cellb"]),
        Paragraph("DESCRIPTION", S["cellb"]),
        Paragraph("W x H (cm)", S["cellb"]),
        Paragraph("QTY", S["cellb"]),
        Paragraph("AREA/UNIT", S["cellb"]),
        Paragraph("UNIT PRICE", S["cellb"]),
        Paragraph("AMOUNT", S["cellb"]),
    ]
    for header in headers:
        header.style = ParagraphStyle("h", parent=S["cellb"], fontSize=7,
                                      textColor=colors.white, leading=9)

    rows = []
    for line in doc.items:
        name = f"<b>{_esc(line.product_name)}</b><br/><font size=7 color='#8494A7'>{_esc(line.product_code)}</font>"
        if line.description:
            name += f"<br/><font size=7>{_esc(line.description)}</font>"
        chosen = getattr(line, "component_options", None)
        if chosen:
            name += f"<br/><font size=7 color='#12294A'>{_esc(chosen)}</font>"
        rows.append([
            Paragraph(str(line.line_no), S["cell"]),
            Paragraph(name, S["cell"]),
            Paragraph(_dimension_text(line), S["right"]),
            Paragraph(fmt_num(line.quantity), S["right"]),
            Paragraph(
                f"{fmt_num(line.measure)} {UNIT_LABEL.get(line.price_unit, '')}", S["right"]
            ),
            Paragraph(fmt_money(line.unit_price, currency), S["right"]),
            Paragraph(fmt_money(line.line_total, currency), S["right"]),
        ])

    story.append(items_table(
        headers, rows,
        [8 * mm, 58 * mm, 21 * mm, 14 * mm, 22 * mm, 23 * mm, 24 * mm],
        numeric_from=2,
    ))
    story.append(Spacer(1, 9))

    discount_label = f"Discount ({fmt_num(doc.discount_percent)}%)"
    rows = [
        ("Sub Total", fmt_money(doc.subtotal, currency)),
        (discount_label, f"({fmt_money(doc.discount_amount, currency)})"),
        ("Netto", fmt_money(doc.netto, currency)),
    ]
    installation = Decimal(str(getattr(doc, "installation_cost", 0) or 0))
    if installation > 0:
        rows.append(("Installation", fmt_money(installation, currency)))
    rows += [
        (f"PPN ({fmt_num(doc.ppn_percent)}%)", fmt_money(doc.ppn_amount, currency)),
        ("TOTAL", fmt_money(doc.total, currency)),
    ]
    story.append(totals_block(rows, currency))
    story.append(Spacer(1, 10))

    story += payment_terms_block(doc, currency)
    return story


def payment_terms_block(doc, currency):
    """TOP: how much is due up front and how much on delivery.

    Skipped entirely when no DP was agreed - printing "DP 0%" would look like
    a mistake rather than an absence.
    """
    percent = getattr(doc, "dp_percent", None)
    if percent in (None, ""):
        return []
    percent = Decimal(str(percent))
    total = Decimal(str(doc.total))
    dp = (total * percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    balance = total - dp

    table = Table(
        [[
            Paragraph(
                f"<b>TERMS OF PAYMENT</b><br/>"
                f"Down payment {fmt_num(percent)}% on order confirmation",
                S["cell"],
            ),
            Paragraph(
                f"<b>{currency} {fmt_money(dp, currency)}</b>",
                ParagraphStyle("dp", parent=S["cellb"], alignment=TA_RIGHT, fontSize=10),
            ),
        ], [
            Paragraph("Balance on delivery", S["cell"]),
            Paragraph(
                f"{currency} {fmt_money(balance, currency)}",
                ParagraphStyle("bal", parent=S["cell"], alignment=TA_RIGHT),
            ),
        ]],
        colWidths=[125 * mm, 45 * mm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.6, BRASS),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [table, Spacer(1, 10)]


def quotation_pdf(quotation) -> bytes:
    company, terms_lines, logo = identity(quotation)
    story = _sales_document(
        quotation,
        "SALES QUOTATION",
        "Quotation No", quotation.quotation_no,
        "Date", quotation.quotation_date,
        [
            ("Payment Terms", quotation.payment_terms or "-"),
            ("Surveyor", quotation.surveyor or "-"),
            ("Currency", quotation.currency),
        ],
        company=company,
        logo=logo,
    )

    if quotation.notes:
        story += [
            Paragraph("NOTES", S["label"]),
            Spacer(1, 2),
            Paragraph(_esc(quotation.notes).replace("\n", "<br/>"), S["cell"]),
            Spacer(1, 8),
        ]

    terms = "".join(f"{i}. {_esc(t.strip())}<br/>"
                    for i, t in enumerate(terms_lines, 1) if t.strip())
    story += [
        Paragraph("TERMS &amp; CONDITIONS", S["label"]),
        Spacer(1, 2),
        Paragraph(terms, S["terms"]),
        Spacer(1, 4),
    ]

    if company.get("bank_account"):
        bank = [f"<b>Payment to:</b> {_esc(company['bank_name'])}"]
        bank.append(f"A/C {_esc(company['bank_account'])}")
        if company.get("bank_holder"):
            bank.append(f"a.n. {_esc(company['bank_holder'])}")
        story.append(Paragraph(" &nbsp;|&nbsp; ".join(bank), S["terms"]))
    story.append(Spacer(1, 12))
    story.append(KeepTogether(
        signature_block("Customer Acceptance", f"For and on behalf of {company['name']}",
                        company["signatory"])
    ))
    return _render(story, company)


def sales_order_pdf(so) -> bytes:
    company, _terms, logo = identity(so)
    story = _sales_document(
        so,
        "INVOICE",
        "Invoice No", so.so_no,
        "Invoice Date", so.order_date,
        [
            ("Delivery Date", fmt_date(so.delivery_date)),
            ("Customer PO", so.po_reference or "-"),
            ("Payment Terms", so.payment_terms or "-"),
        ],
        company=company,
        logo=logo,
    )
    if so.quotation:
        story += [
            Paragraph(
                f"Raised from quotation <b>{_esc(so.quotation.quotation_no)}</b>", S["terms"]
            ),
            Spacer(1, 8),
        ]
    if so.notes:
        story += [
            Paragraph("NOTES", S["label"]),
            Spacer(1, 2),
            Paragraph(_esc(so.notes).replace("\n", "<br/>"), S["cell"]),
            Spacer(1, 10),
        ]
    story.append(KeepTogether(
        signature_block("Customer", "Sales", company["signatory"])
    ))
    return _render(story, company)


def purchase_order_pdf(po) -> bytes:
    currency = po.currency
    company, _terms, logo = identity(po)
    story = letterhead(company, logo)
    story += title_block("PURCHASE ORDER", [
        ("PO No", po.po_no),
        ("Date", fmt_date(po.order_date)),
        ("Required By", fmt_date(po.expected_date)),
        ("Payment Terms", po.payment_terms or "-"),
    ])

    supplier = po.supplier
    story += party_block(
        "SUPPLIER",
        [
            supplier.name if supplier else "",
            supplier.contact_person if supplier else None,
            supplier.address if supplier else None,
            f"Tel {supplier.phone}" if supplier and supplier.phone else None,
        ],
        "DELIVER TO",
        [company["name"], company["address"], company["city"],
         f"Tel {company['phone']}"],
    )

    headers = []
    for text in ("#", "DESCRIPTION", "UNIT", "QTY", "UNIT PRICE", "AMOUNT"):
        headers.append(Paragraph(text, ParagraphStyle(
            "h", parent=S["cellb"], fontSize=7, textColor=colors.white, leading=9)))

    rows = []
    for line in po.items:
        rows.append([
            Paragraph(str(line.line_no), S["cell"]),
            Paragraph(_esc(line.description), S["cell"]),
            Paragraph(_esc(line.unit), S["right"]),
            Paragraph(fmt_num(line.quantity), S["right"]),
            Paragraph(fmt_money(line.unit_price, currency), S["right"]),
            Paragraph(fmt_money(line.line_total, currency), S["right"]),
        ])

    story.append(items_table(
        headers, rows,
        [8 * mm, 78 * mm, 18 * mm, 18 * mm, 24 * mm, 24 * mm],
        numeric_from=2,
    ))
    story.append(Spacer(1, 9))
    story.append(totals_block([
        ("Sub Total", fmt_money(po.subtotal, currency)),
        (f"PPN ({fmt_num(po.ppn_percent)}%)", fmt_money(po.ppn_amount, currency)),
        ("TOTAL", fmt_money(po.total, currency)),
    ], currency))
    story.append(Spacer(1, 10))

    if po.notes:
        story += [
            Paragraph("NOTES", S["label"]),
            Spacer(1, 2),
            Paragraph(_esc(po.notes).replace("\n", "<br/>"), S["cell"]),
            Spacer(1, 10),
        ]
    story.append(KeepTogether(signature_block("Supplier", "Authorised by",
                                              company["signatory"])))
    return _render(story, company)


def delivery_note_pdf(note) -> bytes:
    """Surat Jalan - the sheet that rides with the goods.

    No prices anywhere: the driver and whoever signs at the far end have no
    business seeing what the customer paid. Sizes are shown instead, because
    that is what gets checked against the window on site.
    """
    so = note.sales_order
    customer = so.customer if so else None
    company, _terms, logo = identity(note)

    story = letterhead(company, logo)
    story += title_block("SURAT JALAN", [
        ("No. Surat Jalan", note.sj_no),
        ("Tanggal", fmt_date(note.delivery_date)),
        ("No. Faktur / Invoice No", so.so_no if so else "-"),
        ("No. PO Pelanggan", (so.po_reference if so else None) or "-"),
    ])

    story += party_block(
        "KIRIM KE / DELIVER TO",
        [
            note.deliver_to or (customer.name if customer else ""),
            note.deliver_address,
            f"Telp {note.phone}" if note.phone else None,
        ],
        "KENDARAAN / VEHICLE",
        [
            f"No. Polisi: {note.vehicle_no}" if note.vehicle_no else "No. Polisi: -",
            f"Pengemudi: {note.driver_name}" if note.driver_name else "Pengemudi: -",
        ],
    )

    headers = []
    for text in ("NO", "NAMA BARANG / DESCRIPTION", "UKURAN (cm)", "JUMLAH", "SATUAN"):
        headers.append(Paragraph(text, ParagraphStyle(
            "h", parent=S["cellb"], fontSize=7, textColor=colors.white, leading=9)))

    rows = []
    for line in note.items:
        name = (
            f"<b>{_esc(line.product_name)}</b>"
            f"<br/><font size=7 color='#8494A7'>{_esc(line.product_code)}</font>"
        )
        if line.description:
            name += f"<br/><font size=7>{_esc(line.description)}</font>"

        if line.width_cm and line.height_cm:
            size = f"{fmt_num(line.width_cm)} x {fmt_num(line.height_cm)}"
        elif line.width_cm:
            size = fmt_num(line.width_cm)
        else:
            size = "-"

        rows.append([
            Paragraph(str(line.line_no), S["cell"]),
            Paragraph(name, S["cell"]),
            Paragraph(size, S["right"]),
            Paragraph(fmt_num(line.quantity), S["right"]),
            Paragraph(_esc(line.unit), S["centre"]),
        ])

    story.append(items_table(
        headers, rows,
        [10 * mm, 92 * mm, 28 * mm, 20 * mm, 20 * mm],
        numeric_from=2,
    ))
    story.append(Spacer(1, 6))

    total = sum((Decimal(str(line.quantity)) for line in note.items), Decimal("0"))
    story.append(totals_block([("Total Barang", fmt_num(total))], ""))
    story.append(Spacer(1, 8))

    if note.notes:
        story += [
            Paragraph("CATATAN / NOTES", S["label"]),
            Spacer(1, 2),
            Paragraph(_esc(note.notes).replace("\n", "<br/>"), S["cell"]),
            Spacer(1, 8),
        ]

    story += [
        Paragraph(
            "Barang telah diterima dalam keadaan baik dan cukup. "
            "<i>Goods received in good order and condition.</i>",
            S["terms"],
        ),
        Spacer(1, 12),
    ]

    # Three-way sign-off: who sent it, who drove it, who took it in.
    def cell(label, name):
        # `label` is our own markup and carries a deliberate <br/>; only the
        # name is untrusted and needs escaping.
        return [
            Paragraph(label, S["centre"]),
            Spacer(1, 20 * mm),
            Paragraph(f"( {_esc(name or '_' * 18)} )", S["centre"]),
        ]

    signatures = Table(
        [[cell("Hormat kami,<br/>Sender", company["signatory"]),
          cell("Pengemudi,<br/>Driver", note.driver_name),
          cell("Penerima,<br/>Received by", note.received_by)]],
        colWidths=[56.6 * mm, 56.6 * mm, 56.6 * mm],
    )
    signatures.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(KeepTogether(signatures))

    return _render(story, company)


# Rupiah in words, for the receipt - Indonesian receipts traditionally spell
# the amount out so the figure cannot be altered afterwards.
_ONES = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan",
         "sembilan", "sepuluh", "sebelas"]


def _join(*parts) -> str:
    """Drop empty groups so a round number reads 'satu juta', not
    'satu juta nol ribu nol'."""
    return " ".join(p for p in parts if p)


def _spell(n: int) -> str:
    if n == 0:
        return ""  # an empty group contributes nothing
    if n < 12:
        return _ONES[n]
    if n < 20:
        return _join(_spell(n - 10), "belas")
    if n < 100:
        return _join(_spell(n // 10), "puluh", _spell(n % 10))
    if n < 200:
        return _join("seratus", _spell(n - 100))
    if n < 1000:
        return _join(_spell(n // 100), "ratus", _spell(n % 100))
    if n < 2000:
        return _join("seribu", _spell(n - 1000))
    if n < 1_000_000:
        return _join(_spell(n // 1000), "ribu", _spell(n % 1000))
    if n < 1_000_000_000:
        return _join(_spell(n // 1_000_000), "juta", _spell(n % 1_000_000))
    if n < 1_000_000_000_000:
        return _join(_spell(n // 1_000_000_000), "miliar", _spell(n % 1_000_000_000))
    return _join(_spell(n // 1_000_000_000_000), "triliun", _spell(n % 1_000_000_000_000))


def terbilang(n) -> str:
    n = int(n)
    if n < 0:
        return f"minus {terbilang(-n)}"
    return _spell(n) or "nol"


METHOD_LABEL = {
    "cash": "Cash / Tunai",
    "transfer": "Bank Transfer",
    "cheque": "Cheque / Giro",
    "card": "Card",
    "other": "Other",
}


def receipt_pdf(receipt, amount_paid, balance_due) -> bytes:
    so = receipt.sales_order
    currency = so.currency if so else "IDR"
    company, _terms, logo = identity(receipt)

    story = letterhead(company, logo)
    story += title_block("RECEIPT / KWITANSI", [
        ("Receipt No", receipt.receipt_no),
        ("Date", fmt_date(receipt.receipt_date)),
        ("Invoice No", so.so_no if so else "-"),
    ])

    amount_box = Table(
        [[
            Paragraph("AMOUNT RECEIVED", S["label"]),
            Paragraph(
                f"<b>{currency} {fmt_money(receipt.amount, currency)}</b>",
                ParagraphStyle("amt", parent=S["body"], fontSize=16,
                               textColor=NAVY, alignment=TA_RIGHT, leading=20),
            ),
        ]],
        colWidths=[85 * mm, 85 * mm],
    )
    amount_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.8, NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [amount_box, Spacer(1, 4)]

    if currency == "IDR":
        words = terbilang(whole_rupiah(receipt.amount)).strip()
        story += [
            Paragraph(
                f"<i>Terbilang: <b>{_esc(words)} rupiah</b></i>", S["terms"]
            ),
            Spacer(1, 9),
        ]

    rows = [
        ("Received from", receipt.received_from or (so.customer.name if so and so.customer else "-")),
        ("Payment method", METHOD_LABEL.get(receipt.payment_method, receipt.payment_method)),
        ("Reference", receipt.reference or "-"),
        ("For payment of", f"Invoice {so.so_no}" if so else "-"),
    ]
    if receipt.notes:
        rows.append(("Notes", receipt.notes))

    detail = Table(
        [[Paragraph(_esc(k), S["label"]), Paragraph(_esc(v), S["cell"])] for k, v in rows],
        colWidths=[38 * mm, 132 * mm],
    )
    detail.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [detail, Spacer(1, 10)]

    if so:
        story.append(totals_block([
            ("Order Total", fmt_money(so.total, currency)),
            ("Paid to date", fmt_money(amount_paid, currency)),
            ("Balance Due", fmt_money(balance_due, currency)),
        ], currency))
        story.append(Spacer(1, 12))

    story.append(KeepTogether(
        signature_block("Received by", f"For and on behalf of {company['name']}",
                        company["signatory"])
    ))
    return _render(story, company)
