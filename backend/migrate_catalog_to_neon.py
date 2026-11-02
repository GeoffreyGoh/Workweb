"""One-off: copy the real product catalog from local SQLite into Neon.

Context: the live site was moved from a broken Aiven MySQL connection to
Neon Postgres (see database.py). seed.py only ever loads a small demo
catalog (28 sample products) - the real catalog built up over this project
(133 products, 690 colour variants, 611 fabric/mechanism options) lives in
backend/q2o.db and has never been written anywhere else. This script reads
that SQLite file directly and inserts matching rows into whatever
DATABASE_URL currently points at (Neon, once .env is set to it).

Deliberately narrow: copies only products, product_colors, product_options.
Companies/users/customers/suppliers are left alone - both databases already
agree on those (same seed.py), and quotations/sales orders were excluded on
purpose (Geoffrey's call: looked like test data, not worth carrying over).

Safe to re-run: skips any product whose `code` already exists at the
destination, so running this twice does not create duplicates.

Usage (from backend/, with .env pointing at Neon):
    python migrate_catalog_to_neon.py --dry-run     # show what would happen
    python migrate_catalog_to_neon.py                # actually copy
"""

import argparse
import sqlite3
from decimal import Decimal

import models
from database import SessionLocal, IS_SQLITE

SOURCE_DB = "q2o.db"


def read_source():
    """Pull every row we need out of the local SQLite file as plain dicts."""
    conn = sqlite3.connect(SOURCE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM products")
    products = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM product_colors")
    colors = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM product_options")
    options = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT id, code FROM suppliers")
    supplier_code_by_id = {r["id"]: r["code"] for r in cur.fetchall()}

    conn.close()
    return products, colors, options, supplier_code_by_id


def run(dry_run: bool):
    if IS_SQLITE:
        # Refuse to run against SQLite - the whole point is copying *out* of
        # the local SQLite file, not into another one. Guards against
        # accidentally running this with DATABASE_URL unset.
        raise SystemExit(
            "DATABASE_URL points at SQLite - this script copies catalog data "
            "FROM q2o.db TO whatever DATABASE_URL names. Point it at Neon first."
        )

    products, colors, options, supplier_code_by_id = read_source()
    print(f"Source (q2o.db): {len(products)} products, {len(colors)} colors, "
          f"{len(options)} options.")

    db = SessionLocal()
    try:
        # Map destination supplier code -> destination id, so a mismatched
        # auto-increment sequence between the two databases can't silently
        # attach a product to the wrong supplier.
        dest_supplier_id_by_code = {
            s.code: s.id for s in db.query(models.Supplier).all()
        }

        existing_codes = {p.code for p in db.query(models.Product.code).all()}
        to_add = [p for p in products if p["code"] not in existing_codes]
        skipped = len(products) - len(to_add)
        if skipped:
            print(f"Skipping {skipped} product(s) already present at destination.")

        if dry_run:
            print(f"\n--dry-run: would add {len(to_add)} product(s), plus their "
                  f"colors and options. Nothing was changed.")
            return

        old_id_to_new_product = {}
        added_products = 0
        for row in to_add:
            supplier_code = supplier_code_by_id.get(row["supplier_id"])
            dest_supplier_id = dest_supplier_id_by_code.get(supplier_code)

            product = models.Product(
                code=row["code"],
                name=row["name"],
                category=row["category"],
                price_unit=row["price_unit"],
                unit_price=Decimal(str(row["unit_price"] or 0)),
                min_width_cm=row["min_width_cm"],
                max_width_cm=row["max_width_cm"],
                min_height_cm=row["min_height_cm"],
                max_height_cm=row["max_height_cm"],
                fabric_width_cm=row["fabric_width_cm"],
                description=row["description"],
                is_active=bool(row["is_active"]),
                supplier_id=dest_supplier_id,
            )
            db.add(product)
            db.flush()  # get product.id without a full commit yet
            old_id_to_new_product[row["id"]] = product
            added_products += 1

        added_colors = 0
        for row in colors:
            product = old_id_to_new_product.get(row["product_id"])
            if product is None:
                continue  # belongs to a product that already existed - skip
            db.add(models.ProductColor(
                product_id=product.id,
                color_name=row["color_name"],
                fabric_code=row["fabric_code"],
                max_width_cm=row["max_width_cm"],
                max_height_cm=row["max_height_cm"],
                stock_status=row["stock_status"],
                raw_label=row["raw_label"],
                source_ref=row["source_ref"],
                notes=row["notes"],
                is_active=bool(row["is_active"]),
            ))
            added_colors += 1

        added_options = 0
        for row in options:
            product = old_id_to_new_product.get(row["product_id"])
            if product is None:
                continue
            db.add(models.ProductOption(
                product_id=product.id,
                option_group=row["option_group"],
                option_name=row["option_name"],
                is_available=bool(row["is_available"]),
                unit_price=Decimal(str(row["unit_price"])) if row["unit_price"] is not None else None,
                source_ref=row["source_ref"],
            ))
            added_options += 1

        db.commit()
        print(f"\nAdded {added_products} product(s), {added_colors} color(s), "
              f"{added_options} option(s).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.dry_run)
