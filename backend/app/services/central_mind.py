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

        # Persist agent warnings onto the run so callers can surface them, mirroring
        # handle_message. Without this, autonomous-run warnings are silently dropped.
        # plan_trip is called with either an AgentRun (has `warnings`) or a
        # WorkflowRun (does not) — only persist when the column exists.
        if context.warnings and hasattr(run, "warnings"):
            run.warnings = [*(run.warnings or []), *context.warnings]
            db.add(run)
            db.commit()

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
                    # The agent owns the decision to stop. We trust it: guidance on
                    # when to finalize lives in the system prompt, and the step budget
                    # already bounds the loop. We don't BLOCK the finish, but if an
                    # autonomous run finishes without a finalized itinerary we surface
                    # a non-fatal warning instead of silently shipping an empty plan.
                    if context.mode == "autonomous" and not self._finalized_itinerary(context):
                        context.warnings.append(
                            "O agente finalizou sem chamar finalize_itinerary; o roteiro pode estar incompleto."
                        )
                        if log_step_fn:
                            log_step_fn(db, context.run, "finish_unfinalized", "completed",
                                        "Agent finished without finalize_itinerary")
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

                if result.success and tool_name in ("set_day", "update_item", "remove_item", "insert_item", "rollback_version", "start_itinerary", "place_item", "finalize_itinerary"):
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
        languages_str = ", ".join(trip.languages) if getattr(trip, "languages", None) else "pt"
        age_str = getattr(trip, "age_range", None) or "nao informado"
        sex_str = getattr(trip, "traveler_sex", None) or "nao informado"
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
Age range: {age_str}
Sex: {sex_str}
Spoken languages: {languages_str}
Interests: {interests_str}
Dietary: {dietary_str}
Mobility: {getattr(trip, "mobility_notes", "nenhuma") or "nenhuma"}
Has car: {getattr(trip, "has_car", False)}
Accommodation: {getattr(trip, "accommodation_name", "not set")} ({getattr(trip, "accommodation_lat", "?")}, {getattr(trip, "accommodation_lng", "?")})
Daily schedule: {getattr(trip, "daily_start_time", "09:00")} to {getattr(trip, "daily_end_time", "22:00")}

