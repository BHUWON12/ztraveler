import redis
import numpy as np
from app.embeddings.embed_text import embed_text
from app.config import settings
from motor.motor_asyncio import AsyncIOMotorCollection

# Synchronous Redis connection
r_sync = redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)


def ensure_vector_index(index_name: str, prefix: str, vector_field: str, dim: int):
    """Create Redis vector index if it doesn't exist."""
    try:
        existing = r_sync.ft(index_name)
        existing.info()
        print(f"✅ Index '{index_name}' already exists.")
        return
    except Exception:
        pass  # Index does not exist, so we create it

    # Base schema — minimal universal fields
    base_schema = [
        "ON", "HASH", "PREFIX", "1", f"{prefix}:",
        "SCHEMA",
        vector_field, "VECTOR", "HNSW", "6",
        "TYPE", "FLOAT32", "DIM", str(dim), "DISTANCE_METRIC", "COSINE",
        "name", "TEXT",
        "description", "TEXT",
        "cityName", "TEXT",
        "category", "TEXT",
        "type", "TEXT",
        "price", "NUMERIC",
        "rating", "NUMERIC"
    ]

    try:
        r_sync.execute_command("FT.CREATE", index_name, *base_schema)
        print(f"🆕 Created Redis vector index '{index_name}'.")
    except redis.ResponseError as e:
        if "Index already exists" in str(e):
            print(f"⚠️ Index '{index_name}' already exists (race condition).")
        else:
            raise


async def ensure_embeddings_for_collection(
    collection: AsyncIOMotorCollection,
    index_name: str,
    prefix: str,
    vector_field: str,
    dim: int,
):
    """
    Ensures all docs in Mongo have embeddings.
    Auto-detects best text fields per collection (hotels, transports, etc.).
    Syncs vectors to Redis.
    """
    print(f"🔍 Checking embeddings for collection '{collection.name}'...")

    cursor = collection.find({"embedding": {"$exists": False}})
    count_new = 0

    async for doc in cursor:
        # Dynamically choose text fields to embed
        possible_fields = [
            "hotelName", "name", "description", "route",
            "category", "type", "cityName", "destination"
        ]
        text_parts = [str(doc.get(f, "")) for f in possible_fields if doc.get(f)]
        text = " ".join(text_parts).strip()

        if not text:
            continue  # skip empty docs

        try:
            vec = embed_text(text)
            if vec is None:
                continue

            # Update Mongo
            await collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"embedding": vec.tolist()}},
            )

            # Prepare Redis hash data
            redis_key = f"{prefix}:{doc.get('hotelId') or doc.get('id') or str(doc['_id'])}"
            data = {vector_field: np.array(vec, dtype=np.float32).tobytes()}

            # Include basic metadata (only if exists)
            for field in [
                "hotelName", "name", "cityName", "route",
                "price", "rating", "category", "type"
            ]:
                if doc.get(field):
                    data[field] = str(doc[field])

            r_sync.hset(redis_key, mapping=data)
            count_new += 1

        except Exception as e:
            print(f"⚠️ Skipped {collection.name} doc {doc.get('_id')} — {e}")

    if count_new:
        print(f"✅ Added {count_new} new embeddings for {collection.name}.")
    else:
        print(f"👍 All documents in {collection.name} already have embeddings.")
