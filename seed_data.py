import asyncio
import json
import os
import base64
import numpy as np
from datetime import datetime
from bson import Binary, ObjectId
import motor.motor_asyncio
import redis.asyncio as aioredis
import redis


# ----------------------------------------------------
# Local Imports
# ----------------------------------------------------
from app.config import settings
from app.embeddings.embed_text import embed_text
from app.redis_index import (
    ensure_hotel_index,
    ensure_attraction_index,
    ensure_event_index,
    PFX_HOTEL, EMB_HOTEL,
    PFX_ATTR, EMB_ATTR,
    PFX_EVENT, EMB_EVENT,
)

# ----------------------------------------------------
# Environment Validation
# ----------------------------------------------------
REQUIRED_ENV = [
    "MONGO_URI",
    "MONGO_DB",
    "REDIS_URL",
    "COLL_HOTELS",
    "COLL_ATTRACTIONS",
    "COLL_EVENTS",
]
missing = [v for v in REQUIRED_ENV if not getattr(settings, v, None)]
if missing:
    raise EnvironmentError(f"❌ Missing required environment variables: {', '.join(missing)}")

print("🌍 Loaded environment configuration:")
print(f"  Mongo URI: {settings.MONGO_URI}")
print(f"  Mongo DB: {settings.MONGO_DB}")
print(f"  Redis URL: {settings.REDIS_URL}")
print(f"  Collections → Hotels: {settings.COLL_HOTELS}, Attractions: {settings.COLL_ATTRACTIONS}, Events: {settings.COLL_EVENTS}")
print("----------------------------------------------------")

# ----------------------------------------------------
# Setup Clients
# ----------------------------------------------------
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_URI)
db = mongo_client[settings.MONGO_DB]
redis_sync = redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)
redis_async = aioredis.from_url(settings.REDIS_URL, decode_responses=False)

# ----------------------------------------------------
# Utilities
# ----------------------------------------------------
def _vec_to_bytes(v):
    if isinstance(v, list):
        v = np.array(v, dtype=np.float32)
    return v.astype(np.float32).tobytes()

def _load_json(file):
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)

def _convert_embedding(embedding_field, doc):
    """Normalize or generate embeddings"""
    emb = doc.get(embedding_field)
    if emb is None:
        # Generate embedding dynamically
        text_fields = [doc.get("name"), doc.get("hotelName"),
                       doc.get("description"), doc.get("cityName")]
        combined = " ".join(filter(None, text_fields))
        emb_vec = embed_text(combined)
        return _vec_to_bytes(emb_vec)

    if isinstance(emb, list):
        return _vec_to_bytes(np.array(emb, dtype=np.float32))

    if isinstance(emb, str):
        try:
            return base64.b64decode(emb)
        except Exception:
            if isinstance(emb, dict) and "$binary" in emb:
                return base64.b64decode(emb["$binary"]["base64"])

    if isinstance(emb, Binary):
        return bytes(emb)

    return emb

# ----------------------------------------------------
# Generic Seeder
# ----------------------------------------------------
async def seed_collection(name, file, coll_name,
                          redis_prefix=None, embedding_field=None,
                          ensure_index=None):
    if not os.path.exists(file):
        print(f"⚠️ {file} not found, skipping...")
        return

    data = _load_json(file)
    coll = db[coll_name]
    await coll.delete_many({})

    if ensure_index:
        ensure_index(redis_sync)

    for doc in data:
        # Convert ISO dates to datetime
        for k, v in list(doc.items()):
            if isinstance(v, str) and v.endswith("Z"):
                try:
                    doc[k] = datetime.fromisoformat(v.replace("Z", "+00:00"))
                except Exception:
                    pass

        if embedding_field:
            doc[embedding_field] = _convert_embedding(embedding_field, doc)

        # Insert into MongoDB
        await coll.insert_one(doc)

        # Prepare Redis mapping (safe types only)
        if redis_prefix:
            redis_key = f"{redis_prefix}{doc.get('id') or doc.get('hotelId')}"

            mapping = {}
            for k, v in doc.items():
                if isinstance(v, (bytes, list, dict, Binary)):
                    continue
                if isinstance(v, ObjectId):
                    v = str(v)
                if isinstance(v, datetime):
                    v = v.isoformat()
                mapping[k] = v

            # Add embedding if present
            if embedding_field and doc.get(embedding_field):
                mapping[embedding_field] = doc[embedding_field]

            await redis_async.hset(redis_key, mapping=mapping)

    print(f"✅ Seeded {len(data)} {name} from {file}")

# ----------------------------------------------------
# Main
# ----------------------------------------------------
async def main():
    print("🚀 Starting JSON seeding with .env configuration...")

    await seed_collection("Hotels", "seed/Hotels.json", settings.COLL_HOTELS,
                          redis_prefix=PFX_HOTEL, embedding_field=EMB_HOTEL,
                          ensure_index=ensure_hotel_index)

    await seed_collection("Attractions", "seed/Attractions.json", settings.COLL_ATTRACTIONS,
                          redis_prefix=PFX_ATTR, embedding_field=EMB_ATTR,
                          ensure_index=ensure_attraction_index)

    await seed_collection("Events", "seed/Events.json", settings.COLL_EVENTS,
                          redis_prefix=PFX_EVENT, embedding_field=EMB_EVENT,
                          ensure_index=ensure_event_index)

    await seed_collection("Flights", "seed/Flights.json", getattr(settings, "COLL_FLIGHTS", "flights"))
    await seed_collection("Transports", "seed/Transports.json", getattr(settings, "COLL_TRANSPORTS", "transports"))

    print("🎉 All datasets seeded successfully using .env settings.")

if __name__ == "__main__":
    asyncio.run(main())
