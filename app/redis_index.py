# -------------------------------------------------------------
# Redis Index Management (robust: client + server checks)
# -------------------------------------------------------------
import redis
from app.config import settings

# ---------- Client-side availability (redis-py RediSearch) ----------
try:
    # These are provided by redis-py 4.x/5.x when RediSearch is available
    from redis.commands.search.field import TextField, NumericField, TagField, VectorField
    from redis.commands.search.indexDefinition import IndexDefinition, IndexType
    CLIENT_HAS_REDISEARCH = True
except Exception as e:
    print(f"Redisearch client import failed: {e}")
    CLIENT_HAS_REDISEARCH = False
    TextField = NumericField = TagField = VectorField = IndexDefinition = IndexType = None

# --- Legacy embedding field aliases for backward compatibility ---
# Other modules (e.g., app.rag.redis_vectorstores) import these names.
EMB_HOTEL     = "embedding"
EMB_ATTR      = "embedding"
EMB_EVENT     = "embedding"
EMB_FLIGHT    = "embedding"
EMB_TRANSPORT = "embedding"

# ---------- Constants ----------
# IMPORTANT: set this to the actual embedding dimension you use.
# If your embed_text() uses OpenAI text-embedding-3-large, this is 3072;
# if it uses text-embedding-3-small or text-embedding-ada-002, this is 1536.
EMB_DIM = 1536

IDX_HOTELS       = "idx:hotels"
IDX_ATTRACTIONS  = "idx:attractions"
IDX_EVENTS       = "idx:events"
IDX_FLIGHTS      = "idx:flights"
IDX_TRANSPORTS   = "idx:transports"

PREFIX_MAP = {
    IDX_HOTELS: "hotel:",
    IDX_ATTRACTIONS: "attraction:",
    IDX_EVENTS: "event:",
    IDX_FLIGHTS: "flight:",
    IDX_TRANSPORTS: "transport:",
}


# ---------- Helpers ----------
def get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)


def server_has_redisearch(client: redis.Redis) -> tuple[bool, str | None]:
    """
    Check the Redis server for the RediSearch module via MODULE LIST.
    Returns (has_search, version_str|None).
    """
    try:
        modules = client.execute_command("MODULE", "LIST")
        # Handle both dict-style and list-style module metadata
        for m in modules:
            if isinstance(m, dict):
                name = m.get(b"name", b"").decode()
                ver = m.get(b"ver", None)
            else:
                # Old style: [b"name", b"search", b"ver", 80204, ...]
                mm = {m[i]: m[i + 1] for i in range(0, len(m), 2)}
                name = mm.get(b"name", b"").decode()
                ver = mm.get(b"ver", None)

            if name == "search":
                if isinstance(ver, int):
                    return True, str(int(ver))
                if isinstance(ver, bytes):
                    return True, ver.decode()
                return True, str(ver)
        return False, None
    except Exception:
        # If MODULE LIST is blocked or fails, assume RediSearch is not available
        return False, None


def _create_index(client: redis.Redis, index_name: str, prefix: str, schema):
    """
    Create a single RediSearch index if it does not already exist.
    Uses redis-py search API (client.ft(index_name)).
    """
    # Guard on client-side imports first
    if not CLIENT_HAS_REDISEARCH:
        print(f"Skip {index_name}: redis-py RediSearch client not installed.")
        return

    # Guard on server-side module
    has_search, ver = server_has_redisearch(client)
    if not has_search:
        print(f"Skip {index_name}: Redis server missing RediSearch module.")
        return

    try:
        client.ft(index_name).info()
        print(f"Index '{index_name}' already exists.")
    except Exception:
        try:
            definition = IndexDefinition(prefix=[prefix], index_type=IndexType.HASH)
            client.ft(index_name).create_index(schema, definition=definition)
            print(f"Created index: {index_name}")
        except Exception as e:
            print(f"Failed to create index '{index_name}': {e}")


