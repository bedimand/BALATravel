from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import RouteEstimateCache, Trip


settings = get_settings()
TravelMode = Literal["walk", "drive"]


class RoutingIntegrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RouteEstimateResult:
    duration_min: int
    distance_km: float
    source: str
    encoded_polyline: str | None = None


def _travel_mode_for_trip(trip: Trip) -> TravelMode:
    if trip.has_car:
        return "drive"
    style = (trip.style or "").lower()
    if "mochil" in style:
        return "walk"
    # Fallback to drive for general comfort unless specified
    return "drive"


def _coordinate_key(point: tuple[float, float]) -> str:
    return f"{point[0]:.5f},{point[1]:.5f}"


def _google_routes_estimate(origin: tuple[float, float], destination: tuple[float, float], mode: TravelMode) -> RouteEstimateResult:
    if not settings.google_routes_api_key:
        raise RoutingIntegrationError("GOOGLE_ROUTES_API_KEY is missing.")

    travel_mode = "WALK" if mode == "walk" else "DRIVE"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_routes_api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
    }
    referer = settings.google_routes_http_referer or (settings.cors_origins[0] if settings.cors_origins else None)
    if referer:
        headers["Referer"] = referer
    payload = {
        "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
        "destination": {"location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}},
        "travelMode": travel_mode,
        "routingPreference": "TRAFFIC_UNAWARE",
    }
    try:
        response = httpx.post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            headers=headers,
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        routes = response.json().get("routes") or []
        if not routes:
            raise RoutingIntegrationError("Google Routes returned no route candidates.")
        route = routes[0]
        seconds = int(str(route.get("duration", "0s")).removesuffix("s") or "0")
        distance_m = int(route.get("distanceMeters") or 0)
        return RouteEstimateResult(
            duration_min=max(int(seconds / 60), 1),
            distance_km=round(distance_m / 1000, 2),
            source="google_routes",
            encoded_polyline=((route.get("polyline") or {}).get("encodedPolyline")),
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        raise RoutingIntegrationError(f"Google Routes HTTP {exc.response.status_code}: {detail}") from exc
    except RoutingIntegrationError:
        raise
    except Exception as exc:
        raise RoutingIntegrationError("Google Routes request failed.") from exc


def estimate_route(
    db: Session,
    trip: Trip,
    origin: tuple[float, float],
    destination: tuple[float, float],
    travel_mode: TravelMode | None = None,
) -> RouteEstimateResult:
    mode = travel_mode or _travel_mode_for_trip(trip)
    origin_key = _coordinate_key(origin)
    destination_key = _coordinate_key(destination)
    cached = db.scalar(
        select(RouteEstimateCache).where(
            RouteEstimateCache.trip_id == trip.id,
            RouteEstimateCache.origin_key == origin_key,
            RouteEstimateCache.destination_key == destination_key,
            RouteEstimateCache.travel_mode == mode,
        )
    )
    if cached:
        return RouteEstimateResult(
            duration_min=cached.duration_min,
            distance_km=cached.distance_km,
            source=cached.source,
            encoded_polyline=cached.encoded_polyline,
        )

    route = _google_routes_estimate(origin, destination, mode)

    row = RouteEstimateCache(
        trip_id=trip.id,
        origin_key=origin_key,
        destination_key=destination_key,
        travel_mode=mode,
        duration_min=route.duration_min,
        distance_km=route.distance_km,
        source=route.source,
        encoded_polyline=route.encoded_polyline,
        fetched_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    return route


def summarize_route_burden(trip: Trip) -> dict[str, int | float | str]:
    active = next((version for version in reversed(trip.itinerary_versions) if version.status == "active"), None)
    if not active or not active.items:
        return {
            "travel_mode": _travel_mode_for_trip(trip),
            "total_travel_min": 0,
            "total_distance_km": 0.0,
            "average_leg_min": 0,
            "average_leg_km": 0.0,
            "max_leg_min": 0,
            "max_leg_km": 0.0,
            "source": "unavailable",
        }

    travel_times = [max(item.travel_time_min, 0) for item in active.items]
    travel_distances = [max(float(item.travel_distance_km or 0.0), 0.0) for item in active.items]
    return {
        "travel_mode": _travel_mode_for_trip(trip),
        "total_travel_min": sum(travel_times),
        "total_distance_km": round(sum(travel_distances), 2),
        "average_leg_min": int(sum(travel_times) / len(travel_times)) if travel_times else 0,
        "average_leg_km": round(sum(travel_distances) / len(travel_distances), 2) if travel_distances else 0.0,
        "max_leg_min": max(travel_times) if travel_times else 0,
        "max_leg_km": max(travel_distances) if travel_distances else 0.0,
        "source": "google_routes",
    }
