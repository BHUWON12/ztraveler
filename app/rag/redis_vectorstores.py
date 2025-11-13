from typing import List, Dict, Any, Optional, Union
import numpy as np
import redis
import re
from redis.commands.search.query import Query
from app.config import settings
from app.embeddings.embed_text import embed_text
from app.redis_index import (
    IDX_HOTELS, EMB_HOTEL,
    IDX_ATTRACTIONS, EMB_ATTR,
    IDX_EVENTS, EMB_EVENT,
    IDX_FLIGHTS, EMB_FLIGHT,
    IDX_TRANSPORTS, EMB_TRANSPORT,
)

# ------------------------------------------------------------
# 🔌 Redis connection
# ------------------------------------------------------------
r_sync = redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)


# ------------------------------------------------------------
# 🧹 Utilities
# ------------------------------------------------------------
REDIS_TAG_ESCAPE = re.compile(r"[,.<>{}\[\]\"'\\:;!@#$%^&*()\-=\+~|/ ]")  # includes space

def escape_tag(value: str) -> str:
    """
    Escape/normalize a value for RediSearch TAG fields.
    Spaces must be escaped; we conservatively replace many specials with '\ '.
    """
    if not value:
        return ""
    # Replace any disallowed char (including space) with escaped space
    return REDIS_TAG_ESCAPE.sub(r"\\ ", value.strip())

def to_float32_bytes(vec: Union[np.ndarray, List[float]]) -> bytes:
    if isinstance(vec, np.ndarray):
        arr = vec
    else:
        arr = np.array(vec, dtype=np.float32)
    if arr.dtype != np.float32:
        arr = arr.astype(np.float32)
    return arr.tobytes()

def decode_bytes(val: Any) -> Any:
    if isinstance(val, (bytes, bytearray)):
        try:
            return val.decode("utf-8", errors="ignore")
        except Exception:
            return val
    return val

def coerce_numeric(payload: Dict[str, Any], keys: List[str]):
    for k in keys:
        if k in payload and isinstance(payload[k], str):
            try:
                payload[k] = float(payload[k])
            except Exception:
                pass


