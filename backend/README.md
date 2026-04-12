# BALATravel Backend

FastAPI backend with JWT auth, trip planning endpoints, provider adapters, PDF export, and share links.

Main live integrations:

- `SerpApi` (`google_flights` and `google_hotels`) for flights/hotels
- `Nominatim (OSM)` + `OpenTripMap` for attractions and enrichment
- `OpenRouter` for itinerary summaries and chat analysis

Trip-specific search parameters such as origin airport, currency, and locale are stored on the trip itself rather than in environment variables.

No mock fallback is used for travel search.
`/api/trips/{id}/search` returns partial data with warnings when one provider fails and returns `502` only when all provider domains fail.

## Run

```bash
pip install -e .[dev]
uvicorn app.main:app --reload
```

Backend configuration lives in `backend/.env` by default when you run the API from the `backend/` directory.

## Test

```bash
pytest
```
