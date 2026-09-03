# Workweb — Q2O (Quotation to Order)

Internal web app for a blinds/curtain company, replacing the legacy desktop ERP.
Staff only, 5–10 users.

**Flow:** Quotation → Invoice → Purchase Order (materials) → Surat Jalan
(delivery) → Receipt (payment) → Sales & Financial reports. Every document prints
to a PDF on company letterhead.

## Stack

| Layer    | Choice |
|----------|--------|
| Backend  | Python 3.11, FastAPI, SQLAlchemy 2.0 |
| Database | SQLite local / MySQL production — same code, swap `DATABASE_URL` |
| Auth     | JWT (python-jose) + bcrypt (passlib) |
| PDF      | ReportLab (pure Python — no system libraries on Windows or Linux) |
| Frontend | Plain HTML/CSS/JS — no framework, no build step |

## Running locally

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt

python seed.py --demo         # tables, master data, and a year of sample documents
uvicorn main:app --reload
```

Open <http://localhost:8000/>. The API serves the frontend from the same origin,
so there is nothing else to start. API docs: <http://localhost:8000/docs>.

### Demo logins

| Username | Password   | Role  | Can do |
|----------|------------|-------|--------|
| `admin`  | `admin123` | admin | Everything, including editing other people's documents |
| `budi`   | `budi123`  | user  | Sees everything, edits only what they created |
| `sari`   | `sari123`  | user  | Same |
| `agus`   | `agus123`  | user  | Same |

## The real client catalogue

```bash
pip install openpyxl
python import_catalog.py --dry-run    # parse and report, write nothing
python import_catalog.py              # import for real
```

Imports the client's fabric workbook (`AS PER 11 August 2026 (1).xlsx`) into
`products` + `product_colors`: **133 products, 690 colour variants** across
Roller, Design Shades, All Venetian, Curtain, Cellular Shade and Vertical
Fabric. `Frame Door and Window` is excluded on the product owner's instruction,
along with the six supplementary/legacy sheets.

**Everything lands `is_active = false` with `unit_price = 0`** — the workbook has
no pricing at all. Nothing appears in the quotation product picker until a price
list arrives and the products are activated, so nobody can issue an IDR 0
quotation by accident.

The workbook is hand-maintained, so the parser handles a lot of mess. The
non-obvious parts:

- **A product's colours run over several rows.** Usually column A is blank on
  those rows, but the client also re-types the name — `BOTANY (127 mm)` appears
  on 13 consecutive rows. Both mean "more colours", not a new product.
- **Stock status comes from each cell's background fill**, and the legend
  differs per sheet, so it is read per sheet — from the rows *above* the
  "Colour" header only. A data cell reading `Ice/Artic (max drop 3,2m) Limited
  Stock` would otherwise be mistaken for a legend entry.
- **`Curtain` and `Design Shades` have no legend at all** → their 64 colours are
  `unknown`, not guessed from colour.
- **103 further cells use a fill in no legend** (dark grey `FF666666` mostly) →
  also `unknown`, and counted per sheet in the summary.
- `Curtain` writes decimals with commas (`max drop 3,2m`), carries fabric codes
  in the cell (`Sand : 10502`), and has a divider row; the 4 colours above it are
  tagged `legacy`, not live stock.
- `(BO)` / `(TL)` and `(89 mm)` / `(127 mm)` are kept in the product name —
  dropping them would merge Block Out with Translucent.

Every colour row keeps `raw_label` and `source_ref` (e.g. `Roller!D11`), so any
suspect value can be traced straight back to the cell that produced it.

`seed.py` will not re-add its sample products once a real catalogue is present.

### Still to do on the catalogue

- **Pricing** — must be sourced from the client, then products activated.
- **Confirm the `unknown` statuses** (167 colours) with the client.
- The per-colour `max_width_cm` / `max_height_cm` are stored but not yet enforced
  during quoting; `pricing.py` still validates against the product-level limits.
- `FABRIC CHART` (a mechanism-compatibility matrix) was skipped and may be worth
  importing separately later.

## Sample data

```bash
python seed.py            # master data only - an empty system ready for real work
python seed.py --demo     # the above, plus a year of sample documents
python seed.py --reset    # drop every table first (destroys existing data)
```

`seed.py` loads the masters: 4 users, 10 customers, 6 suppliers, and a **28-item
product catalogue** — roller, venetian and vertical blinds, curtains and roman
shades, tracks and rods, motorisation, and services. It is safe to re-run;
records are matched on their code and existing ones are left alone.

`--demo` additionally runs `demo_data.py`, which builds **17 quotations, 11
invoices, 21 purchase orders, 9 Surat Jalan and 14 receipts** spread over the last
ten months, so every screen and both reports have something to show.

The demo documents are built through the real `pricing.py` and `numbering.py`
rather than by inserting rows, so every total, discount and document number is
exactly what the application itself would produce. The random seed is fixed, so
the same dataset comes out every time.

It deliberately includes the awkward cases you want to see on screen:

- quotations in every status, including one cancelled and one that stalled at *sent*
- orders from *draft* through to *completed*, spread across all four users
- **a partially delivered order** (an invoice with roughly half its goods still outstanding)
- one order delivered over **two separate trips**
- part-paid orders, so the receivables figure is not zero
- purchase orders for stock and packaging that are **not** linked to any order,
  which is what makes the "unattributed cost" note on the financial report appear

Purchase costs are set as a share of order value, so margins land in a plausible
40–55% band rather than being random.

`--demo` refuses to run twice on the same database; use `--demo --reset` to
rebuild. Stop the server first if you use `--reset`, or SQLite may be locked.

## Three companies, one system

Three legal entities share the product catalogue, the customer list, the
suppliers and the staff. What is **not** shared:

- **The letterhead.** Each company has its own name, address, phone, NPWP, bank
  account, signatory and logo. Every document records which entity issued it and
  prints that entity's identity - a GB quotation never shows MJ's bank account.
- **The document numbering.** Each company counts independently:
  `Q-GB-202608-001` and `Q-MJ-202608-001` both exist. The company code is part
  of the number, which is why **the company is fixed once a document is issued** -
  changing it would leave the number lying.

A user picks the issuing company on a new quotation; their own company is
pre-selected. Invoices, purchase orders, Surat Jalan and receipts all inherit
the company of the document they come from, so nothing has to be chosen twice.

Every list, both reports and the delivery schedule take a **company filter**, and
the top bar shows which entity you are working in.

Logos go in `backend/assets/` as `logo_GB.png`, `logo_MJ.png`, `logo_AI.png`.
A company with no logo file prints its name in type instead.

```bash
python migrate.py     # after pulling: adds the companies table and columns
```

`migrate.py` also backfills documents created before the change, attaching them
to the first company so old history stays printable.

## Users and permissions

There are exactly **two roles**.

- **Everyone sees everything.** All quotations, orders, POs and receipts are in one
  shared list regardless of who created them, so anyone can answer a customer call.
- **A normal user can only change what they created.** Editing, status changes and
  deletion of someone else's document return 403; the UI greys those rows (🔒) and
  opens them read-only with a banner.
- **An admin can change anything.** That is the only difference between the roles.
- Products, customers and suppliers are shared master data any user may maintain.

## Putting your company on the PDFs

Edit `backend/company.py`, or set the matching env vars in `.env`
(`COMPANY_NAME`, `COMPANY_ADDRESS`, `COMPANY_NPWP`, `COMPANY_BANK_ACCOUNT`, …).
The defaults are obvious placeholders (`PT NAMA PERUSAHAAN`).

For a logo, drop a **PNG or JPG at `backend/assets/logo.png`** — roughly 3:1
landscape, scaled to 16 mm tall. Without one the company name is set in type.

`QUOTATION_TERMS` holds the terms printed on quotations, `|`-separated.

## Documents

| Endpoint | Produces |
|----------|----------|
| `GET /documents/quotations/{id}.pdf` | Sales Quotation with product table, dimensions, discount, PPN, terms, signature block |
| `GET /documents/sales-orders/{id}.pdf` | Invoice |
| `GET /documents/purchase-orders/{id}.pdf` | Purchase Order to the supplier |
| `GET /documents/delivery-notes/{id}.pdf` | Surat Jalan, with sizes and a three-way sign-off |
| `GET /documents/receipts/{id}.pdf` | Receipt / Kwitansi, amount spelled out in Indonesian |

Add `?download=1` to save rather than preview. The frontend fetches these with the
bearer token and hands the browser a blob, so the token never lands in a URL.

## Layout

```
backend/
  schema.sql      MySQL schema — the shared contract for every module
  models.py       SQLAlchemy models
  database.py     engine/session; SQLite by default
  auth.py         JWT, hashing, get_current_user, require_role, ownership rule
  pricing.py      line pricing, dimension validation, totals
  numbering.py    Q-/INV-/PO-/RCP-/SJ-YYYYMM-### allocation
  company.py      >>> your letterhead details <<<
  pdf.py          ReportLab templates + terbilang (rupiah in words)
  schemas.py      Pydantic models
  routers/        products, customers, suppliers, quotations, sales_orders,
                  purchase_orders, receipts, reports, documents
  main.py         app, /auth/login, /auth/me, static mount
  seed.py         tables + demo data
