"""Create the tables and load master data.

    python seed.py            tables + users, customers, products, suppliers
    python seed.py --demo     the above, plus a year of realistic transactions
    python seed.py --reset    drop everything first (destroys existing data)

Safe to re-run: existing records are matched on their code and left alone.
"""

import sys
from decimal import Decimal

import auth
import models
from database import Base, engine, SessionLocal

COMPANIES = [
    # Three legal entities. Two of them trade under the Accent brand, so they
    # share a logo and are told apart by their address and bank account.
    dict(code="TRI", name="PT TRIRATNA DAMAI SEJAHTERA",
         address="Jl. Tambora IV No. 31", city="Jakarta Barat",
         bank_name="BCA - Cab. Ricci", bank_account="644 0495 859",
         bank_holder="PT TRIRATNA DAMAI SEJAHTERA",
         logo_filename="accent.jpeg"),
    dict(code="MIL", name="MILIE INTERIOR",
         address="Jl. Tambora IV No. 31", city="Jakarta Barat",
         bank_name="BCA - Cab. Ricci", bank_account="644 0699 128",
         bank_holder="Tshin Mymy Wongso",
         logo_filename="milie.jpeg"),
    dict(code="ACC", name="PT ACCENT JENDELA INDONESIA",
         address="Ruko Demansion Blok D9", city="Alam Sutera",
         bank_name="BCA - Cab. Ricci", bank_account="644 0856 789",
         bank_holder="PT ACCENT JENDELA INDONESIA",
         logo_filename="accent.jpeg"),
]

# (username, full name, password, role, default company code)
USERS = [
    ("admin", "Administrator", "admin123", "admin", "TRI"),
    ("user", "User", "user123", "user", "TRI"),
    ("budi", "Budi Santoso", "budi123", "user", "ACC"),
    ("sari", "Sari Dewi", "sari123", "user", "MIL"),
    ("agus", "Agus Prasetyo", "agus123", "user", "TRI"),
]

SUPPLIERS = [
    dict(code="SUP-001", name="PT Tekstil Nusantara", contact_person="Ibu Ratna",
         address="Kawasan Industri Pulogadung Blok C5, Jakarta Timur",
         phone="021-4601122", email="order@tekstilnusantara.co.id",
         payment_terms="30 days"),
    dict(code="SUP-002", name="CV Aluminium Jaya", contact_person="Pak Andi",
         address="Jl. Raya Serpong KM 8, Tangerang",
         phone="021-5390088", email="sales@aluminiumjaya.com",
         payment_terms="14 days"),
    dict(code="SUP-003", name="Somfy Motor Distributor", contact_person="Ms. Linda",
         address="Jl. Gatot Subroto No. 88, Jakarta Selatan",
         phone="021-52901234", email="id.order@motordist.com",
         payment_terms="50% DP"),
    dict(code="SUP-004", name="PT Kayu Indah Furnindo", contact_person="Pak Hasan",
         address="Jl. Industri Raya No. 12, Semarang",
         phone="024-7601234", email="sales@kayuindah.co.id",
         payment_terms="30 days"),
    dict(code="SUP-005", name="Toko Hardware Sentosa", contact_person="Koh Aleng",
         address="Jl. Mangga Dua Raya Blok F No. 21, Jakarta Pusat",
         phone="021-6129900", email="sentosa.hardware@gmail.com",
         payment_terms="COD"),
    dict(code="SUP-006", name="CV Packaging Mandiri", contact_person="Ibu Yuni",
         address="Jl. Cakung Cilincing KM 3, Jakarta Utara",
         phone="021-4403311", email="order@packagingmandiri.id",
         payment_terms="14 days"),
]

