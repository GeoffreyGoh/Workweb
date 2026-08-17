"""Pydantic request/response models."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

PriceUnit = Literal["per_sqm", "per_unit", "per_meter"]
Role = Literal["admin", "user"]
QuotationStatus = Literal["draft", "sent", "approved", "converted", "cancelled"]
SalesOrderStatus = Literal[
    "draft", "confirmed", "in_production", "delivered", "completed", "cancelled"
]
PurchaseOrderStatus = Literal["draft", "sent", "received", "cancelled"]
DeliveryNoteStatus = Literal["draft", "issued", "delivered", "cancelled"]
PaymentMethod = Literal["cash", "transfer", "cheque", "card", "other"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- companies
class CompanyBase(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    name: str = Field(min_length=1, max_length=150)
    tagline: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    npwp: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_holder: Optional[str] = None
    signatory: Optional[str] = None
    logo_filename: Optional[str] = None
    quotation_terms: Optional[str] = None
    is_active: bool = True


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    tagline: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    npwp: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_holder: Optional[str] = None
    signatory: Optional[str] = None
    logo_filename: Optional[str] = None
    quotation_terms: Optional[str] = None
    is_active: Optional[bool] = None


class CompanyOut(ORMModel, CompanyBase):
    id: int


# --------------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: int
    username: str
    full_name: str
    email: Optional[str] = None
    role: str
    is_active: bool
    default_company_id: Optional[int] = None


# ----------------------------------------------------------------- products
class ProductBase(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=150)
    category: Optional[str] = None
    price_unit: PriceUnit = "per_sqm"
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=0)
    min_width_cm: Optional[Decimal] = Field(default=None, ge=0)
    max_width_cm: Optional[Decimal] = Field(default=None, ge=0)
    min_height_cm: Optional[Decimal] = Field(default=None, ge=0)
    max_height_cm: Optional[Decimal] = Field(default=None, ge=0)
    description: Optional[str] = None
    is_active: bool = True
    # Default supplier, used to split purchase orders per supplier.
    supplier_id: Optional[int] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    supplier_id: Optional[int] = None
    price_unit: Optional[PriceUnit] = None
    unit_price: Optional[Decimal] = Field(default=None, ge=0)
    min_width_cm: Optional[Decimal] = Field(default=None, ge=0)
    max_width_cm: Optional[Decimal] = Field(default=None, ge=0)
    min_height_cm: Optional[Decimal] = Field(default=None, ge=0)
    max_height_cm: Optional[Decimal] = Field(default=None, ge=0)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ProductOptionOut(ORMModel):
    option_group: str
    option_name: str
    is_available: bool


class ProductOut(ORMModel, ProductBase):
    id: int
    supplier_name: Optional[str] = None
    # Mechanisms/rails this fabric can be made in (FABRIC CHART).
    options: List[ProductOptionOut] = Field(default_factory=list)


# ---------------------------------------------------------------- customers
class CustomerBase(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=150)
    nik_npwp: Optional[str] = None
    address: Optional[str] = None
    deliver_to: Optional[str] = None
    deliver_address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    price_group: Optional[str] = None
    payment_terms: Optional[str] = None
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    nik_npwp: Optional[str] = None
    address: Optional[str] = None
    deliver_to: Optional[str] = None
    deliver_address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    price_group: Optional[str] = None
    payment_terms: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerOut(ORMModel, CustomerBase):
    id: int


# --------------------------------------------------------------- quotations
class QuotationItemIn(BaseModel):
    """A submitted line. Money fields other than unit_price are ignored -
    the server recalculates them."""

    product_id: int
    description: Optional[str] = None
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    width_cm: Optional[Decimal] = Field(default=None, ge=0)
    height_cm: Optional[Decimal] = Field(default=None, ge=0)
    unit_price: Optional[Decimal] = Field(default=None, ge=0)
    line_discount_pct: Optional[Decimal] = Field(default=None, ge=0, le=100)
    # Chosen mechanism/rail, e.g. "Roller: Standard Roll | Bottom Rail: Flat".
    component_options: Optional[str] = Field(default=None, max_length=255)


class QuotationItemOut(ORMModel):
    component_options: Optional[str] = None
    id: int
    line_no: int
    product_id: int
    product_code: str
    product_name: str
    price_unit: str
    description: Optional[str] = None
    quantity: Decimal
    width_cm: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None
    measure: Decimal
    unit_price: Decimal
    line_discount_pct: Optional[Decimal] = None
    line_total: Decimal
    line_discount_amt: Decimal
    line_net: Decimal


class QuotationBase(BaseModel):
    customer_id: int
    # Which entity issues this. Defaults to the user's own company.
    company_id: Optional[int] = None
    quotation_date: Optional[date] = None
    last_follow_up: Optional[date] = None

    # Left blank, these are copied from the customer master on create.
    nik_npwp: Optional[str] = None
    surveyor: Optional[str] = None
    address: Optional[str] = None
    deliver_to: Optional[str] = None
    deliver_address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    currency: str = "IDR"
    exchange_rate: Decimal = Field(default=Decimal("1"), gt=0)
    price_group: Optional[str] = None
    payment_terms: Optional[str] = None

    # Business rule: base 35%, freely editable per quotation.
    discount_percent: Decimal = Field(default=Decimal("35.00"), ge=0, le=100)
    ppn_percent: Decimal = Field(default=Decimal("11.00"), ge=0, le=100)
    installation_cost: Decimal = Field(default=Decimal("0"), ge=0)
    # TOP / down payment the customer pays up front.
    dp_percent: Optional[Decimal] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None


class QuotationCreate(QuotationBase):
    items: List[QuotationItemIn] = Field(default_factory=list)


class QuotationUpdate(QuotationBase):
    items: Optional[List[QuotationItemIn]] = None


class QuotationListOut(ORMModel):
    id: int
    quotation_no: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    quotation_date: date
    last_follow_up: Optional[date] = None
    status: str
    customer_id: int
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    currency: str
    total: Decimal
    total_qty: Decimal
    created_at: datetime
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    # False when this row belongs to someone else and you are not an admin.
    can_edit: bool = True


class QuotationOut(ORMModel):
    id: int
    quotation_no: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    quotation_date: date
    last_follow_up: Optional[date] = None
    status: str

    customer_id: int
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    nik_npwp: Optional[str] = None
    surveyor: Optional[str] = None
    address: Optional[str] = None
    deliver_to: Optional[str] = None
    deliver_address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    currency: str
    exchange_rate: Decimal
    price_group: Optional[str] = None
    payment_terms: Optional[str] = None

    discount_percent: Decimal
    ppn_percent: Decimal
    installation_cost: Decimal = Decimal("0.00")
    dp_percent: Optional[Decimal] = None
    dp_amount: Decimal = Decimal("0.00")
    dp_balance: Decimal = Decimal("0.00")

    subtotal: Decimal
    discount_amount: Decimal
    netto: Decimal
    ppn_amount: Decimal
    total: Decimal
    total_qty: Decimal

    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: List[QuotationItemOut] = Field(default_factory=list)


class StatusUpdate(BaseModel):
    status: QuotationStatus


# ---------------------------------------------------------------- suppliers
class SupplierBase(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=150)
    contact_person: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    payment_terms: Optional[str] = None
    is_active: bool = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    payment_terms: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierOut(ORMModel, SupplierBase):
    id: int


# ------------------------------------------------------------ sales orders
class SalesOrderItemIn(QuotationItemIn):
    """Same shape as a quotation line - SO lines are priced identically."""


class SalesOrderItemOut(QuotationItemOut):
    pass


class SalesOrderBase(BaseModel):
    customer_id: int
    company_id: Optional[int] = None
    quotation_id: Optional[int] = None
    order_date: Optional[date] = None
    delivery_date: Optional[date] = None

    nik_npwp: Optional[str] = None
    surveyor: Optional[str] = None
    address: Optional[str] = None
    deliver_to: Optional[str] = None
    deliver_address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    currency: str = "IDR"
    exchange_rate: Decimal = Field(default=Decimal("1"), gt=0)
    price_group: Optional[str] = None
    payment_terms: Optional[str] = None
    po_reference: Optional[str] = None

    discount_percent: Decimal = Field(default=Decimal("35.00"), ge=0, le=100)
    ppn_percent: Decimal = Field(default=Decimal("11.00"), ge=0, le=100)
    installation_cost: Decimal = Field(default=Decimal("0"), ge=0)
    # TOP / down payment the customer pays up front.
    dp_percent: Optional[Decimal] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None


class SalesOrderCreate(SalesOrderBase):
    items: List[SalesOrderItemIn] = Field(default_factory=list)


class SalesOrderUpdate(SalesOrderBase):
    items: Optional[List[SalesOrderItemIn]] = None


class SalesOrderListOut(ORMModel):
    id: int
    so_no: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    order_date: date
    delivery_date: Optional[date] = None
    status: str
    customer_id: int
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    quotation_id: Optional[int] = None
    quotation_no: Optional[str] = None
    currency: str
    total: Decimal
    total_qty: Decimal
    amount_paid: Decimal = Decimal("0.00")
    balance_due: Decimal = Decimal("0.00")
    created_at: datetime
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    can_edit: bool = True


class SalesOrderOut(ORMModel):
    id: int
    so_no: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    quotation_id: Optional[int] = None
    quotation_no: Optional[str] = None
    order_date: date
    delivery_date: Optional[date] = None
    status: str

    customer_id: int
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    nik_npwp: Optional[str] = None
    surveyor: Optional[str] = None
    address: Optional[str] = None
    deliver_to: Optional[str] = None
    deliver_address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    currency: str
    exchange_rate: Decimal
    price_group: Optional[str] = None
    payment_terms: Optional[str] = None
    po_reference: Optional[str] = None

    discount_percent: Decimal
    ppn_percent: Decimal
    installation_cost: Decimal = Decimal("0.00")
    dp_percent: Optional[Decimal] = None
    dp_amount: Decimal = Decimal("0.00")
    dp_balance: Decimal = Decimal("0.00")

    subtotal: Decimal
    discount_amount: Decimal
    netto: Decimal
    ppn_amount: Decimal
    total: Decimal
    total_qty: Decimal

    amount_paid: Decimal = Decimal("0.00")
    balance_due: Decimal = Decimal("0.00")

    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: List[SalesOrderItemOut] = Field(default_factory=list)


class SalesOrderStatusUpdate(BaseModel):
    status: SalesOrderStatus


# --------------------------------------------------------- purchase orders
class PurchaseOrderItemIn(BaseModel):
    product_id: Optional[int] = None
    description: str = Field(min_length=1, max_length=255)
    unit: str = Field(default="pcs", max_length=20)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(default=Decimal("0"), ge=0)


class PurchaseOrderItemOut(ORMModel):
    id: int
    line_no: int
    product_id: Optional[int] = None
    description: str
    unit: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class PurchaseOrderBase(BaseModel):
    supplier_id: int
    company_id: Optional[int] = None
    sales_order_id: Optional[int] = None
    order_date: Optional[date] = None
    expected_date: Optional[date] = None
    currency: str = "IDR"
    exchange_rate: Decimal = Field(default=Decimal("1"), gt=0)
    payment_terms: Optional[str] = None
    ppn_percent: Decimal = Field(default=Decimal("11.00"), ge=0, le=100)
    notes: Optional[str] = None


class PurchaseOrderCreate(PurchaseOrderBase):
    items: List[PurchaseOrderItemIn] = Field(default_factory=list)


class PurchaseOrderUpdate(PurchaseOrderBase):
    items: Optional[List[PurchaseOrderItemIn]] = None


class PurchaseOrderListOut(ORMModel):
    id: int
    po_no: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    order_date: date
    expected_date: Optional[date] = None
    status: str
    supplier_id: int
    supplier_name: Optional[str] = None
    supplier_code: Optional[str] = None
    sales_order_id: Optional[int] = None
    so_no: Optional[str] = None
    currency: str
    total: Decimal
    created_at: datetime
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    can_edit: bool = True


class PurchaseOrderOut(ORMModel):
    id: int
    po_no: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    supplier_id: int
    supplier_name: Optional[str] = None
    supplier_code: Optional[str] = None
    supplier_address: Optional[str] = None
    sales_order_id: Optional[int] = None
    so_no: Optional[str] = None
    order_date: date
    expected_date: Optional[date] = None
    status: str

    currency: str
    exchange_rate: Decimal
    payment_terms: Optional[str] = None
    ppn_percent: Decimal

    subtotal: Decimal
    ppn_amount: Decimal
    total: Decimal
    total_qty: Decimal

    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: List[PurchaseOrderItemOut] = Field(default_factory=list)


class PurchaseOrderStatusUpdate(BaseModel):
    status: PurchaseOrderStatus


# ----------------------------------------------------- delivery notes (SJ)
class DeliveryNoteItemIn(BaseModel):
    sales_order_item_id: int
    quantity: Decimal = Field(gt=0)
    unit: str = Field(default="pcs", max_length=20)
    description: Optional[str] = None


class DeliveryNoteItemOut(ORMModel):
    id: int
    line_no: int
    sales_order_item_id: int
    product_code: str
    product_name: str
    description: Optional[str] = None
    width_cm: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None
    quantity: Decimal
    unit: str


class DeliveryNoteBase(BaseModel):
    company_id: Optional[int] = None
    delivery_date: Optional[date] = None
    time_slot: Optional[Literal["morning", "afternoon", "evening"]] = None
    deliver_to: Optional[str] = None
    deliver_address: Optional[str] = None
    phone: Optional[str] = None
    vehicle_no: Optional[str] = None
    driver_name: Optional[str] = None
    notes: Optional[str] = None


class DeliveryNoteCreate(DeliveryNoteBase):
    sales_order_id: int
    items: List[DeliveryNoteItemIn] = Field(default_factory=list)


class DeliveryNoteUpdate(DeliveryNoteBase):
    items: Optional[List[DeliveryNoteItemIn]] = None


class DeliveryNoteListOut(ORMModel):
    id: int
    sj_no: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    delivery_date: date
    time_slot: Optional[str] = None
    status: str
    sales_order_id: int
    so_no: Optional[str] = None
    customer_name: Optional[str] = None
    deliver_to: Optional[str] = None
    vehicle_no: Optional[str] = None
    driver_name: Optional[str] = None
    total_qty: Decimal = Decimal("0.00")
    line_count: int = 0
    created_at: datetime
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    can_edit: bool = True


class DeliveryNoteOut(ORMModel):
    id: int
    sj_no: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    sales_order_id: int
    so_no: Optional[str] = None
    customer_name: Optional[str] = None
    customer_code: Optional[str] = None
    po_reference: Optional[str] = None
    delivery_date: date
    time_slot: Optional[str] = None
    status: str

    deliver_to: Optional[str] = None
    deliver_address: Optional[str] = None
    phone: Optional[str] = None
    vehicle_no: Optional[str] = None
    driver_name: Optional[str] = None
    received_by: Optional[str] = None
    received_at: Optional[date] = None

    notes: Optional[str] = None
    total_qty: Decimal = Decimal("0.00")
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    items: List[DeliveryNoteItemOut] = Field(default_factory=list)


class DeliveryNoteStatusUpdate(BaseModel):
    status: DeliveryNoteStatus
    received_by: Optional[str] = None
    received_at: Optional[date] = None


class OutstandingLine(BaseModel):
    """How much of one order line is still waiting to go out."""

    sales_order_item_id: int
    line_no: int
    product_code: str
    product_name: str
    description: Optional[str] = None
    width_cm: Optional[Decimal] = None
    height_cm: Optional[Decimal] = None
    ordered: Decimal
    delivered: Decimal
    outstanding: Decimal


class SalesOrderDeliveryStatus(BaseModel):
    sales_order_id: int
    so_no: str
    fully_delivered: bool
    lines: List[OutstandingLine] = Field(default_factory=list)


# ----------------------------------------------------------------- receipts
class ReceiptCreate(BaseModel):
    sales_order_id: int
    company_id: Optional[int] = None
    receipt_date: Optional[date] = None
    amount: Decimal = Field(gt=0)
    payment_method: PaymentMethod = "transfer"
    reference: Optional[str] = None
    received_from: Optional[str] = None
    notes: Optional[str] = None


class ReceiptOut(ORMModel):
    id: int
    receipt_no: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    sales_order_id: int
    so_no: Optional[str] = None
    customer_name: Optional[str] = None
    receipt_date: date
    amount: Decimal
    payment_method: str
    reference: Optional[str] = None
    received_from: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    can_edit: bool = True


# ------------------------------------------------------------------ reports
class PeriodBucket(BaseModel):
    period: str
    quotation_count: int = 0
    quotation_value: Decimal = Decimal("0.00")
    order_count: int = 0
    order_value: Decimal = Decimal("0.00")


class CustomerSales(BaseModel):
    customer_id: int
    customer_code: Optional[str] = None
    customer_name: str
    order_count: int
    order_value: Decimal


class ProductSales(BaseModel):
    product_code: str
    product_name: str
    quantity: Decimal
    measure: Decimal
    value: Decimal


class UserSales(BaseModel):
    created_by: Optional[int] = None
    created_by_name: str
    quotation_count: int
    quotation_value: Decimal
    order_count: int
    order_value: Decimal
    conversion_rate: Decimal


class SalesReport(BaseModel):
    date_from: date
    date_to: date
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    currency: str = "IDR"

    quotation_count: int
    quotation_value: Decimal
    order_count: int
    order_value: Decimal
    # Orders raised / quotations issued, in percent.
    conversion_rate: Decimal

    by_period: List[PeriodBucket] = Field(default_factory=list)
    by_customer: List[CustomerSales] = Field(default_factory=list)
    by_product: List[ProductSales] = Field(default_factory=list)
    by_user: List[UserSales] = Field(default_factory=list)
    by_status: dict = Field(default_factory=dict)


class OrderMargin(BaseModel):
    sales_order_id: int
    so_no: str
    customer_name: str
    order_date: date
    revenue: Decimal
    cost: Decimal
    gross_profit: Decimal
    margin_pct: Decimal
    po_count: int


class FinancialPeriod(BaseModel):
    period: str
    revenue: Decimal
    cost: Decimal
    gross_profit: Decimal
    margin_pct: Decimal


class FinancialReport(BaseModel):
    date_from: date
    date_to: date
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    currency: str = "IDR"

    # Revenue and cost are both net of PPN, so the margin is a real margin.
    revenue: Decimal
    cost: Decimal
    gross_profit: Decimal
    margin_pct: Decimal

    cost_linked: Decimal
    cost_unlinked: Decimal

    collected: Decimal
    outstanding: Decimal

    by_period: List[FinancialPeriod] = Field(default_factory=list)
    by_order: List[OrderMargin] = Field(default_factory=list)


# ------------------------------------------------- delivery schedule (Surat Jalan)
class ScheduleStop(ORMModel):
    id: int
    sj_no: str
    status: str
    time_slot: Optional[str] = None
    so_no: Optional[str] = None
    customer_name: Optional[str] = None
    deliver_to: Optional[str] = None
    deliver_address: Optional[str] = None
    phone: Optional[str] = None
    vehicle_no: Optional[str] = None
    driver_name: Optional[str] = None
    total_qty: Decimal = Decimal("0.00")
    line_count: int = 0
    can_edit: bool = True


class ScheduleDay(BaseModel):
    delivery_date: date
    is_today: bool = False
    is_overdue: bool = False
    stop_count: int = 0
    total_qty: Decimal = Decimal("0.00")
    stops: List[ScheduleStop] = Field(default_factory=list)


class DeliverySchedule(BaseModel):
    date_from: date
    date_to: date
    days: List[ScheduleDay] = Field(default_factory=list)
    unscheduled: List[ScheduleStop] = Field(default_factory=list)


# --------------------------------------- purchase orders split across suppliers
class SupplierSplitLine(BaseModel):
    sales_order_item_id: int
    product_id: int
    product_code: str
    product_name: str
    quantity: Decimal
    measure: Decimal
    price_unit: str


class SupplierSplitGroup(BaseModel):
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    supplier_code: Optional[str] = None
    lines: List[SupplierSplitLine] = Field(default_factory=list)


class PurchaseOrderSplitPreview(BaseModel):
    """What `POST /purchase-orders/split/{so}` would create."""

    sales_order_id: int
    so_no: str
    groups: List[SupplierSplitGroup] = Field(default_factory=list)
    # Lines whose product has no default supplier set.
    unassigned: List[SupplierSplitLine] = Field(default_factory=list)
