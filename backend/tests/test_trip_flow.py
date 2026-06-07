from datetime import UTC, date, datetime

import app.services.agent as agent_service
import app.services.agent_tools as agent_tools
from app.services.providers import ProviderIntegrationError


def _mock_flights(_trip):
    now = datetime.now(UTC)
    return [
        {
            "provider_ref": "LIVE-FLT-1",
            "price": "890.00",
            "currency": "BRL",
            "legs_json": [
                {
                    "departure_airport": "GRU",
                    "departure_time": "2026-04-10T08:00:00",
                    "arrival_airport": "GIG",
                    "arrival_time": "2026-04-10T09:00:00",
                }
            ],
            "baggage_summary": "Consulte detalhes na oferta",
            "deeplink": "https://www.google.com/travel/flights",
            "source": "serpapi",
            "confidence": 0.95,
            "fetched_at": now,
        },
        {
            "provider_ref": "LIVE-FLT-2",
            "price": "980.00",
            "currency": "BRL",
            "legs_json": [
                {
                    "departure_airport": "CGH",
                    "departure_time": "2026-04-10T11:00:00",
                    "arrival_airport": "GIG",
                    "arrival_time": "2026-04-10T12:10:00",
                }
            ],
            "baggage_summary": "Consulte detalhes na oferta",
            "deeplink": "https://www.google.com/travel/flights",
            "source": "serpapi",
            "confidence": 0.94,
            "fetched_at": now,
        },
    ]


def _mock_hotels(_trip):
    now = datetime.now(UTC)
    return [
        {
            "provider_ref": "LIVE-HTL-1",
            "name": "Hotel Atlântico Rio",
            "nightly_price": "320.00",
            "total_price": "960.00",
            "rating": 4.4,
            "lat": -22.911,
            "lng": -43.182,
            "deeplink": "https://www.google.com/travel/hotels",
            "source": "serpapi",
            "confidence": 0.93,
            "fetched_at": now,
        },
        {
            "provider_ref": "LIVE-HTL-2",
            "name": "Copacabana Suites",
            "nightly_price": "380.00",
            "total_price": "1140.00",
            "rating": 4.6,
            "lat": -22.967,
            "lng": -43.182,
            "deeplink": "https://www.google.com/travel/hotels",
            "source": "serpapi",
            "confidence": 0.94,
            "fetched_at": now,
        },
    ]


def _mock_places(_trip):
    now = datetime.now(UTC)
    hours = {
        "mon": ["09:00-18:00"],
        "tue": ["09:00-18:00"],
        "wed": ["09:00-18:00"],
        "thu": ["09:00-18:00"],
        "fri": ["09:00-18:00"],
        "sat": ["09:00-18:00"],
        "sun": ["09:00-18:00"],
    }
    return [
        {
            "external_id": "OSM-1",
            "name": "Cristo Redentor",
            "category": "tourist_attraction",
            "lat": -22.9519,
            "lng": -43.2105,
            "opening_hours_json": hours,
            "rating": 4.8,
            "estimated_duration": 120,
            "source": "osm-nominatim",
            "confidence": 0.75,
            "fetched_at": now,
            "summary": "Atracao turistica no Rio de Janeiro.",
            "deeplink": "https://www.openstreetmap.org/",
        },
        {
            "external_id": "OSM-2",
            "name": "Pao de Acucar",
            "category": "tourist_attraction",
            "lat": -22.9486,
            "lng": -43.1566,
            "opening_hours_json": hours,
            "rating": 4.7,
            "estimated_duration": 120,
            "source": "osm-nominatim",
            "confidence": 0.75,
            "fetched_at": now,
            "summary": "Atracao turistica no Rio de Janeiro.",
            "deeplink": "https://www.openstreetmap.org/",
        },
        {
            "external_id": "OSM-3",
            "name": "Jardim Botanico",
            "category": "park",
            "lat": -22.9663,
            "lng": -43.2231,
            "opening_hours_json": hours,
            "rating": 4.6,
            "estimated_duration": 120,
            "source": "osm-nominatim",
            "confidence": 0.74,
            "fetched_at": now,
            "summary": "Parque urbano no Rio de Janeiro.",
            "deeplink": "https://www.openstreetmap.org/",
        },
        {
            "external_id": "OSM-4",
            "name": "Museu do Amanha",
            "category": "museum",
            "lat": -22.8941,
            "lng": -43.1796,
            "opening_hours_json": hours,
            "rating": 4.5,
            "estimated_duration": 120,
            "source": "osm-nominatim",
            "confidence": 0.73,
            "fetched_at": now,
            "summary": "Museu de ciencias no Rio de Janeiro.",
            "deeplink": "https://www.openstreetmap.org/",
        },
        {
            "external_id": "OSM-5",
            "name": "Arpoador",
            "category": "viewpoint",
            "lat": -22.9879,
            "lng": -43.1919,
            "opening_hours_json": hours,
            "rating": 4.4,
            "estimated_duration": 90,
            "source": "osm-nominatim",
            "confidence": 0.72,
            "fetched_at": now,
            "summary": "Ponto de observacao do por do sol.",
            "deeplink": "https://www.openstreetmap.org/",
        },
    ]


