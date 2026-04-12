import threading
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.database import get_db, SessionLocal
from app.models.entities import ItineraryItem, ItineraryVersion, Place, Trip, User
from app.schemas.trip import (
    ChatApplyRequest,
    ChatRequest,
    ChatResponse,
    ExportResponse,
    ItineraryItemRead,
    ItineraryItemUpdate,
    ItineraryResponse,
    MapResponse,
    PlaceSelectionUpdate,
    PlaceRead,
    SearchResponse,
    ShareLinkResponse,
    TodaySummaryRead,
    TripCreate,
    TripRead,
    TripUpdate,
    ReplanDayRequest,
    WorkflowDecisionRequest,
    WorkflowMessageRequest,
    WorkflowStartRequest,
    WorkspaceResponse,
    AgentStatusResponse,
    AgentStepRead,
)
from app.services.agent import AgentCoordinator
from app.services.agent_tools import get_active_itinerary, tool_update_item
from app.services.exports import create_pdf_export
from app.services.planner import build_map_payload
from app.services.shares import create_share_link
from app.services.workflow import WorkflowService


router = APIRouter(prefix="/trips", tags=["trips"])

def start_trip_background(user_id: int, trip_id: int) -> None:
    db_session: Session = SessionLocal()
    try:
        user = db_session.get(User, user_id)
        if not user: return
        service = WorkflowService(user)
        service.start(db_session, trip_id, run_type="setup")
    except Exception as e:
        print(f"Background task failed for trip {trip_id}: {e}")
    finally:
        db_session.close()



def _get_trip_or_404(db: Session, current_user: User, trip_id: int) -> Trip:
    statement = (
        select(Trip)
        .where(Trip.id == trip_id, Trip.user_id == current_user.id)
        .options(
            selectinload(Trip.flights),
            selectinload(Trip.hotels),
            selectinload(Trip.places),
            selectinload(Trip.route_estimates),
            selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
        )
    )
    trip = db.scalar(statement)
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


def _validate_trip_dates(start_date, end_date) -> None:
    if end_date <= start_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_date must be after start_date")


def _active_itinerary_or_404(trip: Trip) -> ItineraryVersion:
    active = get_active_itinerary(trip)
    if not active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active itinerary not found")
    return active


