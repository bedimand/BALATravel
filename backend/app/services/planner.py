from __future__ import annotations
import math
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import HotelOption, ItineraryItem, ItineraryVersion, Place, Trip, TripWeatherSnapshot
from app.services.llm import summarize_itinerary
from app.services.routing import RouteEstimateResult, estimate_route
from app.services.weather import weather_by_date


SLOT_STARTS = [time(9, 0), time(13, 0), time(18, 0)]
DEFAULT_SLOT_MIN_DURATION = 60


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2) * math.sin(dLat / 2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon / 2) * math.sin(dLon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _daterange(start: date, end: date) -> list[date]:
    days = max((end - start).days, 1)
    return [start + timedelta(days=offset) for offset in range(days)]


def _score_place(place: Place, interests: list[str]) -> float:
    return place.rating + (0.8 if place.category in interests else 0)


def _is_outdoor_place(place: Place) -> bool:
    category = (place.category or "").lower()
    return any(
        token in category
        for token in ["park", "beach", "viewpoint", "garden", "outdoor", "tourist_attraction", "trail", "square"]
    )


def _hour_status(place: Place, current_date: date, slot_start: time) -> str:
    weekday = current_date.strftime("%a").lower()[:3]
    windows = place.opening_hours_json.get(weekday, [])
    if not windows:
        return "unknown"
    for window in windows:
        try:
            start_text, end_text = window.split("-")
            start_hour, start_minute = [int(part) for part in start_text.split(":")]
            end_hour, end_minute = [int(part) for part in end_text.split(":")]
            if time(start_hour, start_minute) <= slot_start < time(end_hour, end_minute):
                return "open"
        except Exception:
            continue
    return "closed"


def _time_suitability_bonus(place: Place, slot_start: time) -> float:
    category = (place.category or "").lower()
    hour = slot_start.hour
    
    # Food logic
    is_food = any(t in category for t in ["restaurant", "food", "dining", "meal", "steakhouse", "grill", "bistro", "pizza"])
    is_cafe = any(t in category for t in ["cafe", "coffee", "bakery", "breakfast", "brunch"])
    
    if is_food:
        # Peak lunch: 12-14, Peak dinner: 19-21
        if (12 <= hour <= 14) or (19 <= hour <= 21):
            return 2.5
        if 8 <= hour <= 10: # Breakfast time
            return 1.5 if is_cafe else -5.0 # Penalize non-breakfast food in the morning
        return -1.0 # Slight penalty for off-peak dining
        
    # Sightseeing logic
    is_sightseeing = any(t in category for t in ["museum", "gallery", "landmark", "attraction", "park", "garden"])
    if is_sightseeing:
        if 9 <= hour <= 17: # Daytime is best for sightseeing
            return 1.5
        return -2.0 # Sightseeing at night is often less ideal or closed
        
    return 0.0


def _decode_polyline(encoded: str | None) -> list[list[float]]:
    if not encoded:
        return []

    coordinates: list[list[float]] = []
    index = 0
    lat = 0
    lng = 0

    while index < len(encoded):
        result = 0
        shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1

        result = 0
        shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1

        coordinates.append([round(lng / 1e5, 5), round(lat / 1e5, 5)])

    return coordinates


def build_itinerary(db: Session, trip: Trip, places: list[Place], hotels: list[HotelOption]) -> ItineraryVersion:
    if not places:
        raise ValueError("Cannot build a full itinerary without place options.")

    trip_days = _daterange(trip.start_date, trip.end_date)
    warnings: list[str] = []
    place_pool = [place for place in places if place.is_selected] or places
    ranked_places = sorted(place_pool, key=lambda item: _score_place(item, trip.interests), reverse=True)
    
    # Increase buffer to allow for higher density (target ~5-6 per day)
    target_items_per_day = 6
    selected_places = ranked_places[: max(target_items_per_day, len(trip_days) * target_items_per_day)]
    
    anchor_lat = sum(place.lat for place in selected_places[: min(len(selected_places), 6)]) / max(min(len(selected_places), 6), 1)
    anchor_lng = sum(place.lng for place in selected_places[: min(len(selected_places), 6)]) / max(min(len(selected_places), 6), 1)
    
    weather_lookup = weather_by_date(
        list(
            db.scalars(
                select(TripWeatherSnapshot)
                .where(TripWeatherSnapshot.trip_id == trip.id)
                .order_by(TripWeatherSnapshot.forecast_date.asc())
            )
        )
    )
    
    current_version_number = max((version.version for version in trip.itinerary_versions), default=0) + 1
    itinerary = ItineraryVersion(
        trip_id=trip.id,
        version=current_version_number,
        status="active",
        total_estimated_cost=Decimal("0.00"),
        warnings=[],
        assistant_summary="",
    )

    remaining = selected_places[:]
    total_activity_cost = Decimal("0.00")
    
    for current_date in trip_days:
        day_anchor = (trip.accommodation_lat or anchor_lat, trip.accommodation_lng or anchor_lng)
        # Dynamic time cursor starting at the user's preferred start time
        time_cursor = datetime.combine(current_date, trip.daily_start_time)
        day_end_limit = datetime.combine(current_date, trip.daily_end_time)
        day_category_usage: dict[str, int] = {}
        day_items_scheduled = 0

        while remaining and time_cursor < day_end_limit:
            weather = weather_lookup.get(current_date)
            best_candidate: Place | None = None
            best_candidate_status = "unknown"
            best_route = RouteEstimateResult(0, 0.0, "unavailable", None)
            best_score = -9999.0
            best_reasoning = ""

            # 1. First Pass: Score candidates by rank and suitability (no expensive routing yet)
            scoring_pool = []
            for candidate in remaining[:25]: # Check up to 25 for scoring
                status = _hour_status(candidate, current_date, time_cursor.time())
                if status == "closed":
                    continue
                
                # Diversity Penalty: Avoid repeating categories on the same day
                cat_usage = day_category_usage.get(candidate.category, 0)
                repetition_penalty = cat_usage * 5.0 # Scale penalty significantly
                
                weather_penalty = 2.5 if weather and weather.is_outdoor_risky and _is_outdoor_place(candidate) else 0.0
                status_penalty = 0.0 if status == "open" else 1.0
                time_bonus = _time_suitability_bonus(candidate, time_cursor.time())
                
                rank_score = _score_place(candidate, trip.interests)
                base_score = rank_score + time_bonus - weather_penalty - status_penalty - repetition_penalty
                
                dist_km = haversine_km(day_anchor[0], day_anchor[1], candidate.lat, candidate.lng)
                scoring_pool.append({
                    "candidate": candidate,
                    "base_score": base_score,
                    "dist_km": dist_km,
                    "status": status,
                    "repetition_penalty": repetition_penalty,
                    "time_bonus": time_bonus
                })

            # 2. Second Pass: Filter for top proximity candidates and perform actual routing
            scoring_pool.sort(key=lambda x: x["base_score"], reverse=True)
            top_performers = scoring_pool[:12]
            top_performers.sort(key=lambda x: x["dist_km"])
            
            for entry in top_performers[:5]: # Actual routing for top performers
                candidate = entry["candidate"]
                route = estimate_route(db, trip, day_anchor, (candidate.lat, candidate.lng))
                travel_time_min = route.duration_min
                proximity_score = -(travel_time_min / 30)
                
                final_score = entry["base_score"] + proximity_score
                
                if final_score > best_score:
                    best_score = final_score
                    best_candidate = candidate
                    best_candidate_status = entry["status"]
                    best_route = route
                    
                    # Construct Reasoning
                    reasons = []
                    if _score_place(candidate, trip.interests) > 4.5: reasons.append("Possui avaliação excelente")
                    if candidate.category in trip.interests: reasons.append(f"Combina com seu interesse em '{candidate.category}'")
                    if entry["time_bonus"] > 0: reasons.append("Horário ideal para esta atividade")
                    if travel_time_min < 20: reasons.append("Localização próxima facilita logística")
                    if entry["repetition_penalty"] > 0: reasons.append("Variação de categoria para manter o dia dinâmico")
                    
                    best_reasoning = ". ".join(reasons) + "." if reasons else "Uma ótima opção complementar para o seu roteiro."

            if best_candidate is None:
                time_cursor += timedelta(minutes=60)
                if time_cursor > day_end_limit: break
                continue

            travel_time_min = best_route.duration_min
            arrival_time = time_cursor + timedelta(minutes=travel_time_min)
            duration = max(best_candidate.estimated_duration, DEFAULT_SLOT_MIN_DURATION)
            departure_time = arrival_time + timedelta(minutes=duration)
            
            if arrival_time > day_end_limit + timedelta(minutes=60):
                break

            itinerary.items.append(
                ItineraryItem(
                    date=current_date,
                    start_time=arrival_time.time().replace(second=0, microsecond=0),
                    end_time=departure_time.time().replace(second=0, microsecond=0),
                    item_type=best_candidate.category,
                    title=best_candidate.name,
                    place_ref=best_candidate.external_id,
                    lat=best_candidate.lat,
                    lng=best_candidate.lng,
                    travel_time_min=travel_time_min,
                    travel_distance_km=best_route.distance_km,
                    notes=best_candidate.summary,
                    curator_reasoning=best_reasoning,
                )
            )
            day_items_scheduled += 1
            day_category_usage[best_candidate.category] = day_category_usage.get(best_candidate.category, 0) + 1
            total_activity_cost += Decimal("45.00")
            
            day_anchor = (best_candidate.lat, best_candidate.lng)
            remaining.remove(best_candidate)
            time_cursor = departure_time + timedelta(minutes=15)
            
            if day_items_scheduled >= target_items_per_day:
                break

        if day_items_scheduled < 3:
            warnings.append(f"Dia {current_date.isoformat()} com baixa densidade de atividades.")

    itinerary.total_estimated_cost = total_activity_cost
    itinerary.warnings = list(dict.fromkeys(warnings))
    itinerary.assistant_summary = summarize_itinerary(trip, len(trip_days), itinerary.warnings)

    for version in trip.itinerary_versions:
        version.status = "archived"

    trip.itinerary_versions.append(itinerary)
    trip.status = "planned"
    db.add(itinerary)
    db.commit()
    db.refresh(itinerary)
    return itinerary


def build_map_payload(trip: Trip) -> dict:
    active = next((version for version in reversed(trip.itinerary_versions) if version.status == "active"), None)
    markers = []
    routes = []

    # Add Accommodation Marker
    if trip.accommodation_lat and trip.accommodation_lng:
        markers.append({
            "id": "hotel-marker",
            "title": trip.accommodation_name or "Minha Hospedagem",
            "kind": "accommodation",
            "lat": trip.accommodation_lat,
            "lng": trip.accommodation_lng,
            "summary": trip.accommodation_address,
        })

    place_lookup = {place.external_id: place for place in trip.places} if hasattr(trip, "places") else {}
    previous_marker_id = None
    previous_item: ItineraryItem | None = None
    if active:
        sorted_items = sorted(active.items, key=lambda item: (item.date, item.start_time))
        for item in sorted_items:
            place = place_lookup.get(item.place_ref or "")
            marker_id = f"item-{item.id}"
            markers.append(
                {
                    "id": marker_id,
                    "title": item.title,
                    "kind": item.item_type,
                    "lat": item.lat or 0.0,
                    "lng": item.lng or 0.0,
                    "date": item.date,
                    "start_time": item.start_time,
                    "summary": item.notes,
                    "image_url": place.image_url if place else None,
                    "rating": place.rating if place else None,
                    "user_ratings_total": place.user_ratings_total if place else None,
                    "address_full": place.address_full if place else None,
                    "editorial_note": place.editorial_note if place else None,
                    "price_level": place.price_level if place else None,
                    "website": place.website if place else None,
                    "curator_reasoning": item.curator_reasoning,
                }
            )
            if previous_marker_id and previous_item and previous_item.lat is not None and previous_item.lng is not None and item.lat is not None and item.lng is not None:
                encoded_polyline = None
                for cache_row in trip.route_estimates:
                    if (
                        cache_row.origin_key == f"{previous_item.lat:.5f},{previous_item.lng:.5f}"
                        and cache_row.destination_key == f"{item.lat:.5f},{item.lng:.5f}"
                    ):
                        encoded_polyline = cache_row.encoded_polyline
                        break
                routes.append(
                    {
                        "from_marker_id": previous_marker_id,
                        "to_marker_id": marker_id,
                        "distance_km": round(float(item.travel_distance_km or 0.0), 2),
                        "duration_min": item.travel_time_min,
                        "source": "google_routes" if item.travel_time_min or item.travel_distance_km else "unavailable",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": _decode_polyline(encoded_polyline),
                        },
                    }
                )
            previous_marker_id = marker_id
            previous_item = item
    return {"trip_id": trip.id, "markers": markers, "routes": routes}
