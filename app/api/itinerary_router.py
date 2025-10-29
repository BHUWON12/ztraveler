from fastapi import APIRouter, HTTPException
from app.schemas.itinerary_schema import TravelerPrefs, ItinerarySchema
from app.services.itinerary_service import build_itinerary

router = APIRouter(prefix="/ai-itinerary", tags=["AI Itinerary"])

@router.post("", response_model=ItinerarySchema)
async def create_itinerary(prefs: TravelerPrefs):
    """
    Endpoint to generate an AI-powered itinerary.
    Uses LangChain + RAG + rule-based planning logic.
    """
    try:
        itinerary = await build_itinerary(prefs)
        return itinerary
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build itinerary: {str(e)}")
