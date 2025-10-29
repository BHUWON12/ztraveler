import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    ENV: str = os.getenv("ENV", "development")

    # Mongo
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "travelAI")

    # Redis Stack
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Collections
    COLL_HOTELS: str = os.getenv("COLL_HOTELS", "hotels")
    COLL_ATTRACTIONS: str = os.getenv("COLL_ATTRACTIONS", "attractions")
    COLL_EVENTS: str = os.getenv("COLL_EVENTS", "events")
    COLL_FLIGHTS: str = os.getenv("COLL_FLIGHTS", "flights")
    COLL_TRANSPORTS: str = os.getenv("COLL_TRANSPORTS", "transports")

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Allow extra .env variables without throwing validation errors
    model_config = {"extra": "allow"}

settings = Settings()
