import asyncio
from app.db.mongo import get_mongo_client
from app.embeddings.embed_text import embed_text

async def patch_transports():
    db = get_mongo_client()
    collection = db["transports"]

    # Fetch only documents without embeddings
    cursor = collection.find({"embedding": {"$exists": False}})
    docs = await cursor.to_list(length=100)

    if not docs:
        print("✅ All transport records already have embeddings.")
        return

    for doc in docs:
        text = (
            f"{doc.get('mode', '')} {doc.get('provider', '')} "
            f"from {doc.get('from_city', '')} to {doc.get('to_city', '')} "
            f"price {doc.get('price', '')} SAR"
        )

        # Generate embedding
        embedding = embed_text(text)

        # ✅ Convert NumPy array to list before saving
        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()

        # Update MongoDB document
        await collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"embedding": embedding}}
        )

        print(f"✅ Added embedding for transport: {doc.get('id')} ({doc.get('mode')})")

    print("🎯 Finished patching transport embeddings.")

if __name__ == "__main__":
    asyncio.run(patch_transports())