def _mock_places_without_hours(_trip):
    now = datetime.now(UTC)
    return [
        {
            "external_id": "OSM-X1",
            "name": "Praia Central",
            "category": "beach",
            "lat": -22.95,
            "lng": -43.19,
            "opening_hours_json": {},
            "rating": 4.6,
            "estimated_duration": 120,
            "source": "osm-nominatim",
            "confidence": 0.71,
            "fetched_at": now,
            "summary": "Praia para manha e tarde.",
            "deeplink": "https://www.openstreetmap.org/",
        },
        {
            "external_id": "OSM-X2",
            "name": "Mirante Urbano",
            "category": "viewpoint",
            "lat": -22.97,
            "lng": -43.20,
            "opening_hours_json": {},
            "rating": 4.5,
            "estimated_duration": 90,
            "source": "osm-nominatim",
            "confidence": 0.7,
            "fetched_at": now,
            "summary": "Mirante com vista da cidade.",
            "deeplink": "https://www.openstreetmap.org/",
        },
        {
            "external_id": "OSM-X3",
            "name": "Museu Livre",
            "category": "museum",
            "lat": -22.90,
            "lng": -43.18,
            "opening_hours_json": {},
            "rating": 4.3,
            "estimated_duration": 120,
            "source": "osm-nominatim",
            "confidence": 0.69,
            "fetched_at": now,
            "summary": "Museu com acervo moderno.",
            "deeplink": "https://www.openstreetmap.org/",
        },
    ]


def _select_first_flight_and_hotel(client, auth_headers, trip_id: int) -> None:
    trip_payload = client.get(f"/api/trips/{trip_id}", headers=auth_headers).json()
    flight_id = trip_payload["flights"][0]["id"]
    hotel_id = trip_payload["hotels"][0]["id"]
    choose_flight = client.patch(f"/api/trips/{trip_id}", headers=auth_headers, json={"selected_flight_id": flight_id})
    assert choose_flight.status_code == 200
    choose_hotel = client.patch(f"/api/trips/{trip_id}", headers=auth_headers, json={"selected_hotel_id": hotel_id})
    assert choose_hotel.status_code == 200


