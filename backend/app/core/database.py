from motor.motor_asyncio import AsyncIOMotorClient
from .config import settings

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
        print("MongoDB indexes ensured")
    except Exception as e:
        print(f"Index creation warning: {e}")
    try:
        # Separate so existing duplicates (old data) only skip this one index.
        await db.customers.create_index("CONSUMER_NO", unique=True)
    except Exception as e:
        print(f"Unique CONSUMER_NO index not created (duplicate consumer numbers exist?): {e}")
    await _migrate_user_roles()


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


async def close_db():
    global client
    if client:
        client.close()


def get_db():
    return db
