import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_DB = Path(__file__).parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"

from app.core.database import Base, engine  # noqa: E402
from app.models.entities import TripWeatherSnapshot  # noqa: E402
from app.main import app  # noqa: E402
from app.services.routing import RouteEstimateResult  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def run_background_threads_inline(monkeypatch):
    """Background work is dispatched via threading.Thread in the route handlers.
    In tests we run it synchronously so the response reflects the completed work
    and so a thread can't leak into the next test's DB teardown (the cause of the
    'no such table' races). Endpoints still return 202; callers read the result
    from the follow-up /workspace or response payload."""

    class _InlineThread:
        def __init__(self, target=None, args=(), kwargs=None, **_ignored):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            if self._target:
                self._target(*self._args, **self._kwargs)

        def join(self, timeout=None):
            return None

    monkeypatch.setattr("app.api.routes.trips.threading.Thread", _InlineThread)
    monkeypatch.setattr("app.api.routes.agent.threading.Thread", _InlineThread)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    return {}


@pytest.fixture(autouse=True)
def stub_non_search_external_services(monkeypatch):
    def fake_llm_chat(*_args, **_kwargs) -> str:
        return (
            '{"assistant_message":"Sugestao valida para testes.",'
            '"proposed_changes":[{"type":"update_item","title":"Ajustar item","reason":"Teste","payload":{"item_id":1,"notes":"Teste"}}],'
            '"warnings":[]}'
        )

    def fake_estimate_route(_db, _trip, _origin, _destination, _travel_mode=None):
        return RouteEstimateResult(duration_min=18, distance_km=5.2, source="google_routes", encoded_polyline=None)

    def fake_refresh_trip_weather(db, trip, places=None):
        db.query(TripWeatherSnapshot).filter(TripWeatherSnapshot.trip_id == trip.id).delete()
        days = max((trip.end_date - trip.start_date).days, 1)
        snapshots = []
        for offset in range(days):
            snapshots.append(
                TripWeatherSnapshot(
                    trip_id=trip.id,
                    forecast_date=trip.start_date.fromordinal(trip.start_date.toordinal() + offset),
                    condition_label="clear sky",
                    temp_min_c=22.0,
                    temp_max_c=29.0,
                    rain_probability=0.1,
                    is_outdoor_risky=False,
                    source="openweather",
                    fetched_at=datetime.now(UTC),
                )
            )
        db.add_all(snapshots)
        db.commit()
        return snapshots

    _central_mind_state = {"finalized": False}

    def fake_central_mind_llm_chat(prompt, **kwargs):
        """Deterministic agent for the CentralMind loop, driven by the REAL state
        the prompt reports (Places saved / Active itinerary), not by matching tool
        names in the prompt — those always appear in the AVAILABLE TOOLS list, which
        previously caused the mock to loop forever. The dates used here are derived
        from the trip range parsed out of the prompt so place_item stays in-range."""
        import json as _json
        import re as _re

        prompt_text = _json.dumps(prompt) if isinstance(prompt, list) else prompt

        # First trip day, parsed from "Dates: YYYY-MM-DD to YYYY-MM-DD" in the prompt.
        date_match = _re.search(r"Dates:\s*(\d{4}-\d{2}-\d{2})", prompt_text)
        day = date_match.group(1) if date_match else "2026-01-01"

        # 1. No places yet -> search.
        if "Places saved: 0" in prompt_text:
            return _json.dumps({
                "reasoning": "Search for places.",
                "tool_calls": [{"name": "search_places", "params": {"query": f"top attractions"}}],
            })

        # 2. Places exist but no itinerary started -> start it.
        if "Active itinerary: None" in prompt_text:
            return _json.dumps({
                "reasoning": "Start the itinerary.",
                "tool_calls": [{"name": "start_itinerary", "params": {}}],
            })

        active_match = _re.search(r"Active itinerary: Yes \(version \d+, (\d+) items\)", prompt_text)
        item_count = int(active_match.group(1)) if active_match else 0

        # 3. Itinerary started but empty -> place items (within the trip date range).
        if item_count == 0:
            return _json.dumps({
                "reasoning": "Place activities for the trip.",
                "tool_calls": [
                    {"name": "place_item", "params": {"title": "Cristo Redentor", "item_type": "tourist_attraction", "date": day, "start_time": "09:00", "end_time": "11:00", "lat": -22.9519, "lng": -43.2105}},
                    {"name": "place_item", "params": {"title": "Copacabana", "item_type": "beach", "date": day, "start_time": "14:00", "end_time": "17:00", "lat": -22.9711, "lng": -43.1822}},
                ],
            })

        # 4. Items placed but not yet finalized -> finalize once.
        if not _central_mind_state["finalized"]:
            _central_mind_state["finalized"] = True
            return _json.dumps({
                "reasoning": "Finalize the itinerary.",
                "tool_calls": [{"name": "finalize_itinerary", "params": {"summary": "Roteiro de teste."}}],
            })

        # 5. Done.
        return _json.dumps({
            "reasoning": "Done.",
            "tool_calls": [{"name": "finish", "params": {"message": "Roteiro pronto."}}],
        })

    def fake_provider_search_places(self, trip):
        now = datetime.now(UTC)
        hours = {"mon": ["09:00-18:00"], "tue": ["09:00-18:00"], "wed": ["09:00-18:00"],
                 "thu": ["09:00-18:00"], "fri": ["09:00-18:00"], "sat": ["09:00-18:00"], "sun": ["09:00-18:00"]}
        return [
            {"external_id": "OSM-1", "name": "Cristo Redentor", "category": "tourist_attraction",
             "lat": -22.9519, "lng": -43.2105, "opening_hours_json": hours, "rating": 4.8,
             "estimated_duration": 120, "source": "osm-nominatim", "confidence": 0.75,
             "fetched_at": now, "summary": "Atracao turistica.", "deeplink": "https://osm.org/"},
            {"external_id": "OSM-2", "name": "Pao de Acucar", "category": "tourist_attraction",
             "lat": -22.9486, "lng": -43.1566, "opening_hours_json": hours, "rating": 4.7,
             "estimated_duration": 120, "source": "osm-nominatim", "confidence": 0.75,
             "fetched_at": now, "summary": "Atracao turistica.", "deeplink": "https://osm.org/"},
            {"external_id": "OSM-3", "name": "Copacabana", "category": "beach",
             "lat": -22.9711, "lng": -43.1822, "opening_hours_json": hours, "rating": 4.6,
             "estimated_duration": 180, "source": "osm-nominatim", "confidence": 0.75,
             "fetched_at": now, "summary": "Praia famosa.", "deeplink": "https://osm.org/"},
        ]

    def fake_provider_search_by_interest(self, trip, query, max_results=20, center_lat=None, center_lng=None):
        # Same canned places; the agent-facing search_places tool calls this.
        return fake_provider_search_places(self, trip)[:max_results]

    monkeypatch.setattr("app.services.chat.llm_chat", fake_llm_chat)
    monkeypatch.setattr("app.services.central_mind.llm_chat", fake_central_mind_llm_chat)
    monkeypatch.setattr("app.services.routing.estimate_route", fake_estimate_route)
    monkeypatch.setattr("app.services.weather.refresh_trip_weather", fake_refresh_trip_weather)
    monkeypatch.setattr("app.services.providers.TravelProvider.search_places", fake_provider_search_places)
    monkeypatch.setattr("app.services.providers.TravelProvider.search_places_by_interest", fake_provider_search_by_interest)
