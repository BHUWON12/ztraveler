from typing import List, Dict, Any, Set, Optional
from app.models.itinerary_models import Hotel, Activity, DayPlan


# -------------------------------------------------------------------
# 🏨 Hotel Selector
# -------------------------------------------------------------------
def pick_hotel(hotels: List[Dict[str, Any]], nights: int, hotel_budget: float) -> Optional[Hotel]:
    """
    Selects the best-rated hotel within budget.
    Falls back to the cheapest available if none fit.
    """
    if not hotels:
        return None

    # Sort by rating (desc) then price (asc)
    hotels_sorted = sorted(
        hotels, key=lambda h: (-h.get("rating", 0), h.get("price", 999999))
    )

    # Try to find one within the budget
    for h in hotels_sorted:
        if h.get("price", 0) * nights <= hotel_budget:
            return Hotel(
                id=h.get("hotelId") or h.get("id"),
                name=h.get("hotelName"),
                city=h.get("cityName"),
                price_per_night=float(h.get("price", 0)),
                rating=float(h.get("rating", 0)),
                address=h.get("address"),
                source=h.get("source", "mongo"),
            )

    # Fallback → cheapest available
    cheapest = min(hotels_sorted, key=lambda h: h.get("price", float("inf")))
    return Hotel(
        id=cheapest.get("hotelId") or cheapest.get("id"),
        name=cheapest.get("hotelName"),
        city=cheapest.get("cityName"),
        price_per_night=float(cheapest.get("price", 0)),
        rating=float(cheapest.get("rating", 0)),
        address=cheapest.get("address"),
        source=cheapest.get("source", "mongo"),
    )


# -------------------------------------------------------------------
# 🎯 Activity Selector (unique + diversified)
# -------------------------------------------------------------------
def pick_activities(
    attractions: List[Dict[str, Any]],
    daily_budget: float,
    slots: int = 3,
    used_ids: Optional[Set[str]] = None,
    day_number: int = 1,
) -> List[Activity]:
    """
    Selects activities within budget with diversity and uniqueness.
    - Avoids repeating IDs across days
    - Balances by category
    - Deterministic daily variety via random seeding
    """
    import random

    if not attractions:
        return []

    used_ids = used_ids or set()
    remaining = [a for a in attractions if a.get("id") not in used_ids]

    # Deterministic shuffle for stable variety
    random.seed(day_number)
    random.shuffle(remaining)

    # Prioritize high rating + low entry fee
    remaining.sort(key=lambda a: (-a.get("rating", 0), a.get("entry_fee", 0)))

    picked: List[Activity] = []
    total_spent = 0.0
    categories_used: Set[str] = set()

    for a in remaining:
        aid = a.get("id")
        if aid in used_ids:
            continue

        category = a.get("category") or "general"
        entry_fee = float(a.get("entry_fee", 0) or 0)

        # Skip if over budget or category duplicate
        if total_spent + entry_fee > daily_budget or category in categories_used:
            continue

        picked.append(
            Activity(
                id=aid,
                name=a.get("name"),
                city=a.get("cityName"),
                category=category,
                entry_fee=entry_fee,
                duration_min=a.get("duration_min", 120),
                opening_hours=a.get("opening_hours"),
                best_time_hint=a.get("best_time_hint", "Morning"),
                source=a.get("source", "mongo"),
            )
        )

        used_ids.add(aid)
        categories_used.add(category)
        total_spent += entry_fee

        if len(picked) >= slots:
            break

    return picked


# -------------------------------------------------------------------
# 🧩 Day Plan Builder
# -------------------------------------------------------------------
def build_day(
    city: str,
    day_index: int,
    hotel: Optional[Hotel],
    activities: List[Activity],
    note: Optional[str] = None,
) -> DayPlan:
    """
    Assemble a single day's itinerary plan.
    Includes estimated cost and simple note support.
    """
    estimated_cost = sum(a.entry_fee for a in activities)
    if day_index == 1 and hotel:
        estimated_cost += hotel.price_per_night

    return DayPlan(
        day_index=day_index,
        city=city,
        hotel=hotel if day_index == 1 else None,
        activities=activities,
        notes=note or "Plan transport between activities (≈20–30 min gaps).",
        estimated_day_cost=round(estimated_cost, 2),
    )


# -------------------------------------------------------------------
# 🧠 Advanced Combined Helper (for optional reuse)
# -------------------------------------------------------------------
def plan_city_days(
    city: str,
    days: int,
    hotel: Hotel,
    attractions: List[Dict[str, Any]],
    daily_budget: float,
    start_day_index: int,
) -> List[DayPlan]:
    """
    Generates unique, diversified daily plans for a city.
    Combines hotel on day 1 and unique attractions per day.
    """
    used_ids: Set[str] = set()
    city_plans: List[DayPlan] = []

    for i in range(days):
        day_number = start_day_index + i
        activities = pick_activities(
            attractions,
            daily_budget,
            slots=3,
            used_ids=used_ids,
            day_number=day_number,
        )
        plan = build_day(
            city=city,
            day_index=day_number,
            hotel=hotel if i == 0 else None,
            activities=activities,
            note=f"Auto-generated unique day {i+1} in {city}.",
        )
        city_plans.append(plan)

    return city_plans
