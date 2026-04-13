from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from math import sqrt
import re
from typing import Any
import unicodedata
from urllib.parse import quote_plus

import httpx

from app.core.config import get_settings
from app.models.entities import Place, Trip


settings = get_settings()


class ProviderIntegrationError(RuntimeError):
    pass


def _safe_decimal(value: Any, fallback: str = "0.00") -> Decimal:
    if value is None or value == "":
        return Decimal(fallback)
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except Exception:
        return Decimal(fallback)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    if value is None or value == "":
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except Exception:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match:
            try:
                return float(match.group(0))
            except Exception:
                return fallback
        return fallback


def _first_value(*values: Any, fallback: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return fallback


def _normalize_text(value: str) -> str:
    lowered = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower().strip()
    return re.sub(r"[^a-z0-9 ]+", "", lowered)


def _rough_distance_km(origin: tuple[float, float], destination: tuple[float, float]) -> float:
    return sqrt((origin[0] - destination[0]) ** 2 + (origin[1] - destination[1]) ** 2) * 111


class TravelProvider:
    source = "serpapi"

    def _ensure_serpapi_key(self) -> str:
        if not settings.serpapi_api_key:
            raise ProviderIntegrationError("SERPAPI_API_KEY is missing. Live search cannot run without it.")
        return settings.serpapi_api_key

    def _serpapi_request(self, params: dict[str, Any]) -> dict:
        try:
            response = httpx.get(
                settings.serpapi_base_url,
                params={**params, "api_key": self._ensure_serpapi_key()},
                timeout=25.0,
            )
            if response.status_code >= 400:
                try:
                    payload = response.json()
                    detail = payload.get("error")
                except Exception:
                    detail = None
                if detail:
                    raise ProviderIntegrationError(f"SerpApi error: {detail}")
                raise ProviderIntegrationError(f"SerpApi HTTP {response.status_code}")

            payload = response.json()
            if payload.get("error"):
                raise ProviderIntegrationError(f"SerpApi error: {payload['error']}")
            return payload
        except ProviderIntegrationError:
            raise
        except Exception as exc:
            raise ProviderIntegrationError("SerpApi request failed.") from exc

    def _location_to_iata(self, location: str) -> str:
        text = location.strip()
        if len(text) == 3 and text.isalpha():
            return text.upper()
        normalized = _normalize_text(text)
        city_map = {
            "rio de janeiro": "GIG",
            "sao paulo": "GRU",
            "sao paulo sp": "GRU",
            "salvador": "SSA",
            "recife": "REC",
            "fortaleza": "FOR",
            "brasilia": "BSB",
            "curitiba": "CWB",
            "porto alegre": "POA",
            "florianopolis": "FLN",
            "belo horizonte": "CNF",
        }
        return city_map.get(normalized, text[:3].upper())

    def _trip_origin_iata(self, trip: Trip) -> str:
        origin_city = str(getattr(trip, "origin_city", "") or "").strip()
        if origin_city:
            return self._location_to_iata(origin_city)

        legacy_origin = str(getattr(trip, "origin_iata", "") or "").strip().upper()
        if len(legacy_origin) == 3 and legacy_origin.isalpha():
            return legacy_origin
        raise ProviderIntegrationError("Trip origin city is missing. Set origin_city before running flight search.")

    def _trip_currency(self, trip: Trip) -> str:
        currency = str(getattr(trip, "currency", "") or "").strip().upper()
        return currency if len(currency) == 3 and currency.isalpha() else "BRL"

    def _trip_locale(self, trip: Trip) -> str:
        locale = str(getattr(trip, "locale", "") or "").strip()
        return locale or "pt-BR"

    def _trip_gl_hl(self, trip: Trip) -> tuple[str, str]:
        locale = self._trip_locale(trip)
        parts = locale.replace("_", "-").split("-")
        language = parts[0].lower() if parts and parts[0] else "pt"
        country = parts[1].lower() if len(parts) > 1 and parts[1] else "br"
        return country, f"{language}-{country.upper()}"

    def search_flights(self, trip: Trip) -> list[dict]:
        trip_currency = self._trip_currency(trip)
        trip_gl, trip_hl = self._trip_gl_hl(trip)
        trip_origin_iata = self._trip_origin_iata(trip)
        payload = self._serpapi_request(
            {
                "engine": "google_flights",
                "departure_id": trip_origin_iata,
                "arrival_id": self._location_to_iata(trip.destination),
                "outbound_date": trip.start_date.isoformat(),
                "currency": trip_currency,
                "hl": trip_hl,
                "gl": trip_gl,
                "adults": 1,
                "type": 2,
            }
        )
        offers = [*(payload.get("best_flights") or []), *(payload.get("other_flights") or [])]
        if not offers:
            raise ProviderIntegrationError("No live flight offers returned by SerpApi.")

        search_link = payload.get("search_metadata", {}).get("google_flights_url")
        fetched_at = datetime.now(UTC)
        results = []
        for offer in offers[: settings.serpapi_max_results]:
            segments = offer.get("flights") or []
            if not segments:
                continue
            first_leg = segments[0]
            last_leg = segments[-1]
            results.append(
                {
                    "provider_ref": _first_value(offer.get("booking_token"), offer.get("departure_token"), fallback=f"FLT-{trip.id}-{len(results)}"),
                    "price": _safe_decimal(offer.get("price"), "0.00"),
                    "currency": trip_currency,
                    "legs_json": [
                        {
                            "departure_airport": _first_value((first_leg.get("departure_airport") or {}).get("id"), trip_origin_iata),
                            "departure_time": _first_value((first_leg.get("departure_airport") or {}).get("time"), ""),
                            "arrival_airport": _first_value((last_leg.get("arrival_airport") or {}).get("id"), ""),
                            "arrival_time": _first_value((last_leg.get("arrival_airport") or {}).get("time"), ""),
                        }
                    ],
                    "baggage_summary": "Consulte detalhes na oferta",
                    "deeplink": _first_value(search_link, "https://www.google.com/travel/flights"),
                    "source": self.source,
                    "confidence": 0.93,
                    "fetched_at": fetched_at,
                }
            )
        if not results:
            raise ProviderIntegrationError("SerpApi returned flight payload without usable segments.")
        return results

    def search_hotels(self, trip: Trip) -> list[dict]:
        trip_currency = self._trip_currency(trip)
        trip_gl, trip_hl = self._trip_gl_hl(trip)
        payload = self._serpapi_request(
            {
                "engine": "google_hotels",
                "q": trip.destination,
                "check_in_date": trip.start_date.isoformat(),
                "check_out_date": trip.end_date.isoformat(),
                "adults": 1,
                "currency": trip_currency,
                "hl": trip_hl,
                "gl": trip_gl,
            }
        )
        hotels = payload.get("properties") or []
        if not hotels:
            raise ProviderIntegrationError("No live hotel offers returned by SerpApi.")

        trip_days = max((trip.end_date - trip.start_date).days, 1)
        fetched_at = datetime.now(UTC)
        results = []
        for hotel in hotels[: settings.serpapi_max_results]:
            gps = hotel.get("gps_coordinates") or {}
            nightly = _safe_decimal(
                _first_value(
                    (hotel.get("rate_per_night") or {}).get("lowest"),
                    hotel.get("extracted_rate"),
                ),
                "0.00",
            )
            total = _safe_decimal(
                _first_value(
                    (hotel.get("total_rate") or {}).get("lowest"),
                    nightly * trip_days,
                ),
                "0.00",
            )
            hotel_name = _first_value(hotel.get("name"), fallback="Hotel")
            deeplink = _first_value(
                hotel.get("link"),
                hotel.get("serpapi_property_details_link"),
                fallback=f"https://www.google.com/travel/hotels?q={quote_plus(str(hotel_name))}",
            )
            results.append(
                {
                    "provider_ref": _first_value(hotel.get("property_token"), hotel.get("name"), fallback=f"HTL-{trip.id}-{len(results)}"),
                    "name": hotel_name,
                    "nightly_price": nightly,
                    "total_price": total,
                    "rating": float(_first_value(hotel.get("overall_rating"), hotel.get("rating"), fallback=4.0)),
                    "lat": float(_first_value(gps.get("latitude"), fallback=0.0)),
                    "lng": float(_first_value(gps.get("longitude"), fallback=0.0)),
                    "deeplink": deeplink,
                    "source": self.source,
                    "confidence": 0.92,
                    "fetched_at": fetched_at,
                }
            )
        if not results:
            raise ProviderIntegrationError("SerpApi returned hotel payload without usable records.")
        return results

    def search_places_by_interest(self, trip: Trip, query: str, max_results: int = 20, center_lat: float | None = None, center_lng: float | None = None) -> list[dict]:
        """
        Search Google Maps for places matching a query string.
        If center_lat/lng are provided, biases the search near that location.
        """
        # Internal mapping to expand generic interest categories into better keywords
        category_map = {
            "vida noturna": "nightlife bars clubs cocktail",
            "gastronomia": "best restaurants local food dining",
            "arte e museus": "museums art galleries exhibitions",
            "parques e natureza": "parks botanical gardens nature",
            "compras": "shopping malls markets stores",
            "praia": "beaches seaside",
            "caminhadas": "hiking trails walking paths",
            "landmark": "top iconic landmarks tourist attractions must-see",
            "turismo": "main city highlights points of interest top-rated attractions",
        }
        
        lowered = query.lower().strip()
        dest_lowered = trip.destination.lower().strip()
        for interest, keywords in category_map.items():
            # Match "Interest" or "Interest [Destination]"
            if lowered == interest or lowered == f"{interest} {dest_lowered}":
                query = f"{keywords} in {trip.destination}"
                break

        params = {
            "engine": "google_maps",
            "q": query,
            "type": "search",
            "hl": self._trip_locale(trip).split("-")[0],
            "gl": self._trip_gl_hl(trip)[0],
        }
        
        # Bias search if center is provided
        if center_lat is not None and center_lng is not None:
            params["ll"] = f"@{center_lat},{center_lng},14z"
        # Fallback to hotel only if no center provided AND explicitly desired (but agent should control this)
        # For now, we allow global search if no center is passed.
            
        try:
            payload = self._serpapi_request(params)
            local_results = payload.get("local_results") or []
        except Exception as exc:
            raise ProviderIntegrationError("Live place lookup failed by interest.") from exc
            
        fetched_at = datetime.now(UTC)
        results = []
        for item in local_results[:max_results]:
            place_id = item.get("place_id")
            if not place_id: continue
            
            gps = item.get("gps_coordinates") or {}
            hours_dict = item.get("operating_hours") or {}
            # Normalize hours so the agent can understand them uniformly, fallback to raw dict
            price = item.get("price", "") or ""
            price_level = len(price) if "$" in price else None

            results.append({
                "external_id": f"G-{place_id}",
                "name": item.get("title", ""),
                "google_place_id": place_id,
                "rating": float(item.get("rating") or 4.0),
                "user_ratings_total": item.get("reviews") or 0,
                "price_level": price_level,
                "address_full": item.get("address", ""),
                "lat": float(gps.get("latitude") or 0.0),
                "lng": float(gps.get("longitude") or 0.0),
                "opening_hours_json": hours_dict,
                "image_url": item.get("thumbnail"),
                "deeplink": item.get("link") or f"https://www.google.com/maps/place/?q=place_id:{place_id}",
                "category": str(item.get("type", "atracao")).replace("_", " ").title(),
                "source": "google-maps-serpapi",
                "fetched_at": fetched_at,
            })
        return results

    def get_place_photos(self, google_place_id: str) -> list[str]:
        """Retrieves an array of photo URLs for a given Google Place ID via SerpAPI."""
        if not google_place_id:
            return []
        params = {
            "engine": "google_maps_photos",
            "data_id": google_place_id,
        }
        try:
            # We don't want a failing photo fetching request to break the tool
            payload = self._serpapi_request(params)
            photos = payload.get("photos", [])
            return [str(photo.get("image")) for photo in photos if photo.get("image")][:10]
        except Exception:
            return []

    def _opentripmap_request(self, path: str, params: dict[str, Any]) -> Any:
        if not settings.opentripmap_api_key:
            raise ProviderIntegrationError("OPENTRIPMAP_API_KEY is missing.")
        base_url = settings.opentripmap_base_url.rstrip("/")
        response = httpx.get(
            f"{base_url}/{path.lstrip('/')}",
            params={**params, "apikey": settings.opentripmap_api_key},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise ProviderIntegrationError(f"OpenTripMap error: {payload['error']}")
        return payload

    def _fetch_opentripmap_candidates(self, seed_lat: float, seed_lng: float, target_count: int) -> list[dict[str, Any]]:
        try:
            rows = self._opentripmap_request(
                "radius",
                {
                    "radius": settings.opentripmap_radius_meters,
                    "lon": seed_lng,
                    "lat": seed_lat,
                    "format": "json",
                    "limit": max(target_count * 3, 12),
                },
            )
        except Exception as exc:
            raise ProviderIntegrationError("OpenTripMap radius lookup failed.") from exc

        if not isinstance(rows, list):
            return []

        results: list[dict[str, Any]] = []
        for row in rows:
            xid = row.get("xid")
            if not xid:
                continue
            details: dict[str, Any] = {}
            try:
                details_payload = self._opentripmap_request(f"xid/{xid}", {})
                if isinstance(details_payload, dict):
                    details = details_payload
            except Exception:
                details = {}
            point = row.get("point") or {}
            results.append(
                {
                    "xid": xid,
                    "name": _first_value(row.get("name"), details.get("name"), fallback=""),
                    "lat": _safe_float(_first_value(point.get("lat"), details.get("point", {}).get("lat"), fallback=0.0)),
                    "lng": _safe_float(_first_value(point.get("lon"), details.get("point", {}).get("lon"), fallback=0.0)),
                    "kinds": _first_value(details.get("kinds"), row.get("kinds"), fallback=""),
                    "rate": _safe_float(_first_value(details.get("rate"), row.get("rate"), fallback=0.0)),
                    "summary": _first_value(
                        (details.get("wikipedia_extracts") or {}).get("text"),
                        details.get("info", {}).get("descr"),
                        details.get("wikipedia"),
                        fallback="",
                    ),
                    "image_url": _first_value(
                        (details.get("preview") or {}).get("source"),
                        details.get("image"),
                    ),
                    "opening_hours": details.get("opening_hours"),
                }
            )
        return results

    def search_places(self, trip: Trip) -> list[dict]:
        # Live place lookup via Nominatim + OpenTripMap enrichment.
        if not settings.opentripmap_api_key:
            raise ProviderIntegrationError("OPENTRIPMAP_API_KEY is missing.")
        target_count = max(settings.place_catalog_max_results, 12)
        query_variants = [
            f"top iconic landmarks in {trip.destination}",
            f"must see attractions in {trip.destination}",
            f"best tourist spots {trip.destination}",
            f"attractions {trip.destination}",
            f"things to do in {trip.destination}",
            f"museums in {trip.destination}",
            f"restaurants in {trip.destination}",
            f"parks in {trip.destination}",
            f"landmarks in {trip.destination}",
            f"galleries in {trip.destination}",
            f"historic places in {trip.destination}",
        ]
        raw_places: list[dict[str, Any]] = []
        seen_place_ids: set[str] = set()

        for query in query_variants:
            if len(raw_places) >= target_count:
                break
            try:
                response = httpx.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "limit": target_count,
                        "addressdetails": 1,
                    },
                    headers={"User-Agent": "BALATravel/1.0"},
                    timeout=20.0,
                )
                response.raise_for_status()
                candidates = response.json()
            except Exception as exc:
                raise ProviderIntegrationError("Live place lookup failed (Nominatim).") from exc

            for row in candidates:
                place_id = str(_first_value(row.get("place_id"), fallback=""))
                if place_id and place_id in seen_place_ids:
                    continue
                if place_id:
                    seen_place_ids.add(place_id)
                raw_places.append(row)
                if len(raw_places) >= target_count:
                    break

        if not raw_places:
            raise ProviderIntegrationError("No live attractions returned for destination.")

        def _normalize_opening_hours(raw_value: Any) -> dict[str, Any]:
            if isinstance(raw_value, dict):
                return raw_value
            text = str(raw_value or "").strip().lower()
            if not text:
                return {}
            if "24/7" in text:
                return {day: ["00:00-23:59"] for day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
            match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
            if match:
                start, end = match.group(1), match.group(2)
                return {day: [f"{start}-{end}"] for day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
            return {}

        otm_candidates: list[dict[str, Any]] = []
        if raw_places:
            seed_lat = float(_first_value(raw_places[0].get("lat"), fallback=0.0))
            seed_lng = float(_first_value(raw_places[0].get("lon"), fallback=0.0))
            otm_candidates = self._fetch_opentripmap_candidates(seed_lat, seed_lng, target_count)
        if not otm_candidates:
            raise ProviderIntegrationError("OpenTripMap returned no candidate places for enrichment.")

        def _match_otm_candidate(name: str, lat: float, lng: float, used_xids: set[str]) -> dict[str, Any] | None:
            normalized_name = _normalize_text(name)
            best_row: dict[str, Any] | None = None
            best_distance = 9999.0
            for candidate in otm_candidates:
                xid = candidate.get("xid")
                if not xid or xid in used_xids:
                    continue
                candidate_name = _normalize_text(str(candidate.get("name", "")))
                distance = _rough_distance_km((lat, lng), (float(candidate.get("lat", 0.0)), float(candidate.get("lng", 0.0))))
                names_overlap = bool(normalized_name and candidate_name and (normalized_name in candidate_name or candidate_name in normalized_name))
                if names_overlap and distance <= 6.0:
                    if distance < best_distance:
                        best_row = candidate
                        best_distance = distance
                elif distance < 0.9 and distance < best_distance:
                    best_row = candidate
                    best_distance = distance
            return best_row

        fetched_at = datetime.now(UTC)
        used_xids: set[str] = set()
        places: list[dict[str, Any]] = []
        dedupe_keys: set[tuple[str, int, int]] = set()

        for index, row in enumerate(raw_places):
            lat = float(_first_value(row.get("lat"), fallback=0.0))
            lng = float(_first_value(row.get("lon"), fallback=0.0))
            name = str(_first_value(row.get("name"), row.get("display_name"), fallback=f"Place {index + 1}"))[:120]
            category = str(_first_value(row.get("type"), row.get("class"), fallback="atracao"))[:50]
            summary = str(row.get("display_name", ""))[:400]
            opening_hours = {}
            source = "osm-nominatim"
            confidence = 0.72
            rating = 4.0
            deeplink = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=15/{lat}/{lng}"
            image_url = None

            match = _match_otm_candidate(name, lat, lng, used_xids)
            if match:
                xid = str(match.get("xid"))
                used_xids.add(xid)
                source = "osm-nominatim+opentripmap"
                confidence = 0.84
                category = str(_first_value(str(match.get("kinds", "")).split(",")[0], category, fallback=category))[:50]
                summary = str(_first_value(match.get("summary"), summary, fallback=summary))[:400]
                opening_hours = _normalize_opening_hours(match.get("opening_hours"))
                rating = min(5.0, 3.8 + _safe_float(_first_value(match.get("rate"), fallback=0.0)) * 0.35)
                deeplink = f"https://opentripmap.com/en/card/{xid}"
                image_url = _first_value(match.get("image_url"), image_url)

            dedupe_key = (_normalize_text(name), int(round(lat * 1000)), int(round(lng * 1000)))
            if dedupe_key in dedupe_keys:
                continue
            dedupe_keys.add(dedupe_key)
            places.append(
                {
                    "external_id": f"OSM-{row.get('place_id', index)}",
                    "name": name,
                    "category": category,
                    "lat": lat,
                    "lng": lng,
                        "opening_hours_json": opening_hours,
                        "rating": rating,
                        "estimated_duration": 120,
                        "is_selected": False,
                        "source": source,
                        "confidence": confidence,
                    "fetched_at": fetched_at,
                    "summary": summary,
                    "image_url": image_url,
                    "deeplink": deeplink,
                }
            )

        if len(places) < target_count:
            for candidate in otm_candidates:
                xid = str(_first_value(candidate.get("xid"), fallback=""))
                if not xid or xid in used_xids:
                    continue
                lat = float(_first_value(candidate.get("lat"), fallback=0.0))
                lng = float(_first_value(candidate.get("lng"), fallback=0.0))
                name = str(_first_value(candidate.get("name"), fallback="")).strip()
                if not name:
                    continue
                dedupe_key = (_normalize_text(name), int(round(lat * 1000)), int(round(lng * 1000)))
                if dedupe_key in dedupe_keys:
                    continue
                dedupe_keys.add(dedupe_key)
                places.append(
                    {
                        "external_id": f"OTM-{xid}",
                        "name": name[:120],
                        "category": str(_first_value(str(candidate.get("kinds", "")).split(",")[0], fallback="atracao"))[:50],
                        "lat": lat,
                        "lng": lng,
                        "opening_hours_json": _normalize_opening_hours(candidate.get("opening_hours")),
                        "rating": min(5.0, 3.8 + _safe_float(_first_value(candidate.get("rate"), fallback=0.0)) * 0.35),
                        "estimated_duration": 120,
                        "is_selected": False,
                        "source": "opentripmap",
                        "confidence": 0.79,
                        "fetched_at": fetched_at,
                        "summary": str(_first_value(candidate.get("summary"), fallback=""))[:400],
                        "image_url": _first_value(candidate.get("image_url")),
                        "deeplink": f"https://opentripmap.com/en/card/{xid}",
                    }
                )
                if len(places) >= target_count:
                    break

        places.sort(
            key=lambda row: (
                1 if row.get("image_url") else 0,
                1 if row.get("summary") else 0,
                float(row.get("rating") or 0.0),
            ),
            reverse=True,
        )
        return places[:target_count]


def get_travel_provider() -> TravelProvider:
    return TravelProvider()


def replace_places(trip_id: int, payloads: list[dict]) -> list[Place]:
    return [Place(trip_id=trip_id, **payload) for payload in payloads]
