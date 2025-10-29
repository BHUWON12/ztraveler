import asyncio
from app.db.mongo import get_mongo_client
from app.rag.utils.vector_initilizer import ensure_embeddings_for_collection
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    db = get_mongo_client()

    await ensure_embeddings_for_collection(db["hotels"], "idx:hotels", "hotel", "embedding", 384)
    await ensure_embeddings_for_collection(db["attractions"], "idx:attractions", "attr", "embedding", 384)
    await ensure_embeddings_for_collection(db["events"], "idx:events", "event", "embedding", 384)
    await ensure_embeddings_for_collection(db["flights"], "idx:flights", "flight", "embedding", 384)
    await ensure_embeddings_for_collection(db["transports"], "idx:transports", "transport", "embedding", 384)

if __name__ == "__main__":
    asyncio.run(main())
