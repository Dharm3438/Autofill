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


async def close_db():
    global client
    if client:
        client.close()


def get_db():
    return db