frontend/
  login.html
  quotations.html / quotation-form.html
  sales-orders.html / sales-order-form.html      (receipts + receivable panel)
  statement.html                                 per-customer statement
  purchase-orders.html / purchase-order-form.html
  receipts.html
  reports.html
  css/app.css
  js/api.js          fetch wrapper, formatting, autocomplete, PDF opener
  js/line-editor.js  shared line-item table (quotations + invoices)
  js/*.js            one per page
```

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

540 tests, ~25 seconds. Each one runs against a fresh in-memory SQLite schema,
so tests never see each other's rows and document numbering always starts at 001.

| File | Covers |
|------|--------|
| `test_pricing.py` | measures per unit type, dimension limits, discounts, rounding, rollups |
| `test_auth.py` | login, JWT signing/expiry, deactivated users, every route's 401 |
| `test_permissions.py` | shared visibility, the owner-vs-admin edit rule on every document |
| `test_quotations.py` | totals, validation, numbering, editing, status flow, filters |
| `test_sales_orders.py` | conversion fidelity, lifecycle guards, payment tracking |
| `test_receivables.py` | closing/reopening a receivable, the customer statement |
| `test_purchase_orders.py` | material lines, SO linking, supplier master |
| `test_delivery_notes.py` | partial deliveries, the over-delivery cap, quantity release |
| `test_receipts.py` | overpayment, draft-order and void guards |
| `test_reports.py` | netto arithmetic, cost attribution, conversion rate |
| `test_pdf.py` | all four documents render, and *contain* the expected text |
| `test_masters.py` | product/customer CRUD, numbering, decimal precision |
| `test_companies.py` | per-company numbering, letterhead isolation, every company filter |
| `test_new_features.py` | installation cost, DP/TOP, component options, PO split, schedule |

`test_pdf.py` decodes the generated PDFs (ASCII85 → Flate → text operators) and
asserts on real strings, so a broken letterhead or a missing total fails the
build rather than shipping a blank page.

The suite was mutation-checked: breaking the ownership rule, the line-discount
fallback, the PPN base, the overpayment guard or the number-to-words helper each
made it fail.

## Money rules

Totals are **always** recalculated server-side; client-submitted amounts are
ignored apart from an explicit per-line `unit_price` override.

```
measure    = per_sqm:   (width/100) × (height/100) × qty
             per_meter: (width/100) × qty
             per_unit:  qty

line_total      = measure × unit_price                     (gross)
line_discount   = line_total × (line_discount_pct ?? header discount_percent)
subtotal        = Σ line_total
discount_amount = Σ line_discount
netto           = subtotal − discount_amount
ppn_amount      = netto × ppn_percent
total           = netto + ppn_amount
```

Width/height are validated against the product's `min/max_width_cm` and
`min/max_height_cm`; `NULL` means no limit on that side. Only the dimensions a
product is priced on are required. `discount_percent` defaults to **35.00** and
stays freely editable per quotation.

Purchase orders carry no trade discount: `subtotal → PPN → total`.

## Surat Jalan (delivery notes)

The document that travels with the goods. Raised from a confirmed invoice via
**Create Surat Jalan** on the invoice page, which drafts one for everything still
outstanding — edit the quantities down for a partial delivery and the rest stays
on the order for a later trip.

- **Cannot over-deliver.** Quantities are capped per order line, checked across
  every note on that order, and summed first so splitting a line over two rows
  cannot dodge the limit. Enforced server-side, not just in the browser.
- **Draft notes hold their goods** so two people cannot promise the same stock.
  Cancelling or deleting a note puts the quantities back on the outstanding list.
- **No prices anywhere.** The driver and whoever signs at the far end have no
  business seeing the customer pricing. Sizes are printed instead, because that is
  what gets checked against the window on site.
- Three-way sign-off: sender, driver, recipient. Marking a note delivered records
  who signed and when.

The invoice page shows every delivery against it plus an
ordered / delivered / outstanding table per line.

## Receivables (piutang)

The invoice is the receivable. `amount_paid` and `balance_due` are derived from
the receipts against it, never stored, so they cannot drift.

**Closing a receivable.** Once an invoice is settled, the Receivable card on the
invoice page closes it: a closing date (today by default, backdatable to when the
money actually landed), who closed it, and an optional note. A closed receivable
drops out of the outstanding figure on the customer statement and can be listed
on its own with `GET /sales-orders?receivable=closed`.

- **Closing is refused while anything is still owed** — closing an unpaid
  receivable would quietly write off real money.
- **Voiding a payment reopens it automatically.** Deleting a receipt puts the
  money back on the account, so the debt returns to the outstanding list instead
  of disappearing with the receipt.
- Reopening by hand is also available, for a payment that turns out to have
  bounced.

**Customer statement** (`statement.html`, `GET /reports/statement/{customer_id}`)
is the *rincian pembayaran customer*: every invoice in the period with its total,
paid and balance, then every payment oldest-first with the **account balance
after each one** — which is how a customer reads a statement. Filters: company,
date range, and "open items only". Draft and cancelled invoices are left out
because they are not a debt; a closed receivable still appears so the history
stays complete, but stops counting toward outstanding.

## Status flows

```
Quotation  draft → sent → approved → converted
Invoice  draft → confirmed → in_production → delivered → completed
Purchase Order  draft → sent → received
Surat Jalan  draft → issued → delivered
```

Any of them can go to `cancelled`. Guards worth knowing:

- Only `draft` quotations are editable; `draft`/`confirmed` invoices; `draft`/`sent` POs.
- A quotation can only convert once, and only from `sent` or `approved`.
- A payment cannot be recorded against a `draft` invoice, and cannot exceed the balance.
- An invoice cannot be `completed` while money is outstanding.
- Deleting is blocked when a later document depends on the record.

## Reports

**Sales** — quotation vs order volume by month, conversion rate, ranking by
customer and by product.

**Financial** — revenue (invoices, netto) against cost (purchase orders,
netto), gross profit and margin %, both overall and per invoice. Both sides
exclude PPN, which is collected on behalf of the tax office and would otherwise
inflate the margin.

Cost is attributed per invoice through the **`sales_order_id` link on a purchase
order**. Raise POs from the "Raise Purchase Order" button on an invoice and the
link is set for you. Unlinked POs still count toward total cost, and the report
says how much is unattributed.

## Deployment notes

- Set `DATABASE_URL` and a real `JWT_SECRET_KEY`
  (`python -c "import secrets; print(secrets.token_hex(32))"`).
- Apply `schema.sql` to MySQL rather than relying on `create_all`.
- `bcrypt` is pinned to `4.0.1` — passlib 1.7.4 reads an attribute bcrypt 4.1+
  removed. Don't bump one without replacing the other.

## Not built yet

Delivery orders / installation scheduling, stock control, quotation revision
history, emailing PDFs to customers, and maintenance screens for products,
customers and suppliers (the API endpoints exist; seed data covers them for now).
