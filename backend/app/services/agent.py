from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

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
    get_planning_blockers,
    serialize_trip_snapshot,
    tool_generate_itinerary,
    tool_list_current_options,
    tool_remove_item,
    tool_reorder_day,
    tool_replan_itinerary,
    tool_rollback_to_version,
    tool_search_all,
    tool_update_item,
)
from app.services.chat import build_chat_response
from app.services.llm import llm_chat


MAX_AGENT_STEPS = 5
PROMPT_VERSION = "v1"


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
            selectinload(Trip.flights),
            selectinload(Trip.hotels),
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


def _parse_json_object(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    content = text.strip()
    try:
        payload = json.loads(content)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def _parse_requested_day(message: str, trip: Trip) -> str | None:
    lowered = message.lower()
    digit_match = re.search(r"(?:day|dia)\s+(\d+)", lowered)
    if not digit_match:
        return None
    index = int(digit_match.group(1)) - 1
    if index < 0:
        return None
    days = sorted({item.date.isoformat() for version in trip.itinerary_versions for item in version.items})
    return days[index] if index < len(days) else None


def _fallback_actions(message: str, trip: Trip, has_places: bool) -> list[dict[str, Any]]:
    lowered = message.lower()
    actions: list[dict[str, Any]] = []
    active = get_active_itinerary(trip)

    search_keywords = ["search", "buscar", "find", "options", "place", "atra", "bairro", "museu", "comida", "praia"]
    missing_search_context = not has_places
    if any(keyword in lowered for keyword in search_keywords) or missing_search_context:
        actions.append({"tool": "search_all", "rationale": "Need fresh travel options and places to plan effectively."})

    if any(keyword in lowered for keyword in ["replan", "redo", "refa", "optimize all", "otimize tudo", "make this better", "melhore", "cheaper", "barat", "econom"]):
        actions.append({"tool": "replan_itinerary" if active else "generate_itinerary", "rationale": "Global optimization request requires a refreshed itinerary."})
        return actions

    requested_day = _parse_requested_day(message, trip)
    if requested_day and any(keyword in lowered for keyword in ["optimize", "otimize", "reorder", "organize"]):
        actions.append({"tool": "reorder_day", "date": requested_day, "rationale": f"User asked to optimize {requested_day}."})
        return actions

    if not active:
        actions.append({"tool": "generate_itinerary", "rationale": "No active itinerary exists yet."})
    return actions[:MAX_AGENT_STEPS]


def _format_planning_blocker_message(blockers: list[str]) -> str:
    readable = {
        "place options": "lugares e atracoes",
    }
    labels = [readable.get(item, item) for item in blockers]
    if len(labels) == 1:
        joined = labels[0]
    elif len(labels) == 2:
        joined = f"{labels[0]} e {labels[1]}"
    else:
        joined = ", ".join(labels[:-1]) + f" e {labels[-1]}"
    return f"Nao gerei o roteiro porque ainda faltam dados confiaveis de {joined}. Primeiro preciso buscar e validar esse contexto."


class AgentCoordinator:
    def __init__(self, user: User):
        self.user = user

    def _start_run(self, db: Session, trip: Trip, intent: str, user_message: str | None) -> AgentRun:
        run = AgentRun(
            trip_id=trip.id,
            intent=intent,
            status="running",
            user_message=user_message,
            model="openrouter/auto",
            prompt_version=PROMPT_VERSION,
            warnings=[],
            applied_changes=[],
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _finish_run(
        self,
        db: Session,
        run: AgentRun,
        assistant_message: str,
        warnings: list[str],
        applied_changes: list[dict[str, Any]],
    ) -> AgentRun:
        run.status = "completed"
        run.assistant_message = assistant_message
        run.warnings = warnings
        run.applied_changes = applied_changes
        run.completed_at = datetime.now(UTC)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _build_result(
        self,
        db: Session,
        trip: Trip,
        run: AgentRun,
        warnings: list[str],
        applied_changes: list[dict[str, Any]],
        proposed_followups: list[str] | None = None,
    ) -> AgentExecutionResult:
        active = get_active_itinerary(trip)
        return AgentExecutionResult(
            run=run,
            trip=trip,
            warnings=warnings,
            applied_changes=applied_changes,
            trip_snapshot=serialize_trip_snapshot(trip, _load_places(db, trip.id)),
            itinerary_version_id=active.id if active else None,
            proposed_followups=proposed_followups or [],
        )

    def _tool(
        self,
        db: Session,
        run: AgentRun,
        tool_name: str,
        arguments: dict[str, Any],
        action: Callable[[], Any],
    ) -> Any:
        call = begin_tool_call(db, run, tool_name, arguments)
        try:
            result = action()
            finish_tool_call(
                db,
                call,
                result if isinstance(result, dict) else {"result": result},
            )
            return result
        except HTTPException as exc:
            fail_tool_call(db, call, exc.detail if isinstance(exc.detail, str) else str(exc.detail))
            raise
        except Exception as exc:
            fail_tool_call(db, call, str(exc))
            raise

    def _plan_actions_with_llm(self, trip: Trip, message: str, places: list[Place]) -> list[dict[str, Any]] | None:
        prompt = (
            "Return valid JSON only.\n"
            "Choose up to 3 actions for an autonomous trip-planning agent.\n"
            "Allowed tools: search_all, generate_itinerary, replan_itinerary, reorder_day, update_item, remove_item.\n"
            "Never choose generate_itinerary or replan_itinerary unless place_count > 0 in the trip snapshot.\n"
            "If place_count is zero and the user wants a new plan, choose search_all first instead of hallucinating missing travel context.\n"
            "Use update_item only when you can name an existing item id from the snapshot.\n"
            'JSON format: {"actions":[{"tool":"name","rationale":"why","item_id":123,"updates":{"start_time":"09:00:00"},"date":"YYYY-MM-DD"}]}\n'
            f"Trip snapshot: {json.dumps(serialize_trip_snapshot(trip, places), ensure_ascii=False)}\n"
            f"Active itinerary: {json.dumps({'items': serialize_trip_snapshot(trip, places).get('active_itinerary', {})}, ensure_ascii=False)}\n"
            f"User request: {message}\n"
        )
        parsed = _parse_json_object(
            llm_chat(
                prompt,
                system_prompt=(
                    "You are an autonomous trip planning agent. "
                    "Pick the minimum set of tools needed, prefer local itinerary edits when possible, "
                    "and use full replans only for global requests. Return JSON only."
                ),
                temperature=0.1,
            )
        )
        if not parsed:
            return None
        actions = parsed.get("actions")
        if not isinstance(actions, list):
            return None
        normalized = []
        for row in actions[:MAX_AGENT_STEPS]:
            if isinstance(row, dict) and isinstance(row.get("tool"), str):
                normalized.append(row)
        return normalized or None

    def _preview_changes(self, db: Session, trip: Trip, message: str) -> ChatResponse:
        places = _load_places(db, trip.id)
        return build_chat_response(trip, get_active_itinerary(trip), places, message)

    def _apply_proposed_change(
        self,
        db: Session,
        trip: Trip,
        run: AgentRun,
        change: ProposedChange,
    ) -> tuple[Trip, dict[str, Any]] | None:
        if change.type == "generate_itinerary":
            itinerary, mutation = self._tool(
                db,
                run,
                "generate_itinerary",
                {"trip_id": trip.id},
                lambda: {
                    "itinerary_id": tool_generate_itinerary(db, trip, run=run, rationale=change.reason)[0].id,
                },
            )
            trip = _refresh_trip(db, self.user, trip.id)
            return trip, {"mutation_type": "generate_itinerary", "rationale": change.reason, "itinerary_version_id": itinerary["itinerary_id"]}

        if change.type != "update_item":
            return None

        raw_item_id = change.payload.get("item_id")
        try:
            item_id = int(raw_item_id)
        except Exception:
            return None
        updates = {
            key: value
            for key, value in change.payload.items()
            if key in {"title", "notes", "start_time", "end_time"}
        }
        version = self._tool(
            db,
            run,
            "update_item",
            {"trip_id": trip.id, "item_id": item_id, "updates": updates},
            lambda: {
                "itinerary_id": tool_update_item(db, trip, item_id, updates, rationale=change.reason, run=run)[0].id,
            },
        )
        trip = _refresh_trip(db, self.user, trip.id)
        return trip, {"mutation_type": "update_item", "rationale": change.reason, "itinerary_version_id": version["itinerary_id"]}

    def _autonomous_chat_followup(
        self,
        db: Session,
        trip: Trip,
        run: AgentRun,
        message: str,
    ) -> tuple[Trip, list[dict[str, Any]], list[str], str]:
        preview = self._preview_changes(db, trip, message)
        applied_changes: list[dict[str, Any]] = []
        warnings = list(preview.warnings)
        for change in preview.proposed_changes[:2]:
            applied = self._apply_proposed_change(db, trip, run, change)
            if applied:
                trip, metadata = applied
                applied_changes.append(metadata)
        return trip, applied_changes, warnings, preview.assistant_message

    def send_message(self, db: Session, trip_id: int, message: str) -> AgentExecutionResult:
        trip = _load_trip(db, self.user, trip_id)
        run = self._start_run(db, trip, "message", message)
        warnings: list[str] = []
        applied_changes: list[dict[str, Any]] = []
        assistant_bits: list[str] = []

        places = _load_places(db, trip.id)
        actions = _fallback_actions(message, trip, bool(places))
        if not actions:
            actions = self._plan_actions_with_llm(trip, message, places) or []

        for action in actions[:MAX_AGENT_STEPS]:
            tool_name = action.get("tool")
            if tool_name == "search_all":
                def _run_search() -> dict[str, Any]:
                    result, search_warnings = tool_search_all(db, trip)
                    return {"result": result, "warnings": search_warnings}

                search_payload = self._tool(
                    db,
                    run,
                    "search_all",
                    {"trip_id": trip.id},
                    _run_search,
                )
                warnings.extend(search_payload.get("warnings", []))
                assistant_bits.append("Busquei novas opcoes de voo, hospedagem e lugares.")
                trip = _refresh_trip(db, self.user, trip.id)
                continue

            if tool_name == "generate_itinerary":
                blockers = get_planning_blockers(trip, _load_places(db, trip.id))
                if blockers:
                    warnings.append(f"Missing planning context before generation: {', '.join(blockers)}.")
                    assistant_bits.append(_format_planning_blocker_message(blockers))
                    continue
                generated = self._tool(
                    db,
                    run,
                    "generate_itinerary",
                    {"trip_id": trip.id},
                    lambda: {"itinerary_id": tool_generate_itinerary(db, trip, run=run, rationale=action.get("rationale", ""))[0].id},
                )
                applied_changes.append(
                    {"mutation_type": "generate_itinerary", "rationale": action.get("rationale", ""), "itinerary_version_id": generated["itinerary_id"]}
                )
                assistant_bits.append("Gerei um roteiro novo com base nos dados atuais.")
                trip = _refresh_trip(db, self.user, trip.id)
                continue

            if tool_name == "replan_itinerary":
                blockers = get_planning_blockers(trip, _load_places(db, trip.id))
                if blockers:
                    warnings.append(f"Missing planning context before replanning: {', '.join(blockers)}.")
                    assistant_bits.append(_format_planning_blocker_message(blockers))
                    continue
                replanned = self._tool(
                    db,
                    run,
                    "replan_itinerary",
                    {"trip_id": trip.id},
                    lambda: {"itinerary_id": tool_replan_itinerary(db, trip, run=run, rationale=action.get("rationale", ""))[0].id},
                )
                applied_changes.append(
                    {"mutation_type": "replan_itinerary", "rationale": action.get("rationale", ""), "itinerary_version_id": replanned["itinerary_id"]}
                )
                assistant_bits.append("Replanejei o roteiro para refletir sua solicitacao.")
                trip = _refresh_trip(db, self.user, trip.id)
                continue

            if tool_name == "reorder_day":
                date_text = str(action.get("date", "")).strip()
                if not date_text:
                    continue
                reordered = self._tool(
                    db,
                    run,
                    "reorder_day",
                    {"trip_id": trip.id, "date": date_text},
                    lambda: {"itinerary_id": tool_reorder_day(db, trip, date_text, rationale=action.get("rationale", ""), run=run)[0].id},
                )
                applied_changes.append(
                    {"mutation_type": "reorder_day", "rationale": action.get("rationale", ""), "itinerary_version_id": reordered["itinerary_id"]}
                )
                assistant_bits.append(f"Reorganizei o dia {date_text}.")
                trip = _refresh_trip(db, self.user, trip.id)
                continue

            if tool_name == "update_item":
                raw_item_id = action.get("item_id")
                if raw_item_id is None:
                    continue
                updated = self._tool(
                    db,
                    run,
                    "update_item",
                    {"trip_id": trip.id, "item_id": raw_item_id, "updates": action.get("updates", {})},
                    lambda: {"itinerary_id": tool_update_item(
                        db,
                        trip,
                        int(raw_item_id),
                        dict(action.get("updates", {})),
                        rationale=action.get("rationale", ""),
                        run=run,
                    )[0].id},
                )
                applied_changes.append(
                    {"mutation_type": "update_item", "rationale": action.get("rationale", ""), "itinerary_version_id": updated["itinerary_id"]}
                )
                assistant_bits.append("Ajustei um item especifico do roteiro.")
                trip = _refresh_trip(db, self.user, trip.id)
                continue

            if tool_name == "remove_item":
                raw_item_id = action.get("item_id")
                if raw_item_id is None:
                    continue
                removed = self._tool(
                    db,
                    run,
                    "remove_item",
                    {"trip_id": trip.id, "item_id": raw_item_id},
                    lambda: {"itinerary_id": tool_remove_item(db, trip, int(raw_item_id), rationale=action.get("rationale", ""), run=run)[0].id},
                )
                applied_changes.append(
                    {"mutation_type": "remove_item", "rationale": action.get("rationale", ""), "itinerary_version_id": removed["itinerary_id"]}
                )
                assistant_bits.append("Removi uma atividade do roteiro.")
                trip = _refresh_trip(db, self.user, trip.id)
                continue

        if not applied_changes:
            blockers = get_planning_blockers(trip, _load_places(db, trip.id))
            if blockers and get_active_itinerary(trip) is None:
                warnings.append(f"Autonomous planning blocked because context is incomplete: {', '.join(blockers)}.")
                assistant_bits.append(_format_planning_blocker_message(blockers))
            else:
                trip, chat_changes, chat_warnings, assistant_message = self._autonomous_chat_followup(db, trip, run, message)
                applied_changes.extend(chat_changes)
                warnings.extend(chat_warnings)
                if assistant_message:
                    assistant_bits.append(assistant_message)

        if not assistant_bits:
            assistant_bits.append("Analisei sua solicitacao e nao encontrei uma acao segura para aplicar automaticamente.")

        trip = _refresh_trip(db, self.user, trip.id)
        options = self._tool(
            db,
            run,
            "list_current_options",
            {"trip_id": trip.id},
            lambda: tool_list_current_options(db, trip),
        )
        active = get_active_itinerary(trip)
        proposed_followups = []
        if not active:
            proposed_followups.append("Peça para eu gerar o primeiro roteiro completo.")
        elif not trip.flights or not trip.hotels:
            proposed_followups.append("Posso buscar mais opções para enriquecer a próxima revisão.")
        else:
            proposed_followups.append("Posso otimizar um dia específico, reduzir custo ou refazer o estilo do roteiro.")
        assistant_bits.append(
            f"Estado atual: {options['flights']} voos, {options['hotels']} hoteis e {options['places']} lugares salvos."
        )
        run = self._finish_run(db, run, " ".join(assistant_bits).strip(), list(dict.fromkeys(warnings)), applied_changes)
        return self._build_result(db, trip, run, run.warnings, applied_changes, proposed_followups)

    def preview_message(self, db: Session, trip_id: int, message: str) -> ChatResponse:
        trip = _load_trip(db, self.user, trip_id)
        run = self._start_run(db, trip, "chat_preview", message)
        preview = ChatResponse.model_validate(self._preview_changes(db, trip, message))
        self._finish_run(
            db,
            run,
            preview.assistant_message,
            list(preview.warnings),
            [
                {"mutation_type": row.type, "rationale": row.reason, "payload": row.payload}
                for row in preview.proposed_changes
            ],
        )
        return preview

    def apply_change(self, db: Session, trip_id: int, change: ProposedChange) -> AgentExecutionResult:
        trip = _load_trip(db, self.user, trip_id)
        run = self._start_run(db, trip, "apply_change", change.title)
        applied = self._apply_proposed_change(db, trip, run, change)
        if not applied:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported change type.")
        trip, metadata = applied
        assistant_message = f"Apliquei a mudanca '{change.title}' automaticamente."
        run = self._finish_run(db, run, assistant_message, [], [metadata])
        return self._build_result(db, trip, run, [], [metadata], ["Posso continuar refinando o roteiro com novos ajustes."])

    def rollback(self, db: Session, trip_id: int, version_id: int) -> AgentExecutionResult:
        trip = _load_trip(db, self.user, trip_id)
        run = self._start_run(db, trip, "rollback", f"rollback:{version_id}")
        restored = self._tool(
            db,
            run,
            "rollback",
            {"trip_id": trip.id, "version_id": version_id},
            lambda: {"itinerary_id": tool_rollback_to_version(db, trip, version_id, rationale="Rollback requested by the user.", run=run)[0].id},
        )
        trip = _refresh_trip(db, self.user, trip.id)
        active = get_active_itinerary(trip)
        run = self._finish_run(
            db,
            run,
            "Restaurei uma versao anterior do roteiro.",
            [],
            [{"mutation_type": "rollback", "rationale": "Rollback requested by the user.", "itinerary_version_id": restored["itinerary_id"]}],
        )
        return self._build_result(db, trip, run, [], run.applied_changes, ["Posso continuar a partir desta versao restaurada."])

    def search_trip(self, db: Session, trip_id: int) -> AgentExecutionResult:
        trip = _load_trip(db, self.user, trip_id)
        run = self._start_run(db, trip, "search", "Buscar opcoes para esta viagem.")
        def _run_search() -> dict[str, Any]:
            result, search_warnings = tool_search_all(db, trip)
            return {"result": result, "warnings": search_warnings}

        search_payload = self._tool(
            db,
            run,
            "search_all",
            {"trip_id": trip.id},
            _run_search,
        )
        trip = _refresh_trip(db, self.user, trip.id)
        run = self._finish_run(
            db,
            run,
            "Busquei novas opcoes de voo, hospedagem e lugares.",
            search_payload.get("warnings", []),
            [],
        )
        return self._build_result(db, trip, run, run.warnings, [], ["Posso gerar ou replanejar o roteiro usando estas opcoes."])

    def generate(self, db: Session, trip_id: int, intent: str = "generate") -> AgentExecutionResult:
        trip = _load_trip(db, self.user, trip_id)
        run = self._start_run(db, trip, intent, "Gerar roteiro.")
        warnings: list[str] = []
        places = _load_places(db, trip.id)
        if get_planning_blockers(trip, places):
            def _run_search() -> dict[str, Any]:
                result, search_warnings = tool_search_all(db, trip)
                return {"result": result, "warnings": search_warnings}

            search_payload = self._tool(
                db,
                run,
                "search_all",
                {"trip_id": trip.id},
                _run_search,
            )
            warnings.extend(search_payload.get("warnings", []))
            trip = _refresh_trip(db, self.user, trip.id)
            places = _load_places(db, trip.id)

        blockers = get_planning_blockers(trip, places)
        if blockers:
            detail = f"Cannot generate itinerary yet. Missing planning context: {', '.join(blockers)}."
            run = self._finish_run(
                db,
                run,
                _format_planning_blocker_message(blockers),
                list(dict.fromkeys([*warnings, detail])),
                [],
            )
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

        tool_name = "replan_itinerary" if intent == "replan" and get_active_itinerary(trip) else "generate_itinerary"
        generated = self._tool(
            db,
            run,
            tool_name,
            {"trip_id": trip.id},
            lambda: {"itinerary_id": (tool_replan_itinerary if tool_name == "replan_itinerary" else tool_generate_itinerary)(
                db,
                trip,
                run=run,
                rationale="Generated by an agent shortcut action.",
            )[0].id},
        )
        trip = _refresh_trip(db, self.user, trip.id)
        applied_changes = [{"mutation_type": tool_name, "rationale": "Generated by an agent shortcut action.", "itinerary_version_id": generated["itinerary_id"]}]
        run = self._finish_run(
            db,
            run,
            "Gerei um roteiro atualizado para esta viagem.",
            list(dict.fromkeys(warnings)),
            applied_changes,
        )
        return self._build_result(db, trip, run, run.warnings, applied_changes, ["Posso otimizar um dia específico ou reduzir custo com base neste roteiro."])
