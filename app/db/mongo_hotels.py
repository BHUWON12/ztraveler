# app/db/mongo_hotels.py
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client = AsyncIOMotorClient(settings.MONGO_URI)
db = client[settings.MONGO_DB]

async def fetch_hotels_from_mongo(city: str, limit: int = 10):
    """
    Fetch hotels directly from MongoDB when Redis doesn't return results.
    """
    collection = db[settings.COLL_HOTELS]
    cursor = collection.find({"cityName": {"$regex": f"^{city}$", "$options": "i"}}).limit(limit)
    hotels = await cursor.to_list(length=limit)
    return hotels
