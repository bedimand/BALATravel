from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.entities import AgentRun, PlanMutation, Trip, User
from app.schemas.trip import AgentMessageRequest, AgentMessageResponse, AgentRunRead, AgentThreadResponse
from app.services.agent import AgentCoordinator


router = APIRouter(prefix="/trips", tags=["agent"])


def _get_owned_trip_or_404(db: Session, current_user: User, trip_id: int) -> Trip:
    trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == current_user.id))
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.post("/{trip_id}/agent/messages", response_model=AgentMessageResponse)
def send_agent_message(
    trip_id: int,
    payload: AgentMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentMessageResponse:
    _get_owned_trip_or_404(db, current_user, trip_id)
    result = AgentCoordinator(current_user).send_message(db, trip_id, payload.message)
    return AgentMessageResponse(
        run_id=result.run.id,
        assistant_message=result.run.assistant_message,
        warnings=result.warnings,
        applied_changes=result.applied_changes,
        proposed_followups=result.proposed_followups,
        itinerary_version_id=result.itinerary_version_id,
        trip_snapshot=result.trip_snapshot,
    )


@router.get("/{trip_id}/agent/runs", response_model=list[AgentRunRead])
def list_agent_runs(
    trip_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AgentRun]:
    _get_owned_trip_or_404(db, current_user, trip_id)
    statement = (
        select(AgentRun)
        .where(AgentRun.trip_id == trip_id)
        .order_by(AgentRun.created_at.asc(), AgentRun.id.asc())
        .options(selectinload(AgentRun.tool_calls))
    )
    return list(db.scalars(statement).unique())


@router.get("/{trip_id}/agent/runs/{run_id}", response_model=AgentRunRead)
def get_agent_run(
    trip_id: int,
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentRun:
    _get_owned_trip_or_404(db, current_user, trip_id)
    statement = (
        select(AgentRun)
        .where(AgentRun.trip_id == trip_id, AgentRun.id == run_id)
        .options(selectinload(AgentRun.tool_calls))
    )
    run = db.scalar(statement)
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


@router.get("/{trip_id}/agent/thread", response_model=AgentThreadResponse)
def get_agent_thread(
    trip_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentThreadResponse:
    _get_owned_trip_or_404(db, current_user, trip_id)
    runs = list(
        db.scalars(
            select(AgentRun)
            .where(AgentRun.trip_id == trip_id)
            .order_by(AgentRun.created_at.asc(), AgentRun.id.asc())
            .options(selectinload(AgentRun.tool_calls))
        ).unique()
    )
    mutations = list(
        db.scalars(
            select(PlanMutation)
            .where(PlanMutation.trip_id == trip_id)
            .order_by(PlanMutation.created_at.desc(), PlanMutation.id.desc())
        ).unique()
    )
    return AgentThreadResponse(trip_id=trip_id, runs=runs, mutations=mutations)


@router.post("/{trip_id}/agent/rollback/{version_id}", response_model=AgentMessageResponse)
def rollback_itinerary_version(
    trip_id: int,
    version_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentMessageResponse:
    _get_owned_trip_or_404(db, current_user, trip_id)
    result = AgentCoordinator(current_user).rollback(db, trip_id, version_id)
    return AgentMessageResponse(
        run_id=result.run.id,
        assistant_message=result.run.assistant_message,
        warnings=result.warnings,
        applied_changes=result.applied_changes,
        proposed_followups=result.proposed_followups,
        itinerary_version_id=result.itinerary_version_id,
        trip_snapshot=result.trip_snapshot,
    )
