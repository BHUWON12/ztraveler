from typing import List, Dict, Any, Optional
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
# 🧹 Utility: escape Redis special characters
# ------------------------------------------------------------
def escape_redis_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[,.<>{}\[\]\"'\\:;!@#$%^&*()\-=\+~|/]", " ", value)


# ------------------------------------------------------------
# 🧠 Core KNN query helper with exclusion + field selection
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
    vec_bytes = query_vec.astype(np.float32).tobytes()
    base_filter = filter_str or "*"

    # 🧩 Add exclusions
    if exclude_ids:
        exclude_str = " ".join([f"-@id:{{{eid}}}" for eid in exclude_ids])
        base_filter = f"({base_filter}) {exclude_str}"

    # Compose query
    q = f"{base_filter}=>[KNN {k} @{vector_field} $BLOB AS score]"
    query = Query(q).sort_by("score").paging(0, k)

    ret = return_fields or [
        "id", "name", "cityName", "price", "rating",
        "category", "entry_fee", "description", "type", "date"
    ]
    query.return_fields(*ret, "score")

    params = {"BLOB": vec_bytes}

    try:
        res = r_sync.ft(index).search(query, query_params=params)
    except Exception as e:
        print(f"[Redis Search Error] {e} | Query: {q}")
        return []

    docs = []
    for d in res.docs:
        payload = {k: v for k, v in d.__dict__.items() if not k.startswith("_")}

        # Normalize numeric fields
        for k, v in list(payload.items()):
            if isinstance(v, (bytes, bytearray)):
                try:
                    payload[k] = v.decode("utf-8")
                except Exception:
                    pass
            if k in ("price", "rating", "entry_fee") and isinstance(payload[k], str):
                try:
                    payload[k] = float(payload[k])
                except Exception:
                    pass

        docs.append(payload)
    return docs


# ------------------------------------------------------------
# 🏨 Hotels
# ------------------------------------------------------------
def search_hotels(city: str, max_price: float, k: int = 8) -> List[Dict[str, Any]]:
    safe_city = escape_redis_text(city)
    qvec = embed_text(f"best hotels in {safe_city} under {int(max_price)} SAR")
    where = f"@cityName:{{{safe_city}}}"
    return _knn_query(
        index=IDX_HOTELS,
        vector_field=EMB_HOTEL,
        query_vec=qvec,
        k=k,
        filter_str=where,
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
    safe_city = escape_redis_text(city)
    safe_intent = escape_redis_text(", ".join(interests)) if interests else "top attractions"
    qvec = embed_text(f"{safe_intent} in {safe_city} best tourist spots")
    where = f"@cityName:{{{safe_city}}}"
    return _knn_query(
        index=IDX_ATTRACTIONS,
        vector_field=EMB_ATTR,
        query_vec=qvec,
        k=k,
        filter_str=where,
        return_fields=[
            "id", "name", "cityName", "category", "entry_fee",
            "opening_hours", "description", "rating"
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
    safe_city = escape_redis_text(city)
    qvec = embed_text(f"events and festivals in {safe_city} between {start_iso} and {end_iso}")
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
    safe_origin = escape_redis_text(origin)
    safe_dest = escape_redis_text(destination)
    qvec = embed_text(f"direct flights from {safe_origin} to {safe_dest}")
    where = f"@origin:{{{safe_origin}}} @destination:{{{safe_dest}}}"
    return _knn_query(
        index=IDX_FLIGHTS,
        vector_field=EMB_FLIGHT,
        query_vec=qvec,
        k=k,
        filter_str=where,
        return_fields=["id", "airline", "origin", "destination", "price", "duration_minutes"],
    )


# ------------------------------------------------------------
# 🚗 Transports
# ------------------------------------------------------------
def search_transports(city: str, k: int = 5) -> List[Dict[str, Any]]:
    safe_city = escape_redis_text(city)
    qvec = embed_text(f"public and private transport options in {safe_city}")
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
    safe_city = escape_redis_text(city)
    qvec = embed_text(f"things to do, see and experience in {safe_city} related to {', '.join(interests)}")

    results = []
    results.extend(_knn_query(IDX_ATTRACTIONS, EMB_ATTR, qvec, k_each, f"@cityName:{{{safe_city}}}"))
    results.extend(_knn_query(IDX_EVENTS, EMB_EVENT, qvec, k_each, f"@cityName:{{{safe_city}}}"))
    results.extend(_knn_query(IDX_HOTELS, EMB_HOTEL, qvec, k_each, f"@cityName:{{{safe_city}}}"))

    # Deduplicate by ID
    unique, seen = [], set()
    for item in results:
        iid = item.get("id") or item.get("name")
        if iid not in seen:
            seen.add(iid)
            unique.append(item)

    return unique
