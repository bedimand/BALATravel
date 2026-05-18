from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.entities import (
    AgentRun,
    AgentToolCall,
    ItineraryVersion,
    Place,
    Trip,
    User,
    WorkflowRun,
)
from app.services.agent_tools import (
    begin_tool_call,
    fail_tool_call,
    finish_tool_call,
    get_active_itinerary,
    serialize_trip_snapshot,
)
from app.services.llm import LLMIntegrationError, llm_chat
from app.services.tool_registry import ToolRegistry, ToolResult


settings = get_settings()


@dataclass
class BudgetTracker:
    max_steps: int
    max_tokens: int
    current_step: int = 0
    estimated_tokens: int = 0
    consecutive_errors: int = 0

    @property
    def budget_percent(self) -> float:
        step_pct = self.current_step / self.max_steps if self.max_steps > 0 else 0
        token_pct = self.estimated_tokens / self.max_tokens if self.max_tokens > 0 else 0
        return max(step_pct, token_pct)

    @property
    def should_warn(self) -> bool:
        return self.budget_percent >= 0.85

    @property
    def must_stop(self) -> bool:
        return self.budget_percent >= 0.95 or self.consecutive_errors >= 3

    @property
    def steps_remaining(self) -> int:
        return max(0, self.max_steps - self.current_step)


@dataclass
class MindResult:
    success: bool
    assistant_message: str
    applied_changes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    steps_taken: int = 0
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class MindContext:
    trip: Trip
    run: AgentRun | WorkflowRun
    mode: Literal["autonomous", "reactive"]
    user_message: str | None = None
    budget: BudgetTracker = field(default_factory=lambda: BudgetTracker(max_steps=30, max_tokens=150000))
    history: list[dict[str, Any]] = field(default_factory=list)
    applied_changes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_complete: bool = False
    final_message: str = ""
    _recent_calls: list[str] = field(default_factory=list)