def test_trip_search_generate_edit_export_and_share(client, auth_headers, monkeypatch):
    monkeypatch.setattr(agent_tools.provider, "search_flights", _mock_flights)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _mock_hotels)
    monkeypatch.setattr(agent_tools.provider, "search_places", _mock_places)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "currency": "BRL",
            "locale": "pt-BR",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    assert trip.status_code == 201
    trip_id = trip.json()["id"]
    assert trip.json()["origin_city"] == "Sao Paulo"
    assert trip.json()["currency"] == "BRL"
    assert trip.json()["locale"] == "pt-BR"

    search = client.post(f"/api/trips/{trip_id}/search", headers=auth_headers)
    assert search.status_code == 200
    search_payload = search.json()
    assert len(search_payload["flights"]) >= 2
    assert len(search_payload["hotels"]) >= 2
    assert len(search_payload["places"]) >= 5
    _select_first_flight_and_hotel(client, auth_headers, trip_id)

    itinerary = client.post(f"/api/trips/{trip_id}/itinerary/generate", headers=auth_headers)
    assert itinerary.status_code == 202
    # Background run executed inline (see conftest). Read the built itinerary back.
    workspace = client.get(f"/api/trips/{trip_id}/workspace", headers=auth_headers).json()
    itinerary_payload = {"itinerary": workspace["active_itinerary"]}
    assert itinerary_payload["itinerary"]["items"]

    first_item = itinerary_payload["itinerary"]["items"][0]
    patch = client.patch(
        f"/api/trips/{trip_id}/itinerary/items/{first_item['id']}",
        headers=auth_headers,
        json={"notes": "Comecar aqui para evitar fila", "title": "Centro Historico Premium"},
    )
    assert patch.status_code == 200
    assert patch.json()["title"] == "Centro Historico Premium"

    map_response = client.get(f"/api/trips/{trip_id}/map", headers=auth_headers)
    assert map_response.status_code == 200
    assert len(map_response.json()["markers"]) >= len(itinerary_payload["itinerary"]["items"])

    export = client.post(f"/api/trips/{trip_id}/export", headers=auth_headers)
    assert export.status_code == 200
    assert export.json()["file_url"].endswith(".pdf")

    share = client.post(f"/api/trips/{trip_id}/share-links", headers=auth_headers)
    assert share.status_code == 200
    public_view = client.get(share.json()["public_url"])
    assert public_view.status_code == 200
    assert public_view.json()["destination"] == "Rio de Janeiro"


def test_chat_suggests_and_applies_change(client, auth_headers, monkeypatch):
    monkeypatch.setattr(agent_tools.provider, "search_flights", _mock_flights)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _mock_hotels)
    monkeypatch.setattr(agent_tools.provider, "search_places", _mock_places)
    monkeypatch.setattr(agent_service, "build_chat_response", lambda *_args, **_kwargs: {
        "assistant_message": "Sugiro ajustar o primeiro bloco.",
        "proposed_changes": [
            {
                "type": "update_item",
                "title": "Ajustar primeiro item",
                "reason": "Evitar fila no horario de pico.",
                "payload": {"item_id": 1, "notes": "Chegar 20 min antes."},
            }
        ],
        "warnings": [],
    })

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "currency": "USD",
            "locale": "en-US",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    trip_id = trip.json()["id"]
    client.post(f"/api/trips/{trip_id}/search", headers=auth_headers)
    _select_first_flight_and_hotel(client, auth_headers, trip_id)
    generated = client.post(f"/api/trips/{trip_id}/itinerary/generate", headers=auth_headers)
    assert generated.status_code == 202
    workspace = client.get(f"/api/trips/{trip_id}/workspace", headers=auth_headers).json()
    first_item_id = workspace["active_itinerary"]["items"][0]["id"]

    chat = client.post(
        f"/api/trips/{trip_id}/chat",
        headers=auth_headers,
        json={"message": "Pode melhorar o primeiro horario?"},
    )
    assert chat.status_code == 200
    proposal = chat.json()["proposed_changes"][0]
    proposal["payload"]["item_id"] = first_item_id

    applied = client.post(
        f"/api/trips/{trip_id}/chat/apply",
        headers=auth_headers,
        json={"change": proposal},
    )
    assert applied.status_code == 200
    changed_item = next(item for item in applied.json()["itinerary"]["items"] if item["notes"] == "Chegar 20 min antes.")
    assert changed_item["notes"] == "Chegar 20 min antes."


