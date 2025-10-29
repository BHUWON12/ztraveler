import uuid
import random
from typing import List, Set
from app.models.itinerary_models import (
    TravelerPrefs,
    Itinerary,
    Hotel,
    Activity,
    DayPlan,
    TripCost,
    FlightSegment,
    TransportSegment,
)
from app.rag.retrievers import (
    retrieve_hotels,
    retrieve_attractions,
    retrieve_events,
    retrieve_flights,
    retrieve_transports,
)
from app.planner.budget_splitter import split_budget
from app.planner.rule_based_planner import pick_hotel, build_day
from app.rag.langchain_pipeline.itinerary_chain import generate_ai_itinerary_narrative


# ------------------------------------------------------------------
# 🧠 Helper — smart daily activity selection with uniqueness
# ------------------------------------------------------------------
def pick_unique_activities(
    attr_docs: List[dict],
    event_docs: List[dict],
    daily_budget: float,
    day_number: int,
    used_ids: Set[str],
    slots: int = 3,
) -> List[Activity]:
    """
    Select daily activities with diversity and budget control.
    - Combines attractions + events
    - Avoids repeating the same IDs
    - Ensures varied categories per day
    """
    from app.models.itinerary_models import Activity

    pool = []
    pool.extend(attr_docs)
    pool.extend(event_docs or [])

    if not pool:
        return []

    random.seed(day_number)
    random.shuffle(pool)

    picked, total, categories = [], 0.0, set()
    for doc in pool:
        doc_id = str(doc.get("id"))
        if doc_id in used_ids:
            continue
        category = doc.get("category") or doc.get("type") or "general"
        fee = float(doc.get("entry_fee", 0) or doc.get("price", 0) or 0)

        # skip if duplicate category or over budget
        if category in categories or total + fee > daily_budget:
            continue

        picked.append(
            Activity(
                id=doc_id,
                name=doc.get("name"),
                city=doc.get("cityName"),
                category=category,
                entry_fee=fee,
                duration_min=doc.get("duration_min", 120),
                opening_hours=doc.get("opening_hours"),
                best_time_hint=doc.get("best_time_hint", "Morning"),
                source=doc.get("source", "mongo"),
            )
        )
        used_ids.add(doc_id)
        categories.add(category)
        total += fee

        if len(picked) >= slots:
            break

    return picked