class CentralMind:
    def __init__(self, user: User):
        self.user = user
        self.registry = ToolRegistry()

    def plan_trip(self, db: Session, trip: Trip, run: WorkflowRun, log_step_fn) -> None:
        max_steps = getattr(settings, "agent_max_steps_autonomous", 60)
        max_tokens = getattr(settings, "agent_max_token_budget", 150000)

        context = MindContext(
            trip=trip,
            run=run,
            mode="autonomous",
            budget=BudgetTracker(max_steps=max_steps, max_tokens=max_tokens),
        )

        print(f"\n[MIND] Starting autonomous planning for: {trip.destination} (Trip ID: {trip.id})")
        self._run_loop(db, context, log_step_fn)
        print(f"[MIND] Planning complete. Steps taken: {context.budget.current_step}")

    def handle_message(self, db: Session, trip_id: int, message: str) -> MindResult:
        trip = self._load_trip(db, trip_id)
        max_steps = getattr(settings, "agent_max_steps_reactive", 30)
        max_tokens = getattr(settings, "agent_max_token_budget", 150000)

        run = AgentRun(
            trip_id=trip.id,
            intent="message",
            status="running",
            user_message=message,
            model=settings.openai_model or settings.openrouter_model,
            prompt_version="central_mind_v1",
            warnings=[],
            applied_changes=[],
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        context = MindContext(
            trip=trip,
            run=run,
            mode="reactive",
            user_message=message,
            budget=BudgetTracker(max_steps=max_steps, max_tokens=max_tokens),
        )

        self._run_loop(db, context)

        run.status = "completed"
        run.assistant_message = context.final_message
        run.warnings = context.warnings
        run.applied_changes = context.applied_changes
        run.completed_at = datetime.now(UTC)
        db.add(run)
        db.commit()

        return MindResult(
            success=True,
            assistant_message=context.final_message,
            applied_changes=context.applied_changes,
            warnings=context.warnings,
            steps_taken=context.budget.current_step,
            tool_calls_made=[{"tool": h["tool"], "success": h.get("success", True)} for h in context.history],
        )

    def _run_loop(self, db: Session, context: MindContext, log_step_fn=None) -> None:
        while not context.is_complete:
            should_stop, reason = self._should_terminate(context)
            if should_stop:
                print(f"  [TERMINATE] reason={reason}, budget={context.budget.budget_percent:.0%}, errors={context.budget.consecutive_errors}")
                if not context.final_message:
                    context.final_message = reason
                context.is_complete = True
                break

            try:
                decision = self._think(db, context)
            except LLMIntegrationError as exc:
                context.budget.consecutive_errors += 1
                context.warnings.append(f"LLM error: {str(exc)}")
                if log_step_fn:
                    log_step_fn(db, context.run, "llm_error", "failed", str(exc))
                print(f"  [LLM ERROR] {exc}")
                continue

            context.budget.consecutive_errors = 0

            reasoning = decision.get("reasoning", "")
            tool_calls = decision.get("tool_calls", [])

            if log_step_fn and reasoning:
                log_step_fn(db, context.run, "agent_thought", "completed", reasoning[:200])

            if not tool_calls:
                print(f"  [NO TOOLS] LLM returned no tool_calls. Reasoning: {reasoning[:100]}")
                context.budget.current_step += 1
                continue

            for tc in tool_calls:
                tool_name = tc.get("name", "")
                params = tc.get("params", {})

                if tool_name == "finish":
                    if not context.history and context.mode == "reactive":
                        context.history.append({
                            "tool": "finish_rejected",
                            "params": {},
                            "result": {"error": "You must use tools to make changes before finishing. Do NOT claim work is done without calling the appropriate tool."},
                            "success": False,
                        })
                        break
                    if context.mode == "autonomous" and not self._has_finalized_itinerary(context):
                        context.history.append({
                            "tool": "finish_rejected",
                            "params": {},
                            "result": {"error": "You CANNOT finish without completing the itinerary. You must: place_item for each day, then call finalize_itinerary BEFORE calling finish."},
                            "success": False,
                        })
                        if log_step_fn:
                            log_step_fn(db, context.run, "finish_rejected", "failed", "Agent tried to finish without finalize_itinerary")
                        break
                    context.final_message = params.get("message", reasoning)
                    context.is_complete = True
                    if log_step_fn:
                        log_step_fn(db, context.run, "agent_finish", "completed", context.final_message[:200])
                    break

                result = self._execute_tool(db, context, tool_name, params, log_step_fn)
                context.history.append({
                    "tool": tool_name,
                    "params": params,
                    "result": result.data if result.success else {"error": result.error},
                    "success": result.success,
                })

                if result.success and tool_name in ("generate_itinerary", "replan_itinerary", "reorder_day", "update_item", "remove_item", "insert_item", "rollback_version", "start_itinerary", "place_item", "finalize_itinerary"):
                    context.applied_changes.append({
                        "mutation_type": tool_name,
                        "rationale": params.get("rationale", ""),
                        "data": result.data,
                    })
                    self._refresh_trip_in_context(db, context)

                if not result.success:
                    context.budget.consecutive_errors += 1
                else:
                    context.budget.consecutive_errors = 0

            context.budget.current_step += 1

    def _think(self, db: Session, context: MindContext) -> dict[str, Any]:
        system_prompt = self._build_system_prompt(db, context)
        messages = [{"role": "system", "content": system_prompt}]

        if context.mode == "reactive" and context.user_message:
            messages.append({"role": "user", "content": context.user_message})

        if context.history:
            history_text = self._format_history(context)
            messages.append({"role": "user", "content": history_text})
        elif context.mode == "autonomous":
            messages.append({"role": "user", "content": "Begin planning. Reply with JSON only."})

        if context.budget.should_warn:
            messages.append({
                "role": "user",
                "content": f"WARNING: Budget at {context.budget.budget_percent:.0%}. "
                f"Only {context.budget.steps_remaining} steps remain. Wrap up now.",
            })

        raw = llm_chat(prompt=messages, temperature=0.2)
        chars = len(raw) + sum(len(m["content"]) for m in messages)
        context.budget.estimated_tokens += chars // 4

        return self._parse_decision(raw)

    def _execute_tool(
        self,
        db: Session,
        context: MindContext,
        tool_name: str,
        params: dict[str, Any],
        log_step_fn=None,
    ) -> ToolResult:
        if isinstance(context.run, AgentRun):
            call = begin_tool_call(db, context.run, tool_name, params)

        result = self.registry.execute(tool_name, db, context.trip, context.run, params)

        if isinstance(context.run, AgentRun):
            if result.success:
                finish_tool_call(db, call, result.data)
            else:
                fail_tool_call(db, call, result.error or "Unknown error")

        if log_step_fn:
            status_str = "completed" if result.success else "failed"
            summary = f"{tool_name}: {json.dumps(result.data, ensure_ascii=False)[:150]}" if result.success else f"{tool_name} failed: {result.error}"
            log_step_fn(db, context.run, tool_name, status_str, summary, None, params, result.data if result.success else None)

        return result

    def _should_terminate(self, context: MindContext) -> tuple[bool, str]:
        if context.budget.must_stop:
            if context.budget.consecutive_errors >= 3:
                return True, "Encerrado por erros consecutivos. Tente novamente."
            return True, "Orcamento de processamento atingido. Finalizando com o progresso atual."

        if self._detect_loop(context):
            return True, "Loop detectado. Finalizando para evitar repeticao."

        return False, ""

    def _detect_loop(self, context: MindContext) -> bool:
        if len(context.history) < 5:
            return False
        last_5 = [json.dumps({"t": h["tool"], "p": h["params"]}, sort_keys=True) for h in context.history[-5:]]
        return len(set(last_5)) == 1

    def _build_system_prompt(self, db: Session, context: MindContext) -> str:
        trip = context.trip
        places = self._get_places_summary(db, trip.id)
        active = get_active_itinerary(trip)

        interests_str = ", ".join(trip.interests) if hasattr(trip, "interests") and trip.interests else "exploracao geral"
        dietary_str = ", ".join(trip.dietary_restrictions) if hasattr(trip, "dietary_restrictions") and trip.dietary_restrictions else "nenhuma"
        n_days = max((trip.end_date - trip.start_date).days, 1)

        mode_instructions = self._get_mode_instructions(context, active)
        tools_json = json.dumps(self.registry.list_for_llm(), indent=2, ensure_ascii=False)

        return f"""You are the Central Mind of BALATravel — a fully autonomous travel planning intelligence.
You have COMPLETE FREEDOM to decide what to search, when to search, how many searches to perform, and when to stop.
There are NO predefined search sequences. You decide everything.

== MODE ==
{context.mode.upper()}: {mode_instructions}

== TRAVELER PROFILE ==
Destination: {trip.destination}
Dates: {trip.start_date.isoformat()} to {trip.end_date.isoformat()} ({n_days} days)
Budget: {trip.budget} {trip.currency}
Style: {trip.style or "balanced"}
Interests: {interests_str}
Dietary: {dietary_str}
Mobility: {getattr(trip, "mobility_notes", "nenhuma") or "nenhuma"}
Has car: {getattr(trip, "has_car", False)}
Accommodation: {getattr(trip, "accommodation_name", "not set")} ({getattr(trip, "accommodation_lat", "?")}, {getattr(trip, "accommodation_lng", "?")})
Daily schedule: {getattr(trip, "daily_start_time", "09:00")} to {getattr(trip, "daily_end_time", "22:00")}

== CURRENT STATE ==
Places saved: {places["total"]}
Places selected: {places["selected"]}
Active itinerary: {"Yes (version " + str(active.version) + ", " + str(len(active.items)) + " items)" if active else "None"}
{self._format_itinerary_for_prompt(active) if active else ""}

== BUDGET STATUS ==
Step {context.budget.current_step + 1} | Remaining: {context.budget.steps_remaining} | Usage: {context.budget.budget_percent:.0%}

== AVAILABLE TOOLS ==
{tools_json}

== RULES ==
1. Return ONLY valid JSON. No markdown, no explanation outside JSON.
2. You decide what tools to call, in what order, and how many times.
3. Always call "finish" tool when you're done. Include a message in Portuguese for the user.
4. Do NOT repeat the exact same tool call with identical params.
5. For itinerary generation, you MUST have places saved first.
6. Respond to users in Brazilian Portuguese.
7. CRITICAL: You MUST use tools to make changes. You CANNOT claim to have made a change without calling the appropriate tool. If the user asks to remove/update/add something, you MUST call remove_item/update_item/insert_item with the correct item ID from the itinerary above.
8. For "reorder day" or "start later" requests, use the reorder_day tool with the target date.
9. Use the exact item IDs shown in the ACTIVE ITINERARY ITEMS section above.

== OUTPUT FORMAT ==
{{
  "reasoning": "Your brief thought process (1-2 sentences)",
  "tool_calls": [
    {{"name": "tool_name", "params": {{"key": "value"}}}}
  ]
}}

To signal completion:
{{
  "reasoning": "Done.",
  "tool_calls": [{{"name": "finish", "params": {{"message": "Your message to the user in Portuguese"}}}}]
}}"""

    def _format_itinerary_for_prompt(self, active: ItineraryVersion) -> str:
        if not active or not active.items:
            return ""
        lines = ["\n== ACTIVE ITINERARY ITEMS =="]
        from collections import defaultdict
        by_day: dict[str, list] = defaultdict(list)
        for item in active.items:
            by_day[item.date.isoformat()].append(item)
        for day_key in sorted(by_day.keys()):
            lines.append(f"  {day_key}:")
            for item in sorted(by_day[day_key], key=lambda x: x.start_time):
                lines.append(
                    f"    id={item.id} {item.start_time.strftime('%H:%M')}-{item.end_time.strftime('%H:%M')} \"{item.title}\" ({item.item_type})"
                )
        return "\n".join(lines)

    def _get_mode_instructions(self, context: MindContext, active: ItineraryVersion | None) -> str:
        if context.mode == "autonomous":
            return (
                "You ARE the travel planner. Build the entire itinerary yourself using your tools.\n\n"
                "WORKFLOW:\n"
                "1. Search for places (search_places_by_interest — 4-6 diverse queries covering culture, food, beaches, parks, shopping, nightlife)\n"
                "2. Call list_saved_places to see what you have\n"
                "3. Call start_itinerary to create an empty schedule\n"
                "4. Use place_item repeatedly to build the schedule day by day, activity by activity\n"
                "5. Call finalize_itinerary when done\n"
                "6. Call finish\n\n"
                "SCHEDULING RULES:\n"
                "- Cover ALL days of the trip. Every single day must have 4-6 activities.\n"
                "- Morning: cultural sites, museums, parks (09:00-12:00)\n"
                "- Lunch: restaurant (12:00-14:00)\n"
                "- Afternoon: beaches, shopping, landmarks (14:00-18:00)\n"
                "- Dinner: restaurant (19:00-21:00)\n"
                "- Evening (optional): bars, nightlife (21:00+)\n"
                "- NEVER put 2 restaurants back-to-back. Alternate between food and non-food activities.\n"
                "- Max 1 restaurant for lunch + 1 for dinner per day. Fill the rest with non-food activities.\n"
                "- ALWAYS use title + lat + lng when calling place_item. Do NOT use place_id.\n\n"
                "EFFICIENCY:\n"
                "- You can place multiple items in a single tool_calls array (batch them).\n"
                "- Call list_saved_places ONCE. Remember the place IDs — do NOT call it again.\n"
                "- Call start_itinerary ONCE. Do NOT restart it after placing items.\n"
                "- Place ALL days in sequence without pausing to search or list again.\n"
                "- Target: complete the full itinerary in under 40 steps total."
            )
        return (
            f"The user said: \"{context.user_message}\". "
            "Address their request using whatever tools you need. "
            "Prefer local edits (update_item, remove_item) over full replans unless the request is global. "
            f"{'There is an active itinerary you can modify.' if active else 'No itinerary exists yet — you may need to generate one.'}"
        )

    def _get_places_summary(self, db: Session, trip_id: int) -> dict[str, int]:
        places = list(db.scalars(select(Place).where(Place.trip_id == trip_id)))
        return {
            "total": len(places),
            "selected": sum(1 for p in places if p.is_selected),
        }

    def _format_history(self, context: MindContext) -> str:
        if not context.history:
            return ""

        history = context.history
        window_size = 20
        lines = ["Previous steps:"]

        if len(history) > window_size:
            from collections import Counter
            older = history[:-window_size]
            tool_counts = Counter(h["tool"] for h in older)
            summary_parts = [f"{name}(x{count})" for name, count in tool_counts.most_common()]
            lines.append(f"[{len(older)} earlier steps: {', '.join(summary_parts)}]")

        recent = history[-window_size:]
        offset = len(history) - len(recent)
        for i, entry in enumerate(recent):
            result_str = json.dumps(entry["result"], ensure_ascii=False)
            max_len = 500 if entry["tool"] == "list_saved_places" else 200
            if len(result_str) > max_len:
                result_str = result_str[:max_len] + "..."
            status = "OK" if entry.get("success", True) else "FAILED"
            lines.append(f"Step {offset + i + 1}: {entry['tool']}({json.dumps(entry['params'], ensure_ascii=False)[:80]}) -> [{status}] {result_str}")

        lines.append("\nWhat should I do next? Reply with JSON only.")
        return "\n".join(lines)

    def _parse_decision(self, raw: str) -> dict[str, Any]:
        clean = raw.strip()
        if "```json" in clean:
            clean = clean.split("```json", 1)[1]
        elif "```" in clean:
            clean = clean.split("```", 1)[1]
        if "```" in clean:
            clean = clean.rsplit("```", 1)[0]

        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1:
            clean = clean[start:end + 1]

        try:
            return json.loads(clean)
        except (json.JSONDecodeError, ValueError):
            return {"reasoning": raw[:200], "tool_calls": []}

    def _load_trip(self, db: Session, trip_id: int) -> Trip:
        trip = db.scalar(
            select(Trip)
            .where(Trip.id == trip_id, Trip.user_id == self.user.id)
            .options(
                selectinload(Trip.flights),
                selectinload(Trip.hotels),
                selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
                selectinload(Trip.agent_runs),
                selectinload(Trip.plan_mutations),
            )
        )
        if not trip:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
        return trip

    def _has_finalized_itinerary(self, context: MindContext) -> bool:
        return any(
            h["tool"] == "finalize_itinerary" and h.get("success", False)
            for h in context.history
        )

    def _refresh_trip_in_context(self, db: Session, context: MindContext) -> None:
        db.expire_all()
        if isinstance(context.run, AgentRun):
            context.trip = self._load_trip(db, context.trip.id)
        else:
            context.trip = db.scalar(
                select(Trip)
                .where(Trip.id == context.trip.id)
                .options(
                    selectinload(Trip.flights),
                    selectinload(Trip.hotels),
                    selectinload(Trip.places),
                    selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
                    selectinload(Trip.route_estimates),
                )
            )