def test_trip_validation_rejects_invalid_dates(client, auth_headers):
    response = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Salvador",
            "origin_city": "Salvador",
            "start_date": "2026-04-10",
            "end_date": "2026-04-10",
            "budget": "1900.00",
            "style": "luxo",
            "interests": ["cultura"],
        },
    )
    assert response.status_code == 400


def test_trip_search_returns_502_when_any_provider_fails(client, auth_headers, monkeypatch):
    def _fail(_trip):
        raise ProviderIntegrationError("SERPAPI_API_KEY is missing. Live search cannot run without it.")

    monkeypatch.setattr(agent_tools.provider, "search_flights", _fail)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _mock_hotels)
    monkeypatch.setattr(agent_tools.provider, "search_places", _mock_places)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    trip_id = trip.json()["id"]
    search = client.post(f"/api/trips/{trip_id}/search", headers=auth_headers)
    assert search.status_code == 502
    assert "missing" in search.json()["detail"].lower() or "failed" in search.json()["detail"].lower() or "provider" in search.json()["detail"].lower()


def test_generate_blocks_when_search_context_is_incomplete(client, auth_headers, monkeypatch):
    def _fail(_trip):
        raise ProviderIntegrationError("Provider unavailable.")

    monkeypatch.setattr(agent_tools.provider, "search_flights", _mock_flights)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _mock_hotels)
    monkeypatch.setattr(agent_tools.provider, "search_places", _fail)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    trip_id = trip.json()["id"]

    # Generation is dispatched in the background (202). With places unavailable the
    # agent can't build a plan, so no active itinerary results and the workflow
    # does not reach the "ready" stage.
    generate = client.post(f"/api/trips/{trip_id}/itinerary/generate", headers=auth_headers)
    assert generate.status_code == 202
    workspace = client.get(f"/api/trips/{trip_id}/workspace", headers=auth_headers).json()
    assert workspace["active_itinerary"] is None
    assert workspace["workflow"]["current_stage"] != "ready"


def test_agent_can_plan_without_flights_or_hotels(client, auth_headers, monkeypatch):
    def _fail(_trip):
        raise ProviderIntegrationError("Provider unavailable.")

    monkeypatch.setattr(agent_tools.provider, "search_flights", _fail)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _fail)
    monkeypatch.setattr(agent_tools.provider, "search_places", _mock_places)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Cidade do Mexico",
            "origin_city": "Sao Paulo",
            "start_date": "2026-05-19",
            "end_date": "2026-05-23",
            "budget": "3500.00",
            "style": "economico",
            "interests": ["museus", "cultura"],
        },
    )
    trip_id = trip.json()["id"]

    message = client.post(
        f"/api/trips/{trip_id}/agent/messages",
        headers=auth_headers,
        json={"message": "Monte um roteiro completo para essa viagem."},
    )
    # Async dispatch (202), executed inline by the conftest fixture.
    assert message.status_code == 202
    assert message.json()["run_id"] is not None

    trip_after = client.get(f"/api/trips/{trip_id}", headers=auth_headers)
    assert trip_after.status_code == 200
    assert trip_after.json()["itinerary_versions"]


def test_trip_search_returns_502_when_all_providers_fail(client, auth_headers, monkeypatch):
    def _fail(_trip):
        raise ProviderIntegrationError("Provider unavailable.")

    monkeypatch.setattr(agent_tools.provider, "search_flights", _fail)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _fail)
    monkeypatch.setattr(agent_tools.provider, "search_places", _fail)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    trip_id = trip.json()["id"]
    search = client.post(f"/api/trips/{trip_id}/search", headers=auth_headers)
    assert search.status_code == 502


