# --------------------------------------------------------
# 🧠 Retrieval + Itinerary Construction (Cloud Run Safe)
# --------------------------------------------------------
from typing import List, Dict, Any
from datetime import datetime
import traceback

from app.db.mongo import get_mongo_client, init_mongo
from app.rag.redis_vectorstores import (
    search_hotels,
    search_attractions,
    search_events,
    search_flights,
    search_transports,
)
from app.models.itinerary_models import DayPlan, FlightSegment, ItineraryPlan
from app.schemas.itinerary_schema import ItineraryPreferences


# --------------------------------------------------------
# 🔹 Utility — Lazy Mongo Collection Getter
# --------------------------------------------------------
async def get_collection_safe(name: str):
    """
    Ensures MongoDB connection is initialized before accessing a collection.
    Prevents import-time connection errors during Cloud Run startup.
    """
    try:
        await init_mongo()  # ensure live connection (idempotent)
        db = get_mongo_client()
    except Exception as e:
        print(f"❌ Failed to connect to Mongo for '{name}': {e}")
        traceback.print_exc()
        raise
    return db[name]


# --------------------------------------------------------
# 🔹 Safe Redis wrappers (fallback to Mongo on error)
# --------------------------------------------------------
async def _fallback_find(collection_name: str, query: Dict[str, Any], limit: int):
    coll = await get_collection_safe(collection_name)
    cursor = coll.find(query).limit(limit)
    return await cursor.to_list(length=limit)

async def _safe_search_hotels(city: str, max_price: float, k: int):
    try:
        return search_hotels(city, max_price, k) or []
    except Exception as e:
        print(f"[Redis Search Error] hotels: {e}")
        return []

async def _safe_search_attractions(city: str, interests: List[str], k: int):
    try:
        return search_attractions(city, interests, k) or []
    except Exception as e:
        print(f"[Redis Search Error] attractions: {e}")
        return []

async def _safe_search_events(city: str, start_iso: str, end_iso: str, k: int):
    try:
        return search_events(city, start_iso, end_iso, k) or []
    except Exception as e:
        print(f"[Redis Search Error] events: {e}")
        return []

async def _safe_search_flights(origin: str, destination: str, k: int):
    try:
        return search_flights(origin, destination, k) or []
    except Exception as e:
        print(f"[Redis Search Error] flights: {e}")
        return []

async def _safe_search_transports(city: str, k: int):
    try:
        return search_transports(city, k) or []
    except Exception as e:
        print(f"[Redis Search Error] transports: {e}")
        return []


# --------------------------------------------------------
# 🔹 Retrieval Helpers (Hotels / Attractions / Events / Flights / Transports)
# --------------------------------------------------------
async def retrieve_hotels(city: str, max_price: float, k: int = 8) -> List[Dict[str, Any]]:
    docs = await _safe_search_hotels(city, max_price, k)
    if not docs:
        docs = await _fallback_find("hotels", {"cityName": {"$regex": f"^{city}$", "$options": "i"}}, k)
    return [
        {
            "id": str(d.get("_id") or d.get("id")),
            "hotelId": d.get("hotelId"),
            "hotelName": d.get("hotelName"),
            "cityName": d.get("cityName"),
            "price": float(d.get("price", 0) or 0),
            "rating": float(d.get("rating", 0) or 0),
            "source": "redis" if "embedding" in d else "mongo",
        }
        for d in docs
    ]

async def retrieve_attractions(city: str, interests: List[str], k: int = 12) -> List[Dict[str, Any]]:
    docs = await _safe_search_attractions(city, interests, k)
    if not docs:
        docs = await _fallback_find("attractions", {"cityName": {"$regex": f"^{city}$", "$options": "i"}}, k)
    return [
        {
            "id": str(d.get("_id") or d.get("id")),
            "name": d.get("name"),
            "cityName": d.get("cityName"),
            "category": d.get("category"),
            "entry_fee": float(d.get("entry_fee", 0) or 0),
            "duration_min": 120,
            "rating": float(d.get("rating", 0) or 0),
            "source": "redis" if "embedding" in d else "mongo",
        }
        for d in docs
    ]

async def retrieve_events(city: str, start_iso: str, end_iso: str, k: int = 8) -> List[Dict[str, Any]]:
    docs = await _safe_search_events(city, start_iso, end_iso, k)
    if not docs:
        docs = await _fallback_find("events", {"cityName": {"$regex": f"^{city}$", "$options": "i"}}, k)
    return [
        {
            "id": str(d.get("_id") or d.get("id")),
            "name": d.get("name"),
            "cityName": d.get("cityName"),
            "type": d.get("type"),
            "date": d.get("date"),
            "source": "redis" if "embedding" in d else "mongo",
        }
        for d in docs
    ]

