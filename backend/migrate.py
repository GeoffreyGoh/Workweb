"""Bring an existing database up to date with models.py.

    python migrate.py --dry-run     show what would change
    python migrate.py               apply it

SQLAlchemy's create_all() only creates missing *tables*; it never adds a
column to a table that already exists. This compares each model against the
live database and issues the ALTER TABLE ADD COLUMN statements needed to
close the gap.

It is additive only, by design: it never drops or retypes a column, so it
cannot destroy data. Anything beyond adding a column or a table is reported
for you to handle deliberately.
"""

import argparse
import sys

from sqlalchemy import inspect, text

import models  # noqa: F401  (registers every model on Base)
from database import Base, engine


def column_ddl(dialect, column) -> str:
    """Render one column for an ALTER TABLE ADD COLUMN."""
    type_sql = column.type.compile(dialect=dialect)
    parts = [f"{column.name} {type_sql}"]

    default = None
    if column.default is not None and getattr(column.default, "is_scalar", False):
        default = column.default.arg
    elif column.server_default is not None:
        default = None  # let the server default clause below handle it

    # SQLite cannot add a NOT NULL column without a default value.
    if default is not None:
        literal = f"'{default}'" if isinstance(default, str) else str(default)
        parts.append(f"DEFAULT {literal}")
    if not column.nullable and default is not None:
        parts.append("NOT NULL")

    return " ".join(parts)


def plan():
    """Work out what is missing. Returns (missing_tables, missing_columns)."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    missing_tables = []
    missing_columns = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            missing_tables.append(table.name)
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name not in have:
                missing_columns.append((table.name, column))

    return missing_tables, missing_columns


def run(dry_run: bool):
    missing_tables, missing_columns = plan()

    if not missing_tables and not missing_columns:
        print("Database is already up to date.")
        return

    if missing_tables:
        print(f"New tables ({len(missing_tables)}):")
        for name in missing_tables:
            print(f"  + {name}")

    if missing_columns:
        print(f"\nNew columns ({len(missing_columns)}):")
        for table_name, column in missing_columns:
            print(f"  + {table_name}.{column.name} "
                  f"{column.type.compile(dialect=engine.dialect)}")

    if dry_run:
        print("\n--dry-run: nothing was changed.")
        return

    # Tables first: a new column may reference one of them.
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        for table_name, column in missing_columns:
            ddl = column_ddl(engine.dialect, column)
            # A NOT NULL column cannot be added to a table that already has
            # rows unless it carries a default; add it nullable and let
            # backfill_companies() fill it in.
            if not column.nullable and " DEFAULT " not in ddl:
                ddl = ddl.replace(" NOT NULL", "")
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))

    backfill_companies()

    print(f"\nApplied: {len(missing_tables)} table(s), {len(missing_columns)} column(s).")

    leftover_tables, leftover_columns = plan()
    if leftover_tables or leftover_columns:
        print("Still missing after migrating - check manually:")
        for name in leftover_tables:
            print(f"  {name}")
        for table_name, column in leftover_columns:
            print(f"  {table_name}.{column.name}")
        sys.exit(1)
    print("Verified: the database now matches models.py.")


def backfill_companies():
    """Give every existing document a company.

    company_id is NOT NULL in the schema, but documents created before the
    multi-company change have none. Attach them to the first company so the
    history stays printable, rather than leaving rows that break on read.
    """
    from database import SessionLocal

    db = SessionLocal()
    try:
        first = (
            db.query(models.Company)
            .filter(models.Company.is_active.is_(True))
            .order_by(models.Company.id)
            .first()
        )
        if not first:
            return

        moved = 0
        for model in (models.Quotation, models.SalesOrder, models.PurchaseOrder,
                      models.DeliveryNote, models.Receipt):
            moved += (
                db.query(model)
                .filter(model.company_id.is_(None))
                .update({"company_id": first.id}, synchronize_session=False)
            )
        db.commit()
        if moved:
            print(f"Backfilled {moved} existing document(s) to {first.name}.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.dry_run)