def test_itinerary_generation_uses_best_effort_when_hours_missing(client, auth_headers, monkeypatch):
    monkeypatch.setattr(agent_tools.provider, "search_flights", _mock_flights)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _mock_hotels)
    monkeypatch.setattr(agent_tools.provider, "search_places", _mock_places_without_hours)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    trip_id = trip.json()["id"]
    search = client.post(f"/api/trips/{trip_id}/search", headers=auth_headers)
    assert search.status_code == 200
    _select_first_flight_and_hotel(client, auth_headers, trip_id)

    itinerary = client.post(f"/api/trips/{trip_id}/itinerary/generate", headers=auth_headers)
    assert itinerary.status_code == 202
    workspace = client.get(f"/api/trips/{trip_id}/workspace", headers=auth_headers).json()
    active = workspace["active_itinerary"]
    assert active is not None
    assert active["items"]


def test_trip_defaults_currency_and_locale_from_user(client, auth_headers):
    response = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Recife",
            "origin_city": "Recife",
            "start_date": "2026-05-01",
            "end_date": "2026-05-04",
            "budget": "1800.00",
            "style": "economico",
            "interests": ["praia"],
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["origin_city"] == "Recife"
    assert payload["currency"] == "BRL"
    assert payload["locale"] == "pt-BR"


def test_agent_thread_and_rollback(client, auth_headers, monkeypatch):
    monkeypatch.setattr(agent_tools.provider, "search_flights", _mock_flights)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _mock_hotels)
    monkeypatch.setattr(agent_tools.provider, "search_places", _mock_places)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "currency": "BRL",
            "locale": "pt-BR",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    trip_id = trip.json()["id"]

    message = client.post(
        f"/api/trips/{trip_id}/agent/messages",
        headers=auth_headers,
        json={"message": "Busque opcoes e gere um roteiro completo para esta viagem."},
    )
    assert message.status_code == 200
    assert message.json()["assistant_message"]
    assert message.json()["itinerary_version_id"] is not None

    search_trip = client.get(f"/api/trips/{trip_id}", headers=auth_headers)
    assert search_trip.status_code == 200
    assert search_trip.json()["itinerary_versions"]

    generated = client.post(f"/api/trips/{trip_id}/itinerary/generate", headers=auth_headers)
    assert generated.status_code == 200

    thread = client.get(f"/api/trips/{trip_id}/agent/thread", headers=auth_headers)
    assert thread.status_code == 200
    thread_payload = thread.json()
    assert thread_payload["runs"]

    trip_after = client.get(f"/api/trips/{trip_id}", headers=auth_headers)
    versions = trip_after.json()["itinerary_versions"]
    active_version = next(version for version in versions if version["status"] == "active")

    rollback = client.post(
        f"/api/trips/{trip_id}/agent/rollback/{active_version['id']}",
        headers=auth_headers,
    )
    assert rollback.status_code == 200
    assert rollback.json()["applied_changes"]


def test_workflow_workspace_and_decision_flow(client, auth_headers, monkeypatch):
    monkeypatch.setattr(agent_tools.provider, "search_flights", _mock_flights)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _mock_hotels)
    monkeypatch.setattr(agent_tools.provider, "search_places", _mock_places)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "currency": "BRL",
            "locale": "pt-BR",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    assert trip.status_code == 201
    trip_id = trip.json()["id"]

    workspace = client.get(f"/api/trips/{trip_id}/workspace", headers=auth_headers)
    assert workspace.status_code == 200
    payload = workspace.json()
    assert payload["workflow"]["current_stage"] == "await_plan_approval"
    assert any(decision["kind"] == "plan_approval" for decision in payload["decisions"])
    assert any(artifact["artifact_type"] == "place_curation" for artifact in payload["artifacts"])
    assert any(artifact["artifact_type"] == "plan_draft" for artifact in payload["artifacts"])
    assert payload["active_itinerary"] is not None
    assert payload["weather"]
    assert payload["route_summary"]["total_travel_min"] >= 0

    plan_decision = next(decision for decision in payload["decisions"] if decision["kind"] == "plan_approval")
    approve_plan = client.post(
        f"/api/trips/{trip_id}/workflow/decisions/{plan_decision['id']}",
        headers=auth_headers,
        json={"action": "approve"},
    )
    assert approve_plan.status_code == 200
    approved_payload = approve_plan.json()
    assert approved_payload["workflow"]["current_stage"] == "active_trip"


