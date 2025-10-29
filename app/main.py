from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.itinerary_router import router as itinerary_router
from app.db.mongo import get_mongo_client
from app.rag.utils.vector_initilizer import (
    ensure_vector_index,
    ensure_embeddings_for_collection,
)
from app.redis_index import (
    ensure_hotel_index,
    ensure_attraction_index,
    ensure_event_index,
    ensure_flight_index,
    ensure_transport_index,
)
import redis
from app.config import settings

# Initialize FastAPI
app = FastAPI(title="Travel AI Backend")

# ✅ Allow CORS from everywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Register routers
app.include_router(itinerary_router)

# Redis connection
r_sync = redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"ok": True}


@app.on_event("startup")
async def setup_vector_indexes():
    """Startup routine: ensure Redis indexes + Mongo embeddings exist."""
    print("🔍 Checking Redis vector indexes and Mongo embeddings...")

    # Ensure indexes exist (Redis schema creation)
    ensure_hotel_index(r_sync)
    ensure_attraction_index(r_sync)
    ensure_event_index(r_sync)
    ensure_flight_index(r_sync)
    ensure_transport_index(r_sync)

    # Create or verify vector indexes in Redis
    ensure_vector_index("idx:hotels", "hotel", "embedding", 384)
    ensure_vector_index("idx:attractions", "attr", "embedding", 384)
    ensure_vector_index("idx:events", "event", "embedding", 384)
    ensure_vector_index("idx:flights", "flight", "embedding", 384)
    ensure_vector_index("idx:transports", "transport", "embedding", 384)

    # Get MongoDB client
    db = get_mongo_client()
    hotels = db["hotels"]
    attractions = db["attractions"]
    events = db["events"]
    flights = db["flights"]
    transports = db["transports"]

    # Generate embeddings for missing documents
    await ensure_embeddings_for_collection(hotels, "idx:hotels", "hotel", "embedding", 384)
    await ensure_embeddings_for_collection(attractions, "idx:attractions", "attr", "embedding", 384)
    await ensure_embeddings_for_collection(events, "idx:events", "event", "embedding", 384)
    await ensure_embeddings_for_collection(flights, "idx:flights", "flight", "embedding", 384)
    await ensure_embeddings_for_collection(transports, "idx:transports", "transport", "embedding", 384)

    print("✅ All vector indexes and embeddings verified.")
