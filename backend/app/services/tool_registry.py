from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import AgentRun, Place, Trip, WorkflowRun


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    category: str
    cost_estimate: str = "low"


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._register_all()

    @property
    def tools(self) -> dict[str, ToolDefinition]:
        return self._tools

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_for_llm(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "cost": tool.cost_estimate,
            }
            for tool in self._tools.values()
        ]

    def execute(
        self,
        name: str,
        db: Session,
        trip: Trip,
        run: AgentRun | WorkflowRun,
        params: dict[str, Any],
    ) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(tool_name=name, success=False, error=f"Unknown tool: {name}")
        try:
            result = tool.handler(db=db, trip=trip, run=run, params=params)
            if isinstance(result, dict) and "error" in result:
                return ToolResult(tool_name=name, success=False, data=result, error=result["error"])
            return ToolResult(tool_name=name, success=True, data=result if isinstance(result, dict) else {"result": result})
        except Exception as exc:
            return ToolResult(tool_name=name, success=False, error=str(exc))

    def _register_all(self) -> None:
        self._register_search_tools()
        self._register_intelligence_tools()
        self._register_place_tools()
        self._register_itinerary_tools()
        self._register_scheduling_tools()
        self._register_context_tools()
        self._register_control_tools()

    def _register_search_tools(self) -> None:
        self._tools["search_places"] = ToolDefinition(
            name="search_places",
            description=(
                "Search Google Maps for places matching a query string. Use descriptive, "
                "human-friendly queries (e.g., 'best museums in Paris', 'nightlife bars cocktails'). "
                "Call this multiple times with different queries to build a diverse pool — "
                "results accumulate (new places are added, existing ones kept)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Descriptive search query for places"},
                    "max_results": {"type": "integer", "description": "Max results to return (default 20)", "default": 20},
                    "center_lat": {"type": "number", "description": "Optional latitude to bias search near a point"},
                    "center_lng": {"type": "number", "description": "Optional longitude to bias search near a point"},
                },
                "required": ["query"],
            },
            handler=_handle_search_places,
            category="search",
            cost_estimate="medium",
        )

    def _register_intelligence_tools(self) -> None:
        self._tools["get_weather_forecast"] = ToolDefinition(
            name="get_weather_forecast",
            description=(
                "Fetch weather forecasts for the trip dates at the destination. "
                "Useful for deciding whether to schedule outdoor activities on specific days."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_handle_get_weather,
            category="intelligence",
            cost_estimate="low",
        )

        self._tools["estimate_route"] = ToolDefinition(
            name="estimate_route",
            description=(
                "Estimate travel time and distance between two coordinates. "
                "Useful for checking logistics before scheduling activities."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "origin_lat": {"type": "number", "description": "Origin latitude"},
                    "origin_lng": {"type": "number", "description": "Origin longitude"},
                    "dest_lat": {"type": "number", "description": "Destination latitude"},
                    "dest_lng": {"type": "number", "description": "Destination longitude"},
                },
                "required": ["origin_lat", "origin_lng", "dest_lat", "dest_lng"],
            },
            handler=_handle_estimate_route,
            category="intelligence",
            cost_estimate="low",
        )

    def _register_place_tools(self) -> None:
        self._tools["list_saved_places"] = ToolDefinition(
            name="list_saved_places",
            description=(
                "List all places currently saved for this trip with their names, ratings, "
                "categories, and selection status."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_handle_list_places,
            category="place_management",
            cost_estimate="low",
        )

    def _register_itinerary_tools(self) -> None:
        self._tools["set_day"] = ToolDefinition(
            name="set_day",
            description=(
                "Replace an entire day's schedule with the exact plan YOU decide. "
                "You choose the order, the times, and which activities to keep, move, add, or drop "
                "— this tool does not reorder or reschedule anything for you. Pass the full ordered "
                "list of items for that day. Times must not overlap. Use this for any 'reorganize the day', "
                "'make the afternoon lighter', 'start later', or 'swap activities' request. "
                "The tool recomputes travel time between consecutive stops automatically."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date (YYYY-MM-DD) of the day to set"},
                    "items": {
                        "type": "array",
                        "description": "The complete ordered list of activities for this day.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "start_time": {"type": "string", "description": "HH:MM"},
                                "end_time": {"type": "string", "description": "HH:MM"},
                                "item_type": {"type": "string", "description": "E.g. 'restaurant', 'museum', 'attraction'"},
                                "lat": {"type": "number"},
                                "lng": {"type": "number"},
                                "notes": {"type": "string"},
                                "place_ref": {"type": "string"},
                            },
                            "required": ["title", "start_time", "end_time"],
                        },
                    },
                    "rationale": {"type": "string", "description": "Why you're setting the day this way"},
                },
                "required": ["date", "items"],
            },
            handler=_handle_set_day,
            category="itinerary",
            cost_estimate="medium",
        )

        self._tools["update_item"] = ToolDefinition(
            name="update_item",
            description=(
                "Update a specific itinerary item (change title, time, or notes). "
                "Use for targeted local edits."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "ID of the itinerary item to update"},
                    "updates": {
                        "type": "object",
                        "description": "Fields to update: title, notes, start_time, end_time",
                        "properties": {
                            "title": {"type": "string"},
                            "notes": {"type": "string"},
                            "start_time": {"type": "string", "description": "HH:MM:SS format"},
                            "end_time": {"type": "string", "description": "HH:MM:SS format"},
                        },
                    },
                    "rationale": {"type": "string"},
                },
                "required": ["item_id", "updates"],
            },
            handler=_handle_update_item,
            category="itinerary",
            cost_estimate="low",
        )

        self._tools["remove_item"] = ToolDefinition(
            name="remove_item",
            description="Remove an activity from the itinerary by its item ID.",
            parameters={
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "ID of the item to remove"},
                    "rationale": {"type": "string", "description": "Why removing this item"},
                },
                "required": ["item_id"],
            },
            handler=_handle_remove_item,
            category="itinerary",
            cost_estimate="low",
        )

        self._tools["insert_item"] = ToolDefinition(
            name="insert_item",
            description=(
                "Insert a new activity into the itinerary. Provide date, time, title, and optional coordinates."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                    "start_time": {"type": "string", "description": "HH:MM:SS"},
                    "end_time": {"type": "string", "description": "HH:MM:SS"},
                    "title": {"type": "string"},
                    "item_type": {"type": "string", "description": "E.g. 'attraction', 'restaurant', 'custom'"},
                    "lat": {"type": "number"},
                    "lng": {"type": "number"},
                    "notes": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["date", "title"],
            },
            handler=_handle_insert_item,
            category="itinerary",
            cost_estimate="low",
        )

        self._tools["rollback_version"] = ToolDefinition(
            name="rollback_version",
            description="Restore a previous itinerary version by its ID.",
            parameters={
                "type": "object",
                "properties": {
                    "version_id": {"type": "integer", "description": "Itinerary version ID to restore"},
                    "rationale": {"type": "string"},
                },
                "required": ["version_id"],
            },
            handler=_handle_rollback,
            category="itinerary",
            cost_estimate="low",
        )

    def _register_scheduling_tools(self) -> None:
        self._tools["start_itinerary"] = ToolDefinition(
            name="start_itinerary",
            description=(
                "Create a new empty itinerary version for this trip. Must be called once before "
                "placing items. Archives any previous active version. Returns the new version ID."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_handle_start_itinerary,
            category="scheduling",
            cost_estimate="low",
        )

        self._tools["place_item"] = ToolDefinition(
            name="place_item",
            description=(
                "Place an activity at a specific date and time in the current itinerary. "
                "Use place_id to reference a saved place, OR provide title+lat+lng for custom items. "
                "Travel time is computed from the origin you give in from_lat/from_lng; if you omit it, "
                "it defaults to the previous item that day, else the accommodation. "
                "Validates no time conflicts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "place_id": {"type": "integer", "description": "ID of a saved place (from list_saved_places)"},
                    "title": {"type": "string", "description": "Activity title (used if no place_id)"},
                    "item_type": {"type": "string", "description": "E.g. 'museum', 'restaurant', 'landmark', 'park'"},
                    "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                    "start_time": {"type": "string", "description": "HH:MM (24h format)"},
                    "end_time": {"type": "string", "description": "HH:MM (24h format)"},
                    "lat": {"type": "number", "description": "Latitude (used if no place_id)"},
                    "lng": {"type": "number", "description": "Longitude (used if no place_id)"},
                    "from_lat": {"type": "number", "description": "Optional: latitude to measure travel time from (you decide the origin)"},
                    "from_lng": {"type": "number", "description": "Optional: longitude to measure travel time from"},
                    "notes": {"type": "string", "description": "Optional notes or reasoning"},
                },
                "required": ["date", "start_time", "end_time"],
            },
            handler=_handle_place_item,
            category="scheduling",
            cost_estimate="medium",
        )

        self._tools["check_route"] = ToolDefinition(
            name="check_route",
            description=(
                "Check travel time and distance between two points. Use place IDs or coordinates. "
                "Call before placing to evaluate logistics. Returns duration_min and distance_km."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "from_place_id": {"type": "integer", "description": "Origin place ID"},
                    "from_lat": {"type": "number", "description": "Origin latitude (if no place ID)"},
                    "from_lng": {"type": "number", "description": "Origin longitude (if no place ID)"},
                    "to_place_id": {"type": "integer", "description": "Destination place ID"},
                    "to_lat": {"type": "number", "description": "Destination latitude (if no place ID)"},
                    "to_lng": {"type": "number", "description": "Destination longitude (if no place ID)"},
                },
                "required": [],
            },
            handler=_handle_check_route,
            category="scheduling",
            cost_estimate="low",
        )

        self._tools["get_day_schedule"] = ToolDefinition(
            name="get_day_schedule",
            description=(
                "View all items already placed on a specific day in the current itinerary. "
                "Returns the list with times, titles, and coordinates."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                },
                "required": ["date"],
            },
            handler=_handle_get_day_schedule,
            category="scheduling",
            cost_estimate="low",
        )

        self._tools["get_day_context"] = ToolDefinition(
            name="get_day_context",
            description=(
                "Get full context for planning a specific day: weather, items already placed, "
                "starting coordinates, and remaining unplaced places sorted by distance. "
                "Call this before scheduling each day to make informed decisions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date YYYY-MM-DD to plan for"},
                },
                "required": ["date"],
            },
            handler=_handle_get_day_context,
            category="scheduling",
            cost_estimate="low",
        )

        self._tools["review_itinerary"] = ToolDefinition(
            name="review_itinerary",
            description=(
                "Review the WHOLE current itinerary against objective quality checks. Returns, for every "
                "trip day, the timeline, activity-type counts, travel/gap stats, and a list of issues "
                "tagged 'blocking' or 'warning'. Use this as your mirror: call it before finalizing, fix "
                "every blocking issue (search for an anchor, swap a venue, add lunch/dinner, rebalance with "
                "set_day), then review again. By default finalize_itinerary refuses a plan that still has "
                "blocking issues — but if YOU judge a flagged issue is actually fine for this trip, you can "
                "finalize anyway with override=true and a reason."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_handle_review_itinerary,
            category="scheduling",
            cost_estimate="low",
        )

        self._tools["finalize_itinerary"] = ToolDefinition(
            name="finalize_itinerary",
            description=(
                "Mark the current itinerary as complete. Generates a summary and records the mutation. "
                "Call after all items have been placed. By default this refuses while any blocking issue "
                "remains and returns the full list — fix them and try again. If you have reviewed a blocking "
                "issue and judge it acceptable for this specific trip (e.g. reusing one great venue, or a day "
                "the traveler wants lighter), pass override=true with override_reason to finalize anyway; the "
                "remaining issues are then recorded as warnings on the plan."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Brief summary of the itinerary in Portuguese"},
                    "override": {"type": "boolean", "description": "Set true to finalize despite remaining blocking issues, when you judge them acceptable."},
                    "override_reason": {"type": "string", "description": "Required if override=true: why the flagged issues are acceptable for this trip."},
                },
                "required": [],
            },
            handler=_handle_finalize_itinerary,
            category="scheduling",
            cost_estimate="medium",
        )

    def _register_context_tools(self) -> None:
        self._tools["get_trip_snapshot"] = ToolDefinition(
            name="get_trip_snapshot",
            description=(
                "Get a full snapshot of the current trip state: destination, dates, budget, "
                "place count, active itinerary summary. Use to orient yourself."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_handle_get_trip_snapshot,
            category="context",
            cost_estimate="low",
        )

        self._tools["list_current_options"] = ToolDefinition(
            name="list_current_options",
            description="Get a count summary of the places available for this trip.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_handle_list_options,
            category="context",
            cost_estimate="low",
        )

    def _register_control_tools(self) -> None:
        self._tools["finish"] = ToolDefinition(
            name="finish",
            description=(
                "Signal that you are done with the current task. In autonomous mode, call this "
                "after generating the itinerary. In reactive mode, call this after addressing "
                "the user's request. Include your final message to the user."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Final message to show the user (in Portuguese)"},
                },
                "required": ["message"],
            },
            handler=_handle_finish,
            category="control",
            cost_estimate="low",
        )


