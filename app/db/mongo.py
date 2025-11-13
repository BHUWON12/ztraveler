# -------------------------------------------------------------
# 🌍 MongoDB Connection Manager (Cloud Run Safe, Truthiness-safe)
# -------------------------------------------------------------
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from app.config import settings
import traceback
import asyncio

_mongo_client: Optional[AsyncIOMotorClient] = None
_mongo_db: Optional[AsyncIOMotorDatabase] = None
_lock = asyncio.Lock()


async def init_mongo() -> AsyncIOMotorDatabase:
    """
    Initialize the MongoDB connection exactly once (idempotent).
    Safe to call multiple times concurrently.
    """
    global _mongo_client, _mongo_db

    async with _lock:
        if _mongo_db is not None:
            return _mongo_db

        try:
            # Mask credentials in logs
            try:
                host_part = settings.MONGO_URI.split("@")[-1]
            except Exception:
                host_part = "<hidden>"
            print(f"🧩 Connecting to MongoDB: {host_part}")

            client = AsyncIOMotorClient(settings.MONGO_URI)
            db = client[settings.MONGO_DB]

            # Lightweight connectivity check
            await db.command("ping")

            _mongo_client = client
            _mongo_db = db
            print("✅ MongoDB connection established successfully.")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            traceback.print_exc()
            raise

    return _mongo_db


def get_mongo_client() -> AsyncIOMotorDatabase:
    """
    Backward-compatible synchronous getter.

    - If already initialized (via await init_mongo()), returns the live DB.
    - If not yet initialized, returns a *lazy* DB handle (no ping performed).
      Callers that need guaranteed connectivity should `await init_mongo()` first.
    """
    global _mongo_db, _mongo_client

    if _mongo_db is not None:
        return _mongo_db

    # Provide a non-pinged handle to avoid raising at import-time code paths.
    # This keeps old code working; warmup/route handlers should call init_mongo().
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
    return _mongo_client[settings.MONGO_DB]


def get_collection(name: str) -> AsyncIOMotorCollection:
    """
    Returns an AsyncIOMotorCollection for the given name.
    Example:
        hotels = get_collection("hotels")
    """
    if not name:
        raise ValueError("Collection name is required")
    db = get_mongo_client()
    return db[name]
