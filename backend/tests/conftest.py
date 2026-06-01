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

    _central_mind_step = {"n": 0}

    def fake_central_mind_llm_chat(prompt, **kwargs):
        """Returns agent tool-call JSON for the CentralMind loop."""
        import json as _json
        prompt_text = _json.dumps(prompt) if isinstance(prompt, list) else prompt
        _central_mind_step["n"] += 1

        if "Places saved: 0" in prompt_text:
            return _json.dumps({
                "reasoning": "Search for places.",
                "tool_calls": [{"name": "search_places_general", "params": {}}],
            })
        if "Active itinerary: None" in prompt_text and "start_itinerary" not in prompt_text:
            return _json.dumps({
                "reasoning": "Start itinerary and place items.",
                "tool_calls": [{"name": "start_itinerary", "params": {}}],
            })
        if "start_itinerary" in prompt_text and "item_count" not in prompt_text:
            return _json.dumps({
                "reasoning": "Place activities for the trip.",
                "tool_calls": [
                    {"name": "place_item", "params": {"title": "Cristo Redentor", "item_type": "tourist_attraction", "date": "2025-01-15", "start_time": "09:00", "end_time": "11:00", "lat": -22.9519, "lng": -43.2105}},
                    {"name": "place_item", "params": {"title": "Copacabana", "item_type": "beach", "date": "2025-01-15", "start_time": "14:00", "end_time": "17:00", "lat": -22.9711, "lng": -43.1822}},
                ],
            })
        if "finalize_itinerary" not in prompt_text and "item_count" not in prompt_text and "Active itinerary: " in prompt_text:
            return _json.dumps({
                "reasoning": "Finalize the itinerary.",
                "tool_calls": [{"name": "finalize_itinerary", "params": {"summary": "Roteiro de teste."}}],
            })
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

    monkeypatch.setattr("app.services.chat.llm_chat", fake_llm_chat)
    monkeypatch.setattr("app.services.central_mind.llm_chat", fake_central_mind_llm_chat)
    monkeypatch.setattr("app.services.routing.estimate_route", fake_estimate_route)
    monkeypatch.setattr("app.services.weather.refresh_trip_weather", fake_refresh_trip_weather)
    monkeypatch.setattr("app.services.providers.TravelProvider.search_places", fake_provider_search_places)
