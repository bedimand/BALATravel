# BALATravel

Monorepo with a `FastAPI` backend and a `Next.js` frontend for BALATravel, a travel planning copilot.

## Structure

- `backend/`: Python API, planner engine, provider adapters, export/share logic, tests.
- `frontend/`: Next.js app with landing, auth, trip creation, history, profile, and planner workspace.

## Quick start

### Backend

```bash
cd backend
pip install -e .[dev]
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` if the backend is not running on `http://127.0.0.1:8000`.

## Environment

Use `backend/.env` for backend variables. The backend also supports a root `.env` if you prefer to centralize shared values.

Use `frontend/.env.local` for frontend variables. A starter file is included at `frontend/.env.local.example`.

Main integrations:

- `SERPAPI_API_KEY` enables live flight and hotel search (Google Flights + Google Hotels).
- `OPENTRIPMAP_API_KEY` enriches attractions from OSM seed results.
- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` enable LLM summaries.

Trip-specific search settings such as origin airport, currency, and locale now come from trip data, not environment variables.

Travel search is live-only. `/api/trips/{id}/search` returns partial data with warnings when one provider fails, and returns `502` only when all provider domains fail.
