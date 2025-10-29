from typing import List, Dict, Any
from datetime import datetime
from app.db.mongo import get_mongo_client
from app.rag.redis_vectorstores import (
    search_hotels,
    search_attractions,
    search_events,
    search_flights,
    search_transports,
)
from app.models.itinerary_models import (
    DayPlan,
    FlightSegment,
    ItineraryPlan,
)
from app.schemas.itinerary_schema import ItineraryPreferences

db = get_mongo_client()

# --------------------------------------------------------
# 🔹 Retrieval Helpers
# --------------------------------------------------------

async def retrieve_hotels(city: str, max_price: float, k: int = 8) -> List[Dict[str, Any]]:
    docs = search_hotels(city, max_price, k)
    if not docs:
        collection = db["hotels"]
        cursor = collection.find({"cityName": {"$regex": f"^{city}$", "$options": "i"}}).limit(k)
        docs = await cursor.to_list(length=k)
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
    docs = search_attractions(city, interests, k)
    if not docs:
        collection = db["attractions"]
        cursor = collection.find({"cityName": {"$regex": f"^{city}$", "$options": "i"}}).limit(k)
        docs = await cursor.to_list(length=k)
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
    docs = search_events(city, start_iso, end_iso, k)
    if not docs:
        collection = db["events"]
        cursor = collection.find({"cityName": {"$regex": f"^{city}$", "$options": "i"}}).limit(k)
        docs = await cursor.to_list(length=k)
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
    docs = search_flights(origin, destination, k)
    if not docs:
        collection = db["flights"]
        cursor = collection.find(
            {
                "origin": {"$regex": f"^{origin}$", "$options": "i"},
                "destination": {"$regex": f"^{destination}$", "$options": "i"},
            }
        ).limit(k)
        docs = await cursor.to_list(length=k)
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
    docs = search_transports(city, k)
    if not docs:
        collection = db["transports"]
        cursor = collection.find(
            {
                "$or": [
                    {"from_city": {"$regex": f"^{city}$", "$options": "i"}},
                    {"to_city": {"$regex": f"^{city}$", "$options": "i"}},
                    {"cityName": {"$regex": f"^{city}$", "$options": "i"}},
                ]
            }
        ).limit(k)
        docs = await cursor.to_list(length=k)
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
    all_days: List[DayPlan] = []
    flights_total = 0
    current_day_index = 1
    num_cities = len(prefs.destination)

    # 1️⃣ Entry flight from source → first destination
    if prefs.source and prefs.destination:
        entry_city = prefs.destination[0]
        print(f"✈️ Entry route: {prefs.source} → {entry_city}")

        entry_flight = await retrieve_flights(prefs.source, entry_city)
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
                first_leg = await retrieve_flights(prefs.source, hub)
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
                        from_city=prefs.source,
                        to_city=entry_city,
                        price=1800,
                        duration_minutes=420,
                    )
                )
                flights_total += 1800

        all_days.append(
            DayPlan(
                day_index=current_day_index,
                city=prefs.source,
                flight=entry_segments[0],
                notes=f"Travel day from {prefs.source} → {entry_city}",
                estimated_day_cost=0,
            )
        )
        current_day_index += 1

    # 2️⃣ For each destination
    for idx, city in enumerate(prefs.destination):
        print(f"🏙️ Planning {city}")

        hotels = await retrieve_hotels(city, prefs.max_budget_per_city)
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

        # ✈️ Handle city-to-city transfers
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
                    segments.append(FlightSegment(airline="Road Route", from_city=city, to_city=next_city, price=300, duration_minutes=360))
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

    # 3️⃣ Return flight to source
    if prefs.source and prefs.destination:
        last_city = prefs.destination[-1]
        print(f"🛫 Return route: {last_city} → {prefs.source}")

        return_flight = await retrieve_flights(last_city, prefs.source)
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
                second_leg = await retrieve_flights(hub, prefs.source)
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
                        to_city=prefs.source,
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
                notes=f"Return flight from {last_city} → {prefs.source}",
                estimated_day_cost=0,
            )
        )

    # ✅ Final itinerary plan
    return ItineraryPlan(
        trip_id=f"TRIP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        created_at=datetime.utcnow(),
        days=all_days,
        cost_summary={"flights_total": flights_total},
    )
