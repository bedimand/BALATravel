from __future__ import annotations

from datetime import UTC, date, datetime
import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Place, Trip, TripWeatherSnapshot


settings = get_settings()


class WeatherIntegrationError(RuntimeError):
    pass


def _weather_condition_label(code: int, description: str | None) -> str:
    if description:
        return description
    if 200 <= code < 600:
        return "rain"
    if 600 <= code < 700:
        return "snow"
    if 700 <= code < 800:
        return "fog"
    if code == 800:
        return "clear"
    if code > 800:
        return "clouds"
    return "unknown"


def refresh_trip_weather(db: Session, trip: Trip, places: list[Place] | None = None) -> list[TripWeatherSnapshot]:
    target_place = (places or [])[:1]
    lat = target_place[0].lat if target_place else None
    lng = target_place[0].lng if target_place else None
    if not settings.openweather_api_key:
        raise WeatherIntegrationError("OPENWEATHER_API_KEY is missing.")
    if lat is None or lng is None:
        raise WeatherIntegrationError("Cannot fetch weather without place coordinates.")

    db.execute(delete(TripWeatherSnapshot).where(TripWeatherSnapshot.trip_id == trip.id))
    db.flush()

    snapshots: list[TripWeatherSnapshot] = []
    try:
        response = httpx.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={
                "lat": lat,
                "lon": lng,
                "appid": settings.openweather_api_key,
                "units": "metric",
            },
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        grouped: dict[date, list[dict]] = {}
        for row in payload.get("list", []):
            forecast_date = datetime.fromtimestamp(int(row.get("dt", 0)), tz=UTC).date()
            if forecast_date < trip.start_date or forecast_date >= trip.end_date:
                continue
            grouped.setdefault(forecast_date, []).append(row)

        for forecast_date, rows in sorted(grouped.items()):
            primary = rows[len(rows) // 2]
            weather = (primary.get("weather") or [{}])[0]
            probabilities = [float(row.get("pop") or 0.0) for row in rows]
            mins = [float((row.get("main") or {}).get("temp_min")) for row in rows if (row.get("main") or {}).get("temp_min") is not None]
            maxes = [float((row.get("main") or {}).get("temp_max")) for row in rows if (row.get("main") or {}).get("temp_max") is not None]
            code = int(weather.get("id") or 0)
            probability = max(probabilities) if probabilities else 0.0
            snapshots.append(
                TripWeatherSnapshot(
                    trip_id=trip.id,
                    forecast_date=forecast_date,
                    condition_label=_weather_condition_label(code, weather.get("description")),
                    temp_min_c=min(mins) if mins else None,
                    temp_max_c=max(maxes) if maxes else None,
                    rain_probability=probability,
                    is_outdoor_risky=probability >= 0.45 or 200 <= code < 700,
                    source="openweather",
                    fetched_at=datetime.now(UTC),
                )
            )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        raise WeatherIntegrationError(f"OpenWeather HTTP {exc.response.status_code}: {detail}") from exc
    except WeatherIntegrationError:
        raise
    except Exception as exc:
        raise WeatherIntegrationError("OpenWeather request failed.") from exc

    if not snapshots:
        raise WeatherIntegrationError("OpenWeather returned no forecast rows for the trip window.")

    db.add_all(snapshots)
    db.commit()
    return list(
        db.scalars(
            select(TripWeatherSnapshot)
            .where(TripWeatherSnapshot.trip_id == trip.id)
            .order_by(TripWeatherSnapshot.forecast_date.asc())
        )
    )


def weather_by_date(snapshots: list[TripWeatherSnapshot]) -> dict[date, TripWeatherSnapshot]:
    return {row.forecast_date: row for row in snapshots}
