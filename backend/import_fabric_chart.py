"""Import the FABRIC CHART compatibility matrix into product_options.

    python import_fabric_chart.py --dry-run
    python import_fabric_chart.py

The sheet is a matrix: one row per fabric, one column per mechanism or rail,
grouped under Roman / Roller / Panel Glide / Vertical. A cell holds "True"
(the fabric can be made that way) or "x" (it cannot).

That drives the component dropdown on a quotation line: pick ASPEN (BO) and
you are offered only the mechanisms it can actually be made in.

Fabric names here do not match the catalogue exactly - the chart writes
"Aspen (BO)" where the Roller sheet writes "ASPEN (BO)" - so matching is done
on a normalised name and anything unmatched is reported rather than dropped
silently.
"""

import argparse
import re
import sys
from collections import Counter, defaultdict

import models
from database import Base, SessionLocal, engine

DEFAULT_FILE = r"C:\Users\Lenovo\Downloads\AS PER 11 August 2026 (1).xlsx"
SHEET = "FABRIC CHART"

GROUP_ROW = 2
HEADER_ROW = 3
FIRST_OPTION_COL = 3
NAME_COL = 1
MAX_WIDTH_COL = 2


def clean(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalise(name: str) -> str:
    """'Aspen (BO)' and 'ASPEN  (BO)' must compare equal."""
    return re.sub(r"[^a-z0-9]", "", clean(name).lower())


def split_name(name: str):
    """('Clovelly (T)') -> ('clovelly', 't'). Suffix is '' when absent."""
    text = clean(name)
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", text)
    if match:
        return normalise(match.group(1)), normalise(match.group(2))
    return normalise(text), ""


def match_product(chart_name: str, exact: dict, by_base: dict):
    """Find the catalogue product a chart row refers to.

    Three passes, each stricter about what it will accept:
      1. the whole name, normalised            "Aspen (BO)"   -> ASPEN (BO)
      2. base name, when only one product has it  "Cabaret"   -> CABARET (BO)
      3. base name plus a suffix that is a prefix of the catalogue's
         "Clovelly (T)" -> CLOVELLY (TL), but never (BO)

    Anything still ambiguous is left unmatched and reported: guessing between
    block out and translucent would attach the wrong mechanisms to a fabric.
    """
    product = exact.get(normalise(chart_name))
    if product:
        return product, "exact"

    base, suffix = split_name(chart_name)
    candidates = by_base.get(base, [])

    if len(candidates) == 1 and not suffix:
        return candidates[0], "base name"

    if suffix:
        narrowed = [
            p for p in candidates
            if split_name(p.name)[1].startswith(suffix) or suffix.startswith(split_name(p.name)[1])
        ]
        if len(narrowed) == 1:
            return narrowed[0], "suffix prefix"

    if len(candidates) == 1:
        return candidates[0], "base name"

    return None, "ambiguous" if candidates else "no match"


def parse(ws):
    """Return (rows, option_columns) where each row is (name, max_width, cells)."""
    # Group labels are sparse: "Roman" sits above the first of its columns and
    # applies until the next label appears.
    groups = {}
    current = None
    for col in range(FIRST_OPTION_COL, ws.max_column + 1):
        label = clean(ws.cell(GROUP_ROW, col).value)
        if label:
            current = label
        groups[col] = current or "Other"

    columns = []
    for col in range(FIRST_OPTION_COL, ws.max_column + 1):
        header = clean(ws.cell(HEADER_ROW, col).value)
        if header:
            columns.append((col, groups[col], header))

    rows = []
    for r in range(HEADER_ROW + 1, ws.max_row + 1):
        name = clean(ws.cell(r, NAME_COL).value)
        if not name or name.lower().startswith("available"):
            continue
        # The legend ("= recommended") sits in the matrix area on some rows.
        if name.startswith("="):
            continue
        rows.append((r, name, clean(ws.cell(r, MAX_WIDTH_COL).value),
                     {col: clean(ws.cell(r, col).value) for col, _, _ in columns}))
    return rows, columns


def run(path: str, dry_run: bool):
    try:
        import openpyxl
    except ImportError:
        sys.exit("openpyxl is required:  pip install openpyxl")

    workbook = openpyxl.load_workbook(path)
    if SHEET not in workbook.sheetnames:
        sys.exit(f"{SHEET!r} not found in the workbook")

    rows, columns = parse(workbook[SHEET])
    print(f"Read {len(rows)} fabric rows and {len(columns)} option columns")
    for group, names in _grouped(columns).items():
        print(f"  {group:<14} {', '.join(names)}")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        products = db.query(models.Product).all()
        exact = {normalise(p.name): p for p in products}
        by_base = defaultdict(list)
        for p in products:
            by_base[split_name(p.name)[0]].append(p)

        matched, unmatched = [], []
        how = Counter()
        for r, name, max_width, cells in rows:
            product, reason = match_product(name, exact, by_base)
            how[reason] += 1
            if product:
                matched.append((r, name, max_width, cells, product))
            else:
                unmatched.append((name, reason))

        print(f"\n  matched   {len(matched):>3} fabrics to catalogue products")
        for reason, n in how.most_common():
            if reason in ("exact", "base name", "suffix prefix"):
                print(f"      by {reason:<14} {n:>3}")
        print(f"  unmatched {len(unmatched):>3}")
        for name, reason in unmatched[:12]:
            print(f"      {name!r} ({reason})")
        if len(unmatched) > 12:
            print(f"      ... and {len(unmatched) - 12} more")

        if dry_run:
            available = sum(
                1 for _, _, _, cells, _ in matched
                for col, _, _ in columns
                if cells.get(col, "").lower() == "true"
            )
            print(f"\n--dry-run: would write {len(matched) * len(columns)} option rows "
                  f"({available} available, the rest marked unavailable). Nothing written.")
            return

        db.query(models.ProductOption).delete(synchronize_session=False)
        db.commit()

        written = Counter()
        widths_set = 0
        for r, name, max_width, cells, product in matched:
            for col, group, option in columns:
                value = cells.get(col, "").lower()
                is_available = value == "true"
                product.options.append(models.ProductOption(
                    option_group=group,
                    option_name=option,
                    is_available=is_available,
                    source_ref=f"{SHEET}!{_col_letter(col)}{r}",
                ))
                written["available" if is_available else "unavailable"] += 1

            # The chart also states a max blind width in mm; the catalogue
            # sheets only give it per colour, so fill the product-level cap.
            if max_width and product.max_width_cm is None:
                try:
                    product.max_width_cm = round(float(max_width.replace(",", ".")) / 10, 2)
                    widths_set += 1
                except ValueError:
                    pass

        db.commit()

        print(f"\n  wrote {sum(written.values())} option rows "
              f"({written['available']} available, {written['unavailable']} not recommended)")
        print(f"  set product max width from the chart on {widths_set} products")
        if unmatched:
            print(f"\n  {len(unmatched)} chart fabrics had no catalogue match and were "
                  "skipped -\n  they may be named differently or not stocked.")
    finally:
        db.close()


def _grouped(columns):
    out = defaultdict(list)
    for _, group, header in columns:
        out[group].append(header)
    return out


def _col_letter(index: int) -> str:
    from openpyxl.utils import get_column_letter

    return get_column_letter(index)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=DEFAULT_FILE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.file, args.dry_run)
