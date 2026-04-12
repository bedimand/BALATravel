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
    def fake_summarize_itinerary(*_args, **_kwargs) -> str:
        return "Resumo do roteiro gerado para testes."

    def fake_summarize_recommendations(*_args, **_kwargs) -> str:
        return "Sugestoes consolidadas para testes."

    def fake_openrouter_chat(*_args, **_kwargs) -> str:
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

    monkeypatch.setattr("app.services.planner.summarize_itinerary", fake_summarize_itinerary)
    monkeypatch.setattr("app.services.agent_tools.summarize_recommendations", fake_summarize_recommendations)
    monkeypatch.setattr("app.services.chat.openrouter_chat", fake_openrouter_chat)
    monkeypatch.setattr("app.services.agent.openrouter_chat", fake_openrouter_chat)
    monkeypatch.setattr("app.services.planner.estimate_route", fake_estimate_route)
    monkeypatch.setattr("app.services.workflow.refresh_trip_weather", fake_refresh_trip_weather)
