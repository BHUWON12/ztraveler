import redis
from redis.commands.search.field import (
    TextField,
    NumericField,
    TagField,
    VectorField,
)
from redis.commands.search.index_definition import IndexDefinition, IndexType
from app.config import settings

# -----------------------------
# Constants
# -----------------------------
IDX_HOTELS = "idx:hotels"
IDX_ATTRACTIONS = "idx:attractions"
IDX_EVENTS = "idx:events"
IDX_FLIGHTS = "idx:flights"         # ✈️ New
IDX_TRANSPORTS = "idx:transports"   # 🚗 New

PFX_HOTEL = "hotel:"
PFX_ATTR = "attraction:"
PFX_EVENT = "event:"
PFX_FLIGHT = "flight:"              # ✈️ New
PFX_TRANSPORT = "transport:"        # 🚗 New

EMB_HOTEL = "embedding"
EMB_ATTR = "embedding"
EMB_EVENT = "embedding"
EMB_FLIGHT = "embedding"            # ✈️ New
EMB_TRANSPORT = "embedding"         # 🚗 New

# -----------------------------
# Common helper
# -----------------------------
def _create_index(client: redis.Redis, index_name: str, prefix: str, schema):
    """Create a RediSearch index if it doesn't exist."""
    try:
        client.ft(index_name).info()
        print(f"ℹ️ Index {index_name} already exists.")
    except Exception:
        definition = IndexDefinition(prefix=[prefix], index_type=IndexType.HASH)
        client.ft(index_name).create_index(schema, definition=definition)
        print(f"✅ Created index: {index_name}")

# -----------------------------
# 🏨 Hotel Index
# -----------------------------
def ensure_hotel_index(client: redis.Redis):
    schema = (
        TagField("cityName"),
        TextField("hotelName"),
        NumericField("price"),
        NumericField("rating"),
        TextField("description"),
        VectorField(EMB_HOTEL, "FLAT", {"TYPE": "FLOAT32", "DIM": 1536, "DISTANCE_METRIC": "COSINE"}),
    )
    _create_index(client, IDX_HOTELS, PFX_HOTEL, schema)

# -----------------------------
# 🏛️ Attraction Index
# -----------------------------
def ensure_attraction_index(client: redis.Redis):
    schema = (
        TagField("cityName"),
        TextField("name"),
        TagField("category"),
        NumericField("entry_fee"),
        TextField("opening_hours"),
        NumericField("rating"),
        VectorField(EMB_ATTR, "FLAT", {"TYPE": "FLOAT32", "DIM": 1536, "DISTANCE_METRIC": "COSINE"}),
    )
    _create_index(client, IDX_ATTRACTIONS, PFX_ATTR, schema)

# -----------------------------
# 🎭 Event Index
# -----------------------------
def ensure_event_index(client: redis.Redis):
    schema = (
        TagField("cityName"),
        TextField("name"),
        TextField("type"),
        TextField("date"),
        TextField("description"),
        VectorField(EMB_EVENT, "FLAT", {"TYPE": "FLOAT32", "DIM": 1536, "DISTANCE_METRIC": "COSINE"}),
    )
    _create_index(client, IDX_EVENTS, PFX_EVENT, schema)

# -----------------------------
# ✈️ Flight Index
# -----------------------------
def ensure_flight_index(client: redis.Redis):
    schema = (
        TagField("origin"),
        TagField("destination"),
        TextField("airline"),
        NumericField("price"),
        TextField("duration"),
        VectorField(EMB_FLIGHT, "FLAT", {"TYPE": "FLOAT32", "DIM": 1536, "DISTANCE_METRIC": "COSINE"}),
    )
    _create_index(client, IDX_FLIGHTS, PFX_FLIGHT, schema)

# -----------------------------
# 🚗 Transport Index
# -----------------------------
def ensure_transport_index(client: redis.Redis):
    schema = (
        TagField("cityName"),
        TextField("name"),
        TextField("type"),
        NumericField("price"),
        TextField("description"),
        VectorField(EMB_TRANSPORT, "FLAT", {"TYPE": "FLOAT32", "DIM": 1536, "DISTANCE_METRIC": "COSINE"}),
    )
    _create_index(client, IDX_TRANSPORTS, PFX_TRANSPORT, schema)