# --- Tool handler implementations ---


def _handle_search_places(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.providers import get_travel_provider

    provider = get_travel_provider()
    query = params.get("query", "")
    if not query:
        return {"error": "Query parameter is required"}

    results = provider.search_places_by_interest(
        trip,
        query,
        max_results=params.get("max_results", 20),
        center_lat=params.get("center_lat"),
        center_lng=params.get("center_lng"),
    )

    added = 0
    if results:
        existing_ids = {
            row.external_id
            for row in db.scalars(select(Place).where(Place.trip_id == trip.id))
        }
        new_places = []
        for p in results:
            if p.get("external_id") not in existing_ids:
                new_places.append(Place(trip_id=trip.id, **p))
        if new_places:
            db.add_all(new_places)
            db.commit()
            added = len(new_places)

    # Return the actual places found (not just a count + top-5), so the agent can
    # immediately decide and — crucially — reuse a venue's lat/lng as center_lat/
    # center_lng for an anchored follow-up search (e.g. restaurants inside a mall)
    # without a separate list_saved_places round-trip.
    return {
        "count": len(results),
        "added": added,
        "query": query,
        "results": [
            {
                "name": r.get("name"),
                "category": r.get("category"),
                "rating": r.get("rating", 0),
                "lat": r.get("lat"),
                "lng": r.get("lng"),
                "address": r.get("address_full"),
            }
            for r in results
        ],
    }


def _handle_get_weather(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.weather import WeatherIntegrationError, refresh_trip_weather

    places = list(db.scalars(select(Place).where(Place.trip_id == trip.id).limit(1)))
    try:
        snapshots = refresh_trip_weather(db, trip, places)
        return {
            "source": "openweather_api",
            "days_forecasted": len(snapshots),
            "summary": [
                {"date": s.forecast_date.isoformat(), "condition": s.condition_label, "temp_min": s.temp_min_c, "temp_max": s.temp_max_c, "rain_probability": s.rain_probability, "outdoor_risky": s.is_outdoor_risky}
                for s in snapshots[:7]
            ],
        }
    except WeatherIntegrationError:
        month = trip.start_date.strftime("%B")
        return {
            "source": "unavailable",
            "fallback_instruction": (
                f"Weather API cannot provide forecast for these dates. "
                f"Use your knowledge of typical weather in {trip.destination} during {month}. "
                f"Consider: is it rainy season? Hot or cold? Windy? "
                f"Schedule outdoor activities on days you estimate will be safe, "
                f"and avoid outdoor-heavy days if the region typically has rain in {month}."
            ),
            "destination": trip.destination,
            "month": month,
        }


def _handle_estimate_route(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.routing import RoutingIntegrationError, estimate_route

    origin = (params["origin_lat"], params["origin_lng"])
    dest = (params["dest_lat"], params["dest_lng"])
    try:
        result = estimate_route(db, trip, origin, dest)
        return {"duration_min": result.duration_min, "distance_km": result.distance_km, "source": result.source}
    except RoutingIntegrationError as exc:
        return {"error": str(exc)}


def _format_opening_hours(hours_json: dict[str, Any]) -> dict[str, str]:
    result = {}
    for day, windows in hours_json.items():
        if windows:
            result[day] = ", ".join(windows) if isinstance(windows, list) else str(windows)
    return result


def _handle_list_places(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    places = list(db.scalars(select(Place).where(Place.trip_id == trip.id)))
    return {
        "total": len(places),
        "selected_count": sum(1 for p in places if p.is_selected),
        "places": [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "rating": p.rating,
                "is_selected": p.is_selected,
                "lat": p.lat,
                "lng": p.lng,
                "opening_hours": _format_opening_hours(p.opening_hours_json) if p.opening_hours_json else None,
                "neighborhood": p.neighborhood,
                "price_level": p.price_level,
                "summary": (p.summary[:80] + "...") if p.summary and len(p.summary) > 80 else p.summary,
            }
            for p in places
        ],
    }




def _handle_set_day(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.agent_tools import tool_set_day

    date_text = params.get("date", "")
    items = params.get("items", [])
    rationale = params.get("rationale", "Day set by central mind agent.")
    agent_run = run if isinstance(run, AgentRun) else None
    itinerary, mutation = tool_set_day(db, trip, date_text, items, rationale, run=agent_run)
    return {
        "itinerary_id": itinerary.id,
        "date": date_text,
        "item_count": len(mutation.changed_item_ids),
    }


def _handle_update_item(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.agent_tools import tool_update_item

    item_id = int(params["item_id"])
    updates = params.get("updates", {})
    rationale = params.get("rationale", "Updated by central mind agent.")
    agent_run = run if isinstance(run, AgentRun) else None
    itinerary, mutation = tool_update_item(db, trip, item_id, updates, rationale, run=agent_run)
    return {"itinerary_id": itinerary.id, "item_id": item_id}


def _handle_remove_item(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.agent_tools import tool_remove_item

    item_id = int(params["item_id"])
    rationale = params.get("rationale", "Removed by central mind agent.")
    agent_run = run if isinstance(run, AgentRun) else None
    itinerary, mutation = tool_remove_item(db, trip, item_id, rationale, run=agent_run)
    return {"itinerary_id": itinerary.id, "item_id": item_id}


def _handle_insert_item(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.agent_tools import tool_insert_item

    rationale = params.get("rationale", "Inserted by central mind agent.")
    payload = {k: v for k, v in params.items() if k != "rationale"}
    agent_run = run if isinstance(run, AgentRun) else None
    itinerary, mutation = tool_insert_item(db, trip, payload, rationale, run=agent_run)
    return {"itinerary_id": itinerary.id}


def _handle_rollback(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.agent_tools import tool_rollback_to_version

    version_id = int(params["version_id"])
    rationale = params.get("rationale", "Rollback by central mind agent.")
    agent_run = run if isinstance(run, AgentRun) else None
    itinerary, mutation = tool_rollback_to_version(db, trip, version_id, rationale, run=agent_run)
    return {"itinerary_id": itinerary.id, "restored_version": version_id}


def _handle_get_trip_snapshot(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.agent_tools import serialize_trip_snapshot

    places = list(db.scalars(select(Place).where(Place.trip_id == trip.id).order_by(Place.rating.desc())))
    return serialize_trip_snapshot(trip, places)


def _handle_list_options(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.agent_tools import tool_list_current_options

    return tool_list_current_options(db, trip)


def _handle_start_itinerary(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.models.entities import ItineraryVersion, PlanMutation

    active = next((v for v in trip.itinerary_versions if v.status == "active"), None)
    if active and active.items:
        return {"error": f"An active itinerary (v{active.version}) already has {len(active.items)} items. Use place_item to add more, or call finalize_itinerary when done. Do NOT restart."}

    for version in trip.itinerary_versions:
        if version.status == "active":
            version.status = "archived"
            db.add(version)

    next_version = max((v.version for v in trip.itinerary_versions), default=0) + 1
    itinerary = ItineraryVersion(
        trip_id=trip.id,
        version=next_version,
        status="active",
        total_estimated_cost=0,
        assistant_summary="",
        warnings=[],
    )
    db.add(itinerary)
    db.commit()
    db.refresh(itinerary)
    return {"itinerary_id": itinerary.id, "version": itinerary.version}


def _handle_place_item(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from datetime import date as date_type, time as time_type
    from app.models.entities import ItineraryItem, ItineraryVersion
    from app.services.routing import estimate_route, RoutingIntegrationError

    active = next((v for v in reversed(trip.itinerary_versions) if v.status == "active"), None)
    if not active:
        return {"error": "No active itinerary. Call start_itinerary first."}

    place_id = params.get("place_id")
    title = params.get("title", "Atividade")
    item_type = params.get("item_type", "custom")
    lat = params.get("lat")
    lng = params.get("lng")
    place_ref = None

    if place_id:
        place = db.scalar(select(Place).where(Place.id == place_id, Place.trip_id == trip.id))
        if not place:
            return {"error": f"Place ID {place_id} not found for this trip."}
        title = place.name
        item_type = place.category or "attraction"
        lat = place.lat
        lng = place.lng
        place_ref = place.external_id

    date_str = params.get("date", "")
    start_str = params.get("start_time", "09:00")
    end_str = params.get("end_time", "11:00")

    try:
        parts = date_str.split("-")
        item_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return {"error": f"Invalid date format: {date_str}. Use YYYY-MM-DD."}

    try:
        st_parts = start_str.replace(":", " ").split()
        start_time = time_type(int(st_parts[0]), int(st_parts[1]))
        et_parts = end_str.replace(":", " ").split()
        end_time = time_type(int(et_parts[0]), int(et_parts[1]))
    except (ValueError, IndexError):
        return {"error": f"Invalid time format. Use HH:MM."}

    if end_time <= start_time:
        return {"error": "end_time must be after start_time."}

    for existing in active.items:
        if existing.date != item_date:
            continue
        if not (end_time <= existing.start_time or start_time >= existing.end_time):
            return {"error": f"Time conflict with '{existing.title}' ({existing.start_time.strftime('%H:%M')}-{existing.end_time.strftime('%H:%M')})."}

    travel_time_min = 0
    travel_distance_km = 0.0
    if lat and lng:
        # Origin priority: (1) what the agent explicitly passes via from_lat/from_lng,
        # (2) the last item already placed that day, (3) the accommodation. The agent
        # owns the choice; the fallback only kicks in when it stays silent.
        origin: tuple[float, float] | None = None
        if params.get("from_lat") is not None and params.get("from_lng") is not None:
            origin = (params["from_lat"], params["from_lng"])
        else:
            day_items = sorted(
                [i for i in active.items if i.date == item_date],
                key=lambda x: x.start_time,
            )
            if day_items and day_items[-1].lat and day_items[-1].lng:
                origin = (day_items[-1].lat, day_items[-1].lng)
            elif trip.accommodation_lat and trip.accommodation_lng:
                origin = (trip.accommodation_lat, trip.accommodation_lng)
        if origin:
            try:
                route = estimate_route(db, trip, origin, (lat, lng))
                travel_time_min = route.duration_min
                travel_distance_km = route.distance_km
            except RoutingIntegrationError:
                pass

    item = ItineraryItem(
        itinerary_version_id=active.id,
        date=item_date,
        start_time=start_time,
        end_time=end_time,
        item_type=item_type[:30],
        title=title[:120],
        place_ref=place_ref,
        lat=lat,
        lng=lng,
        travel_time_min=travel_time_min,
        travel_distance_km=travel_distance_km,
        notes=params.get("notes"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "item_id": item.id,
        "title": item.title,
        "date": item_date.isoformat(),
        "time": f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}",
        "travel_from_previous_min": travel_time_min,
        "travel_distance_km": travel_distance_km,
    }


def _handle_check_route(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.routing import RoutingIntegrationError, estimate_route

    from_lat = params.get("from_lat")
    from_lng = params.get("from_lng")
    to_lat = params.get("to_lat")
    to_lng = params.get("to_lng")

    if params.get("from_place_id"):
        place = db.scalar(select(Place).where(Place.id == params["from_place_id"], Place.trip_id == trip.id))
        if place:
            from_lat, from_lng = place.lat, place.lng

    if params.get("to_place_id"):
        place = db.scalar(select(Place).where(Place.id == params["to_place_id"], Place.trip_id == trip.id))
        if place:
            to_lat, to_lng = place.lat, place.lng

    if not all([from_lat, from_lng, to_lat, to_lng]):
        return {"error": "Could not resolve coordinates. Provide place IDs or lat/lng pairs."}

    try:
        result = estimate_route(db, trip, (from_lat, from_lng), (to_lat, to_lng))
        return {"duration_min": result.duration_min, "distance_km": result.distance_km, "source": result.source}
    except RoutingIntegrationError as exc:
        return {"error": str(exc)}


def _handle_get_day_schedule(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.agent_tools import get_active_itinerary

    active = get_active_itinerary(trip)
    if not active:
        return {"items": [], "message": "No active itinerary."}

    date_str = params.get("date", "")
    day_items = [
        item for item in active.items
        if item.date.isoformat() == date_str
    ]
    day_items.sort(key=lambda x: x.start_time)

    # Inline quality report so the agent sees issues while arranging the day,
    # not only at review time. Same analyzer as review_itinerary/finalize.
    from app.services.itinerary_quality import analyze_day, classify_item
    quality = None
    if day_items:
        pace = getattr(trip, "travel_pace", None)
        quality = analyze_day(day_items, pace).as_dict()

    return {
        "date": date_str,
        "item_count": len(day_items),
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "start_time": item.start_time.strftime("%H:%M"),
                "end_time": item.end_time.strftime("%H:%M"),
                "item_type": item.item_type,
                "bucket": classify_item(item),
                "lat": item.lat,
                "lng": item.lng,
                "travel_time_min": item.travel_time_min,
            }
            for item in day_items
        ],
        "quality": quality,
    }


def _handle_get_day_context(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    import math
    from datetime import date as date_type
    from app.models.entities import TripWeatherSnapshot
    from app.services.agent_tools import get_active_itinerary

    date_str = params.get("date", "")
    try:
        parts = date_str.split("-")
        target_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return {"error": f"Invalid date format: {date_str}. Use YYYY-MM-DD."}

    weather_snap = db.scalar(
        select(TripWeatherSnapshot).where(
            TripWeatherSnapshot.trip_id == trip.id,
            TripWeatherSnapshot.forecast_date == target_date,
        )
    )
    weather = None
    if weather_snap:
        weather = {
            "condition": weather_snap.condition_label,
            "outdoor_risky": weather_snap.is_outdoor_risky,
        }

    active = get_active_itinerary(trip)
    placed_items = []
    if active:
        day_items = sorted(
            [i for i in active.items if i.date == target_date],
            key=lambda x: x.start_time,
        )
        placed_items = [
            {"id": i.id, "title": i.title, "start": i.start_time.strftime("%H:%M"), "end": i.end_time.strftime("%H:%M"), "lat": i.lat, "lng": i.lng}
            for i in day_items
        ]

    anchor_lat = trip.accommodation_lat
    anchor_lng = trip.accommodation_lng
    if placed_items:
        last = placed_items[-1]
        if last["lat"] and last["lng"]:
            anchor_lat = last["lat"]
            anchor_lng = last["lng"]

    all_places = list(db.scalars(select(Place).where(Place.trip_id == trip.id).order_by(Place.rating.desc())))
    placed_refs = set()
    if active:
        placed_refs = {i.place_ref for i in active.items if i.place_ref}

    remaining = []
    for p in all_places:
        if p.external_id in placed_refs:
            continue
        dist_km = None
        if anchor_lat and anchor_lng:
            dlat = math.radians(p.lat - anchor_lat)
            dlng = math.radians(p.lng - anchor_lng)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(anchor_lat)) * math.cos(math.radians(p.lat)) * math.sin(dlng / 2) ** 2
            dist_km = round(6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)
        remaining.append({
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "rating": p.rating,
            "dist_km_from_anchor": dist_km,
            "opening_hours": _format_opening_hours(p.opening_hours_json) if p.opening_hours_json else None,
        })

    # Sort by proximity as a convenience, but DO NOT truncate — the agent sees
    # every remaining place (with distance as data) and decides what to use.
    # Truncating here would silently hide good options that happen to be farther.
    remaining.sort(key=lambda x: x["dist_km_from_anchor"] if x["dist_km_from_anchor"] is not None else 999)

    return {
        "date": date_str,
        "weather": weather,
        "accommodation": {"lat": trip.accommodation_lat, "lng": trip.accommodation_lng, "name": trip.accommodation_name},
        "anchor_point": {"lat": anchor_lat, "lng": anchor_lng},
        "placed_items": placed_items,
        "remaining_places": remaining,
        "total_remaining": len(remaining),
    }


def _handle_review_itinerary(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.services.agent_tools import get_active_itinerary
    from app.services.itinerary_quality import analyze_itinerary

    active = get_active_itinerary(trip)
    if not active:
        return {"error": "No active itinerary to review. Call start_itinerary and place items first."}

    pace = getattr(trip, "travel_pace", None)
    report = analyze_itinerary(trip, active, pace)
    if report["blocking_count"] == 0:
        report["verdict"] = "OK — no blocking issues. You may call finalize_itinerary."
    else:
        report["verdict"] = (
            f"{report['blocking_count']} blocking issue(s) across the trip. Fix them, then review again. "
            "finalize_itinerary refuses until they are resolved — unless you judge a flagged issue acceptable "
            "for this trip, in which case finalize with override=true and a reason."
        )
    return report


def _handle_finalize_itinerary(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    from app.models.entities import PlanMutation
    from app.services.agent_tools import get_active_itinerary
    from app.services.itinerary_quality import analyze_itinerary
    from app.services.llm import summarize_itinerary, LLMIntegrationError

    active = get_active_itinerary(trip)
    if not active:
        return {"error": "No active itinerary to finalize."}

    if not active.items:
        return {"error": "Itinerary has no items. Place items before finalizing."}

    # Quality gate. By default the agent must iterate (search for an anchor, add
    # lunch/dinner, rebalance with set_day) until review_itinerary reports zero
    # blocking issues. But the agent OWNS the final judgement: if it reviewed a
    # flagged issue and considers it acceptable for this trip, it can override.
    # Same analyzer that powers review_itinerary, so the two never disagree.
    pace = getattr(trip, "travel_pace", None)
    report = analyze_itinerary(trip, active, pace)
    override = bool(params.get("override"))
    override_reason = str(params.get("override_reason") or "").strip()

    if report["blocking_count"] > 0 and not override:
        offending = [
            {"date": d["date"], "issues": [i for i in d["issues"] if i["severity"] == "blocking"]}
            for d in report["days"]
            if d["blocking_count"] > 0
        ]
        return {
            "error": (
                f"Cannot finalize — {report['blocking_count']} blocking issue(s) remain. "
                "Fix each one (search_places for a missing anchor or meal, swap a venue, or rebalance the "
                "day with set_day), then call review_itinerary again. If you judge a flagged issue is actually "
                "fine for this trip, finalize again with override=true and override_reason."
            ),
            "blocking_days": offending,
        }

    # All issues that remain at finalize time become soft warnings on the plan.
    # When overriding, that includes the blocking ones the agent chose to accept.
    validation_warnings = [
        f"{d['date']}: {i['message']}"
        for d in report["days"]
        for i in d["issues"]
        if override or i["severity"] == "warning"
    ]
    if override and report["blocking_count"] > 0:
        validation_warnings.insert(
            0,
            f"Agente finalizou com {report['blocking_count']} ressalva(s) aceita(s)"
            + (f": {override_reason}" if override_reason else "."),
        )

    n_days = len(set(item.date for item in active.items))
    active.total_estimated_cost = trip.budget / max(len(active.items), 1)

    summary = params.get("summary")
    if not summary:
        try:
            summary = summarize_itinerary(trip, n_days, validation_warnings)
        except LLMIntegrationError:
            summary = f"Roteiro de {n_days} dias em {trip.destination} com {len(active.items)} atividades."
    active.assistant_summary = summary
    active.warnings = validation_warnings

    agent_run = run if isinstance(run, AgentRun) else None
    mutation = PlanMutation(
        trip_id=trip.id,
        run_id=agent_run.id if agent_run else None,
        from_itinerary_version_id=None,
        to_itinerary_version_id=active.id,
        mutation_type="agent_built_itinerary",
        rationale="Itinerary built step-by-step by the central mind agent.",
        changed_item_ids=[item.id for item in active.items],
    )
    db.add(mutation)
    db.add(active)
    db.commit()
    db.refresh(active)

    return {
        "itinerary_id": active.id,
        "version": active.version,
        "item_count": len(active.items),
        "days": n_days,
        "summary": summary[:200],
    }


def _handle_finish(
    db: Session, trip: Trip, run: AgentRun | WorkflowRun, params: dict[str, Any]
) -> dict[str, Any]:
    return {"done": True, "message": params.get("message", "")}
