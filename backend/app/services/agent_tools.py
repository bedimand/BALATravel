from __future__ import annotations

from datetime import UTC, date as dt_date, datetime, time as dt_time, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentRun,
    AgentToolCall,
    ItineraryItem,
    ItineraryVersion,
    Place,
    PlanMutation,
    Trip,
)
from app.services.providers import get_travel_provider, replace_places


provider = get_travel_provider()


def get_active_itinerary(trip: Trip) -> ItineraryVersion | None:
    return next((version for version in reversed(trip.itinerary_versions) if version.status == "active"), None)


def serialize_itinerary(version: ItineraryVersion | None) -> dict[str, Any] | None:
    if version is None:
        return None
    return {
        "id": version.id,
        "version": version.version,
        "status": version.status,
        "total_estimated_cost": str(version.total_estimated_cost),
        "assistant_summary": version.assistant_summary,
        "warnings": list(version.warnings),
        "items": [
            {
                "id": item.id,
                "date": item.date.isoformat(),
                "start_time": item.start_time.isoformat(),
                "end_time": item.end_time.isoformat(),
                "title": item.title,
                "item_type": item.item_type,
                "travel_time_min": item.travel_time_min,
                "travel_distance_km": item.travel_distance_km,
                "notes": item.notes,
            }
            for item in sorted(version.items, key=lambda row: (row.date, row.start_time, row.id))
        ],
    }


def serialize_trip_snapshot(trip: Trip, places: list[Place] | None = None) -> dict[str, Any]:
    active = get_active_itinerary(trip)
    places_payload = places if places is not None else []
    return {
        "trip_id": trip.id,
        "destination": trip.destination,
        "currency": trip.currency,
        "locale": trip.locale,
        "start_date": trip.start_date.isoformat(),
        "end_date": trip.end_date.isoformat(),
        "budget": str(trip.budget),
        "style": trip.style,
        "interests": list(trip.interests),
        "place_count": len(places_payload) if places_payload else 0,
        "active_itinerary": serialize_itinerary(active),
    }


def begin_tool_call(db: Session, run: AgentRun, tool_name: str, arguments: dict[str, Any]) -> AgentToolCall:
    call = AgentToolCall(run_id=run.id, tool_name=tool_name, arguments_json=arguments, status="running")
    db.add(call)
    db.commit()
    db.refresh(call)
    return call


def finish_tool_call(db: Session, call: AgentToolCall, result: dict[str, Any], status_name: str = "completed") -> AgentToolCall:
    call.result_json = result
    call.status = status_name
    call.completed_at = datetime.now(UTC)
    db.add(call)
    db.commit()
    db.refresh(call)
    return call


def fail_tool_call(db: Session, call: AgentToolCall, detail: str) -> None:
    finish_tool_call(db, call, {"detail": detail}, status_name="failed")


def _next_itinerary_version_number(trip: Trip) -> int:
    return max((version.version for version in trip.itinerary_versions), default=0) + 1


def create_mutated_itinerary_version(
    db: Session,
    trip: Trip,
    source: ItineraryVersion,
    mutation_type: str,
    rationale: str,
    run: AgentRun | None = None,
) -> tuple[ItineraryVersion, dict[int, ItineraryItem], PlanMutation]:
    for version in trip.itinerary_versions:
        if version.status == "active":
            version.status = "archived"
            db.add(version)

    cloned = ItineraryVersion(
        trip_id=trip.id,
        version=_next_itinerary_version_number(trip),
        status="active",
        total_estimated_cost=source.total_estimated_cost,
        assistant_summary=source.assistant_summary,
        warnings=list(source.warnings),
    )
    item_map: dict[int, ItineraryItem] = {}
    for source_item in sorted(source.items, key=lambda row: (row.date, row.start_time, row.id)):
        cloned_item = ItineraryItem(
            date=source_item.date,
            start_time=source_item.start_time,
            end_time=source_item.end_time,
            item_type=source_item.item_type,
            title=source_item.title,
            place_ref=source_item.place_ref,
            lat=source_item.lat,
            lng=source_item.lng,
            travel_time_min=source_item.travel_time_min,
            travel_distance_km=source_item.travel_distance_km,
            notes=source_item.notes,
        )
        cloned.items.append(cloned_item)
        item_map[source_item.id] = cloned_item

    trip.itinerary_versions.append(cloned)
    db.add(cloned)
    db.flush()

    mutation = PlanMutation(
        trip_id=trip.id,
        run_id=run.id if run else None,
        from_itinerary_version_id=source.id,
        to_itinerary_version_id=cloned.id,
        mutation_type=mutation_type,
        rationale=rationale,
        changed_item_ids=[],
    )
    db.add(mutation)
    db.commit()
    db.refresh(cloned)
    db.refresh(mutation)
    return cloned, item_map, mutation


