from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import date, datetime
import uuid


# ============================================================
# 🎒 Traveler Preferences (input schema)
# ============================================================
class TravelerPrefs(BaseModel):
    origin: str
    destination: List[str]
    start_date: date
    end_date: date
    budget_total: float = Field(..., gt=0)
    interests: List[str] = Field(default_factory=list)
    traveler_type: str = Field(default="solo")

    # -------------------- Validators --------------------
    @field_validator("origin", mode="before")
    @classmethod
    def _norm_origin(cls, v):
        return str(v).strip().title() if v else v

    @field_validator("destination", mode="before")
    @classmethod
    def _norm_dest(cls, v):
        if isinstance(v, list):
            return [str(x).strip().title() for x in v]
        return [str(v).strip().title()]

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date must be on/after start_date")
        return v


# ============================================================
# 🏨 Hotel Schema
# ============================================================
class HotelSchema(BaseModel):
    id: Optional[str] = None
    name: str
    city: str
    price_per_night: float
    rating: Optional[float] = None
    address: Optional[str] = None
    source: str = "mongo"


# ============================================================
# 🎡 Activity Schema
# ============================================================
class ActivitySchema(BaseModel):
    id: Optional[str] = None
    name: str
    city: str
    category: Optional[str] = None
    entry_fee: float = 0
    duration_min: int = 120
    opening_hours: Optional[str] = None
    best_time_hint: Optional[str] = None
    source: str = "mongo"


# ============================================================
# 🚗 Transport Segment
# ============================================================
class TransportSegmentSchema(BaseModel):
    mode: Optional[str] = "car"
    provider: Optional[str] = "Local Transport"
    from_place: str
    to_place: str
    price: float = 0
    source: Optional[str] = "mongo"


# ============================================================
# ✈️ Flight Segment
# ============================================================
class FlightSegmentSchema(BaseModel):
    airline: Optional[str] = None
    from_city: Optional[str] = None
    to_city: Optional[str] = None
    price: float = 0
    duration_minutes: Optional[int] = None
    departure_time: Optional[datetime] = None
    arrival_time: Optional[datetime] = None
    source: Optional[str] = "mongo"


# ============================================================
# 📅 Daily Plan (Day-wise structure)
# ============================================================
class DayPlanSchema(BaseModel):
    day_index: int
    city: str
    hotel: Optional[HotelSchema] = None
    activities: List[ActivitySchema] = Field(default_factory=list)
    transport_segments: List[TransportSegmentSchema] = Field(default_factory=list)
    flight: Optional[FlightSegmentSchema] = None
    notes: Optional[str] = None
    estimated_day_cost: float = 0


# ============================================================
# 💰 Trip Cost Summary
# ============================================================
class TripCostSchema(BaseModel):
    hotel_total: float = 0
    activities_total: float = 0
    transport_total: float = 0
    flights_total: float = 0
    total: float = 0


# ============================================================
# 🧳 Final Itinerary Schema (response)
# ============================================================
class ItinerarySchema(BaseModel):
    trip_id: str = Field(default_factory=lambda: f"TRIP-{uuid.uuid4().hex[:8].upper()}")
    summary_text: str
    highlights: List[str] = Field(default_factory=list)
    days: List[DayPlanSchema]
    cost: TripCostSchema
    assumptions: List[str] = Field(default_factory=list)


# ============================================================
# 🧩 Aliases for Backward Compatibility
# ============================================================
# Some modules use different names — keep aliases to prevent ImportErrors
ItineraryPreferences = TravelerPrefs
ItineraryResponse = ItinerarySchema
