from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.entities import Trip, User
from app.services.llm import openrouter_chat
from app.services.providers import get_travel_provider
from app.services.routing import estimate_route
from app.services.weather import refresh_trip_weather


def main() -> int:
    provider = get_travel_provider()
    today = date.today()
    search_trip = Trip(
        id=1,
        user_id=1,
        destination="Rio de Janeiro",
        origin_city="Sao Paulo",
        currency="BRL",
        locale="pt-BR",
        start_date=today + timedelta(days=14),
        end_date=today + timedelta(days=17),
        budget=Decimal("2500.00"),
        style="economico",
        interests=["cultura", "gastronomia", "natureza"],
    )
    weather_trip = Trip(
        id=2,
        user_id=1,
        destination="Rio de Janeiro",
        origin_city="Sao Paulo",
        currency="BRL",
        locale="pt-BR",
        start_date=today + timedelta(days=1),
        end_date=today + timedelta(days=4),
        budget=Decimal("2500.00"),
        style="economico",
        interests=["cultura", "gastronomia", "natureza"],
    )

    payload: dict[str, object] = {}
    failures: list[str] = []

    try:
        flights = provider.search_flights(search_trip)
        hotels = provider.search_hotels(search_trip)
        places = provider.search_places(search_trip)
        if not flights or not hotels or not places:
            raise RuntimeError("One or more travel search providers returned no usable results.")
        payload["serpapi_flights"] = {
            "status": "ok",
            "count": len(flights),
            "first_price": str(flights[0]["price"]),
            "first_route": flights[0]["legs_json"][0],
        }
        payload["serpapi_hotels"] = {
            "status": "ok",
            "count": len(hotels),
            "first_name": hotels[0]["name"],
            "first_total_price": str(hotels[0]["total_price"]),
        }
        payload["places"] = {
            "status": "ok",
            "count": len(places),
            "first_name": places[0]["name"],
            "first_source": places[0]["source"],
        }
    except Exception as exc:
        payload["search"] = {"status": "error", "detail": str(exc)}
        failures.append("search")
        flights = []
        hotels = []
        places = []

    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with Session() as db:
        user = User(name="Local Traveler", email="local@balatravel.app", password_hash="local-only")
        db.add(user)
        db.commit()
        db.refresh(user)

        weather_trip.user_id = user.id
        db.add(weather_trip)
        db.commit()
        db.refresh(weather_trip)

        if hotels and places:
            try:
                route_duration_min, route_distance_km, route_source = estimate_route(
                    db,
                    weather_trip,
                    (hotels[0]["lat"], hotels[0]["lng"]),
                    (places[0]["lat"], places[0]["lng"]),
                )
                payload["google_routes"] = {
                    "status": "ok",
                    "duration_min": route_duration_min,
                    "distance_km": route_distance_km,
                    "source": route_source,
                }
            except Exception as exc:
                payload["google_routes"] = {"status": "error", "detail": str(exc)}
                failures.append("google_routes")

            try:
                weather_rows = refresh_trip_weather(
                    db,
                    weather_trip,
                    [SimpleNamespace(lat=places[0]["lat"], lng=places[0]["lng"])],
                )
                payload["openweather"] = {
                    "status": "ok",
                    "count": len(weather_rows),
                    "first_date": weather_rows[0].forecast_date.isoformat(),
                    "first_condition": weather_rows[0].condition_label,
                    "source": weather_rows[0].source,
                }
            except Exception as exc:
                payload["openweather"] = {"status": "error", "detail": str(exc)}
                failures.append("openweather")

    try:
        llm_reply = openrouter_chat(
            "Responda em uma frase curta: qual a capital da Franca?",
            system_prompt="You are a concise assistant. Reply in Brazilian Portuguese only.",
            temperature=0,
        )
        payload["openrouter"] = {"status": "ok", "preview": llm_reply[:120]}
    except Exception as exc:
        payload["openrouter"] = {"status": "error", "detail": str(exc)}
        failures.append("openrouter")

    payload["summary"] = {
        "overall_status": "ok" if not failures else "error",
        "failed_integrations": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
