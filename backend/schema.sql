-- =====================================================================
-- Q2O (Quotation-to-Order) - MySQL schema
-- Source of truth for the data model. Modules not yet built (Sales
-- Order, Purchase Order) will extend this file, so keep names stable.
-- =====================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------
-- companies - the legal entities that issue documents.
--
-- Three of them share one product catalogue, one customer list and one set
-- of suppliers; what differs is the letterhead, the bank account and the
-- document numbering. Every document therefore records which company issued
-- it, and prints that company's identity.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    -- Short code, used inside document numbers: Q-GB-202608-001.
    code          VARCHAR(10)  NOT NULL,
    name          VARCHAR(150) NOT NULL,
    tagline       VARCHAR(150) NULL,

    address       VARCHAR(255) NULL,
    city          VARCHAR(120) NULL,
    phone         VARCHAR(60)  NULL,
    email         VARCHAR(120) NULL,
    website       VARCHAR(120) NULL,
    npwp          VARCHAR(40)  NULL,

    bank_name     VARCHAR(120) NULL,
    bank_account  VARCHAR(60)  NULL,
    bank_holder   VARCHAR(150) NULL,
    signatory     VARCHAR(120) NULL,

    -- File in backend/assets/. Blank falls back to the company name in type.
    logo_filename VARCHAR(120) NULL,
    -- Terms printed on a quotation, one per line, separated by "|".
    quotation_terms TEXT       NULL,

    is_active     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_companies_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL,
    full_name     VARCHAR(120) NOT NULL,
    email         VARCHAR(120) NULL,
    password_hash VARCHAR(255) NOT NULL,
    -- admin | sales | surveyor | factory
    role          VARCHAR(20)  NOT NULL DEFAULT 'sales',
    is_active     TINYINT(1)   NOT NULL DEFAULT 1,
    -- Pre-selected on new documents; the user may still pick another.
    default_company_id INT      NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- customers
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    code            VARCHAR(30)  NOT NULL,
    name            VARCHAR(150) NOT NULL,
    nik_npwp        VARCHAR(40)  NULL,
    address         TEXT         NULL,
    deliver_to      VARCHAR(150) NULL,
    deliver_address TEXT         NULL,
    phone           VARCHAR(40)  NULL,
    email           VARCHAR(120) NULL,
    price_group     VARCHAR(30)  NULL,
    payment_terms   VARCHAR(60)  NULL,
    is_active       TINYINT(1)   NOT NULL DEFAULT 1,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_customers_code (code),
    KEY ix_customers_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    code         VARCHAR(40)   NOT NULL,
    name         VARCHAR(150)  NOT NULL,
    category     VARCHAR(60)   NULL,
    -- per_sqm | per_unit | per_meter
    price_unit   VARCHAR(20)   NOT NULL DEFAULT 'per_sqm',
    unit_price   DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    -- NULL means "no limit on this side"
    min_width_cm  DECIMAL(10,2) NULL,
    max_width_cm  DECIMAL(10,2) NULL,
    min_height_cm DECIMAL(10,2) NULL,
    max_height_cm DECIMAL(10,2) NULL,
    description  TEXT          NULL,
    is_active    TINYINT(1)    NOT NULL DEFAULT 1,
    -- Default supplier. Raising a purchase order from a sales order groups
    -- the lines by this and creates one PO per supplier.
    supplier_id  INT           NULL,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_products_code (code),
    KEY ix_products_name (name),
    KEY ix_products_supplier (supplier_id)
    -- The foreign key to suppliers is added at the foot of this file:
    -- suppliers is created later, so it cannot be declared inline here.
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- product_options - which mechanisms/rails a fabric can be made in.
--
-- Imported from the "FABRIC CHART" sheet of the client workbook, a matrix of
-- fabric x option with True (recommended) or x (not recommended). Drives the
-- component dropdown shown when a fabric is added to a quotation line.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_options (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    product_id   INT          NOT NULL,
    option_group VARCHAR(40)  NOT NULL,   -- Roman | Roller | Panel Glide | Vertical
    option_name  VARCHAR(60)  NOT NULL,   -- Classic, Standard Roll, Flat Bottom Rail
    is_available TINYINT(1)   NOT NULL DEFAULT 1,   -- False where the sheet says "x"
    source_ref   VARCHAR(40)  NULL,

    KEY ix_popt_product (product_id),
    KEY ix_popt_group (option_group),
    CONSTRAINT fk_popt_product FOREIGN KEY (product_id)
        REFERENCES products (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- quotations
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quotations (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    quotation_no    VARCHAR(30)  NOT NULL,
    -- The entity that issued this document.
    company_id     INT         NOT NULL,
    quotation_date  DATE         NOT NULL,
    last_follow_up  DATE         NULL,
    -- draft | sent | approved | converted | cancelled
    status          VARCHAR(20)  NOT NULL DEFAULT 'draft',

    customer_id     INT          NOT NULL,
    -- Snapshot of customer details at quotation time. The customer master
    -- may change later; a printed quotation must not.
    nik_npwp        VARCHAR(40)  NULL,
    surveyor        VARCHAR(120) NULL,
    address         TEXT         NULL,
    deliver_to      VARCHAR(150) NULL,
    deliver_address TEXT         NULL,
    phone           VARCHAR(40)  NULL,
    email           VARCHAR(120) NULL,

    currency        VARCHAR(10)   NOT NULL DEFAULT 'IDR',
    exchange_rate   DECIMAL(15,4) NOT NULL DEFAULT 1.0000,
    price_group     VARCHAR(30)   NULL,
    payment_terms   VARCHAR(60)   NULL,

    -- Business rule: base 35%, but freely editable per quotation.
    discount_percent DECIMAL(5,2) NOT NULL DEFAULT 35.00,
    ppn_percent      DECIMAL(5,2) NOT NULL DEFAULT 11.00,
    -- Installation is charged for the job as a whole, after the line
    -- discount and before PPN (a service, so it is taxed).
    installation_cost DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    -- TOP / down payment: the share the customer pays up front.
    dp_percent       DECIMAL(5,2)  NULL,
    dp_amount        DECIMAL(15,2) NOT NULL DEFAULT 0.00,

    -- All derived; recalculated server-side on every write.
    subtotal        DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    discount_amount DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    netto           DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    ppn_amount      DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    total           DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    total_qty       DECIMAL(12,2) NOT NULL DEFAULT 0.00,

    notes           TEXT     NULL,
    created_by      INT      NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_quotations_no (quotation_no),
    KEY ix_quotations_status (status),
    KEY ix_quotations_customer (customer_id),
    CONSTRAINT fk_quotations_customer FOREIGN KEY (customer_id)
        REFERENCES customers (id),
    CONSTRAINT fk_quotations_user FOREIGN KEY (created_by)
        REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- quotation_items
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quotation_items (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    quotation_id INT NOT NULL,
    line_no      INT NOT NULL,
    product_id   INT NOT NULL,

    -- Snapshot so historical quotations stay readable if the product changes.
    product_code VARCHAR(40)  NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    price_unit   VARCHAR(20)  NOT NULL,

    description  VARCHAR(255)  NULL,
    quantity     DECIMAL(12,2) NOT NULL DEFAULT 1.00,
    width_cm     DECIMAL(10,2) NULL,
    height_cm    DECIMAL(10,2) NULL,
    -- Billable measure: sqm, running metres, or pieces (depends on price_unit).
    measure      DECIMAL(12,4) NOT NULL DEFAULT 0.0000,
    unit_price   DECIMAL(15,2) NOT NULL DEFAULT 0.00,

    -- NULL = fall back to the quotation-level discount_percent.
    -- Chosen components, e.g. "Roller: Standard Roll | Bottom Rail: Flat".
    component_options VARCHAR(255)  NULL,
    line_discount_pct DECIMAL(5,2)  NULL,
    line_total        DECIMAL(15,2) NOT NULL DEFAULT 0.00,  -- gross, before discount
    line_discount_amt DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    line_net          DECIMAL(15,2) NOT NULL DEFAULT 0.00,  -- line_total - discount

    KEY ix_items_quotation (quotation_id),
    CONSTRAINT fk_items_quotation FOREIGN KEY (quotation_id)
        REFERENCES quotations (id) ON DELETE CASCADE,
    CONSTRAINT fk_items_product FOREIGN KEY (product_id)
        REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================================
-- Step 3: Sales Order, Purchase Order, Receipts.
-- Added after the quotation module; the five tables above are unchanged.
-- Note: users.role now holds only 'admin' or 'user' (see auth.ROLES).
-- =====================================================================

-- ---------------------------------------------------------------------
-- product_colors - one row per colour variant of a fabric/product.
--
-- Imported from the client catalogue workbook (see import_catalog.py).
-- Size caps live here rather than on `products` because they vary per
-- colour: ASPEN Avocado maxes at 2.9m while ASPEN Chrystal maxes at 2.7m.
--
-- stock_status values:
--   in_stock | limited_stock | out_of_stock | discontinued
--   will_discontinue  - legend says "STOCK WILL DISCONTINUE"
--   new_range         - legend says "NEW FABRIC RANGE"/"NEW FABRIC COLOUR";
--                       both use the same fill, so they cannot be told apart
--   unknown           - sheet has no legend, or the cell fill is not in it
--   legacy            - Curtain rows above the "Current Fabrics Available
--                       (2025)" divider; historic, not active inventory
--
-- Stored as VARCHAR rather than ENUM to match the other status columns in
-- this schema and to stay portable to SQLite in local development.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_colors (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    product_id    INT          NOT NULL,
    color_name    VARCHAR(100) NOT NULL,
    fabric_code   VARCHAR(30)  NULL,     -- e.g. "10502", Curtain sheet only
    max_width_cm  DECIMAL(6,2) NULL,     -- NULL = not stated for this colour
    max_height_cm DECIMAL(6,2) NULL,
    stock_status  VARCHAR(20)  NOT NULL DEFAULT 'unknown',

    -- Provenance. The source workbook is messy and hand-maintained, so keep
    -- the original cell text and address: without them a wrong import cannot
    -- be traced back to the cell that caused it.
    raw_label  VARCHAR(255) NULL,        -- cell text exactly as written
    source_ref VARCHAR(40)  NULL,        -- e.g. "Roller!B7"
    notes      VARCHAR(255) NULL,        -- leftovers e.g. "approx 24 sets"

    is_active  TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME   NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY ix_pc_product (product_id),
    KEY ix_pc_status (stock_status),
    KEY ix_pc_name (color_name),
    CONSTRAINT fk_pc_product FOREIGN KEY (product_id)
        REFERENCES products (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- suppliers - raw material vendors for purchase orders
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppliers (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    code           VARCHAR(30)  NOT NULL,
    name           VARCHAR(150) NOT NULL,
    contact_person VARCHAR(120) NULL,
    address        TEXT         NULL,
    phone          VARCHAR(40)  NULL,
    email          VARCHAR(120) NULL,
    payment_terms  VARCHAR(60)  NULL,
    is_active      TINYINT(1)   NOT NULL DEFAULT 1,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_suppliers_code (code),
    KEY ix_suppliers_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- sales_orders - a quotation the customer accepted
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sales_orders (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    so_no         VARCHAR(30) NOT NULL,
    -- The entity that issued this document.
    company_id     INT         NOT NULL,
    quotation_id  INT         NULL,          -- NULL = raised directly
    customer_id   INT         NOT NULL,
    order_date    DATE        NOT NULL,
    delivery_date DATE        NULL,
    -- draft | confirmed | in_production | delivered | completed | cancelled
    status        VARCHAR(20) NOT NULL DEFAULT 'draft',

    -- Customer snapshot, same reasoning as quotations.
    nik_npwp        VARCHAR(40)  NULL,
    surveyor        VARCHAR(120) NULL,
    address         TEXT         NULL,
    deliver_to      VARCHAR(150) NULL,
    deliver_address TEXT         NULL,
    phone           VARCHAR(40)  NULL,
    email           VARCHAR(120) NULL,

    currency      VARCHAR(10)   NOT NULL DEFAULT 'IDR',
    exchange_rate DECIMAL(15,4) NOT NULL DEFAULT 1.0000,
    price_group   VARCHAR(30)   NULL,
    payment_terms VARCHAR(60)   NULL,
    po_reference  VARCHAR(60)   NULL,        -- the customer own PO number

    discount_percent DECIMAL(5,2) NOT NULL DEFAULT 35.00,
    ppn_percent      DECIMAL(5,2) NOT NULL DEFAULT 11.00,
    -- Installation is charged for the job as a whole, after the line
    -- discount and before PPN (a service, so it is taxed).
    installation_cost DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    -- TOP / down payment: the share the customer pays up front.
    dp_percent       DECIMAL(5,2)  NULL,
    dp_amount        DECIMAL(15,2) NOT NULL DEFAULT 0.00,

    subtotal        DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    discount_amount DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    netto           DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    ppn_amount      DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    total           DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    total_qty       DECIMAL(12,2) NOT NULL DEFAULT 0.00,

    notes      TEXT     NULL,
    created_by INT      NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_so_no (so_no),
    KEY ix_so_status (status),
    KEY ix_so_customer (customer_id),
    CONSTRAINT fk_so_quotation FOREIGN KEY (quotation_id) REFERENCES quotations (id),
    CONSTRAINT fk_so_customer  FOREIGN KEY (customer_id)  REFERENCES customers (id),
    CONSTRAINT fk_so_user      FOREIGN KEY (created_by)   REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sales_order_items (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    sales_order_id INT NOT NULL,
    line_no        INT NOT NULL,
    product_id     INT NOT NULL,

    product_code VARCHAR(40)  NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    price_unit   VARCHAR(20)  NOT NULL,

    description  VARCHAR(255)  NULL,
    quantity     DECIMAL(12,2) NOT NULL DEFAULT 1.00,
    width_cm     DECIMAL(10,2) NULL,
    height_cm    DECIMAL(10,2) NULL,
    measure      DECIMAL(12,4) NOT NULL DEFAULT 0.0000,
    unit_price   DECIMAL(15,2) NOT NULL DEFAULT 0.00,

    -- Chosen components, e.g. "Roller: Standard Roll | Bottom Rail: Flat".
    component_options VARCHAR(255)  NULL,
    line_discount_pct DECIMAL(5,2)  NULL,
    line_total        DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    line_discount_amt DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    line_net          DECIMAL(15,2) NOT NULL DEFAULT 0.00,

    KEY ix_soi_order (sales_order_id),
    CONSTRAINT fk_soi_order   FOREIGN KEY (sales_order_id)
        REFERENCES sales_orders (id) ON DELETE CASCADE,
    CONSTRAINT fk_soi_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- purchase_orders - raw materials, optionally tied to the SO they serve.
-- That link is what makes the gross-margin report possible.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS purchase_orders (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    po_no          VARCHAR(30) NOT NULL,
    -- The entity that issued this document.
    company_id     INT         NOT NULL,
    supplier_id    INT         NOT NULL,
    sales_order_id INT         NULL,
    order_date     DATE        NOT NULL,
    expected_date  DATE        NULL,
    -- draft | sent | received | cancelled
    status         VARCHAR(20) NOT NULL DEFAULT 'draft',

    currency      VARCHAR(10)   NOT NULL DEFAULT 'IDR',
    exchange_rate DECIMAL(15,4) NOT NULL DEFAULT 1.0000,
    payment_terms VARCHAR(60)   NULL,
    ppn_percent   DECIMAL(5,2)  NOT NULL DEFAULT 11.00,

    subtotal   DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    ppn_amount DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    total      DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    total_qty  DECIMAL(12,2) NOT NULL DEFAULT 0.00,

    notes      TEXT     NULL,
    created_by INT      NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_po_no (po_no),
    KEY ix_po_status (status),
    KEY ix_po_supplier (supplier_id),
    KEY ix_po_sales_order (sales_order_id),
    CONSTRAINT fk_po_supplier FOREIGN KEY (supplier_id)    REFERENCES suppliers (id),
    CONSTRAINT fk_po_so       FOREIGN KEY (sales_order_id) REFERENCES sales_orders (id),
    CONSTRAINT fk_po_user     FOREIGN KEY (created_by)     REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS purchase_order_items (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    purchase_order_id INT NOT NULL,
    line_no           INT NOT NULL,
    -- Raw materials often are not finished goods, so product_id is optional
    -- and the free-text description carries the item.
    product_id  INT           NULL,
    description VARCHAR(255)  NOT NULL,
    unit        VARCHAR(20)   NOT NULL DEFAULT 'pcs',
    quantity    DECIMAL(12,2) NOT NULL DEFAULT 1.00,
    unit_price  DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    line_total  DECIMAL(15,2) NOT NULL DEFAULT 0.00,

    KEY ix_poi_order (purchase_order_id),
    CONSTRAINT fk_poi_order   FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders (id) ON DELETE CASCADE,
    CONSTRAINT fk_poi_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- delivery_notes - Surat Jalan, the document that travels with the goods.
--
-- One sales order can be delivered in several trips, so this is its own
-- document with its own number rather than a view of the order. Deliberately
-- carries no prices: the driver and whoever signs at the far end should not
-- be handed the customer pricing.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery_notes (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    sj_no          VARCHAR(30) NOT NULL,
    -- The entity that issued this document.
    company_id     INT         NOT NULL,
    sales_order_id INT         NOT NULL,
    delivery_date  DATE        NOT NULL,
    -- draft | issued | delivered | cancelled
    status         VARCHAR(20) NOT NULL DEFAULT 'draft',

    -- Snapshot of where it went, which can differ per trip.
    deliver_to      VARCHAR(150) NULL,
    deliver_address TEXT         NULL,
    phone           VARCHAR(40)  NULL,

    -- Scheduling: which slot of the day the run is planned for.
    time_slot      VARCHAR(20)  NULL,   -- morning | afternoon | evening
    vehicle_no     VARCHAR(30)  NULL,
    driver_name    VARCHAR(120) NULL,
    -- Filled in when the goods are signed for.
    received_by    VARCHAR(120) NULL,
    received_at    DATE         NULL,

    notes      TEXT     NULL,
    created_by INT      NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_sj_no (sj_no),
    KEY ix_sj_status (status),
    KEY ix_sj_sales_order (sales_order_id),
    CONSTRAINT fk_sj_order FOREIGN KEY (sales_order_id) REFERENCES sales_orders (id),
    CONSTRAINT fk_sj_user  FOREIGN KEY (created_by)     REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS delivery_note_items (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    delivery_note_id INT NOT NULL,
    line_no          INT NOT NULL,
    -- Which order line this consignment draws down.
    sales_order_item_id INT NOT NULL,

    product_code VARCHAR(40)  NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    description  VARCHAR(255) NULL,
    -- Sizes matter on site: the installer checks them against the window.
    width_cm     DECIMAL(10,2) NULL,
    height_cm    DECIMAL(10,2) NULL,
    quantity     DECIMAL(12,2) NOT NULL DEFAULT 1.00,
    unit         VARCHAR(20)   NOT NULL DEFAULT 'pcs',

    KEY ix_sji_note (delivery_note_id),
    CONSTRAINT fk_sji_note FOREIGN KEY (delivery_note_id)
        REFERENCES delivery_notes (id) ON DELETE CASCADE,
    CONSTRAINT fk_sji_order_item FOREIGN KEY (sales_order_item_id)
        REFERENCES sales_order_items (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- receipts - payments received against a sales order (kwitansi)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS receipts (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    receipt_no     VARCHAR(30)   NOT NULL,
    -- The entity that issued this document.
    company_id     INT         NOT NULL,
    sales_order_id INT           NOT NULL,
    receipt_date   DATE          NOT NULL,
    amount         DECIMAL(15,2) NOT NULL,
    -- cash | transfer | cheque | card | other
    payment_method VARCHAR(20)   NOT NULL DEFAULT 'transfer',
    reference      VARCHAR(120)  NULL,     -- bank ref / cheque no
    received_from  VARCHAR(150)  NULL,
    notes          TEXT          NULL,
    created_by     INT           NULL,
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_receipt_no (receipt_no),
    KEY ix_receipt_so (sales_order_id),
    CONSTRAINT fk_receipt_so   FOREIGN KEY (sales_order_id) REFERENCES sales_orders (id),
    CONSTRAINT fk_receipt_user FOREIGN KEY (created_by)     REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Deferred foreign keys: these point at tables created later in this file.
-- ---------------------------------------------------------------------
ALTER TABLE products
    ADD CONSTRAINT fk_products_supplier FOREIGN KEY (supplier_id)
    REFERENCES suppliers (id);

ALTER TABLE users
    ADD CONSTRAINT fk_users_company FOREIGN KEY (default_company_id)
    REFERENCES companies (id);
ALTER TABLE quotations
    ADD CONSTRAINT fk_quotations_company FOREIGN KEY (company_id)
    REFERENCES companies (id);
ALTER TABLE sales_orders
    ADD CONSTRAINT fk_so_company FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE purchase_orders
    ADD CONSTRAINT fk_po_company FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE delivery_notes
    ADD CONSTRAINT fk_sj_company FOREIGN KEY (company_id) REFERENCES companies (id);
ALTER TABLE receipts
    ADD CONSTRAINT fk_receipt_company FOREIGN KEY (company_id) REFERENCES companies (id);
