"""Developer CLI for managing user accounts directly - create a user, change
a password, change a role, deactivate/reactivate, or list everyone.

There is no web UI or API endpoint for this (users.py is read-only - it
only lists staff for report filters), so this script is the only way to
manage accounts right now. Run it with DATABASE_URL set to whichever
database you mean to change - it uses whatever database.py resolves,
same as every other script in this folder (seed.py, migrate.py, ...).

    # See everyone
    python manage_user.py list

    # Add a new user (role must be 'admin' or 'user')
    python manage_user.py create geoffrey "Geoffrey Goh" admin --company TRI

    # Change a password
    python manage_user.py set-password geoffrey

    # Promote/demote
    python manage_user.py set-role budi admin

    # Deactivate without deleting (keeps their name on old documents)
    python manage_user.py deactivate agus
    python manage_user.py reactivate agus

Unlike seed.py (which only ever creates - it silently skips a username
that already exists), every command here acts on request, so re-running
set-password actually changes it.
"""
import argparse
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")

import auth
import models
from database import SessionLocal


def masked_input(prompt: str) -> str:
    """Read a password with a '*' echoed per keystroke, Backspace supported.

    Plain getpass() shows nothing at all while typing, which is secure but
    gives zero feedback if a key was missed or double-pressed - Geoffrey
    asked for visible masking specifically to catch that. msvcrt (Windows)
    and termios (Mac/Linux) are both stdlib - no extra dependency - but
    read input differently, so each OS gets its own small reader; both
    fall back to plain input() if the terminal does not support raw mode
    (e.g. input piped from a file) rather than crashing.
    """
    print(prompt, end="", flush=True)
    try:
        if sys.platform == "win32":
            import msvcrt
            chars = []
            while True:
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    break
                if ch == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt
                if ch == "\b":  # Backspace
                    if chars:
                        chars.pop()
                        print("\b \b", end="", flush=True)
                    continue
                chars.append(ch)
                print("*", end="", flush=True)
            print()
            return "".join(chars)
        else:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            chars = []
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ("\r", "\n"):
                        break
                    if ch == "\x03":
                        raise KeyboardInterrupt
                    if ch in ("\x7f", "\b"):  # Backspace/Delete
                        if chars:
                            chars.pop()
                            sys.stdout.write("\b \b")
                            sys.stdout.flush()
                        continue
                    chars.append(ch)
                    sys.stdout.write("*")
                    sys.stdout.flush()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            print()
            return "".join(chars)
    except Exception:
        # No raw terminal available (e.g. input piped, or an unusual
        # shell) - fall back to a normal visible prompt rather than
        # crashing the whole command.
        return input(prompt + "(terminal can't mask input - typed plainly) ")


def prompt_password(label: str) -> str:
    """Prompt twice and require a match - catches a mistyped character
    that asterisk-masking alone would not (you'd see the same number of
    asterisks for a typo as for the correct password)."""
    while True:
        first = masked_input(f"{label}: ")
        if not first:
            print("A password is required.")
            continue
        second = masked_input(f"{label} (again): ")
        if first != second:
            print("Those two didn't match - try again.\n")
            continue
        return first


def cmd_list(args, db):
    users = db.query(models.User).order_by(models.User.username).all()
    if not users:
        print("No users found.")
        return
    print(f"{'username':<16} {'full name':<24} {'role':<8} {'active':<8} {'company'}")
    for u in users:
        company = u.default_company.code if u.default_company else "-"
        print(f"{u.username:<16} {u.full_name:<24} {u.role:<8} {str(u.is_active):<8} {company}")


