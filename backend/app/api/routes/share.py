from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models.entities import ItineraryVersion, Trip
from app.schemas.trip import PublicTripResponse
from app.services.shares import get_share_link


router = APIRouter(prefix="/share", tags=["share"])


@router.get("/{token}", response_model=PublicTripResponse)
def read_shared_trip(token: str, db: Session = Depends(get_db)) -> PublicTripResponse:
    link = get_share_link(db, token)
    trip = db.get(Trip, link.trip_id, options=[selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items)])
    active = next((version for version in reversed(trip.itinerary_versions) if version.status == "active"), None)
    return PublicTripResponse(
        destination=trip.destination,
        start_date=trip.start_date,
        end_date=trip.end_date,
        itinerary=active,
    )