@router.post("", response_model=TripRead, status_code=201)
def create_trip(
    payload: TripCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Trip:
    _validate_trip_dates(payload.start_date, payload.end_date)
    trip_payload = payload.model_dump()
    trip_payload["origin_iata"] = None
    trip_payload["currency"] = trip_payload.get("currency") or current_user.currency or "BRL"
    trip_payload["locale"] = trip_payload.get("locale") or current_user.locale or "pt-BR"
    trip = Trip(user_id=current_user.id, **trip_payload)
    db.add(trip)
    db.commit()
    service = WorkflowService(current_user)
    service.initialize_trip(db, trip.id)
    
    t = threading.Thread(target=start_trip_background, args=(current_user.id, trip.id))
    t.start()
    
    return _get_trip_or_404(db, current_user, trip.id)


@router.get("", response_model=list[TripRead])
def list_trips(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Trip]:
    statement = (
        select(Trip)
        .where(Trip.user_id == current_user.id)
        .order_by(Trip.created_at.desc())
        .options(
            selectinload(Trip.flights),
            selectinload(Trip.hotels),
            selectinload(Trip.places),
            selectinload(Trip.route_estimates),
            selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
        )
    )
    return list(db.scalars(statement).unique())


@router.get("/{trip_id}", response_model=TripRead)
def get_trip(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Trip:
    return _get_trip_or_404(db, current_user, trip_id)


@router.get("/{trip_id}/places", response_model=list[PlaceRead])
def get_trip_places(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Place]:
    trip = _get_trip_or_404(db, current_user, trip_id)
    return list(db.scalars(select(Place).where(Place.trip_id == trip.id).order_by(Place.rating.desc())))


@router.patch("/{trip_id}/places/{place_id}", response_model=WorkspaceResponse)
def update_trip_place_selection(
    trip_id: int,
    place_id: int,
    payload: PlaceSelectionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceResponse:
    _get_trip_or_404(db, current_user, trip_id)
    return WorkflowService(current_user).update_place_selection(db, trip_id, place_id, payload.is_selected)


@router.patch("/{trip_id}", response_model=TripRead)
def update_trip(trip_id: int, payload: TripUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Trip:
    trip = _get_trip_or_404(db, current_user, trip_id)
    updates = payload.model_dump(exclude_unset=True)
    if "origin_city" in updates:
        updates["origin_iata"] = None
    if "selected_flight_id" in updates and updates["selected_flight_id"] is not None:
        if not any(flight.id == updates["selected_flight_id"] for flight in trip.flights):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected flight does not belong to this trip.")
    if "selected_hotel_id" in updates and updates["selected_hotel_id"] is not None:
        if not any(hotel.id == updates["selected_hotel_id"] for hotel in trip.hotels):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected hotel does not belong to this trip.")
    next_start = updates.get("start_date", trip.start_date)
    next_end = updates.get("end_date", trip.end_date)
    _validate_trip_dates(next_start, next_end)
    for field, value in updates.items():
        setattr(trip, field, value)
    db.add(trip)
    db.commit()
    return _get_trip_or_404(db, current_user, trip_id)


@router.post("/{trip_id}/search", response_model=SearchResponse)
def search_trip_options(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SearchResponse:
    result = AgentCoordinator(current_user).search_trip(db, trip_id)
    refreshed_trip = _get_trip_or_404(db, current_user, trip_id)
    places_from_db = list(db.scalars(select(Place).where(Place.trip_id == trip_id).order_by(Place.rating.desc())))
    return SearchResponse(
        trip_id=refreshed_trip.id,
        destination=refreshed_trip.destination,
        flights=refreshed_trip.flights,
        hotels=refreshed_trip.hotels,
        places=places_from_db,
        warnings=result.warnings,
    )


@router.post("/{trip_id}/itinerary/generate", response_model=ItineraryResponse)
def generate_itinerary(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ItineraryResponse:
    result = AgentCoordinator(current_user).generate(db, trip_id, intent="generate")
    trip = _get_trip_or_404(db, current_user, trip_id)
    itinerary = _active_itinerary_or_404(trip)
    return ItineraryResponse(
        itinerary=itinerary,
        warnings=list(dict.fromkeys([*itinerary.warnings, *result.warnings])),
        assistant_summary=result.run.assistant_message,
    )


@router.post("/{trip_id}/itinerary/replan", response_model=ItineraryResponse)
def replan_itinerary(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ItineraryResponse:
    result = AgentCoordinator(current_user).generate(db, trip_id, intent="replan")
    trip = _get_trip_or_404(db, current_user, trip_id)
    itinerary = _active_itinerary_or_404(trip)
    return ItineraryResponse(
        itinerary=itinerary,
        warnings=list(dict.fromkeys([*itinerary.warnings, *result.warnings])),
        assistant_summary=result.run.assistant_message,
    )


@router.post("/{trip_id}/chat", response_model=ChatResponse)
def chat_about_trip(
    trip_id: int,
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    return AgentCoordinator(current_user).preview_message(db, trip_id, payload.message)


@router.post("/{trip_id}/chat/apply", response_model=ItineraryResponse)
def apply_chat_change(
    trip_id: int,
    payload: ChatApplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItineraryResponse:
    result = AgentCoordinator(current_user).apply_change(db, trip_id, payload.change)
    trip = _get_trip_or_404(db, current_user, trip_id)
    itinerary = _active_itinerary_or_404(trip)
    return ItineraryResponse(itinerary=itinerary, warnings=result.warnings, assistant_summary=result.run.assistant_message)


@router.patch("/{trip_id}/itinerary/items/{item_id}", response_model=ItineraryItemRead)
def update_itinerary_item(
    trip_id: int,
    item_id: int,
    payload: ItineraryItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItineraryItem:
    trip = _get_trip_or_404(db, current_user, trip_id)
    cloned, mutation = tool_update_item(
        db,
        trip,
        item_id,
        payload.model_dump(exclude_unset=True),
        rationale="Manual itinerary edit from the workspace.",
        run=None,
    )
    changed_ids = set(mutation.changed_item_ids)
    item = next((row for row in cloned.items if row.id in changed_ids), None)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary item not found")
    return item


@router.get("/{trip_id}/map", response_model=MapResponse)
def get_trip_map(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MapResponse:
    trip = _get_trip_or_404(db, current_user, trip_id)
    return MapResponse(**build_map_payload(trip))


@router.post("/{trip_id}/export", response_model=ExportResponse)
def export_trip(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExportResponse:
    trip = _get_trip_or_404(db, current_user, trip_id)
    export = create_pdf_export(db, trip)
    return ExportResponse(export_id=export.id, file_url=export.file_url, format=export.format)


@router.post("/{trip_id}/share-links", response_model=ShareLinkResponse)
def share_trip(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ShareLinkResponse:
    trip = _get_trip_or_404(db, current_user, trip_id)
    link = create_share_link(db, trip.id)
    return ShareLinkResponse(token=link.token, public_url=f"/api/share/{link.token}", expires_at=link.expires_at)


@router.get("/{trip_id}/workspace", response_model=WorkspaceResponse)
def get_trip_workspace(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> WorkspaceResponse:
    _get_trip_or_404(db, current_user, trip_id)
    return WorkflowService(current_user).build_workspace(db, trip_id)


@router.post("/{trip_id}/workflow/start", response_model=WorkspaceResponse)
def start_trip_workflow(
    trip_id: int,
    payload: WorkflowStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceResponse:
    _get_trip_or_404(db, current_user, trip_id)
    return WorkflowService(current_user).start(db, trip_id, run_type=payload.run_type)


@router.post("/{trip_id}/workflow/messages", response_model=WorkspaceResponse)
def send_workflow_message(
    trip_id: int,
    payload: WorkflowMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceResponse:
    _get_trip_or_404(db, current_user, trip_id)
    return WorkflowService(current_user).message(db, trip_id, payload.message, scope=payload.scope)


@router.post("/{trip_id}/workflow/decisions/{decision_id}", response_model=WorkspaceResponse)
def decide_workflow_request(
    trip_id: int,
    decision_id: int,
    payload: WorkflowDecisionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceResponse:
    _get_trip_or_404(db, current_user, trip_id)
    return WorkflowService(current_user).decide(db, trip_id, decision_id, payload.action, payload.selected_option_id)


@router.post("/{trip_id}/workflow/refresh", response_model=WorkspaceResponse)
def refresh_trip_workflow(
    trip_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceResponse:
    _get_trip_or_404(db, current_user, trip_id)
    return WorkflowService(current_user).refresh(db, trip_id)


@router.post("/{trip_id}/workflow/replan-day", response_model=WorkspaceResponse)
def replan_trip_day(
    trip_id: int,
    payload: ReplanDayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceResponse:
    _get_trip_or_404(db, current_user, trip_id)
    return WorkflowService(current_user).replan_day(db, trip_id, payload.date, payload.goal)


@router.post("/{trip_id}/workflow/rebuild-plan", response_model=WorkspaceResponse)
def rebuild_trip_plan(
    trip_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceResponse:
    _get_trip_or_404(db, current_user, trip_id)
    return WorkflowService(current_user).rebuild_plan_from_selection(db, trip_id)


@router.get("/{trip_id}/today", response_model=TodaySummaryRead | None)
def get_trip_today(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TodaySummaryRead | None:
    _get_trip_or_404(db, current_user, trip_id)
    service = WorkflowService(current_user)
    trip = service._load_trip(db, trip_id)
    return service.build_today_summary(db, trip)


@router.get("/{trip_id}/agent-status", response_model=AgentStatusResponse)
def get_agent_status(trip_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentStatusResponse:
    trip = _get_trip_or_404(db, current_user, trip_id)
    
    # Process runs to find active or latest
    run = next((r for r in trip.workflow_runs if r.status == "running"), None)
    if not run:
        runs = sorted(trip.workflow_runs, key=lambda x: x.started_at, reverse=True)
        if runs:
            run = runs[0]
        else:
            return AgentStatusResponse(run_id=0, status="idle", progress_percent=0, steps=[])

    steps = sorted(run.steps, key=lambda x: x.started_at)
    
    agent_steps = [
        AgentStepRead(
            step_key=step.step_key,
            status=step.status,
            summary=step.summary,
            reasoning=step.reasoning,
            duration_ms=int((step.completed_at - step.started_at).total_seconds() * 1000) if step.completed_at else None
        )
        for step in steps
    ]
    
    # Progress percent approximation
    progress = min(100, int((len(agent_steps) / 15) * 100)) if run.status == "running" else 100
    
    current_step_key = steps[-1].step_key if steps else None
    current_step_summary = steps[-1].summary if steps else None

    return AgentStatusResponse(
        run_id=run.id,
        status=run.status,
        current_step_key=current_step_key,
        current_step_summary=current_step_summary,
        progress_percent=progress,
        steps=agent_steps
    )