async def retrieve_flights(origin: str, destination: str, k: int = 5) -> List[Dict[str, Any]]:
    docs = await _safe_search_flights(origin, destination, k)
    if not docs:
        docs = await _fallback_find(
            "flights",
            {"origin": {"$regex": f"^{origin}$", "$options": "i"},
             "destination": {"$regex": f"^{destination}$", "$options": "i"}},
            k,
        )
    return [
        {
            "id": str(d.get("_id") or d.get("id")),
            "airline": d.get("airline"),
            "flight_number": d.get("flight_number"),
            "from": d.get("origin"),
            "to": d.get("destination"),
            "price": float(d.get("price", 0) or 0),
            "duration": d.get("duration_minutes", 0),
            "source": "redis" if "embedding" in d else "mongo",
        }
        for d in docs
    ]

async def retrieve_transports(city: str, k: int = 5) -> List[Dict[str, Any]]:
    docs = await _safe_search_transports(city, k)
    if not docs:
        docs = await _fallback_find(
            "transports",
            {"$or": [
                {"from_city": {"$regex": f"^{city}$", "$options": "i"}},
                {"to_city": {"$regex": f"^{city}$", "$options": "i"}},
                {"cityName": {"$regex": f"^{city}$", "$options": "i"}},
            ]},
            k,
        )
    return [
        {
            "id": str(d.get("_id") or d.get("id")),
            "mode": d.get("mode") or d.get("type"),
            "provider": d.get("provider") or "Local Transport",
            "from_city": d.get("from_city") or d.get("cityName"),
            "to_city": d.get("to_city") or d.get("cityName"),
            "price": float(d.get("price", 0) or 0),
            "source": "redis" if "embedding" in d else "mongo",
        }
        for d in docs
    ]


