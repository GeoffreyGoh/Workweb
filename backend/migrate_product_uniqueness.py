"""One-off schema migration: Product.code loosened from globally-unique
to part of a composite (code, name, category) uniqueness check.

Why this needs its own script instead of migrate.py:
migrate.py only ADDS missing columns/tables - it deliberately never
touches an existing constraint or index, by design (additive-only, so it
can never destroy data). This change removes the old unique index on
products.code and adds a new composite one, which is exactly the kind
of constraint change migrate.py intentionally does not attempt.

What this does, in order:
  1. Checks for any EXISTING rows that would violate the new composite
     uniqueness (same code+name+category) - if any exist, refuses to
     proceed and lists them, rather than silently leaving duplicate
     "identical" products in place once the old blanket-unique code
     constraint is gone.
  2. Drops the old unique index on code alone (ix_products_code).
  3. Creates a new plain (non-unique) index on code, so lookups by code
     are still fast even though it's no longer required to be unique.
  4. Creates the new unique index covering (code, name, category).

Run as:
    python migrate_product_uniqueness.py --dry-run
    python migrate_product_uniqueness.py
"""
import argparse
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")

from sqlalchemy import inspect, text
from database import engine, SessionLocal
import models


def find_existing_duplicates(db):
    """Rows that would violate the new (code, name, category) uniqueness.

    category is nullable - two rows with category=NULL and the same
    code+name are duplicates under our rule even though plain SQL
    wouldn't treat NULL=NULL as a match, so this groups in Python
    rather than relying on a raw SQL GROUP BY to get that part right.
    """
    products = db.query(models.Product).all()
    groups = {}
    for p in products:
        key = (p.code, p.name, p.category)
        groups.setdefault(key, []).append(p)
    return {k: v for k, v in groups.items() if len(v) > 1}


def run(dry_run: bool):
    db = SessionLocal()
    try:
        dupes = find_existing_duplicates(db)
        if dupes:
            print("REFUSING to proceed - these existing rows are already duplicates")
            print("under the new rule (same code+name+category). Resolve them by")
            print("hand first (change one field, or delete/deactivate the extra row):\n")
            for (code, name, category), rows in dupes.items():
                ids = ", ".join(str(r.id) for r in rows)
                print(f"  code={code!r} name={name!r} category={category!r} -> product ids {ids}")
            sys.exit(1)
        print("No existing duplicates under the new rule - safe to proceed.\n")
    finally:
        db.close()

    inspector = inspect(engine)
    indexes = {idx["name"]: idx for idx in inspector.get_indexes("products")}

    steps = []
    if "ix_products_code" in indexes and indexes["ix_products_code"]["unique"]:
        steps.append("DROP INDEX ix_products_code" if engine.dialect.name == "postgresql"
                     else "DROP INDEX ix_products_code")
    if "ix_products_code" not in indexes or indexes["ix_products_code"]["unique"]:
        steps.append("CREATE INDEX ix_products_code ON products (code)")
    if "uq_products_code_name_category" not in indexes:
        steps.append(
            "CREATE UNIQUE INDEX uq_products_code_name_category "
            "ON products (code, name, category)"
        )

    if not steps:
        print("Nothing to do - schema already matches.")
        return

    print("Planned statements:")
    for s in steps:
        print(f"  {s}")

    if dry_run:
        print("\n--dry-run: nothing was changed.")
        return

    with engine.begin() as conn:
        for s in steps:
            conn.execute(text(s))

    print("\nApplied. Verifying...")
    inspector = inspect(engine)
    indexes = {idx["name"] for idx in inspector.get_indexes("products")}
    if "uq_products_code_name_category" in indexes:
        print("Confirmed: uq_products_code_name_category now exists.")
    else:
        print("WARNING: uq_products_code_name_category still missing after running - check manually.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.dry_run)
