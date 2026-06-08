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

    def _trip_locale(self, trip: Trip) -> str:
        locale = str(getattr(trip, "locale", "") or "").strip()
        return locale or "pt-BR"

    def _trip_gl_hl(self, trip: Trip) -> tuple[str, str]:
        locale = self._trip_locale(trip)
        parts = locale.replace("_", "-").split("-")
        language = parts[0].lower() if parts and parts[0] else "pt"
        country = parts[1].lower() if len(parts) > 1 and parts[1] else "br"
        return country, f"{language}-{country.upper()}"

    def search_places_by_interest(self, trip: Trip, query: str, max_results: int = 20, center_lat: float | None = None, center_lng: float | None = None) -> list[dict]:
        """
        Search Google Maps for places matching a query string.
        If center_lat/lng are provided, biases the search near that location.

        The agent's query is sent to the provider VERBATIM. We deliberately do
        NOT rewrite or expand it: the agent writes its own descriptive and
        context-aware queries (e.g. "restaurants inside RioMar Shopping"), and
        silently mutating them would fight its intent and break anchored
        searches.
        """
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
            # A specific query that resolves to a single famous entity (a named
            # beach, mall, or landmark) comes back under place_results as one
            # object instead of a local_results list. Without this fallback the
            # city's most recognizable anchors are silently dropped.
            if not local_results:
                single = payload.get("place_results")
                if single:
                    local_results = [single]
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