CUSTOMERS = [
    dict(code="CUST-001", name="PT Graha Interior", nik_npwp="01.234.567.8-901.000",
         address="Jl. Sudirman No. 45, Jakarta Pusat", phone="021-5551234",
         email="purchasing@grahainterior.co.id", price_group="PROJECT",
         payment_terms="30 days"),
    dict(code="CUST-002", name="Bapak Hendra Wijaya",
         address="Perumahan Green Hill Blok C2 No. 8, Bandung",
         phone="0812-3456-7890", email="hendra.w@gmail.com",
         price_group="RETAIL", payment_terms="50% DP, 50% on delivery"),
    dict(code="CUST-003", name="Hotel Santika Dyandra", nik_npwp="02.876.543.2-109.000",
         address="Jl. Kapten Muslim No. 100, Medan",
         deliver_to="Hotel Santika - Purchasing Dept",
         deliver_address="Jl. Kapten Muslim No. 100, Medan (Loading dock B)",
         phone="061-4567890", email="procurement@santikadyandra.com",
         price_group="PROJECT", payment_terms="45 days"),
    dict(code="CUST-004", name="PT Cipta Karya Developer", nik_npwp="03.111.222.3-045.000",
         address="Kawasan Bisnis CBD Lot 5, Tangerang Selatan",
         phone="021-29001500", email="proc@ciptakarya.co.id",
         price_group="PROJECT", payment_terms="60 days"),
    dict(code="CUST-005", name="Ibu Melinda Tanuwijaya",
         address="Jl. Pluit Karang Ayu Blok B7 No. 15, Jakarta Utara",
         phone="0811-998-2211", email="melinda.t@yahoo.com",
         price_group="RETAIL", payment_terms="50% DP, 50% on delivery"),
    dict(code="CUST-006", name="Studio Arsitek Ruang Kita",
         address="Jl. Kemang Selatan VIII No. 3, Jakarta Selatan",
         phone="021-7180099", email="admin@ruangkita.studio",
         price_group="DESIGNER", payment_terms="30 days"),
    dict(code="CUST-007", name="RS Bhakti Medika", nik_npwp="04.555.666.7-088.000",
         address="Jl. Ahmad Yani No. 210, Surabaya",
         deliver_to="RS Bhakti Medika - Logistik",
         deliver_address="Jl. Ahmad Yani No. 210, Surabaya (Gudang belakang)",
         phone="031-8291000", email="pengadaan@bhaktimedika.co.id",
         price_group="PROJECT", payment_terms="45 days"),
    dict(code="CUST-008", name="Kantor Notaris Sutrisno & Rekan",
         address="Jl. Diponegoro No. 77, Semarang",
         phone="024-8412345", email="office@notarissutrisno.id",
         price_group="RETAIL", payment_terms="30 days"),
    dict(code="CUST-009", name="Bapak Rudi Hartono",
         address="Cluster Palm Spring Blok D5 No. 22, Bekasi",
         phone="0857-1122-3344", email="rudi.hartono88@gmail.com",
         price_group="RETAIL", payment_terms="50% DP, 50% on delivery"),
    dict(code="CUST-010", name="PT Mitra Boga Sejahtera", nik_npwp="05.777.888.9-012.000",
         address="Ruko Golden Boulevard Blok K No. 9, BSD City",
         phone="021-53150077", email="finance@mitraboga.co.id",
         price_group="PROJECT", payment_terms="30 days"),
]


def product(code, name, category, price_unit, price, w=None, W=None, h=None, H=None,
            description=None):
    """Shorthand: w/W are min/max width, h/H min/max height, all in cm."""
    return dict(
        code=code, name=name, category=category, price_unit=price_unit,
        unit_price=Decimal(str(price)),
        min_width_cm=Decimal(str(w)) if w is not None else None,
        max_width_cm=Decimal(str(W)) if W is not None else None,
        min_height_cm=Decimal(str(h)) if h is not None else None,
        max_height_cm=Decimal(str(H)) if H is not None else None,
        description=description,
    )


PRODUCTS = [
    # ---------------------------------------------------------- roller blinds
    product("RB-BO-01", "Roller Blind Blackout - Plain", "Roller Blind",
            "per_sqm", 385000, 40, 300, 40, 400),
    product("RB-BO-02", "Roller Blind Blackout - Textured", "Roller Blind",
            "per_sqm", 425000, 40, 300, 40, 400),
    product("RB-SS-03", "Roller Blind Sunscreen 3%", "Roller Blind",
            "per_sqm", 455000, 40, 280, 40, 350,
            "3% openness - maximum glare control"),
    product("RB-SS-05", "Roller Blind Sunscreen 5%", "Roller Blind",
            "per_sqm", 425000, 40, 280, 40, 350,
            "5% openness - keeps the outside view"),
    product("RB-DIM-01", "Roller Blind Dimout", "Roller Blind",
            "per_sqm", 350000, 40, 300, 40, 400),
    product("RB-ZEB-01", "Zebra / Combi Blind", "Roller Blind",
            "per_sqm", 495000, 45, 280, 45, 320,
            "Alternating sheer and solid bands"),

    # -------------------------------------------------------- venetian blinds
    product("VB-ALU-25", "Venetian Blind Aluminium 25mm", "Venetian Blind",
            "per_sqm", 295000, 30, 240, 30, 300),
    product("VB-ALU-16", "Venetian Blind Aluminium 16mm", "Venetian Blind",
            "per_sqm", 325000, 30, 200, 30, 260),
    product("VB-WD-50", "Venetian Blind Wood 50mm", "Venetian Blind",
            "per_sqm", 875000, 40, 240, 40, 280,
            "Basswood slats, cord ladder"),

    # -------------------------------------------------------- vertical blinds
    product("VRT-FB-89", "Vertical Blind Fabric 89mm", "Vertical Blind",
            "per_sqm", 265000, 60, 400, 60, 320),
    product("VRT-PVC-89", "Vertical Blind PVC 89mm", "Vertical Blind",
            "per_sqm", 225000, 60, 400, 60, 320,
            "Wipe-clean, suited to kitchens and clinics"),

    # --------------------------------------------------------------- curtains
    product("CT-BLK-01", "Curtain Blackout 3 Pass - Custom Make", "Curtain",
            "per_sqm", 510000, 50, 600, 50, 400),
    product("CT-SHR-01", "Curtain Sheer / Vitrase", "Curtain",
            "per_sqm", 285000, 50, 600, 50, 400),
    product("CT-LIN-01", "Curtain Linen Look - Custom Make", "Curtain",
            "per_sqm", 465000, 50, 600, 50, 400),
    product("CT-RMN-01", "Roman Shade - Custom Make", "Curtain",
            "per_sqm", 625000, 40, 250, 40, 300),

    # --------------------------------------------------------------- hardware
    product("TRK-DBL-AL", "Curtain Track Double Aluminium", "Hardware",
            "per_meter", 165000, 60, 800,
            description="Priced per running metre of track."),
    product("TRK-SGL-AL", "Curtain Track Single Aluminium", "Hardware",
            "per_meter", 110000, 60, 800,
            description="Priced per running metre of track."),
    product("TRK-MTR-01", "Motorised Curtain Track", "Hardware",
            "per_meter", 485000, 100, 700,
            description="Motor and remote quoted separately."),
    product("ROD-WD-28", "Wooden Curtain Rod 28mm", "Hardware",
            "per_meter", 195000, 60, 500),
    product("BRK-STD", "Mounting Bracket Set", "Hardware",
            "per_unit", 35000, description="Per window."),

    # ---------------------------------------------------------- motorisation
    product("MTR-TUB-45", "Motorised Tubular Motor 45mm + Remote", "Motorisation",
            "per_unit", 1850000),
    product("MTR-RMT-15", "Extra Remote Control 15 Channel", "Motorisation",
            "per_unit", 650000),
    product("MTR-HUB-WIFI", "WiFi Hub / Smart Home Bridge", "Motorisation",
            "per_unit", 1450000, description="Connects motors to a phone app."),

    # --------------------------------------------------------------- services
    product("INS-STD", "Installation Service - Standard", "Service",
            "per_unit", 75000, description="Per installation point."),
    product("INS-HIGH", "Installation Service - High Ceiling", "Service",
            "per_unit", 165000, description="Above 4m, scaffolding required."),
    product("SRV-SURVEY", "Site Survey & Measurement", "Service",
            "per_unit", 250000, description="Waived if the order proceeds."),
    product("SRV-REMOVE", "Removal & Disposal of Old Blinds", "Service",
            "per_unit", 55000, description="Per window."),
    product("SRV-DELIV", "Delivery Charge - Greater Jakarta", "Service",
            "per_unit", 350000, description="Per trip."),
]


