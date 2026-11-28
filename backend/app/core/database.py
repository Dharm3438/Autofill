from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings
from datetime import datetime, timezone

from ..models.catalog import (
    DEFAULTS as CATALOG_DEFAULTS,
    normalize_value as normalize_catalog_value,
    value_key,
)

client: AsyncIOMotorClient = None
db = None


async def connect_db():
    global client, db
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client["solar_docs"]
    # Ping to verify connection
    await client.admin.command("ping")
    print("Connected to MongoDB Atlas")
    await _ensure_indexes()


async def _ensure_indexes():
    """
    Create the indexes the app relies on at scale. Idempotent — Mongo no-ops if
    an index already exists, so this is safe to run on every startup.

      • signing_submissions.token       — looked up on every signing request
                                           (verify / send-otp / verify-otp /
                                           submit / download); unique because
                                           tokens are unique by construction.
      • signing_submissions.customer_id — used to find a customer's submission.
      • customers.created_at            — default sort for the admin list.
      • customers.CONSUMER_NO           — unique: no two customers share a
                                           consumer number, even when saved at
                                           the same moment.

    Index creation is best-effort: a failure here (e.g. a pre-existing duplicate
    blocking the unique index) must not stop the API from booting.
    """
    try:
        await db.signing_submissions.create_index("token", unique=True)
        await db.signing_submissions.create_index("customer_id")
        await db.customers.create_index("created_at")
        await db.customers.create_index("created_by")
        # One base-stock document per equipment combination.
        await db.inventory.create_index(
            [("category", 1), ("company", 1), ("spec", 1)], unique=True
        )
        # One option per (list, lower-cased value) — blocks "Polycab"/"polycab".
        await db.catalog_items.create_index([("type", 1), ("key", 1)], unique=True)
        print("MongoDB indexes ensured")
    except Exception as e:
        print(f"Index creation warning: {e}")
    try:
        # Separate so existing duplicates (old data) only skip this one index.
        await db.customers.create_index("CONSUMER_NO", unique=True)
    except Exception as e:
        print(f"Unique CONSUMER_NO index not created (duplicate consumer numbers exist?): {e}")
    await _migrate_user_roles()
    await _setup_auth_collections()
    await seed_catalog(db)


async def seed_catalog(database):
    """
    Idempotent: fill each dealer/equipment list the first time it's empty, with
    the options that used to be hard-coded in the frontend. Once a list has any item — even a
    deactivated one — it's left alone, so admin changes are never overwritten.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        for type_, defaults in CATALOG_DEFAULTS.items():
            if await database.catalog_items.count_documents({"type": type_}):
                continue
            entries = [
                (d, None) if isinstance(d, str) else d
                for d in defaults
            ]
            seen = set()
            n = 0
            for raw, warranty in entries:
                try:
                    value = normalize_catalog_value(type_, raw)
                except ValueError:
                    continue
                if value_key(value) in seen:
                    continue
                seen.add(value_key(value))
                doc = {
                    "type": type_, "value": value, "key": value_key(value),
                    "active": True, "created_by": None,
                    "created_at": now, "updated_at": now,
                }
                if warranty:
                    doc["warranty"] = warranty
                await database.catalog_items.insert_one(doc)
                n += 1
            if n:
                print(f"Seeded {n} {type_} catalog items")
    except Exception as e:
        print(f"Catalog seed warning: {e}")


async def _migrate_user_roles():
    """
    One-time, idempotent move from the old single `role` string to the
    `roles` list. Before RBAC every account was created with role "admin", so
    legacy users without a `roles` field keep admin access (otherwise the
    existing admins would be locked out on deploy). New signups get roles=[].
    """
    try:
        async for u in db.users.find({"roles": {"$exists": False}}, {"role": 1}):
            legacy = u.get("role") or "admin"
            roles = [legacy] if legacy in ("admin", "data_entry", "installation", "documents") else []
            await db.users.update_one(
                {"_id": u["_id"]},
                {"$set": {"roles": roles}, "$unset": {"role": ""}},
            )
            print(f"Migrated user {u['_id']} to roles={roles}")
    except Exception as e:
        print(f"User role migration warning: {e}")


async def _migrate_user_emails(database) -> list[str]:
    """
    Lower-case stored emails so login is case-insensitive. An address whose
    lower-cased form already belongs to another account is left alone and
    reported: an admin must merge or fix those two accounts by hand.
    Returns the list of conflicting emails.
    """
    conflicts = []
    async for u in database.users.find({}, {"email": 1}):
        email = u.get("email") or ""
        lower = email.strip().lower()
        if email == lower:
            continue
        if await database.users.find_one({"email": lower, "_id": {"$ne": u["_id"]}}):
            conflicts.append(email)
            continue
        await database.users.update_one({"_id": u["_id"]}, {"$set": {"email": lower}})
        print(f"Lower-cased email for user {u['_id']}")
    for email in conflicts:
        print(f"WARNING: {email!r} differs only in letter case from another account; "
              "this user can't sign in by email until one of the two is changed (Users page).")
    return conflicts


async def _setup_auth_collections():
    """Email normalisation + the unique / expiry indexes the auth flows rely on."""
    try:
        await _migrate_user_emails(db)
    except Exception as e:
        print(f"User email migration warning: {e}")
    for args, kwargs, label in [
        (("email",), {"unique": True}, "unique users.email"),
        # Only real usernames are unique; older accounts may not have one yet.
        (("username",), {"unique": True, "partialFilterExpression": {"username": {"$type": "string"}}},
         "unique users.username"),
        (([("purpose", 1), ("subject", 1)],), {"unique": True}, "auth_codes key"),
        (("expires_at",), {"expireAfterSeconds": 0}, "auth_codes expiry"),
    ]:
        coll = db.users if label.startswith("unique users") else db.auth_codes
        try:
            await coll.create_index(*args, **kwargs)
        except Exception as e:
            print(f"Index {label} not created: {e}")
    try:
        await db.auth_attempts.create_index([("key", 1), ("created_at", 1)])
        await db.auth_attempts.create_index("expires_at", expireAfterSeconds=0)
    except Exception as e:
        print(f"auth_attempts index warning: {e}")


async def close_db():
    global client
    if client:
        client.close()


def get_db():
    return db
