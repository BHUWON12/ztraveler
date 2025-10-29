from app.models.itinerary_models import TripCost

def split_budget(total_budget: float) -> TripCost:
    """
    Split total budget into structured allocations:
      - 60% → hotels
      - 25% → activities
      - 15% → transport
    Returns a TripCost model (not a dict).
    """
    if not total_budget or total_budget <= 0:
        total_budget = 1000  # fallback minimum

    hotel_total = total_budget * 0.6
    activities_total = total_budget * 0.25
    transport_total = total_budget * 0.15

    return TripCost(
        hotel_total=round(hotel_total, 2),
        activities_total=round(activities_total, 2),
        transport_total=round(transport_total, 2),
        total=round(total_budget, 2),
    )