# --------------------------------------------------------
# 🧭 Build the Complete Itinerary (Round Trip)
# --------------------------------------------------------
async def build_itinerary(prefs: ItineraryPreferences) -> ItineraryPlan:
    """
    Builds a multi-city itinerary plan (hotels, attractions, flights, transports).
    """
    try:
        await init_mongo()
    except Exception as e:
        print(f"⚠️ Mongo initialization failed during itinerary build: {e}")
        traceback.print_exc()

    all_days: List[DayPlan] = []
    flights_total = 0
    current_day_index = 1
    num_cities = len(prefs.destination)

    # Use max_budget_per_city if available; else derive from total
    max_per_city = getattr(prefs, "max_budget_per_city", None) or max(
        0, (getattr(prefs, "budget_total", 0) or 0) // max(1, num_cities or 1)
    )

    # 1️⃣ Entry flight from origin → first destination   <-- CHANGED: origin
    if getattr(prefs, "origin", None) and prefs.destination:
        entry_city = prefs.destination[0]
        print(f"✈️ Entry route: {prefs.origin} → {entry_city}")

        entry_flight = await retrieve_flights(prefs.origin, entry_city)
        entry_segments = []

        if entry_flight:
            best = sorted(entry_flight, key=lambda f: f.get("price", 999999))[0]
            flights_total += best.get("price", 0)
            entry_segments.append(
                FlightSegment(
                    airline=best.get("airline", "International Airline"),
                    from_city=best.get("from"),
                    to_city=best.get("to"),
                    price=best.get("price", 0),
                    duration_minutes=best.get("duration", 0),
                )
            )
        else:
            for hub in ["Dubai", "Doha", "Abu Dhabi"]:
                first_leg = await retrieve_flights(prefs.origin, hub)
                second_leg = await retrieve_flights(hub, entry_city)
                if first_leg and second_leg:
                    f1 = sorted(first_leg, key=lambda f: f.get("price", 999999))[0]
                    f2 = sorted(second_leg, key=lambda f: f.get("price", 999999))[0]
                    flights_total += f1.get("price", 0) + f2.get("price", 0)
                    entry_segments.extend([
                        FlightSegment(airline=f1.get("airline", "Transit"), from_city=f1.get("from"), to_city=f1.get("to"), price=f1.get("price", 0), duration_minutes=f1.get("duration", 0)),
                        FlightSegment(airline=f2.get("airline", "Transit"), from_city=f2.get("from"), to_city=f2.get("to"), price=f2.get("price", 0), duration_minutes=f2.get("duration", 0))
                    ])
                    break
            if not entry_segments:
                entry_segments.append(
                    FlightSegment(
                        airline="Fallback Route",
                        from_city=prefs.origin,
                        to_city=entry_city,
                        price=1800,
                        duration_minutes=420,
                    )
                )
                flights_total += 1800

        all_days.append(
            DayPlan(
                day_index=current_day_index,
                city=prefs.origin,
                flight=entry_segments[0],
                notes=f"Travel day from {prefs.origin} → {entry_city}",
                estimated_day_cost=0,
            )
        )
        current_day_index += 1

    # 2️⃣ For each destination city
    for idx, city in enumerate(prefs.destination):
        print(f"🏙️ Planning {city}")

        hotels = await retrieve_hotels(city, max_per_city)
        hotel = hotels[0] if hotels else None
        attractions = await retrieve_attractions(city, prefs.interests)
        events = await retrieve_events(city, prefs.start_date, prefs.end_date)
        transports = await retrieve_transports(city)

        all_days.append(
            DayPlan(
                day_index=current_day_index,
                city=city,
                hotel=hotel,
                activities=attractions[:3] + events[:1],
                transport_segments=transports[:3],
                flight=None,
                notes=f"Auto-generated day in {city}",
                estimated_day_cost=hotel["price"] if hotel else 0,
            )
        )
        current_day_index += 1

        # ✈️ Intercity transfers
        if idx < num_cities - 1:
            next_city = prefs.destination[idx + 1]
            print(f"✈️ Route {city} → {next_city}")
            hop_flight = await retrieve_flights(city, next_city)
            segments = []

            if hop_flight:
                best = sorted(hop_flight, key=lambda f: f.get("price", 999999))[0]
                flights_total += best.get("price", 0)
                segments.append(
                    FlightSegment(
                        airline=best.get("airline", "Local Airline"),
                        from_city=best.get("from"),
                        to_city=best.get("to"),
                        price=best.get("price", 0),
                        duration_minutes=best.get("duration", 0),
                    )
                )
            else:
                for hub in ["Riyadh", "Jeddah", "Dammam"]:
                    if hub.lower() in [city.lower(), next_city.lower()]:
                        continue
                    first_leg = await retrieve_flights(city, hub)
                    second_leg = await retrieve_flights(hub, next_city)
                    if first_leg and second_leg:
                        f1 = sorted(first_leg, key=lambda f: f.get("price", 999999))[0]
                        f2 = sorted(second_leg, key=lambda f: f.get("price", 999999))[0]
                        flights_total += f1.get("price", 0) + f2.get("price", 0)
                        segments.extend([
                            FlightSegment(airline=f1.get("airline", "Transit"), from_city=f1.get("from"), to_city=f1.get("to"), price=f1.get("price", 0), duration_minutes=f1.get("duration", 0)),
                            FlightSegment(airline=f2.get("airline", "Transit"), from_city=f2.get("from"), to_city=f2.get("to"), price=f2.get("price", 0), duration_minutes=f2.get("duration", 0))
                        ])
                        break
                if not segments:
                    segments.append(
                        FlightSegment(airline="Road Route", from_city=city, to_city=next_city, price=300, duration_minutes=360)
                    )
                    flights_total += 300

            for seg in segments:
                all_days.append(
                    DayPlan(
                        day_index=current_day_index,
                        city=seg.from_city,
                        flight=seg,
                        notes=f"Travel day: {seg.from_city} → {seg.to_city}",
                        estimated_day_cost=0,
                    )
                )
                current_day_index += 1

    # 3️⃣ Return flight to origin   <-- CHANGED: origin
    if getattr(prefs, "origin", None) and prefs.destination:
        last_city = prefs.destination[-1]
        print(f"🛫 Return route: {last_city} → {prefs.origin}")

        return_flight = await retrieve_flights(last_city, prefs.origin)
        return_segments = []

        if return_flight:
            best = sorted(return_flight, key=lambda f: f.get("price", 999999))[0]
            flights_total += best.get("price", 0)
            return_segments.append(
                FlightSegment(
                    airline=best.get("airline", "International Airline"),
                    from_city=best.get("from"),
                    to_city=best.get("to"),
                    price=best.get("price", 0),
                    duration_minutes=best.get("duration", 0),
                )
            )
        else:
            for hub in ["Dubai", "Doha", "Abu Dhabi"]:
                first_leg = await retrieve_flights(last_city, hub)
                second_leg = await retrieve_flights(hub, prefs.origin)
                if first_leg and second_leg:
                    f1 = sorted(first_leg, key=lambda f: f.get("price", 999999))[0]
                    f2 = sorted(second_leg, key=lambda f: f.get("price", 999999))[0]
                    flights_total += f1.get("price", 0) + f2.get("price", 0)
                    return_segments.extend([
                        FlightSegment(airline=f1.get("airline", "Transit"), from_city=f1.get("from"), to_city=f1.get("to"), price=f1.get("price", 0), duration_minutes=f1.get("duration", 0)),
                        FlightSegment(airline=f2.get("airline", "Transit"), from_city=f2.get("from"), to_city=f2.get("to"), price=f2.get("price", 0), duration_minutes=f2.get("duration", 0))
                    ])
                    break
            if not return_segments:
                return_segments.append(
                    FlightSegment(
                        airline="Fallback Route",
                        from_city=last_city,
                        to_city=prefs.origin,
                        price=1800,
                        duration_minutes=420,
                    )
                )
                flights_total += 1800

        all_days.append(
            DayPlan(
                day_index=current_day_index,
                city=last_city,
                flight=return_segments[0],
                notes=f"Return flight from {last_city} → {prefs.origin}",
                estimated_day_cost=0,
            )
        )

    # ✅ Final itinerary output
    return ItineraryPlan(
        trip_id=f"TRIP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        created_at=datetime.utcnow(),
        days=all_days,
        cost_summary={"flights_total": flights_total},
    )