def cmd_create(args, db):
    if args.role not in auth.ROLES:
        print(f"role must be one of {auth.ROLES}, got '{args.role}'")
        raise SystemExit(1)
    if db.query(models.User).filter(models.User.username == args.username).first():
        print(f"'{args.username}' already exists - use set-password/set-role to change it.")
        raise SystemExit(1)

    company_id = None
    if args.company:
        company = (
            db.query(models.Company)
            .filter(models.Company.code == args.company)
            .first()
        )
        if not company:
            print(f"No company with code '{args.company}' - check companies.code.")
            raise SystemExit(1)
        company_id = company.id

    password = args.password or prompt_password(f"Password for {args.username}")
    if not password:
        print("A password is required.")
        raise SystemExit(1)

    user = models.User(
        username=args.username,
        full_name=args.full_name,
        role=args.role,
        password_hash=auth.hash_password(password),
        default_company_id=company_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    print(f"Created '{args.username}' ({args.role}).")


def cmd_set_password(args, db):
    user = _require_user(db, args.username)
    password = args.password or prompt_password(f"New password for {args.username}")
    if not password:
        print("A password is required.")
        raise SystemExit(1)
    user.password_hash = auth.hash_password(password)
    db.commit()
    print(f"Password changed for '{args.username}'.")


def cmd_set_role(args, db):
    if args.role not in auth.ROLES:
        print(f"role must be one of {auth.ROLES}, got '{args.role}'")
        raise SystemExit(1)
    user = _require_user(db, args.username)
    user.role = args.role
    db.commit()
    print(f"'{args.username}' is now role '{args.role}'.")


def cmd_deactivate(args, db):
    user = _require_user(db, args.username)
    user.is_active = False
    db.commit()
    print(f"Deactivated '{args.username}' - they can no longer log in.")


def cmd_reactivate(args, db):
    user = _require_user(db, args.username)
    user.is_active = True
    db.commit()
    print(f"Reactivated '{args.username}'.")


def cmd_delete(args, db):
    """Permanently remove a user. Only allowed when they never created a
    real document - every quotation/invoice/PO/delivery note/receipt
    references its creator by created_by with no cascade-delete, so a
    hard delete on a user who HAS created something would leave those
    documents' created_by pointing at nothing. Same safety pattern as
    DELETE /products/{id} - block instead of risking an orphaned record.
    """
    user = _require_user(db, args.username)
    in_use = (
        db.query(models.Quotation.id).filter(models.Quotation.created_by == user.id).first()
        or db.query(models.SalesOrder.id).filter(models.SalesOrder.created_by == user.id).first()
        or db.query(models.PurchaseOrder.id).filter(models.PurchaseOrder.created_by == user.id).first()
        or db.query(models.DeliveryNote.id).filter(models.DeliveryNote.created_by == user.id).first()
        or db.query(models.Receipt.id).filter(models.Receipt.created_by == user.id).first()
    )
    if in_use:
        print(
            f"'{args.username}' has already created a document (quotation, invoice, "
            "purchase order, delivery note, or receipt) and cannot be deleted - "
            "deleting them would leave that document's 'created by' pointing at "
            "nothing. Use 'deactivate' instead: it blocks their login but keeps "
            "their name on everything they made."
        )
        raise SystemExit(1)

    if not args.yes:
        answer = input(f"Permanently delete '{args.username}'? This cannot be undone. [y/N] ")
        if answer.strip().lower() != "y":
            print("Cancelled - nothing was deleted.")
            return
    db.delete(user)
    db.commit()
    print(f"Deleted '{args.username}'.")


def _require_user(db, username):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        print(f"No user '{username}'. Run 'list' to see existing usernames.")
        raise SystemExit(1)
    return user


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Show every user.")

    p = sub.add_parser("create", help="Add a new user.")
    p.add_argument("username")
    p.add_argument("full_name")
    p.add_argument("role", choices=auth.ROLES)
    p.add_argument("--company", help="Default company code (e.g. TRI, ACC, MIL) - optional.")
    p.add_argument("--password", help="Omit to be prompted (hidden input) instead.")

    p = sub.add_parser("set-password", help="Change an existing user's password.")
    p.add_argument("username")
    p.add_argument("--password", help="Omit to be prompted (hidden input) instead.")

    p = sub.add_parser("set-role", help="Change an existing user's role.")
    p.add_argument("username")
    p.add_argument("role", choices=auth.ROLES)

    p = sub.add_parser("deactivate", help="Block login without deleting the account.")
    p.add_argument("username")

    p = sub.add_parser("reactivate", help="Allow login again.")
    p.add_argument("username")

    p = sub.add_parser(
        "delete",
        help="Permanently remove a user who has never created a document.",
    )
    p.add_argument("username")
    p.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")

    args = parser.parse_args()
    db = SessionLocal()
    try:
        {
            "list": cmd_list,
            "create": cmd_create,
            "set-password": cmd_set_password,
            "set-role": cmd_set_role,
            "deactivate": cmd_deactivate,
            "reactivate": cmd_reactivate,
            "delete": cmd_delete,
        }[args.command](args, db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
