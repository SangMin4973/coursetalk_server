from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.database import get_db
from app.schemas import ItineraryRequest, ItineraryResponse
from app.services.itinerary_service import generate_itinerary


router = APIRouter(prefix="/itineraries", tags=["itineraries"])


@router.post("/generate", response_model=ItineraryResponse)
def create_itinerary(
    payload: ItineraryRequest,
    db: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        return generate_itinerary(db, settings, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
