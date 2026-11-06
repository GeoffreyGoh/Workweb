"""One-off: relax quotation_items.product_id and sales_order_items.product_id
from NOT NULL to nullable, so a sparepart sub-line (which has no catalogue
Product of its own) can be saved.

migrate.py deliberately never does this - it only adds missing columns,
by design, so it can never destroy data by itself. Loosening an existing
NOT NULL constraint is a genuine constraint change, which is why this is
a separate, explicit script rather than folded into migrate.py.

This does NOT touch any existing row's data - every current product_id
value is already non-null, so relaxing the constraint has zero effect on
anything already saved. It only affects what is allowed to be inserted
from now on.

Usage:
    DATABASE_URL=sqlite:///./q2o.db python relax_product_id_nullable.py --dry-run
    DATABASE_URL=sqlite:///./q2o.db python relax_product_id_nullable.py
"""
import argparse
import sys

from sqlalchemy import inspect, text

from database import engine, IS_SQLITE, IS_POSTGRES, IS_MYSQL

TABLES = ["quotation_items", "sales_order_items"]


def check(dry_run: bool):
    inspector = inspect(engine)
    for table in TABLES:
        cols = {c["name"]: c for c in inspector.get_columns(table)}
        col = cols.get("product_id")
        if col is None:
            print(f"  {table}.product_id: COLUMN NOT FOUND - skipping")
            continue
        if col["nullable"]:
            print(f"  {table}.product_id: already nullable - nothing to do")
            continue
        print(f"  {table}.product_id: NOT NULL -> would relax to nullable")

    if dry_run:
        print("\n--dry-run: nothing was changed.")
        return

    with engine.begin() as conn:
        for table in TABLES:
            cols = {c["name"]: c for c in inspector.get_columns(table)}
            if cols.get("product_id") is None or cols["product_id"]["nullable"]:
                continue

            if IS_POSTGRES:
                conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN product_id DROP NOT NULL"))
                print(f"  Applied (Postgres): {table}.product_id is now nullable")
            elif IS_MYSQL:
                conn.execute(text(f"ALTER TABLE {table} MODIFY product_id INTEGER NULL"))
                print(f"  Applied (MySQL): {table}.product_id is now nullable")
            elif IS_SQLITE:
                # SQLite has no ALTER COLUMN - rebuild the table via its
                # own documented recipe: new table, copy rows, swap names.
                # Column list is hand-written here (not introspected) so
                # the rebuilt table's shape matches models.py exactly.
                cols_sql = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                col_defs = []
                col_names = []
                for cid, name, ctype, notnull, dflt, pk in cols_sql:
                    col_names.append(name)
                    parts = [name, ctype]
                    if name == "product_id":
                        pass  # drop NOT NULL deliberately
                    elif notnull:
                        parts.append("NOT NULL")
                    if dflt is not None:
                        parts.append(f"DEFAULT {dflt}")
                    if pk:
                        parts.append("PRIMARY KEY")
                    col_defs.append(" ".join(parts))

                tmp = f"{table}_new"
                conn.execute(text(f"CREATE TABLE {tmp} ({', '.join(col_defs)})"))
                cols_csv = ", ".join(col_names)
                conn.execute(text(f"INSERT INTO {tmp} ({cols_csv}) SELECT {cols_csv} FROM {table}"))
                conn.execute(text(f"DROP TABLE {table}"))
                conn.execute(text(f"ALTER TABLE {tmp} RENAME TO {table}"))
                print(f"  Applied (SQLite rebuild): {table}.product_id is now nullable")

    print("\nDone. Re-run with --dry-run to verify.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    check(args.dry_run)
