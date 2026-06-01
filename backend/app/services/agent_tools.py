from __future__ import annotations

from datetime import UTC, datetime, time as dt_time, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AgentRun,
    AgentToolCall,
    FlightOption,
    HotelOption,
    ItineraryItem,
    ItineraryVersion,
    Place,
    PlanMutation,
    Trip,
)
from app.services.llm import LLMIntegrationError
from app.services.providers import ProviderIntegrationError, get_travel_provider, replace_places


provider = get_travel_provider()


def get_active_itinerary(trip: Trip) -> ItineraryVersion | None:
    return next((version for version in reversed(trip.itinerary_versions) if version.status == "active"), None)


def get_planning_blockers(trip: Trip, places: list[Place] | None = None) -> list[str]:
    blockers: list[str] = []
    loaded_places = places if places is not None else []
    if not loaded_places:
        blockers.append("place options")
    return blockers


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
        "origin_city": trip.origin_city,
        "currency": trip.currency,
        "locale": trip.locale,
        "start_date": trip.start_date.isoformat(),
        "end_date": trip.end_date.isoformat(),
        "budget": str(trip.budget),
        "style": trip.style,
        "interests": list(trip.interests),
        "flight_count": len(trip.flights),
        "hotel_count": len(trip.hotels),
        "place_count": len(places_payload) if places_payload else 0,
        "selected_flight_id": trip.selected_flight_id,
        "selected_hotel_id": trip.selected_hotel_id,
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


def _replace_flights(db: Session, trip: Trip, payloads: list[dict[str, Any]]) -> list[FlightOption]:
    db.execute(delete(FlightOption).where(FlightOption.trip_id == trip.id))
    db.flush()
    trip.selected_flight_id = None
    rows = [FlightOption(trip_id=trip.id, **payload) for payload in payloads]
    db.add_all(rows)
    db.commit()
    db.expire(trip, ["flights"])
    return rows


def _replace_hotels(db: Session, trip: Trip, payloads: list[dict[str, Any]]) -> list[HotelOption]:
    db.execute(delete(HotelOption).where(HotelOption.trip_id == trip.id))
    db.flush()
    trip.selected_hotel_id = None
    rows = [HotelOption(trip_id=trip.id, **payload) for payload in payloads]
    db.add_all(rows)
    db.commit()
    db.expire(trip, ["hotels"])
    return rows


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


def tool_search_flights(db: Session, trip: Trip) -> dict[str, Any]:
    payloads = provider.search_flights(trip)
    rows = _replace_flights(db, trip, payloads)
    return {"count": len(rows), "currency": rows[0].currency if rows else trip.currency}


def tool_search_hotels(db: Session, trip: Trip) -> dict[str, Any]:
    payloads = provider.search_hotels(trip)
    rows = _replace_hotels(db, trip, payloads)
    cheapest = min((row.total_price for row in rows), default=Decimal("0.00"))
    return {"count": len(rows), "cheapest_total": str(cheapest)}


def tool_search_places(db: Session, trip: Trip) -> dict[str, Any]:
    payloads = provider.search_places(trip)
    rows = _replace_places(db, trip, payloads)
    return {"count": len(rows), "top_place": rows[0].name if rows else None}


def tool_search_all(db: Session, trip: Trip) -> tuple[dict[str, Any], list[str]]:
    try:
        result = {
            "flights": tool_search_flights(db, trip)["count"],
            "hotels": tool_search_hotels(db, trip)["count"],
            "places": tool_search_places(db, trip)["count"],
        }
    except ProviderIntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return result, []




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
    new_item = ItineraryItem(
        itinerary_version_id=cloned.id,
        date=payload["date"],
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


def tool_reorder_day(
    db: Session,
    trip: Trip,
    date_text: str,
    rationale: str,
    run: AgentRun | None = None,
) -> tuple[ItineraryVersion, PlanMutation]:
    active = get_active_itinerary(trip)
    if not active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active itinerary not found")

    cloned, _, mutation = create_mutated_itinerary_version(db, trip, active, "reorder_day", rationale, run=run)
    day_items = [row for row in cloned.items if row.date.isoformat() == date_text]
    if not day_items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No itinerary items found for the requested day.")

    anchor = datetime.combine(day_items[0].date, trip.daily_start_time)
    changed_ids: list[int] = []
    for item in sorted(day_items, key=lambda row: (row.travel_time_min, row.start_time, row.id)):
        duration = datetime.combine(item.date, item.end_time) - datetime.combine(item.date, item.start_time)
        if duration <= timedelta():
            duration = timedelta(minutes=90)
        item.start_time = anchor.time().replace(second=0, microsecond=0)
        item.end_time = (anchor + duration).time().replace(second=0, microsecond=0)
        anchor = anchor + duration + timedelta(minutes=max(item.travel_time_min, 15))
        db.add(item)
        changed_ids.append(item.id)

    cloned.assistant_summary = f"{cloned.assistant_summary} Dia reorganizado: {rationale}".strip()
    mutation.changed_item_ids = changed_ids
    db.add(cloned)
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
        "flights": len(trip.flights),
        "hotels": len(trip.hotels),
        "places": len(places),
        "top_hotel": trip.hotels[0].name if trip.hotels else None,
        "top_place": places[0].name if places else None,
    }