def test_today_and_replan_day_workflow(client, auth_headers, monkeypatch):
    monkeypatch.setattr(agent_tools.provider, "search_flights", _mock_flights)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _mock_hotels)
    monkeypatch.setattr(agent_tools.provider, "search_places", _mock_places)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "currency": "BRL",
            "locale": "pt-BR",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    trip_id = trip.json()["id"]

    workspace = client.get(f"/api/trips/{trip_id}/workspace", headers=auth_headers).json()
    plan_decision = next(decision for decision in workspace["decisions"] if decision["kind"] == "plan_approval")
    approve_plan = client.post(
        f"/api/trips/{trip_id}/workflow/decisions/{plan_decision['id']}",
        headers=auth_headers,
        json={"action": "approve"},
    )
    assert approve_plan.status_code == 200
    approved_payload = approve_plan.json()
    assert approved_payload["workflow"]["current_stage"] == "active_trip"

    today = client.get(f"/api/trips/{trip_id}/today", headers=auth_headers)
    assert today.status_code == 200
    today_payload = today.json()
    expected_today = date.today().isoformat()
    assert today_payload["date"] == expected_today
    assert today_payload["quick_actions"]

    replan = client.post(
        f"/api/trips/{trip_id}/workflow/replan-day",
        headers=auth_headers,
        json={"date": "2026-04-10", "goal": "Reorganize este dia por causa de chuva."},
    )
    assert replan.status_code == 200
    replan_payload = replan.json()
    assert replan_payload["workflow"]["current_stage"] == "targeted_replan"
    change_decision = next(decision for decision in replan_payload["decisions"] if decision["kind"] == "change_approval")
    assert change_decision["status"] == "pending"


def test_place_selection_and_rebuild_plan(client, auth_headers, monkeypatch):
    monkeypatch.setattr(agent_tools.provider, "search_flights", _mock_flights)
    monkeypatch.setattr(agent_tools.provider, "search_hotels", _mock_hotels)
    monkeypatch.setattr(agent_tools.provider, "search_places", _mock_places)

    trip = client.post(
        "/api/trips",
        headers=auth_headers,
        json={
            "destination": "Rio de Janeiro",
            "origin_city": "Sao Paulo",
            "currency": "BRL",
            "locale": "pt-BR",
            "start_date": "2026-04-10",
            "end_date": "2026-04-13",
            "budget": "2500.00",
            "style": "economico",
            "interests": ["cultura", "gastronomia", "natureza"],
        },
    )
    trip_id = trip.json()["id"]

    places = client.get(f"/api/trips/{trip_id}/places", headers=auth_headers)
    assert places.status_code == 200
    place_rows = places.json()
    assert place_rows

    toggle = client.patch(
        f"/api/trips/{trip_id}/places/{place_rows[-1]['id']}",
        headers=auth_headers,
        json={"is_selected": False},
    )
    assert toggle.status_code == 200
    toggled_workspace = toggle.json()
    curated = next(artifact for artifact in toggled_workspace["artifacts"] if artifact["artifact_type"] == "place_curation")
    toggled_place = next(place for place in curated["payload_json"]["places"] if place["id"] == place_rows[-1]["id"])
    assert toggled_place["is_selected"] is False

    rebuild = client.post(f"/api/trips/{trip_id}/workflow/rebuild-plan", headers=auth_headers)
    assert rebuild.status_code == 200
    rebuilt_payload = rebuild.json()
    assert rebuilt_payload["workflow"]["current_stage"] == "await_plan_approval"
    assert any(decision["kind"] == "plan_approval" for decision in rebuilt_payload["decisions"])
