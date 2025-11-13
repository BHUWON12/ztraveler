# -------------------------------------------------------------
# Travel AI Backend — FastAPI Entrypoint (Cloud Run Ready)
# -------------------------------------------------------------
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

# Routers
from app.api.itinerary_router import router as itinerary_router

# Mongo init
from app.db.mongo import get_mongo_client, init_mongo

# Redis index management
from app.redis_index import ensure_all_indexes

# Embeddings / vector utilities
from app.rag.utils.vector_initilizer import ensure_embeddings_for_collection

from app.config import settings
import redis
import asyncio
import traceback


# -------------------------------------------------------------
# Initialize FastAPI App
# -------------------------------------------------------------
app = FastAPI(
    title="Travel AI Backend",
    description="FastAPI backend for ZTraveler / Hala Saudi PMS-AI",
    version="1.0.0",
)

# Allow all origins (relax later for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(itinerary_router)


# -------------------------------------------------------------
# Health Check
# -------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


# -------------------------------------------------------------
# Manual warmup endpoint (optional)
# -------------------------------------------------------------
@app.get("/warmup")
async def warmup(background_tasks: BackgroundTasks):
    background_tasks.add_task(initialize_services)
    return {"message": "Warmup initiated — check logs for progress."}


# -------------------------------------------------------------
# Startup Hook — Automatically run initialization
# -------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    print("Application startup complete.")
    asyncio.create_task(initialize_services())


# -------------------------------------------------------------
# Initialization Logic (Redis + MongoDB + Embeddings)
# -------------------------------------------------------------
async def initialize_services():
    try:
        print("Starting warmup process...")
        print(f"Environment: {settings.ENV}")
        print(f"MongoDB URI: {settings.MONGO_URI}")
        print(f"Redis URL: {settings.REDIS_URL}")

        # -------------------------------------------------
        # Connect to Redis
        # -------------------------------------------------
        r = None
        try:
            r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)
            r.ping()
            print("Connected to Redis.")
        except Exception as re:
            print(f"Redis connection failed: {re}")
            traceback.print_exc()
            return

        # -------------------------------------------------
        # Create RediSearch vector indexes
        # -------------------------------------------------
        print("Ensuring Redis indexes exist...")
        ensure_all_indexes(r)

        # -------------------------------------------------
        # MongoDB connection
        # -------------------------------------------------
        print("Initializing MongoDB connection...")
        try:
            await init_mongo()
            db = get_mongo_client()
            print("MongoDB connected.")
        except Exception as me:
            print(f"MongoDB initialization failed: {me}")
            traceback.print_exc()
            return

        # -------------------------------------------------
        # Ensure embeddings for all Mongo collections
        # -------------------------------------------------
        print("Ensuring MongoDB embeddings...")
        await asyncio.gather(
            ensure_embeddings_for_collection(db["hotels"], "idx:hotels", "hotel", "embedding", 384),
            ensure_embeddings_for_collection(db["attractions"], "idx:attractions", "attr", "embedding", 384),
            ensure_embeddings_for_collection(db["events"], "idx:events", "event", "embedding", 384),
            ensure_embeddings_for_collection(db["flights"], "idx:flights", "flight", "embedding", 384),
            ensure_embeddings_for_collection(db["transports"], "idx:transports", "transport", "embedding", 384),
        )

        print("Warmup completed successfully.")

    except Exception as e:
        print(f"Warmup process failed: {e}")
        traceback.print_exc()