# ---------- Individual index builders ----------
def ensure_hotel_index(client: redis.Redis):
    if not CLIENT_HAS_REDISEARCH:
        print("Skipping hotel index — redis-py RediSearch client not installed.")
        return

    schema = [
        TagField("cityName"),
        TextField("hotelName"),
        NumericField("price"),
        NumericField("rating"),
        TextField("description"),
        VectorField(
            "embedding",
            "FLAT",
            {
                "TYPE": "FLOAT32",
                "DIM": EMB_DIM,
                "DISTANCE_METRIC": "COSINE",
            },
        ),
    ]
    _create_index(client, IDX_HOTELS, PREFIX_MAP[IDX_HOTELS], schema)


def ensure_attraction_index(client: redis.Redis):
    if not CLIENT_HAS_REDISEARCH:
        print("Skipping attraction index — redis-py RediSearch client not installed.")
        return

    schema = [
        TagField("cityName"),
        TextField("name"),
        TagField("category"),
        NumericField("entry_fee"),
        TextField("opening_hours"),
        NumericField("rating"),
        VectorField(
            "embedding",
            "FLAT",
            {
                "TYPE": "FLOAT32",
                "DIM": EMB_DIM,
                "DISTANCE_METRIC": "COSINE",
            },
        ),
    ]
    _create_index(client, IDX_ATTRACTIONS, PREFIX_MAP[IDX_ATTRACTIONS], schema)


def ensure_event_index(client: redis.Redis):
    if not CLIENT_HAS_REDISEARCH:
        print("Skipping event index — redis-py RediSearch client not installed.")
        return

    schema = [
        TagField("cityName"),
        TextField("name"),
        TextField("type"),
        TextField("date"),
        TextField("description"),
        VectorField(
            "embedding",
            "FLAT",
            {
                "TYPE": "FLOAT32",
                "DIM": EMB_DIM,
                "DISTANCE_METRIC": "COSINE",
            },
        ),
    ]
    _create_index(client, IDX_EVENTS, PREFIX_MAP[IDX_EVENTS], schema)


def ensure_flight_index(client: redis.Redis):
    if not CLIENT_HAS_REDISEARCH:
        print("Skipping flight index — redis-py RediSearch client not installed.")
        return

    schema = [
        TagField("origin"),
        TagField("destination"),
        TextField("airline"),
        NumericField("price"),
        TextField("duration"),
        VectorField(
            "embedding",
            "FLAT",
            {
                "TYPE": "FLOAT32",
                "DIM": EMB_DIM,
                "DISTANCE_METRIC": "COSINE",
            },
        ),
    ]
    _create_index(client, IDX_FLIGHTS, PREFIX_MAP[IDX_FLIGHTS], schema)


def ensure_transport_index(client: redis.Redis):
    if not CLIENT_HAS_REDISEARCH:
        print("Skipping transport index — redis-py RediSearch client not installed.")
        return

    schema = [
        TagField("cityName"),
        TextField("name"),
        TextField("type"),
        NumericField("price"),
        TextField("description"),
        VectorField(
            "embedding",
            "FLAT",
            {
                "TYPE": "FLOAT32",
                "DIM": EMB_DIM,
                "DISTANCE_METRIC": "COSINE",
            },
        ),
    ]
    _create_index(client, IDX_TRANSPORTS, PREFIX_MAP[IDX_TRANSPORTS], schema)


# ---------- One-call helper for main.py ----------
def ensure_all_indexes(client: redis.Redis):
    has_search_client = CLIENT_HAS_REDISEARCH
    has_search_server, ver = server_has_redisearch(client)

    print("-----------------------------------------------------")
    print("Redis Vector Index System")
    print(f"Redis URL: {settings.REDIS_URL}")
    print(f"redis-py search client installed: {has_search_client}")
    print(
        "Redis server RediSearch loaded:  "
        f"{has_search_server}" + (f" (ver {ver})" if ver else "")
    )
    print("-----------------------------------------------------")

    if not (has_search_client and has_search_server):
        print("Skipping all index creations — RediSearch not fully available.")
        return

    ensure_hotel_index(client)
    ensure_attraction_index(client)
    ensure_event_index(client)
    ensure_flight_index(client)
    ensure_transport_index(client)