Use this profile to tailor every choice: match activities and venues to the traveler's age, interests and pace; prefer places that accommodate the spoken languages; respect dietary and mobility constraints when picking restaurants and routes.

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
8. To reorganize a whole day (reorder, start later, make the afternoon lighter, swap activities), call set_day with the FULL ordered list of items you want for that day — you decide the order and times; the tool just saves and validates them.
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

            pace = (getattr(context.trip, "travel_pace", None) or "balanced").strip().lower()
            if pace in ("leve", "relaxed", "relaxado", "tranquilo"):
                pace_guidance = "Traveler prefers a RELAXED pace. Cap at 4 activities per day. Leave long gaps for spontaneous exploration."
            elif pace in ("intenso", "intensive", "fast", "rapido"):
                pace_guidance = "Traveler wants an INTENSIVE pace. Schedule 6-7 activities per day. Maximize coverage."
            else:
                pace_guidance = "Traveler has a BALANCED pace. Target 5 activities per day."

            return (
                "You ARE the travel planner. Build a complete, realistic, day-by-day itinerary that a real person can follow.\n"
                "You have full freedom over what to search, what goes where, the order, and the times. There is NO fixed\n"
                "sequence of steps to follow — gather and arrange in whatever order makes the best plan, and keep iterating\n"
                "until it is genuinely good. Cost is not a concern; thoroughness is.\n"
                f"{replan_hint}\n\n"
                "== FORAGE FREELY (search is not a one-time phase) ==\n"
                "- Search whenever it helps, as many times as you like. Use descriptive, specific queries.\n"
                "- Be CONTEXT-AWARE: when you place or consider a notable venue (a famous mall, a market, a landmark),\n"
                "  search again for what is INSIDE or AROUND it — pass that venue's lat/lng as center_lat/center_lng to\n"
                "  search_places. E.g. after placing a big shopping mall, search 'restaurants inside <mall>' centered on\n"
                "  its coordinates to find a great lunch spot right there.\n"
                "- Re-search any time a day looks thin, repetitive, or food-heavy, or when you lack a strong anchor\n"
                "  (a museum, landmark, park, or beach) for a day or a neighborhood.\n"
                "- search_places returns the places it found with their coordinates — reuse those directly.\n\n"
                f"== PACE ==\n{pace_guidance}\n\n"
                "== WHAT A GOOD DAY LOOKS LIKE (principles, not a rigid template) ==\n"
                "- Has a real ANCHOR: at least one cultural site or outdoor highlight (museum, landmark, historic site,\n"
                "  park, beach, viewpoint). A day of only food and shopping is NOT acceptable.\n"
                "- Has lunch (a restaurant around 12:00-14:00) and dinner (around 19:00-21:30). Never skip either.\n"
                "- Varied rhythm: don't stack restaurants/cafés back-to-back, and don't chain the same category.\n"
                "- Geographically tight: focus each day on one area/neighborhood; keep hops between stops short.\n"
                "  Day 1 nearest the accommodation, later days expanding outward.\n"
                "- Continuous: no long dead gaps — fill from morning through dinner.\n"
                "- Respects opening hours (no museum at 21:00, no bar at 09:00) and weather (outdoor on dry days).\n"
                "- Never repeats a place used on another day. Covers every trip day, start_date to end_date inclusive.\n\n"
                "== DURATIONS (you decide) ==\n"
                "You determine how long each activity takes. Guidelines:\n"
                "  Squares, viewpoints, bridges: 30-45min | Restaurants: 60-90min | Bars: 90-120min\n"
                "  Small museums, galleries, churches: 45-75min | Large museums, cultural centers: 90-120min\n"
                "  Parks, beaches: 60-150min | Markets, shopping: 60-90min\n"
                "Use your knowledge of the specific place: a world-famous museum deserves more time than a local gallery.\n\n"
                "== REVIEW AND ITERATE (mandatory before finishing) ==\n"
                "1. Build the days (place_item per day, or set_day for a full day). get_day_schedule shows you a day's\n"
                "   inline quality report as you go.\n"
                "2. Call review_itinerary. It returns, per day, the timeline and a list of issues tagged 'blocking' or\n"
                "   'warning', plus the trip-wide blocking_count.\n"
                "3. READ every issue in the report (the full list is given to you). For each blocking issue, fix it:\n"
                "   search for a missing anchor, add the missing lunch/dinner, swap a repeated venue, or rebalance the\n"
                "   whole day with set_day. Then call review_itinerary again.\n"
                "4. Repeat until blocking_count is 0, then call finalize_itinerary.\n"
                "   YOU are the final judge. If after reviewing an issue you genuinely believe it's fine for THIS trip\n"
                "   (e.g. reusing one excellent restaurant, or a deliberately lighter day), don't thrash against it —\n"
                "   call finalize_itinerary with override=true and override_reason explaining why. Use override only for\n"
                "   issues you've actually considered, not to skip real fixes. Address warnings too when reasonable.\n\n"
                "== PRACTICAL NOTES ==\n"
                "- ALWAYS provide title + lat + lng when calling place_item (use coordinates from your searches).\n"
                "- You can batch a whole day of place_item calls in one tool_calls array.\n"
                "- If a tool errors, read the error, adapt, and move on — don't repeat the identical failing call."
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
            # review_itinerary / get_day_schedule carry the full list of mistakes the
            # agent must read to fix the plan — NEVER truncate them, or the agent loops
            # blindly re-asking for a report it can't see. Other big results get a cap.
            if entry["tool"] in ("review_itinerary", "get_day_schedule"):
                max_len = None
            elif entry["tool"] in ("list_saved_places", "get_day_context"):
                max_len = 1500
            else:
                max_len = 300
            if max_len is not None and len(result_str) > max_len:
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
                selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
                selectinload(Trip.agent_runs),
                selectinload(Trip.plan_mutations),
            )
        )
        if not trip:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
        return trip

    def _finalized_itinerary(self, context: MindContext) -> bool:
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
                    selectinload(Trip.places),
                    selectinload(Trip.itinerary_versions).selectinload(ItineraryVersion.items),
                    selectinload(Trip.route_estimates),
                )
            )