def _replace_places(db: Session, trip: Trip, payloads: list[dict[str, Any]]) -> list[Place]:
    existing_selection = {
        row.external_id: row.is_selected
        for row in db.scalars(select(Place).where(Place.trip_id == trip.id))
    }
    db.execute(delete(Place).where(Place.trip_id == trip.id))
    db.flush()
    rows = replace_places(trip.id, payloads)
    db.add_all(rows)
    db.commit()
    persisted = list(db.scalars(select(Place).where(Place.trip_id == trip.id).order_by(Place.rating.desc())))
    default_selected_count = min(len(persisted), max((trip.end_date - trip.start_date).days * 4, 10))
    preserved_any = any(row.external_id in existing_selection for row in persisted)
    for index, row in enumerate(persisted):
        if row.external_id in existing_selection:
            row.is_selected = existing_selection[row.external_id]
        else:
            row.is_selected = (not preserved_any) and index < default_selected_count
        db.add(row)
    db.commit()
    return list(db.scalars(select(Place).where(Place.trip_id == trip.id).order_by(Place.rating.desc())))






def tool_update_item(
    db: Session,
    trip: Trip,
    item_id: int,
    updates: dict[str, Any],
    rationale: str,
    run: AgentRun | None = None,
) -> tuple[ItineraryVersion, PlanMutation]:
    active = get_active_itinerary(trip)
    if not active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active itinerary not found")
    current_item = next((row for row in active.items if row.id == item_id), None)
    if not current_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary item not found")

    cloned, item_map, mutation = create_mutated_itinerary_version(db, trip, active, "update_item", rationale, run=run)
    target = item_map[item_id]
    next_start = updates.get("start_time", target.start_time)
    next_end = updates.get("end_time", target.end_time)
    if isinstance(next_start, str):
        next_start = dt_time.fromisoformat(next_start)
    if isinstance(next_end, str):
        next_end = dt_time.fromisoformat(next_end)
    if next_end <= next_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_time must be after start_time.")

    for other in cloned.items:
        if other.id == target.id or other.date != target.date:
            continue
        overlap = not (next_end <= other.start_time or next_start >= other.end_time)
        if overlap:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Time conflict with itinerary item id={other.id}.",
            )

    target.title = str(updates.get("title", target.title)).strip()[:120]
    target.notes = str(updates.get("notes", target.notes or "")).strip()[:500] if "notes" in updates else target.notes
    target.start_time = next_start
    target.end_time = next_end
    cloned.assistant_summary = f"{cloned.assistant_summary} Ajuste aplicado: {rationale}".strip()
    mutation.changed_item_ids = [target.id]
    db.add(target)
    db.add(cloned)
    db.add(mutation)
    db.commit()
    db.refresh(cloned)
    db.refresh(mutation)
    return cloned, mutation


def tool_remove_item(
    db: Session,
    trip: Trip,
    item_id: int,
    rationale: str,
    run: AgentRun | None = None,
) -> tuple[ItineraryVersion, PlanMutation]:
    active = get_active_itinerary(trip)
    if not active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active itinerary not found")
    if not any(row.id == item_id for row in active.items):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary item not found")

    cloned, item_map, mutation = create_mutated_itinerary_version(db, trip, active, "remove_item", rationale, run=run)
    target = item_map[item_id]
    cloned.items.remove(target)
    db.delete(target)
    cloned.assistant_summary = f"{cloned.assistant_summary} Item removido: {rationale}".strip()
    mutation.changed_item_ids = []
    db.add(cloned)
    db.add(mutation)
    db.commit()
    db.refresh(cloned)
    db.refresh(mutation)
    return cloned, mutation


def tool_insert_item(
    db: Session,
    trip: Trip,
    payload: dict[str, Any],
    rationale: str,
    run: AgentRun | None = None,
) -> tuple[ItineraryVersion, PlanMutation]:
    active = get_active_itinerary(trip)
    if not active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active itinerary not found")

    cloned, _, mutation = create_mutated_itinerary_version(db, trip, active, "insert_item", rationale, run=run)
    start_time = payload.get("start_time") or "12:00:00"
    end_time = payload.get("end_time") or "13:30:00"
    if isinstance(start_time, str):
        start_time = dt_time.fromisoformat(start_time)
    if isinstance(end_time, str):
        end_time = dt_time.fromisoformat(end_time)
    item_date = payload["date"]
    if isinstance(item_date, str):
        item_date = dt_date.fromisoformat(item_date)
    new_item = ItineraryItem(
        itinerary_version_id=cloned.id,
        date=item_date,
        start_time=start_time,
        end_time=end_time,
        item_type=str(payload.get("item_type", "custom"))[:30],
        title=str(payload.get("title", "Nova atividade"))[:120],
        place_ref=payload.get("place_ref"),
        lat=payload.get("lat"),
        lng=payload.get("lng"),
        travel_time_min=int(payload.get("travel_time_min", 0)),
        travel_distance_km=float(payload.get("travel_distance_km", 0.0)),
        notes=str(payload.get("notes", "") or "")[:500] or None,
    )
    cloned.items.append(new_item)
    cloned.assistant_summary = f"{cloned.assistant_summary} Item inserido: {rationale}".strip()
    db.add(new_item)
    db.add(cloned)
    db.commit()
    db.refresh(cloned)
    mutation.changed_item_ids = [new_item.id]
    db.add(mutation)
    db.commit()
    db.refresh(mutation)
    return cloned, mutation