# ------------------------------------------------------------------
# 🚀 Core Service: Build Multi-City Itinerary
# ------------------------------------------------------------------
async def build_itinerary(prefs: TravelerPrefs) -> Itinerary:
    """Builds a full multi-city itinerary with hotels, flights, and daily plans."""

    total_days = (prefs.end_date - prefs.start_date).days + 1
    if total_days <= 0:
        raise ValueError("Invalid date range")

    num_cities = len(prefs.destination)
    if num_cities == 0:
        raise ValueError("No destinations provided")

    # 💰 Budget allocation
    costs = split_budget(prefs.budget_total)
    daily_budget = costs.activities_total / total_days

    all_days: List[DayPlan] = []
    current_day_index = 1
    used_activity_ids: Set[str] = set()

    hotel_total = 0
    activities_total = 0
    transport_total = 0
    flights_total = 0

    # 🏙️ Loop through cities
    for idx, city in enumerate(prefs.destination):
        city_days = max(1, total_days // num_cities + (1 if idx < total_days % num_cities else 0))

        # 1️⃣ Retrieve data
        hotel_docs = await retrieve_hotels(city, max_price=costs.hotel_total / total_days, k=8)
        attr_docs = await retrieve_attractions(city, prefs.interests, k=20)
        event_docs = await retrieve_events(city, prefs.start_date.isoformat(), prefs.end_date.isoformat(), k=10)
        transport_docs = await retrieve_transports(city, k=5)

        hotel = pick_hotel(hotel_docs, city_days, costs.hotel_total)
        if not hotel:
            continue

        best_transport = min(transport_docs, key=lambda t: t.get("price", 999999), default=None)

        # ✈️ Flight from previous city (or origin)
        prev_city = prefs.origin if idx == 0 else prefs.destination[idx - 1]
        inbound_flights = await retrieve_flights(prev_city, city)
        best_inbound = min(inbound_flights, key=lambda f: f.get("price", 999999), default=None)

        # 2️⃣ Generate daily plans for this city
        for _ in range(city_days):
            acts = pick_unique_activities(attr_docs, event_docs, daily_budget, current_day_index, used_activity_ids)
            transport_segments: List[TransportSegment] = []

            # 🚗 Local transport sequence
            if best_transport and hotel and acts:
                # hotel → each activity → hotel
                for j, act in enumerate(acts):
                    from_place = hotel.name if j == 0 else acts[j - 1].name
                    to_place = act.name
                    transport_segments.append(
                        TransportSegment(
                            mode=best_transport.get("mode", "car"),
                            provider=best_transport.get("provider", "Local Transport"),
                            from_place=from_place,
                            to_place=to_place,
                            price=float(best_transport.get("price", 0)),
                        )
                    )
                transport_segments.append(
                    TransportSegment(
                        mode=best_transport.get("mode", "car"),
                        provider=best_transport.get("provider", "Local Transport"),
                        from_place=acts[-1].name,
                        to_place=hotel.name,
                        price=float(best_transport.get("price", 0)),
                    )
                )

            # ✈️ Flight segment on first day in city
            flight_segment = None
            if current_day_index == 1 and best_inbound:
                flight_segment = FlightSegment(
                    airline=best_inbound.get("airline", "Unknown Airline"),
                    from_city=best_inbound.get("from"),
                    to_city=best_inbound.get("to"),
                    price=best_inbound.get("price", 0),
                    duration_minutes=best_inbound.get("duration_minutes", 0),
                )
                transport_segments.insert(
                    0,
                    TransportSegment(
                        mode="car",
                        provider="Airport Transfer",
                        from_place=f"{best_inbound.get('to')} Airport",
                        to_place=hotel.name,
                        price=best_transport.get("price", 0) if best_transport else 100,
                    ),
                )

            # 🏨 Build the day's plan
            all_days.append(
                DayPlan(
                    day_index=current_day_index,
                    city=city,
                    hotel=hotel if _ == 0 else None,
                    activities=acts,
                    transport_segments=transport_segments,
                    flight=flight_segment,
                    notes=f"Auto-generated day in {city}.",
                    estimated_day_cost=round(hotel.price_per_night if _ == 0 else 0, 2),
                )
            )
            current_day_index += 1

        # ✈️ Inter-city flight to next city
        if idx < num_cities - 1:
            next_city = prefs.destination[idx + 1]
            hop_flights = await retrieve_flights(city, next_city)
            if hop_flights:
                best_hop = min(hop_flights, key=lambda f: f.get("price", 999999))
                flights_total += best_hop.get("price", 0)
                all_days.append(
                    DayPlan(
                        day_index=current_day_index,
                        city=city,
                        hotel=None,
                        activities=[],
                        transport_segments=[],
                        flight=FlightSegment(
                            airline=best_hop.get("airline", "Local Airline"),
                            from_city=best_hop.get("from"),
                            to_city=best_hop.get("to"),
                            price=best_hop.get("price", 0),
                            duration_minutes=best_hop.get("duration_minutes", 0),
                        ),
                        notes=f"Travel day from {city} → {next_city}",
                        estimated_day_cost=0,
                    )
                )
                current_day_index += 1

        # 🧾 Totals
        hotel_total += hotel.price_per_night * city_days
        activities_total += sum(a.entry_fee for a in acts)
        if best_transport:
            transport_total += best_transport.get("price", 0) * city_days * 3
        if best_inbound:
            flights_total += best_inbound.get("price", 0)

    # 🛫 Return flight (last city → origin)
    last_city = prefs.destination[-1]
    return_flights = await retrieve_flights(last_city, prefs.origin)
    if return_flights:
        best_return = min(return_flights, key=lambda f: f.get("price", 999999))
        flights_total += best_return.get("price", 0)
        all_days.append(
            DayPlan(
                day_index=current_day_index,
                city=last_city,
                hotel=None,
                activities=[],
                transport_segments=[],
                flight=FlightSegment(
                    airline=best_return.get("airline", "Return Airline"),
                    from_city=best_return.get("from"),
                    to_city=best_return.get("to"),
                    price=best_return.get("price", 0),
                    duration_minutes=best_return.get("duration_minutes", 0),
                ),
                notes=f"Return flight {last_city} → {prefs.origin}",
                estimated_day_cost=0,
            )
        )

    # 💰 Cost summary
    total_cost = hotel_total + activities_total + flights_total + transport_total
    cost_summary = TripCost(
        hotel_total=hotel_total,
        activities_total=activities_total,
        transport_total=transport_total,
        flights_total=flights_total,
        total=total_cost,
    )

    # 🧩 AI Narrative Summary
    try:
        ai_summary = generate_ai_itinerary_narrative(
            origin=prefs.origin,
            destination=", ".join(prefs.destination),
            start_date=prefs.start_date.isoformat(),
            end_date=prefs.end_date.isoformat(),
            traveler_type=prefs.traveler_type,
            budget_total=prefs.budget_total,
            interests=prefs.interests,
            context="Multi-city travel plan with unique daily experiences and event blending.",
        )
        summary_text = ai_summary.get("summary_text", f"{total_days}-day trip across {', '.join(prefs.destination)}.")
        highlights = ai_summary.get("highlights", [])
        assumptions = [ai_summary.get("ai_commentary", "Generated via AI summarization.")]
    except Exception as e:
        summary_text = f"{total_days}-day trip covering {', '.join(prefs.destination)}."
        highlights = ["AI summary unavailable — using fallback description."]
        assumptions = [f"AI summary generation failed: {str(e)}"]

    # 🎁 Final Itinerary
    return Itinerary(
        trip_id=f"TRIP-{uuid.uuid4().hex[:8].upper()}",
        summary_text=summary_text,
        highlights=highlights,
        days=all_days,
        cost=cost_summary,
        assumptions=assumptions,
    )
