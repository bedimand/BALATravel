from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import AgentRun, ItineraryVersion, Place, Trip, User
from app.schemas.trip import ChatResponse, ProposedChange
from app.services.agent_tools import (
    begin_tool_call,
    fail_tool_call,
    finish_tool_call,
    get_active_itinerary,
    serialize_trip_snapshot,
    tool_rollback_to_version,
    tool_update_item,
)
from app.services.central_mind import CentralMind
from app.services.chat import build_chat_response


PROMPT_VERSION = "central_mind_v1"


@dataclass
class AgentExecutionResult:
    run: AgentRun
    trip: Trip
    warnings: list[str]
    applied_changes: list[dict[str, Any]]
    trip_snapshot: dict[str, Any]
    itinerary_version_id: int | None
    proposed_followups: list[str]


def _load_trip(db: Session, user: User, trip_id: int) -> Trip:
    statement = (
        select(Trip)
        .where(Trip.id == trip_id, Trip.user_id == user.id)
        .options(
            selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
            selectinload(Trip.agent_runs),
            selectinload(Trip.plan_mutations),
        )
    )
    trip = db.scalar(statement)
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


def _load_places(db: Session, trip_id: int) -> list[Place]:
    return list(db.scalars(select(Place).where(Place.trip_id == trip_id).order_by(Place.rating.desc())))


def _refresh_trip(db: Session, user: User, trip_id: int) -> Trip:
    db.expire_all()
    return _load_trip(db, user, trip_id)


class AgentCoordinator:
    """Thin adapter that delegates to CentralMind for all reasoning."""

    def __init__(self, user: User):
        self.user = user
        self.mind = CentralMind(user)

    def send_message(self, db: Session, trip_id: int, message: str) -> AgentExecutionResult:
        result = self.mind.handle_message(db, trip_id, message)

        trip = _refresh_trip(db, self.user, trip_id)
        active = get_active_itinerary(trip)
        places = _load_places(db, trip_id)

        run = db.scalar(
            select(AgentRun)
            .where(AgentRun.trip_id == trip_id)
            .order_by(AgentRun.id.desc())
            .limit(1)
        )

        proposed_followups = []
        if not active:
            proposed_followups.append("Posso gerar o primeiro roteiro completo.")
        else:
            proposed_followups.append("Posso otimizar um dia especifico, reduzir custo ou refazer o estilo do roteiro.")

        return AgentExecutionResult(
            run=run,
            trip=trip,
            warnings=result.warnings,
            applied_changes=result.applied_changes,
            trip_snapshot=serialize_trip_snapshot(trip, places),
            itinerary_version_id=active.id if active else None,
            proposed_followups=proposed_followups,
        )

    def preview_message(self, db: Session, trip_id: int, message: str) -> ChatResponse:
        trip = _load_trip(db, self.user, trip_id)
        places = _load_places(db, trip.id)
        active = get_active_itinerary(trip)
        return build_chat_response(trip, active, places, message)

    def apply_change(self, db: Session, trip_id: int, change: ProposedChange) -> AgentExecutionResult:
        trip = _load_trip(db, self.user, trip_id)
        run = AgentRun(
            trip_id=trip.id,
            intent="apply_change",
            status="running",
            # The user's real message already lives in the thread (recorded when the
            # proposal was created), so leave this null to avoid a duplicate bubble
            # echoing the proposal title.
            user_message=None,
            model="central_mind",
            prompt_version=PROMPT_VERSION,
            warnings=[],
            applied_changes=[],
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        applied = self._apply_proposed_change(db, trip, run, change)
        if not applied:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported change type.")
        trip, metadata = applied

        run.status = "completed"
        run.assistant_message = f"Pronto! {change.title} já está no seu roteiro. ✓"
        run.applied_changes = [metadata]
        run.completed_at = datetime.now(UTC)
        db.add(run)
        db.commit()

        trip = _refresh_trip(db, self.user, trip.id)
        active = get_active_itinerary(trip)
        places = _load_places(db, trip.id)
        return AgentExecutionResult(
            run=run,
            trip=trip,
            warnings=[],
            applied_changes=[metadata],
            trip_snapshot=serialize_trip_snapshot(trip, places),
            itinerary_version_id=active.id if active else None,
            proposed_followups=["Posso continuar refinando o roteiro com novos ajustes."],
        )

    def rollback(self, db: Session, trip_id: int, version_id: int) -> AgentExecutionResult:
        trip = _load_trip(db, self.user, trip_id)
        run = AgentRun(
            trip_id=trip.id,
            intent="rollback",
            status="running",
            user_message=f"rollback:{version_id}",
            model="central_mind",
            prompt_version=PROMPT_VERSION,
            warnings=[],
            applied_changes=[],
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        call = begin_tool_call(db, run, "rollback", {"version_id": version_id})
        try:
            itinerary, _ = tool_rollback_to_version(db, trip, version_id, rationale="Rollback requested by the user.", run=run)
            finish_tool_call(db, call, {"itinerary_id": itinerary.id})
        except Exception as exc:
            fail_tool_call(db, call, str(exc))
            raise

        trip = _refresh_trip(db, self.user, trip.id)
        active = get_active_itinerary(trip)
        places = _load_places(db, trip.id)

        metadata = {"mutation_type": "rollback", "rationale": "Rollback requested by the user.", "itinerary_version_id": itinerary.id}
        run.status = "completed"
        run.assistant_message = "Restaurei uma versao anterior do roteiro."
        run.applied_changes = [metadata]
        run.completed_at = datetime.now(UTC)
        db.add(run)
        db.commit()

        return AgentExecutionResult(
            run=run,
            trip=trip,
            warnings=[],
            applied_changes=[metadata],
            trip_snapshot=serialize_trip_snapshot(trip, places),
            itinerary_version_id=active.id if active else None,
            proposed_followups=["Posso continuar a partir desta versao restaurada."],
        )

    def _apply_proposed_change(
        self,
        db: Session,
        trip: Trip,
        run: AgentRun,
        change: ProposedChange,
    ) -> tuple[Trip, dict[str, Any]] | None:
        if change.type == "generate_itinerary":
            from app.models.entities import WorkflowRun
            workflow_run = WorkflowRun(trip_id=trip.id, intent="plan_trip", status="running")
            db.add(workflow_run)
            db.commit()
            db.refresh(workflow_run)
            mind = CentralMind(self.user)
            mind.plan_trip(db, trip, workflow_run, log_step_fn=None)
            trip = _refresh_trip(db, self.user, trip.id)
            active = get_active_itinerary(trip)
            return trip, {"mutation_type": "plan_trip", "rationale": change.reason, "itinerary_version_id": active.id if active else None}

        if change.type == "update_item":
            raw_item_id = change.payload.get("item_id")
            try:
                item_id = int(raw_item_id)
            except Exception:
                return None
            updates = {k: v for k, v in change.payload.items() if k in {"title", "notes", "start_time", "end_time"}}
            call = begin_tool_call(db, run, "update_item", {"item_id": item_id, "updates": updates})
            try:
                itinerary, _ = tool_update_item(db, trip, item_id, updates, rationale=change.reason, run=run)
                finish_tool_call(db, call, {"itinerary_id": itinerary.id})
            except Exception as exc:
                fail_tool_call(db, call, str(exc))
                raise
            trip = _refresh_trip(db, self.user, trip.id)
            return trip, {"mutation_type": "update_item", "rationale": change.reason, "itinerary_version_id": itinerary.id}

        return None