def tool_set_day(
    db: Session,
    trip: Trip,
    date_text: str,
    items: list[dict[str, Any]],
    rationale: str,
    run: AgentRun | None = None,
) -> tuple[ItineraryVersion, PlanMutation]:
    """Declarative full-day replacement. The agent decides the entire day —
    order, times, which activities — and passes it as `items`. This tool does NOT
    reorder, reschedule, or invent times; it validates the agent's plan and
    persists it, recomputing only the travel time between consecutive stops.

    Each entry in `items`:
      {title, start_time "HH:MM", end_time "HH:MM", item_type?, lat?, lng?, notes?, place_ref?}

    Items from other days are left untouched; the named day is fully replaced.
    """
    active = get_active_itinerary(trip)
    if not active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active itinerary not found")

    try:
        day = dt_date.fromisoformat(date_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid date: {date_text}. Use YYYY-MM-DD.") from exc

    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="set_day requires at least one item.")

    # Parse + validate every item before mutating anything.
    parsed: list[dict[str, Any]] = []
    for idx, raw in enumerate(items):
        title = str(raw.get("title", "")).strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Item {idx} is missing a title.")
        try:
            start_time = dt_time.fromisoformat(str(raw["start_time"]))
            end_time = dt_time.fromisoformat(str(raw["end_time"]))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Item '{title}' has invalid start_time/end_time (use HH:MM).") from exc
        if end_time <= start_time:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Item '{title}': end_time must be after start_time.")
        parsed.append({
            "title": title[:120],
            "start_time": start_time,
            "end_time": end_time,
            "item_type": str(raw.get("item_type", "custom"))[:30],
            "lat": raw.get("lat"),
            "lng": raw.get("lng"),
            "notes": (str(raw.get("notes", "") or "")[:500] or None),
            "place_ref": raw.get("place_ref"),
        })

    parsed.sort(key=lambda r: r["start_time"])
    for a, b in zip(parsed, parsed[1:]):
        if b["start_time"] < a["end_time"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Overlapping items: '{a['title']}' ends after '{b['title']}' starts.",
            )

    cloned, _, mutation = create_mutated_itinerary_version(db, trip, active, "set_day", rationale, run=run)

    # Drop the existing items for this day; keep all other days intact.
    for existing in [row for row in cloned.items if row.date == day]:
        cloned.items.remove(existing)
        db.delete(existing)

    from app.services.routing import estimate_route, RoutingIntegrationError

    changed_ids: list[int] = []
    prev_coords: tuple[float, float] | None = None
    if trip.accommodation_lat and trip.accommodation_lng:
        prev_coords = (trip.accommodation_lat, trip.accommodation_lng)

    for entry in parsed:
        travel_time_min = 0
        travel_distance_km = 0.0
        coords = (entry["lat"], entry["lng"]) if entry["lat"] and entry["lng"] else None
        if coords and prev_coords:
            try:
                route = estimate_route(db, trip, prev_coords, coords)
                travel_time_min = route.duration_min
                travel_distance_km = route.distance_km
            except RoutingIntegrationError:
                pass
        new_item = ItineraryItem(
            date=day,
            start_time=entry["start_time"],
            end_time=entry["end_time"],
            item_type=entry["item_type"],
            title=entry["title"],
            place_ref=entry["place_ref"],
            lat=entry["lat"],
            lng=entry["lng"],
            travel_time_min=travel_time_min,
            travel_distance_km=travel_distance_km,
            notes=entry["notes"],
        )
        cloned.items.append(new_item)
        if coords:
            prev_coords = coords

    cloned.assistant_summary = f"{cloned.assistant_summary} Dia {date_text} redefinido: {rationale}".strip()
    db.add(cloned)
    db.flush()
    changed_ids = [item.id for item in cloned.items if item.date == day]
    mutation.changed_item_ids = changed_ids
    db.add(mutation)
    db.commit()
    db.refresh(cloned)
    db.refresh(mutation)
    return cloned, mutation


def tool_rollback_to_version(
    db: Session,
    trip: Trip,
    version_id: int,
    rationale: str,
    run: AgentRun | None = None,
) -> tuple[ItineraryVersion, PlanMutation]:
    source = next((version for version in trip.itinerary_versions if version.id == version_id), None)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Itinerary version not found")
    cloned, _, mutation = create_mutated_itinerary_version(db, trip, source, "rollback", rationale, run=run)
    cloned.assistant_summary = f"{cloned.assistant_summary} Restaurado de uma versao anterior.".strip()
    mutation.changed_item_ids = [item.id for item in cloned.items]
    db.add(cloned)
    db.add(mutation)
    db.commit()
    db.refresh(cloned)
    db.refresh(mutation)
    return cloned, mutation


def tool_list_current_options(db: Session, trip: Trip) -> dict[str, Any]:
    places = list(db.scalars(select(Place).where(Place.trip_id == trip.id).order_by(Place.rating.desc())))
    return {
        "places": len(places),
        "top_place": places[0].name if places else None,
    }
