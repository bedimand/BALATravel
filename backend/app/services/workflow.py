from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    AgentArtifact,
    DecisionRequest,
    ItineraryVersion,
    Place,
    Trip,
    TripWeatherSnapshot,
    TripWorkflowState,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.schemas.trip import (
    AgentArtifactRead,
    DecisionRequestRead,
    ItineraryVersionRead,
    MapResponse,
    ProposedChange,
    RouteSummaryRead,
    TodaySummaryRead,
    TripRead,
    TripWeatherSnapshotRead,
    WorkspaceResponse,
    WorkflowRunRead,
    WorkflowStateRead,
)
from app.services.agent import AgentCoordinator
from app.services.agent_tools import get_active_itinerary, tool_generate_itinerary, tool_reorder_day
from app.services.chat import build_chat_response
from app.services.llm import LLMIntegrationError
from app.services.planner import build_map_payload
from app.services.routing import summarize_route_burden


WORKFLOW_STAGES = {
    "trip_intake",
    "search_context",
    "curate_places",
    "enrich_weather",
    "draft_itinerary",
    "critic_review",
    "await_plan_approval",
    "active_trip",
    "targeted_replan",
    "publish_revision",
}


@dataclass
class WorkflowExecutionResult:
    trip: Trip
    workflow_state: TripWorkflowState
    warnings: list[str]


def _now() -> datetime:
    return datetime.now(UTC)
