"""SQLAlchemy models mirroring schema.sql."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import relationship

from database import Base


class Dec(TypeDecorator):
    """DECIMAL that survives SQLite.

    SQLite has no native decimal type, so SQLAlchemy would round-trip values
    through float and warn about it. Store as TEXT there and convert back to
    Decimal on read; MySQL gets a real DECIMAL column.
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, precision=15, scale=2):
        self.precision = precision
        self.scale = scale
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(32))
        return dialect.type_descriptor(Numeric(self.precision, self.scale))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        quant = Decimal(1).scaleb(-self.scale)
        value = Decimal(str(value)).quantize(quant)
        return str(value) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(str(value))


def Money():
    return Dec(15, 2)


def Pct():
    return Dec(5, 2)


def Qty():
    return Dec(12, 2)


class Company(Base):
    """A legal entity that issues documents.

    Three of them share the product catalogue, customers and suppliers; what
    differs is the letterhead, the bank account and the document numbering.
    """

    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    # Short code that appears inside document numbers: Q-GB-202608-001.
    code = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    tagline = Column(String(150))

    address = Column(String(255))
    city = Column(String(120))
    phone = Column(String(60))
    email = Column(String(120))
    website = Column(String(120))
    npwp = Column(String(40))

    bank_name = Column(String(120))
    bank_account = Column(String(60))
    bank_holder = Column(String(150))
    signatory = Column(String(120))

    logo_filename = Column(String(120))
    quotation_terms = Column(Text)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(120))
    password_hash = Column(String(255), nullable=False)
    # 'admin' or 'user' - see auth.ROLES
    role = Column(String(20), nullable=False, default="user")
    is_active = Column(Boolean, nullable=False, default=True)
    # Pre-selected on new documents; the user may still choose another.
    default_company_id = Column(Integer, ForeignKey("companies.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    default_company = relationship("Company", lazy="joined")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    code = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    nik_npwp = Column(String(40))
    address = Column(Text)
    deliver_to = Column(String(150))
    deliver_address = Column(Text)
    phone = Column(String(40))
    email = Column(String(120))
    price_group = Column(String(30))
    payment_terms = Column(String(60))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    code = Column(String(40), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    category = Column(String(60))
    price_unit = Column(String(20), nullable=False, default="per_sqm")
    unit_price = Column(Money(), nullable=False, default=Decimal("0.00"))
    min_width_cm = Column(Qty())
    max_width_cm = Column(Qty())
    min_height_cm = Column(Qty())
    max_height_cm = Column(Qty())
    description = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    supplier_id = Column(Integer, ForeignKey("suppliers.id"), index=True)

    supplier = relationship("Supplier", lazy="joined")
    options = relationship(
        "ProductOption",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductOption.option_group",
        lazy="selectin",
    )
    colors = relationship(
        "ProductColor",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductColor.color_name",
        lazy="selectin",
    )


class Quotation(Base):
    __tablename__ = "quotations"

    id = Column(Integer, primary_key=True)
    quotation_no = Column(String(30), unique=True, nullable=False, index=True)
    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    quotation_date = Column(Date, nullable=False, default=date.today)
    last_follow_up = Column(Date)
    status = Column(String(20), nullable=False, default="draft", index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    # Snapshot of customer details at quotation time - the master may change
    # later, a printed quotation must not.
    nik_npwp = Column(String(40))
    surveyor = Column(String(120))
    address = Column(Text)
    deliver_to = Column(String(150))
    deliver_address = Column(Text)
    phone = Column(String(40))
    email = Column(String(120))

    currency = Column(String(10), nullable=False, default="IDR")
    exchange_rate = Column(Dec(15, 4), nullable=False, default=Decimal("1.0000"))
    price_group = Column(String(30))
    payment_terms = Column(String(60))

    discount_percent = Column(Pct(), nullable=False, default=Decimal("35.00"))
    ppn_percent = Column(Pct(), nullable=False, default=Decimal("11.00"))
    installation_cost = Column(Money(), nullable=False, default=Decimal("0.00"))
    dp_percent = Column(Pct())
    dp_amount = Column(Money(), nullable=False, default=Decimal("0.00"))

    subtotal = Column(Money(), nullable=False, default=Decimal("0.00"))
    discount_amount = Column(Money(), nullable=False, default=Decimal("0.00"))
    netto = Column(Money(), nullable=False, default=Decimal("0.00"))
    ppn_amount = Column(Money(), nullable=False, default=Decimal("0.00"))
    total = Column(Money(), nullable=False, default=Decimal("0.00"))
    total_qty = Column(Qty(), nullable=False, default=Decimal("0.00"))

    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    customer = relationship("Customer", lazy="joined")
    creator = relationship("User", lazy="joined")
    company = relationship("Company", lazy="joined")
    items = relationship(
        "QuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="QuotationItem.line_no",
        lazy="selectin",
    )


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True)
    quotation_id = Column(
        Integer,
        ForeignKey("quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no = Column(Integer, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    product_code = Column(String(40), nullable=False)
    product_name = Column(String(150), nullable=False)
    price_unit = Column(String(20), nullable=False)

    description = Column(String(255))
    quantity = Column(Qty(), nullable=False, default=Decimal("1.00"))
    width_cm = Column(Qty())
    height_cm = Column(Qty())
    # Billable measure: sqm, running metres, or pieces (depends on price_unit).
    measure = Column(Dec(12, 4), nullable=False, default=Decimal("0.0000"))
    unit_price = Column(Money(), nullable=False, default=Decimal("0.00"))

    component_options = Column(String(255))
    line_discount_pct = Column(Pct())
    line_total = Column(Money(), nullable=False, default=Decimal("0.00"))
    line_discount_amt = Column(Money(), nullable=False, default=Decimal("0.00"))
    line_net = Column(Money(), nullable=False, default=Decimal("0.00"))

    quotation = relationship("Quotation", back_populates="items")


class ProductOption(Base):
    """A mechanism or rail a fabric can be made in.

    Imported from the workbook's FABRIC CHART sheet. `is_available` is False
    where the chart says "x" - the option exists but is not recommended for
    that fabric, so the UI hides it rather than offering a bad combination.
    """

    __tablename__ = "product_options"

    id = Column(Integer, primary_key=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    option_group = Column(String(40), nullable=False, index=True)
    option_name = Column(String(60), nullable=False)
    is_available = Column(Boolean, nullable=False, default=True)
    source_ref = Column(String(40))

    product = relationship("Product", back_populates="options")


class ProductColor(Base):
    """One colour variant of a product, imported from the client catalogue.

    Size caps sit here rather than on Product because they vary per colour.

    stock_status: in_stock | limited_stock | out_of_stock | discontinued |
    will_discontinue | new_range | unknown | legacy. See schema.sql for what
    each one means and why 'unknown' exists.
    """

    __tablename__ = "product_colors"

    id = Column(Integer, primary_key=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    color_name = Column(String(100), nullable=False, index=True)
    fabric_code = Column(String(30))
    max_width_cm = Column(Dec(6, 2))
    max_height_cm = Column(Dec(6, 2))
    stock_status = Column(String(20), nullable=False, default="unknown", index=True)

    # Provenance for a hand-maintained source workbook.
    raw_label = Column(String(255))
    source_ref = Column(String(40))
    notes = Column(String(255))

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    product = relationship("Product", back_populates="colors")


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    code = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    contact_person = Column(String(120))
    address = Column(Text)
    phone = Column(String(40))
    email = Column(String(120))
    payment_terms = Column(String(60))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SalesOrder(Base):
    __tablename__ = "sales_orders"

    id = Column(Integer, primary_key=True)
    so_no = Column(String(30), unique=True, nullable=False, index=True)
    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    quotation_id = Column(Integer, ForeignKey("quotations.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    order_date = Column(Date, nullable=False, default=date.today)
    delivery_date = Column(Date)
    status = Column(String(20), nullable=False, default="draft", index=True)

    nik_npwp = Column(String(40))
    surveyor = Column(String(120))
    address = Column(Text)
    deliver_to = Column(String(150))
    deliver_address = Column(Text)
    phone = Column(String(40))
    email = Column(String(120))

    currency = Column(String(10), nullable=False, default="IDR")
    exchange_rate = Column(Dec(15, 4), nullable=False, default=Decimal("1.0000"))
    price_group = Column(String(30))
    payment_terms = Column(String(60))
    po_reference = Column(String(60))

    discount_percent = Column(Pct(), nullable=False, default=Decimal("35.00"))
    ppn_percent = Column(Pct(), nullable=False, default=Decimal("11.00"))
    installation_cost = Column(Money(), nullable=False, default=Decimal("0.00"))
    dp_percent = Column(Pct())
    dp_amount = Column(Money(), nullable=False, default=Decimal("0.00"))

    subtotal = Column(Money(), nullable=False, default=Decimal("0.00"))
    discount_amount = Column(Money(), nullable=False, default=Decimal("0.00"))
    netto = Column(Money(), nullable=False, default=Decimal("0.00"))
    ppn_amount = Column(Money(), nullable=False, default=Decimal("0.00"))
    total = Column(Money(), nullable=False, default=Decimal("0.00"))
    total_qty = Column(Qty(), nullable=False, default=Decimal("0.00"))

    # Closing the receivable (closing pembayaran piutang): set once the
    # invoice is settled, so it drops out of outstanding receivables.
    receivable_closed_at = Column(Date)
    receivable_closed_by = Column(Integer, ForeignKey("users.id"))
    receivable_close_note = Column(String(255))

    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    customer = relationship("Customer", lazy="joined")
    creator = relationship("User", lazy="joined", foreign_keys=[created_by])
    closed_by = relationship("User", lazy="joined", foreign_keys=[receivable_closed_by])
    company = relationship("Company", lazy="joined")
    quotation = relationship("Quotation", lazy="joined")
    items = relationship(
        "SalesOrderItem",
        back_populates="sales_order",
        cascade="all, delete-orphan",
        order_by="SalesOrderItem.line_no",
        lazy="selectin",
    )
    receipts = relationship(
        "Receipt", back_populates="sales_order", lazy="selectin",
        order_by="Receipt.receipt_date",
    )
    delivery_notes = relationship(
        "DeliveryNote", back_populates="sales_order", lazy="selectin",
        order_by="DeliveryNote.delivery_date",
    )


class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"

    id = Column(Integer, primary_key=True)
    sales_order_id = Column(
        Integer,
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no = Column(Integer, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    product_code = Column(String(40), nullable=False)
    product_name = Column(String(150), nullable=False)
    price_unit = Column(String(20), nullable=False)

    description = Column(String(255))
    quantity = Column(Qty(), nullable=False, default=Decimal("1.00"))
    width_cm = Column(Qty())
    height_cm = Column(Qty())
    measure = Column(Dec(12, 4), nullable=False, default=Decimal("0.0000"))
    unit_price = Column(Money(), nullable=False, default=Decimal("0.00"))

    component_options = Column(String(255))
    line_discount_pct = Column(Pct())
    line_total = Column(Money(), nullable=False, default=Decimal("0.00"))
    line_discount_amt = Column(Money(), nullable=False, default=Decimal("0.00"))
    line_net = Column(Money(), nullable=False, default=Decimal("0.00"))

    sales_order = relationship("SalesOrder", back_populates="items")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True)
    po_no = Column(String(30), unique=True, nullable=False, index=True)
    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), index=True)
    order_date = Column(Date, nullable=False, default=date.today)
    expected_date = Column(Date)
    status = Column(String(20), nullable=False, default="draft", index=True)

    currency = Column(String(10), nullable=False, default="IDR")
    exchange_rate = Column(Dec(15, 4), nullable=False, default=Decimal("1.0000"))
    payment_terms = Column(String(60))
    ppn_percent = Column(Pct(), nullable=False, default=Decimal("11.00"))

    subtotal = Column(Money(), nullable=False, default=Decimal("0.00"))
    ppn_amount = Column(Money(), nullable=False, default=Decimal("0.00"))
    total = Column(Money(), nullable=False, default=Decimal("0.00"))
    total_qty = Column(Qty(), nullable=False, default=Decimal("0.00"))

    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    supplier = relationship("Supplier", lazy="joined")
    creator = relationship("User", lazy="joined")
    company = relationship("Company", lazy="joined")
    sales_order = relationship("SalesOrder", lazy="joined")
    items = relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderItem.line_no",
        lazy="selectin",
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(
        Integer,
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no = Column(Integer, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"))
    description = Column(String(255), nullable=False)
    unit = Column(String(20), nullable=False, default="pcs")
    quantity = Column(Qty(), nullable=False, default=Decimal("1.00"))
    unit_price = Column(Money(), nullable=False, default=Decimal("0.00"))
    line_total = Column(Money(), nullable=False, default=Decimal("0.00"))

    purchase_order = relationship("PurchaseOrder", back_populates="items")


class DeliveryNote(Base):
    """Surat Jalan - travels with the goods, carries no prices."""

    __tablename__ = "delivery_notes"

    id = Column(Integer, primary_key=True)
    sj_no = Column(String(30), unique=True, nullable=False, index=True)
    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    sales_order_id = Column(
        Integer, ForeignKey("sales_orders.id"), nullable=False, index=True
    )
    delivery_date = Column(Date, nullable=False, default=date.today)
    status = Column(String(20), nullable=False, default="draft", index=True)

    deliver_to = Column(String(150))
    deliver_address = Column(Text)
    phone = Column(String(40))

    time_slot = Column(String(20))          # morning | afternoon | evening
    vehicle_no = Column(String(30))
    driver_name = Column(String(120))
    received_by = Column(String(120))
    received_at = Column(Date)

    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    sales_order = relationship("SalesOrder", back_populates="delivery_notes")
    creator = relationship("User", lazy="joined")
    company = relationship("Company", lazy="joined")
    items = relationship(
        "DeliveryNoteItem",
        back_populates="delivery_note",
        cascade="all, delete-orphan",
        order_by="DeliveryNoteItem.line_no",
        lazy="selectin",
    )


class DeliveryNoteItem(Base):
    __tablename__ = "delivery_note_items"

    id = Column(Integer, primary_key=True)
    delivery_note_id = Column(
        Integer,
        ForeignKey("delivery_notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no = Column(Integer, nullable=False)
    sales_order_item_id = Column(
        Integer, ForeignKey("sales_order_items.id"), nullable=False
    )

    product_code = Column(String(40), nullable=False)
    product_name = Column(String(150), nullable=False)
    description = Column(String(255))
    width_cm = Column(Qty())
    height_cm = Column(Qty())
    quantity = Column(Qty(), nullable=False, default=Decimal("1.00"))
    unit = Column(String(20), nullable=False, default="pcs")

    delivery_note = relationship("DeliveryNote", back_populates="items")


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True)
    receipt_no = Column(String(30), unique=True, nullable=False, index=True)
    company_id = Column(
        Integer, ForeignKey("companies.id"), nullable=False, index=True
    )
    sales_order_id = Column(
        Integer, ForeignKey("sales_orders.id"), nullable=False, index=True
    )
    receipt_date = Column(Date, nullable=False, default=date.today)
    amount = Column(Money(), nullable=False)
    payment_method = Column(String(20), nullable=False, default="transfer")
    reference = Column(String(120))
    received_from = Column(String(150))
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    sales_order = relationship("SalesOrder", back_populates="receipts")
    creator = relationship("User", lazy="joined")
    company = relationship("Company", lazy="joined")
