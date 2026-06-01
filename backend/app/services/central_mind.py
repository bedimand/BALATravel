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

                if result.success and tool_name in ("reorder_day", "update_item", "remove_item", "insert_item", "rollback_version", "start_itinerary", "place_item", "finalize_itinerary"):
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
        n_days = max((trip.end_date - trip.start_date).days + 1, 1)

        mode_instructions = self._get_mode_instructions(db, context, active)
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
        from collections import defaultdict
        by_day: dict[str, list] = defaultdict(list)
        for item in active.items:
            by_day[item.date.isoformat()].append(item)

        all_days = sorted(by_day.keys())
        MAX_DETAIL_DAYS = 10

        if len(all_days) <= MAX_DETAIL_DAYS:
            detail_days = set(all_days)
        else:
            days_by_priority = sorted(all_days, key=lambda d: (len(by_day[d]), d))
            detail_days = set(days_by_priority[:MAX_DETAIL_DAYS])

        lines = ["\n== ACTIVE ITINERARY ITEMS =="]
        for day_key in all_days:
            if day_key in detail_days:
                lines.append(f"  {day_key}:")
                for item in sorted(by_day[day_key], key=lambda x: x.start_time):
                    lines.append(
                        f"    id={item.id} {item.start_time.strftime('%H:%M')}-{item.end_time.strftime('%H:%M')} \"{item.title}\" ({item.item_type})"
                    )
            else:
                lines.append(f"  {day_key}: {len(by_day[day_key])} items (summarized)")
        return "\n".join(lines)

    def _get_mode_instructions(self, db: Session, context: MindContext, active: ItineraryVersion | None) -> str:
        if context.mode == "autonomous":
            places_summary = self._get_places_summary(db, context.trip.id)
            has_places = places_summary["total"] > 0

            replan_hint = ""
            if has_places:
                replan_hint = (
                    f"\nNOTE: {places_summary['total']} places are already saved for this trip. "
                    "You may skip searching and go directly to list_saved_places if the existing pool is adequate. "
                    "Only re-search if you believe the pool lacks diversity or doesn't cover the trip duration well."
                )

            pace = getattr(context.trip, "travel_pace", None) or "balanced"
            if pace == "relaxed":
                pace_guidance = "Traveler prefers a RELAXED pace. Cap at 4 activities per day. Leave long gaps for spontaneous exploration."
            elif pace in ("intensive", "fast"):
                pace_guidance = "Traveler wants an INTENSIVE pace. Schedule 6-7 activities per day. Maximize coverage."
            else:
                pace_guidance = "Traveler has a BALANCED pace. Target 5 activities per day."

            return (
                "You ARE the travel planner. Build a complete, realistic, day-by-day itinerary that a real person can follow.\n"
                f"{replan_hint}\n\n"
                "== WORKFLOW ==\n"
                "1. Search for places (search_places_by_interest — 4-6 diverse queries)\n"
                "2. Call list_saved_places ONCE to review all options\n"
                "3. Call get_weather_forecast\n"
                "4. Call start_itinerary\n"
                "5. For EACH day: call get_day_context, then place ALL items for that day in one batch\n"
                "6. Call get_day_schedule for each day to self-check, fix any issues\n"
                "7. Call finalize_itinerary, then finish\n\n"
                f"== PACE ==\n{pace_guidance}\n\n"
                "== DAILY STRUCTURE (mandatory) ==\n"
                "Every single day MUST follow this skeleton. Fill each slot:\n\n"
                "  MORNING (09:00-12:00): 2-3 activities\n"
                "    Cultural sites, museums, parks, historic landmarks.\n"
                "    Start from accommodation, move to the day's main area.\n\n"
                "  LUNCH (12:30-14:00): 1 restaurant\n"
                "    Choose one NEAR the morning cluster. Never skip lunch.\n\n"
                "  AFTERNOON (14:30-18:00): 2-3 activities\n"
                "    Markets, shopping, lighter attractions, churches, scenic walks.\n"
                "    Stay in the same geographic zone when possible.\n\n"
                "  DINNER (19:30-21:30): 1 restaurant\n"
                "    Choose based on evening location or near hotel. Never skip dinner.\n\n"
                "  OPTIONAL EVENING (21:30+): bar, show, or nightlife if the traveler's style fits.\n\n"
                "This means each day has 6-8 items minimum: morning activities + lunch + afternoon activities + dinner.\n"
                "If a day has fewer than 6 items or is missing lunch/dinner, it is INCOMPLETE.\n\n"
                "== GEOGRAPHIC LOGIC ==\n"
                "- Each day should focus on ONE area/neighborhood of the city.\n"
                "- Pick a cluster of nearby places and fill the day from them.\n"
                "- Travel between consecutive items should be <20min. If you see >20min in the response, you're zigzagging.\n"
                "- Day 1: closest area to hotel. Day 2+: expand outward to other neighborhoods.\n\n"
                "== DURATIONS (you decide) ==\n"
                "You determine how long each activity takes. Guidelines:\n"
                "  Squares, viewpoints, bridges: 30-45min\n"
                "  Restaurants: 60-90min\n"
                "  Small museums, galleries, churches: 45-75min\n"
                "  Large museums, cultural centers: 90-120min\n"
                "  Parks, beaches: 60-150min\n"
                "  Markets, shopping: 60-90min\n"
                "  Bars: 90-120min\n"
                "Use your knowledge of the specific place. A world-famous museum deserves more time than a local gallery.\n\n"
                "== HARD RULES ==\n"
                "- EVERY day must have lunch AND dinner. No exceptions.\n"
                "- NEVER repeat the same place on different days.\n"
                "- NEVER place two restaurants back-to-back.\n"
                "- NEVER place two activities of the same category back-to-back (e.g. two museums in a row, two shops in a row).\n"
                "- NEVER leave gaps >1h between activities. Fill 09:00 through dinner continuously.\n"
                "  If last afternoon activity ends at 17:00 and dinner is at 19:30, you MUST add something between (a walk, a bar, a viewpoint, a park).\n"
                "- Activities must respect opening hours (no museum at 21:00, no bar at 09:00).\n"
                "- Outdoor activities avoid rainy forecast days.\n"
                "- ALL trip days must be covered. The trip has days from start_date to end_date INCLUSIVE.\n\n"
                "== SELF-CHECK (before finalize) ==\n"
                "Call get_day_schedule for each day. For each day verify:\n"
                "  1. Has lunch? (one restaurant between 12:00-14:30)\n"
                "  2. Has dinner? (one restaurant between 19:00-22:00)\n"
                "  3. No gap >1h between any two consecutive items? (check end_time vs next start_time)\n"
                "  4. No two consecutive items of the same category?\n"
                "  5. No repeated places from other days?\n"
                "  6. All trip days have activities? (start_date to end_date inclusive)\n"
                "If ANY check fails: FIX IT before calling finalize.\n\n"
                "== EFFICIENCY ==\n"
                "- Batch an ENTIRE DAY of place_item calls in one tool_calls array.\n"
                "- Call list_saved_places ONCE. Remember the data.\n"
                "- Call get_day_context at most ONCE per day.\n"
                "- NEVER repeat a tool call that already succeeded.\n"
                "- Target: complete everything in under 25 steps.\n"
                "- ALWAYS provide title + lat + lng when calling place_item.\n"
                "- If a tool errors, adapt and move on. Do not retry endlessly."
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
            max_len = 1500 if entry["tool"] in ("list_saved_places", "get_day_context") else 300
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
