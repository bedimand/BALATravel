from __future__ import annotations

from app.models.entities import ItineraryItem, Trip


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


def build_map_payload(trip: Trip) -> dict:
    active = next((version for version in reversed(trip.itinerary_versions) if version.status == "active"), None)
    markers = []
    routes = []

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