# ------------------------------------------------------------
# 🧠 Core KNN query helper (DIALECT 2)
# ------------------------------------------------------------
def _knn_query(
    index: str,
    vector_field: str,
    query_vec: np.ndarray,
    k: int,
    filter_str: Optional[str] = None,
    return_fields: Optional[List[str]] = None,
    exclude_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Executes a DIALECT 2 KNN query with optional filter and exclusions.
    NOTE: Exclusions only work if you actually store a field like 'doc_id' or 'id' in your schema.
    RediSearch's internal document id (key name) is not directly filterable unless stored.
    """
    # Prepare vector param
    vec_bytes = to_float32_bytes(query_vec)

    # Base filter
    base_filter = filter_str or "*"

    # Optional: try exclusion if 'id' is a real indexed field in your schema
    if exclude_ids:
        # This assumes you have a TagField/TextField named 'id'. If not, this clause will be ignored by RediSearch.
        no_ids = " ".join([f"-@id:{{{escape_tag(eid)}}}" for eid in exclude_ids])
        base_filter = f"({base_filter}) {no_ids}".strip()

    # Compose DIALECT 2 KNN query
    # IMPORTANT: Use PARAMS (query_params) with $BLOB, and set .dialect(2)
    q_str = f"{base_filter}=>[KNN {k} @{vector_field} $BLOB AS score]"
    q = Query(q_str).sort_by("score").paging(0, k).dialect(2)

    # Return fields
    ret = return_fields or [
        "id", "name", "cityName", "price", "rating",
        "category", "entry_fee", "description", "type", "date",
    ]
    q.return_fields(*ret, "score")

    try:
        res = r_sync.ft(index).search(q, query_params={"BLOB": vec_bytes})
    except Exception as e:
        print(f"[Redis Search Error] {e} | Query: {q_str}")
        return []

    docs: List[Dict[str, Any]] = []
    for d in getattr(res, "docs", []):
        # d.__dict__ contains fields; exclude private attrs
        payload = {k: v for k, v in d.__dict__.items() if not k.startswith("_")}
        # Decode bytes fields
        for k, v in list(payload.items()):
            payload[k] = decode_bytes(v)
        # Coerce numeric
        coerce_numeric(payload, ["price", "rating", "entry_fee"])
        docs.append(payload)
    return docs


# ------------------------------------------------------------
# 🏨 Hotels
# ------------------------------------------------------------
def search_hotels(city: str, max_price: float, k: int = 8) -> List[Dict[str, Any]]:
    safe_city = escape_tag(city)
    # Build semantic vector
    qvec = embed_text(f"best hotels in {city} under {int(max_price)} SAR")
    # Filter by cityName (TAG) and optional price range if indexed numeric
    # If 'price' is NumericField, this works: @price:[0 {max_price}]
    price_clause = f"@price:[0 {max_price}]" if (max_price and max_price > 0) else ""
    where = f"@cityName:{{{safe_city}}} {price_clause}".strip()

    return _knn_query(
        index=IDX_HOTELS,
        vector_field=EMB_HOTEL,
        query_vec=qvec,
        k=k,
        filter_str=where if where else "*",
        return_fields=["hotelName", "cityName", "price", "rating", "description"],
    )


# ------------------------------------------------------------
# 🏛️ Attractions
# ------------------------------------------------------------
def search_attractions(
    city: str,
    interests: List[str],
    k: int = 12,
    exclude_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    safe_city = escape_tag(city)
    safe_intent = ", ".join(interests) if interests else "top attractions"
    qvec = embed_text(f"{safe_intent} in {city} best tourist spots")
    where = f"@cityName:{{{safe_city}}}"

    return _knn_query(
        index=IDX_ATTRACTIONS,
        vector_field=EMB_ATTR,
        query_vec=qvec,
        k=k,
        filter_str=where,
        return_fields=[
            "id", "name", "cityName", "category", "entry_fee",
            "opening_hours", "description", "rating",
        ],
        exclude_ids=exclude_ids,
    )


# ------------------------------------------------------------
# 🎭 Events
# ------------------------------------------------------------
def search_events(
    city: str,
    start_iso: str,
    end_iso: str,
    k: int = 8,
    exclude_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    safe_city = escape_tag(city)
    qvec = embed_text(f"events and festivals in {city} between {start_iso} and {end_iso}")
    where = f"@cityName:{{{safe_city}}}"

    return _knn_query(
        index=IDX_EVENTS,
        vector_field=EMB_EVENT,
        query_vec=qvec,
        k=k,
        filter_str=where,
        return_fields=["id", "name", "cityName", "type", "date", "description"],
        exclude_ids=exclude_ids,
    )


# ------------------------------------------------------------
# ✈️ Flights
# ------------------------------------------------------------
def search_flights(origin: str, destination: str, k: int = 5) -> List[Dict[str, Any]]:
    safe_origin = escape_tag(origin)
    safe_dest = escape_tag(destination)
    qvec = embed_text(f"direct flights from {origin} to {destination}")
    where = f"@origin:{{{safe_origin}}} @destination:{{{safe_dest}}}"

    # Note: schema field might be 'duration' (TextField) or 'duration_minutes' (Numeric in Mongo).
    # We'll request both and normalize later.
    return _knn_query(
        index=IDX_FLIGHTS,
        vector_field=EMB_FLIGHT,
        query_vec=qvec,
        k=k,
        filter_str=where,
        return_fields=["id", "airline", "origin", "destination", "price", "duration", "duration_minutes"],
    )


# ------------------------------------------------------------
# 🚗 Transports
# ------------------------------------------------------------
def search_transports(city: str, k: int = 5) -> List[Dict[str, Any]]:
    safe_city = escape_tag(city)
    qvec = embed_text(f"public and private transport options in {city}")
    where = f"@cityName:{{{safe_city}}}"

    return _knn_query(
        index=IDX_TRANSPORTS,
        vector_field=EMB_TRANSPORT,
        query_vec=qvec,
        k=k,
        filter_str=where,
        return_fields=["id", "mode", "provider", "cityName", "price", "description"],
    )


# ------------------------------------------------------------
# 🧩 Multi-Index Hybrid Search (Attractions + Events + Hotels)
# ------------------------------------------------------------
def search_city_experiences(city: str, interests: List[str], k_each: int = 5) -> List[Dict[str, Any]]:
    """
    Combined semantic search across attractions, events, and hotels for a given city.
    Perfect for RAG-driven 'Things to do in Jeddah' queries.
    """
    safe_city = escape_tag(city)
    qvec = embed_text(f"things to do, see and experience in {city} related to {', '.join(interests or [])}")

    results: List[Dict[str, Any]] = []
    results.extend(_knn_query(IDX_ATTRACTIONS, EMB_ATTR, qvec, k_each, f"@cityName:{{{safe_city}}}"))
    results.extend(_knn_query(IDX_EVENTS,      EMB_EVENT, qvec, k_each, f"@cityName:{{{safe_city}}}"))
    results.extend(_knn_query(IDX_HOTELS,      EMB_HOTEL, qvec, k_each, f"@cityName:{{{safe_city}}}"))

    # Deduplicate by explicit 'id' if present; else fall back to 'name'
    unique, seen = [], set()
    for item in results:
        iid = item.get("id") or item.get("name")
        if iid not in seen:
            seen.add(iid)
            unique.append(item)
    return unique
