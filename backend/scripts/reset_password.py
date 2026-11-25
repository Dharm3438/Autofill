"""
Emergency password reset, run on the server. Use it when nobody can sign in,
e.g. the only admin has lost access to their email. Normal users should use
"Forgot password" on the sign-in page instead.

Run from the backend/ directory with the venv active. It uses MONGODB_URI from
backend/.env:

    python scripts/reset_password.py <email-or-username>
    python scripts/reset_password.py <email-or-username> --make-admin

You are asked for the new password (it is never shown or put in your shell
history). Every existing session of that user is signed out.
"""
import argparse
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("identifier", help="the user's email or username")
    parser.add_argument("--make-admin", action="store_true", help="also give the account the admin role and enable it")
    args = parser.parse_args()

    os.chdir(BACKEND_DIR)  # so pydantic-settings finds backend/.env
    from pymongo import MongoClient
    from app.core.config import settings
    from app.core.security import hash_password
    from app.models.user import check_new_password

    db = MongoClient(settings.MONGODB_URI)["solar_docs"]
    ident = args.identifier.strip().lower()
    user = db.users.find_one({"email": ident} if "@" in ident else {"username": ident})
    if not user:
        print(f"No user found for {args.identifier!r}")
        return 1
    print(f"User: {user['name']} <{user['email']}> roles={user.get('roles', [])}")

    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat new password: "):
        print("The passwords don't match. Nothing changed.")
        return 1
    try:
        check_new_password(password)
    except ValueError as e:
        print(f"Password {e}. Nothing changed.")
        return 1

    now = datetime.now(timezone.utc).isoformat()
    update = {"password_hash": hash_password(password), "password_changed_at": now, "updated_at": now}
    if args.make_admin:
        update["roles"] = sorted(set(user.get("roles", [])) | {"admin"})
        update["is_active"] = True
    db.users.update_one({"_id": user["_id"]}, {"$set": update, "$inc": {"token_version": 1}})
    db.auth_attempts.delete_many({"key": f"login-fail:acct:{user['_id']}"})
    print("Password updated; all of this user's sessions were signed out."
          + (" Admin role granted." if args.make_admin else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
