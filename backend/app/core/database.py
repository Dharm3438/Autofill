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

    Index creation is best-effort: a failure here (e.g. a pre-existing duplicate
    blocking the unique index) must not stop the API from booting.
    """
    try:
        await db.signing_submissions.create_index("token", unique=True)
        await db.signing_submissions.create_index("customer_id")
        await db.customers.create_index("created_at")
        # DEALER_NAME is an exact-match filter on the installations overview,
        # which scans the whole collection — an index turns that filter from a
        # COLLSCAN into an index lookup.
        await db.customers.create_index("DEALER_NAME")
        print("MongoDB indexes ensured")
    except Exception as e:
        print(f"Index creation warning: {e}")


async def close_db():
    global client
    if client:
        client.close()


def get_db():
    return db
