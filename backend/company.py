"""Company identity used on printed documents.

>>> EDIT THESE, or set the matching env vars in .env. <<<
They appear on every PDF the system produces, so they should be the details
you want a customer to see.

A logo is optional: drop a PNG or JPG at backend/assets/logo.png and it will be
placed at the top-left of the letterhead. Without one, the company name is set
in type instead. Roughly 3:1 landscape works best; it is scaled to 45pt tall.
"""

import os
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = ASSETS_DIR / "logo.png"


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


COMPANY = {
    "name": _env("COMPANY_NAME", "PT NAMA PERUSAHAAN"),
    "tagline": _env("COMPANY_TAGLINE", "Blinds, Curtains & Window Furnishings"),
    "address": _env("COMPANY_ADDRESS", "Jl. Contoh Alamat No. 123, Kecamatan"),
    "city": _env("COMPANY_CITY", "Jakarta 12345, Indonesia"),
    "phone": _env("COMPANY_PHONE", "+62 21 1234 5678"),
    "email": _env("COMPANY_EMAIL", "sales@perusahaan.co.id"),
    "website": _env("COMPANY_WEBSITE", "www.perusahaan.co.id"),
    "npwp": _env("COMPANY_NPWP", "00.000.000.0-000.000"),
    "bank_name": _env("COMPANY_BANK_NAME", "Bank Central Asia (BCA)"),
    "bank_account": _env("COMPANY_BANK_ACCOUNT", "1234567890"),
    "bank_holder": _env("COMPANY_BANK_HOLDER", "PT NAMA PERUSAHAAN"),
    # Printed under the signature line on quotations.
    "signatory": _env("COMPANY_SIGNATORY", "Sales Manager"),
}

# Standard terms printed at the foot of a quotation. One per line.
QUOTATION_TERMS = _env(
    "QUOTATION_TERMS",
    "Prices are valid for 30 days from the date of this quotation.|"
    "Lead time is 14-21 working days after receipt of down payment.|"
    "Measurements are the customer's responsibility unless surveyed by us.|"
    "Installation is charged separately unless stated otherwise.",
).split("|")


def logo_file():
    """Path to the letterhead logo, or None if none has been supplied."""
    for name in ("logo.png", "logo.jpg", "logo.jpeg"):
        candidate = ASSETS_DIR / name
        if candidate.is_file():
            return candidate
    return None