def seed_masters(db) -> dict:
    created = {"users": 0, "customers": 0, "products": 0, "suppliers": 0,
               "companies": 0}

    for data in COMPANIES:
        if db.query(models.Company).filter(models.Company.code == data["code"]).first():
            continue
        db.add(models.Company(**data))
        created["companies"] += 1
    db.commit()

    companies = {c.code: c for c in db.query(models.Company).all()}

    for username, full_name, password, role, company_code in USERS:
        if db.query(models.User).filter(models.User.username == username).first():
            continue
        company = companies.get(company_code)
        db.add(models.User(username=username, full_name=full_name,
                           password_hash=auth.hash_password(password), role=role,
                           default_company_id=company.id if company else None))
        created["users"] += 1

    # Once the real catalogue has been imported (import_catalog.py), never
    # push the sample products back in alongside it - their codes differ, so
    # the usual "skip if the code exists" guard would not catch them.
    real_catalog = db.query(models.ProductColor.id).first() is not None

    for table, rows, key in (
        (models.Customer, CUSTOMERS, "customers"),
        (models.Product, PRODUCTS, "products"),
        (models.Supplier, SUPPLIERS, "suppliers"),
    ):
        if table is models.Product and real_catalog:
            continue
        for data in rows:
            if db.query(table).filter(table.code == data["code"]).first():
                continue
            db.add(table(**data))
            created[key] += 1

    if real_catalog:
        created["products"] = -1  # signals "left the imported catalogue alone"

    db.commit()
    return created


def seed(with_demo: bool = False, reset: bool = False):
    if reset:
        Base.metadata.drop_all(bind=engine)
        print("Dropped every table.")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        created = seed_masters(db)
        print("Tables ready.")
        if created["products"] == -1:
            print(f"Added {created['companies']} company(ies), {created['users']} user(s), "
                  f"{created['customers']} customer(s), {created['suppliers']} supplier(s).")
            print("Left the imported client catalogue untouched "
                  "(sample products not re-added).")
        else:
            print(f"Added {created['companies']} company(ies), {created['users']} user(s), "
                  f"{created['customers']} customer(s), {created['products']} product(s), "
                  f"{created['suppliers']} supplier(s).")

        if with_demo:
            import demo_data

            print()
            demo_data.generate(db)

        print()
        for company in db.query(models.Company).order_by(models.Company.code).all():
            print(f"  {company.code}: {company.name}")
        print()
        print("  admin / admin123   (admin, TRI - can edit anyone's documents)")
        print("  budi  / budi123    (user, ACC - can edit only their own)")
        print("  sari  / sari123    (user, MIL)")
        print("  agus  / agus123    (user, TRI)")
    finally:
        db.close()


if __name__ == "__main__":
    seed(with_demo="--demo" in sys.argv, reset="--reset" in sys.argv)