class WorkflowService:
    def __init__(self, user: User):
        self.user = user

    def _load_trip(self, db: Session, trip_id: int) -> Trip:
        trip = db.scalar(
            select(Trip)
            .where(Trip.id == trip_id, Trip.user_id == self.user.id)
            .options(
                selectinload(Trip.flights),
                selectinload(Trip.hotels),
                selectinload(Trip.places),
                selectinload(Trip.route_estimates),
                selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
                selectinload(Trip.workflow_state),
                selectinload(Trip.workflow_runs).selectinload(WorkflowRun.steps),
                selectinload(Trip.decision_requests),
                selectinload(Trip.artifacts),
                selectinload(Trip.weather_snapshots),
            )
        )
        if not trip:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
        return trip

    def _load_places(self, db: Session, trip_id: int) -> list[Place]:
        return list(db.scalars(select(Place).where(Place.trip_id == trip_id).order_by(Place.rating.desc())))

    def _get_or_create_state(self, db: Session, trip: Trip) -> TripWorkflowState:
        state = trip.workflow_state
        if state:
            return state
        state = TripWorkflowState(
            trip_id=trip.id,
            current_stage="trip_intake",
            stage_status="idle",
            last_synced_at=_now(),
        )
        db.add(state)
        db.commit()
        db.refresh(state)
        return state

    def initialize_trip(self, db: Session, trip_id: int) -> None:
        trip = self._load_trip(db, trip_id)
        self._get_or_create_state(db, trip)

    def _start_run(self, db: Session, trip: Trip, run_type: str) -> tuple[TripWorkflowState, WorkflowRun]:
        state = self._get_or_create_state(db, trip)
        run = WorkflowRun(trip_id=trip.id, run_type=run_type, status="running")
        db.add(run)
        db.flush()
        state.active_workflow_run_id = run.id
        state.stage_status = "running"
        state.last_synced_at = _now()
        db.add(state)
        db.commit()
        db.refresh(state)
        db.refresh(run)
        return state, run

    def _finish_run(self, db: Session, state: TripWorkflowState, run: WorkflowRun, *, stage_status: str) -> None:
        run.status = "completed"
        run.completed_at = _now()
        state.stage_status = stage_status
        state.last_synced_at = _now()
        db.add(run)
        db.add(state)
        db.commit()

    def _log_step(
        self,
        db: Session,
        run: WorkflowRun,
        step_key: str,
        status_name: str,
        summary: str,
        reasoning: str | None = None,
        input_json: dict[str, Any] | None = None,
        output_json: dict[str, Any] | None = None,
    ) -> None:
        row = WorkflowStep(
            workflow_run_id=run.id,
            step_key=step_key,
            status=status_name,
            summary=summary,
            reasoning=reasoning,
            input_json=input_json or {},
            output_json=output_json or {},
            completed_at=_now(),
        )
        db.add(row)
        db.commit()

    def _replace_artifact(
        self,
        db: Session,
        trip: Trip,
        artifact_type: str,
        title: str,
        summary: str,
        payload_json: dict[str, Any],
        run: WorkflowRun | None = None,
    ) -> AgentArtifact:
        db.execute(delete(AgentArtifact).where(AgentArtifact.trip_id == trip.id, AgentArtifact.artifact_type == artifact_type))
        artifact = AgentArtifact(
            trip_id=trip.id,
            workflow_run_id=run.id if run else None,
            artifact_type=artifact_type,
            title=title,
            summary=summary,
            payload_json=payload_json,
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return artifact

    def _replace_decision(
        self,
        db: Session,
        trip: Trip,
        kind: str,
        title: str,
        summary: str,
        options_json: list[dict[str, Any]],
        recommended_option_id: str | None,
        payload_json: dict[str, Any] | None = None,
        run: WorkflowRun | None = None,
    ) -> DecisionRequest:
        for row in trip.decision_requests:
            if row.kind == kind and row.status == "pending":
                row.status = "superseded"
                row.decided_at = _now()
                db.add(row)
        decision = DecisionRequest(
            trip_id=trip.id,
            workflow_run_id=run.id if run else None,
            kind=kind,
            status="pending",
            title=title,
            summary=summary,
            options_json=options_json,
            recommended_option_id=recommended_option_id,
            payload_json=payload_json or {},
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)
        return decision

    def _default_today_date(self, trip: Trip) -> date:
        current = datetime.now().date()
        if trip.start_date <= current < trip.end_date:
            return current
        return trip.start_date

    def _create_change_decision(self, db: Session, trip: Trip, message: str, run: WorkflowRun | None = None) -> None:
        active = get_active_itinerary(trip)
        places = self._load_places(db, trip.id)
        proposal: dict[str, Any] | None = None
        lowered = message.lower()
        if active and any(token in lowered for token in ["chuva", "rain", "atras", "late", "walking", "andar", "afternoon", "tarde", "today", "hoje"]):
            proposal = {
                "type": "reorder_day",
                "title": "Reorganizar o dia atual",
                "reason": message,
                "payload": {"date": self._default_today_date(trip).isoformat()},
            }
        elif active:
            try:
                preview = build_chat_response(trip, active, places, message)
            except LLMIntegrationError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            if preview.proposed_changes:
                proposal = preview.proposed_changes[0].model_dump()

        if not proposal:
            self._replace_artifact(
                db,
                trip,
                "change_diff",
                "Nenhuma mudanca segura encontrada",
                "O pedido foi salvo, mas ainda nao encontrei uma mudanca automatica segura para aprovar.",
                {"message": message},
                run=run,
            )
            return

        self._replace_artifact(
            db,
            trip,
            "change_diff",
            proposal["title"],
            proposal["reason"],
            {"proposal": proposal, "message": message},
            run=run,
        )
        self._replace_decision(
            db,
            trip,
            "change_approval",
            proposal["title"],
            proposal["reason"],
            [
                {"id": "approve", "label": "Aprovar"},
                {"id": "reject", "label": "Rejeitar"},
            ],
            "approve",
            payload_json={"proposal": proposal},
            run=run,
        )

    def _apply_change_proposal(self, db: Session, trip: Trip, proposal: dict[str, Any]) -> None:
        proposal_type = proposal.get("type")
        if proposal_type in {"generate_itinerary", "update_item"}:
            AgentCoordinator(self.user).apply_change(db, trip.id, ProposedChange.model_validate(proposal))
            return
        if proposal_type == "reorder_day":
            date_text = str((proposal.get("payload") or {}).get("date") or "").strip()
            if not date_text:
                raise HTTPException(status_code=400, detail="Missing date for reorder_day proposal.")
            tool_reorder_day(db, trip, date_text, rationale=str(proposal.get("reason") or "Workflow reorder"), run=None)
            return
        raise HTTPException(status_code=400, detail="Unsupported proposal type.")

    def _progress_workflow(self, db: Session, trip_id: int, run_type: str) -> WorkflowExecutionResult:
        trip = self._load_trip(db, trip_id)
        state, run = self._start_run(db, trip, run_type)
        warnings: list[str] = []
        
        from app.services.central_agent import CentralPlanningAgent
        agent = CentralPlanningAgent()
        
        try:
            agent.plan_trip(db, trip, run, self._log_step)
        except Exception as e:
            warnings.append(f"Agent execution failed: {str(e)}")
            self._log_step(db, run, "agent_error", "failed", f"Execution error: {str(e)}")

        trip = self._load_trip(db, trip.id)
        active = get_active_itinerary(trip)

        if active:
            state.current_stage = "await_plan_approval"
            self._replace_artifact(
                db,
                trip,
                "plan_draft",
                "Primeiro rascunho do roteiro",
                active.assistant_summary if active else "Roteiro gerado.",
                {
                    "itinerary_version_id": active.id if active else None,
                    "warnings": active.warnings if active else [],
                },
                run=run,
            )
# Decision request removed to avoid intrusive popups before user inspection
            # self._replace_decision(...)
            db.add(state)
            db.commit()
            self._finish_run(db, state, run, stage_status="waiting_user")
        else:
            state.current_stage = "trip_intake"
            db.add(state)
            db.commit()
            self._finish_run(db, state, run, stage_status="failed")
            
        return WorkflowExecutionResult(trip=self._load_trip(db, trip.id), workflow_state=state, warnings=warnings)

    def start(self, db: Session, trip_id: int, run_type: str = "setup") -> WorkspaceResponse:
        self._progress_workflow(db, trip_id, run_type)
        return self.build_workspace(db, trip_id)

    def refresh(self, db: Session, trip_id: int) -> WorkspaceResponse:
        return self.start(db, trip_id, run_type="refresh")

    def message(self, db: Session, trip_id: int, message: str, scope: str = "trip") -> WorkspaceResponse:
        trip = self._load_trip(db, trip_id)
        state, run = self._start_run(db, trip, "in_trip_update" if get_active_itinerary(trip) else "setup")
        state.last_user_goal = message
        state.current_stage = "targeted_replan" if get_active_itinerary(trip) else state.current_stage
        db.add(state)
        db.commit()
        self._create_change_decision(db, trip, message, run=run)
        self._log_step(db, run, "workflow_message", "completed", "Pedido do usuario transformado em proposta revisavel.", {"message": message, "scope": scope})
        self._finish_run(db, state, run, stage_status="waiting_user")
        return self.build_workspace(db, trip_id)

    def decide(self, db: Session, trip_id: int, decision_id: int, action: str, selected_option_id: str | None = None) -> WorkspaceResponse:
        trip = self._load_trip(db, trip_id)
        decision = next((row for row in trip.decision_requests if row.id == decision_id), None)
        if not decision:
            raise HTTPException(status_code=404, detail="Decision request not found")

        decision.status = "approved" if action in {"approve", "select"} else "rejected"
        decision.selected_option_id = selected_option_id or decision.selected_option_id or decision.recommended_option_id
        decision.decided_at = _now()
        db.add(decision)
        db.commit()

        state = self._get_or_create_state(db, trip)
        if decision.kind == "plan_approval":
            state.current_stage = "active_trip" if action == "approve" else "targeted_replan"
            state.stage_status = "ready" if action == "approve" else "waiting_user"
            db.add(state)
            db.commit()
            return self.build_workspace(db, trip.id)

        if decision.kind == "change_approval" and action == "approve":
            proposal = (decision.payload_json or {}).get("proposal") or {}
            self._apply_change_proposal(db, trip, proposal)
            state.current_stage = "publish_revision"
            state.stage_status = "ready"
            db.add(state)
            db.commit()
            self._replace_artifact(
                db,
                trip,
                "plan_draft",
                "Revisao aplicada",
                str(proposal.get("reason") or "Mudanca aprovada e aplicada."),
                {"proposal": proposal},
            )
            state.current_stage = "active_trip"
            db.add(state)
            db.commit()
            return self.build_workspace(db, trip.id)

        if decision.kind == "change_approval" and action == "reject":
            state.current_stage = "active_trip"
            state.stage_status = "ready"
            db.add(state)
            db.commit()
            return self.build_workspace(db, trip.id)

        return self.build_workspace(db, trip.id)

    def replan_day(self, db: Session, trip_id: int, target_date: date, goal: str) -> WorkspaceResponse:
        trip = self._load_trip(db, trip_id)
        state, run = self._start_run(db, trip, "replan")
        state.last_user_goal = goal
        state.current_stage = "targeted_replan"
        db.add(state)
        db.commit()
        proposal = {
            "type": "reorder_day",
            "title": f"Reorganizar {target_date.isoformat()}",
            "reason": goal,
            "payload": {"date": target_date.isoformat()},
        }
        self._replace_artifact(
            db,
            trip,
            "change_diff",
            proposal["title"],
            proposal["reason"],
            {"proposal": proposal},
            run=run,
        )
        self._replace_decision(
            db,
            trip,
            "change_approval",
            proposal["title"],
            proposal["reason"],
            [{"id": "approve", "label": "Aprovar"}, {"id": "reject", "label": "Rejeitar"}],
            "approve",
            payload_json={"proposal": proposal},
            run=run,
        )
        self._log_step(db, run, "replan_day", "completed", "Pedido de replanejamento preparado para aprovacao.", {"date": target_date.isoformat(), "goal": goal})
        self._finish_run(db, state, run, stage_status="waiting_user")
        return self.build_workspace(db, trip.id)

    def update_place_selection(self, db: Session, trip_id: int, place_id: int, is_selected: bool) -> WorkspaceResponse:
        trip = self._load_trip(db, trip_id)
        place = next((row for row in trip.places if row.id == place_id), None)
        if not place:
            raise HTTPException(status_code=404, detail="Place not found")

        selected_count = sum(1 for row in trip.places if row.is_selected and row.id != place_id)
        if not is_selected and selected_count == 0:
            raise HTTPException(status_code=400, detail="At least one place must remain selected.")

        place.is_selected = is_selected
        db.add(place)
        db.commit()
        trip = self._load_trip(db, trip_id)
        self._replace_artifact(
            db,
            trip,
            "place_curation",
            "O que vale fazer nessa viagem",
            "A curadoria abaixo prioriza experiencias e bairros que combinam com o perfil informado.",
            {
                "places": [
                    {
                        "id": row.id,
                        "name": row.name,
                        "category": row.category,
                        "rating": row.rating,
                        "summary": row.summary,
                        "image_url": row.image_url,
                        "is_selected": row.is_selected,
                        "deeplink": row.deeplink,
                    }
                    for row in trip.places
                ]
            },
        )
        return self.build_workspace(db, trip_id)

    def rebuild_plan_from_selection(self, db: Session, trip_id: int) -> WorkspaceResponse:
        trip = self._load_trip(db, trip_id)
        selected_places = [place for place in trip.places if place.is_selected]
        if not selected_places:
            raise HTTPException(status_code=400, detail="Select at least one place before rebuilding the plan.")

        state, run = self._start_run(db, trip, "selection_rebuild")
        state.current_stage = "draft_itinerary"
        db.add(state)
        db.commit()

        itinerary, _ = tool_generate_itinerary(
            db,
            trip,
            run=None,
            rationale="Rebuilt itinerary using the user-selected places.",
        )
        trip = self._load_trip(db, trip.id)
        active = get_active_itinerary(trip)
        self._replace_artifact(
            db,
            trip,
            "plan_draft",
            "Roteiro atualizado pelos lugares selecionados",
            active.assistant_summary if active else "Roteiro atualizado.",
            {
                "itinerary_version_id": active.id if active else None,
                "warnings": active.warnings if active else [],
                "selected_place_count": len(selected_places),
            },
            run=run,
        )
# Decision request removed
        # self._replace_decision(...)
        self._log_step(
            db,
            run,
            "rebuild_plan_from_selection",
            "completed",
            "Roteiro reconstruido com base na selecao manual de lugares.",
            {"selected_place_count": len(selected_places)},
            {"itinerary_id": itinerary.id},
        )
        state.current_stage = "await_plan_approval"
        db.add(state)
        db.commit()
        self._finish_run(db, state, run, stage_status="waiting_user")
        return self.build_workspace(db, trip.id)

    def build_today_summary(self, db: Session, trip: Trip) -> TodaySummaryRead | None:
        active = get_active_itinerary(trip)
        if not active:
            return None
        target_date = self._default_today_date(trip)
        day_items = [item for item in active.items if item.date == target_date]
        weather = db.scalar(
            select(TripWeatherSnapshot)
            .where(TripWeatherSnapshot.trip_id == trip.id, TripWeatherSnapshot.forecast_date == target_date)
        )
        headline = "Dia pronto para seguir." if day_items else "Ainda nao ha itens planejados para hoje."
        if weather and weather.is_outdoor_risky:
            headline = f"Ajuste recomendado por causa de {weather.condition_label}."
        return TodaySummaryRead(
            date=target_date,
            headline=headline,
            quick_actions=[
                "Reduzir caminhada",
                "Reorganizar a tarde",
                "Buscar comida perto da proxima parada",
                "Adaptar por chuva",
            ],
            item_ids=[item.id for item in day_items],
            route_burden_min=sum(item.travel_time_min for item in day_items),
            weather=TripWeatherSnapshotRead.model_validate(weather) if weather else None,
        )

    def build_workspace(self, db: Session, trip_id: int) -> WorkspaceResponse:
        trip = self._load_trip(db, trip_id)
        state = self._get_or_create_state(db, trip)
        active = get_active_itinerary(trip)
        route_summary = RouteSummaryRead(**summarize_route_burden(trip))
        map_payload = MapResponse(**build_map_payload(trip))
        pending_decisions = sorted(
            [row for row in trip.decision_requests if row.status == "pending"],
            key=lambda row: row.created_at,
            reverse=True,
        )
        latest_artifacts = sorted(trip.artifacts, key=lambda row: row.created_at, reverse=True)[:8]
        weather_rows = sorted(trip.weather_snapshots, key=lambda row: row.forecast_date)
        workflow_runs = sorted(trip.workflow_runs, key=lambda row: row.started_at, reverse=True)[:6]
        return WorkspaceResponse(
            trip=TripRead.model_validate(trip),
            workflow=WorkflowStateRead.model_validate(state),
            workflow_runs=[WorkflowRunRead.model_validate(row) for row in workflow_runs],
            decisions=[DecisionRequestRead.model_validate(row) for row in pending_decisions],
            artifacts=[AgentArtifactRead.model_validate(row) for row in latest_artifacts],
            active_itinerary=ItineraryVersionRead.model_validate(active) if active else None,
            version_history=[ItineraryVersionRead.model_validate(row) for row in trip.itinerary_versions],
            map=map_payload,
            today=self.build_today_summary(db, trip),
            weather=[TripWeatherSnapshotRead.model_validate(row) for row in weather_rows],
            route_summary=route_summary,
        )
