from typing import List, Optional
from pydantic import BaseModel
from datetime import date
import uuid


# ------------------------------------------------------------
#  Traveler Preferences (Input)
# ------------------------------------------------------------
class TravelerPrefs(BaseModel):
    origin: Optional[str] = None
    destination: List[str]
    start_date: date
    end_date: date
    budget_total: float
    interests: List[str]
    traveler_type: Optional[str] = "solo"


# ------------------------------------------------------------
#  Core Itinerary Components
# ------------------------------------------------------------
class Hotel(BaseModel):
    id: Optional[str]
    name: str
    city: str
    price_per_night: float
    rating: Optional[float]
    address: Optional[str]
    source: Optional[str] = "mongo"


class Activity(BaseModel):
    id: Optional[str]
    name: str
    city: str
    category: Optional[str]
    entry_fee: float = 0.0
    duration_min: Optional[int] = 120
    opening_hours: Optional[str] = None
    best_time_hint: Optional[str] = None
    source: Optional[str] = "mongo"


# ------------------------------------------------------------
#  Transport and Flight Segments
# ------------------------------------------------------------
class TransportSegment(BaseModel):
    mode: str
    provider: Optional[str] = None
    from_place: str
    to_place: str
    price: float
    source: Optional[str] = "mongo"


class FlightSegment(BaseModel):
    airline: str
    from_city: str
    to_city: str
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    price: float
    duration_minutes: Optional[int] = None
    cabin_class: Optional[str] = "Economy"
    source: Optional[str] = "mongo"


# ------------------------------------------------------------
#  Day-wise Plan
# ------------------------------------------------------------
class DayPlan(BaseModel):
    day_index: int
    city: str
    hotel: Optional[Hotel]
    activities: List[Activity]
    transport_segments: Optional[List[TransportSegment]] = []
    flight: Optional[FlightSegment] = None
    notes: Optional[str]
    estimated_day_cost: float


# ------------------------------------------------------------
#  Cost Breakdown
# ------------------------------------------------------------
class TripCost(BaseModel):
    hotel_total: float
    activities_total: float
    transport_total: float
    flights_total: Optional[float] = 0.0
    total: float


# ------------------------------------------------------------
#  Full AI Itinerary Response
# ------------------------------------------------------------
class Itinerary(BaseModel):
    trip_id: str = f"TRIP-{uuid.uuid4().hex[:8].upper()}"
    summary_text: str
    highlights: List[str]
    days: List[DayPlan]
    cost: TripCost
    assumptions: List[str]


# ------------------------------------------------------------
#  Backward Compatibility Alias (Fix for ImportError)
# ------------------------------------------------------------
# Old services (e.g., itinerary_service.py) import ItineraryPlan
# Keep alias to avoid breaking imports.
ItineraryPlan = Itinerary
