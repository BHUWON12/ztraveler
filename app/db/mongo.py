from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

_mongo_client = None

def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(settings.MONGO_URI)[settings.MONGO_DB]
    return _mongo_client

def get_collection(name: str):
    """
    Returns an AsyncIOMotorCollection instance for the given collection name.
    Example: hotels = get_collection("hotels")
    """
    if not name:
        raise ValueError("Collection name is required")

    db = get_mongo_client()
    return db[name]
