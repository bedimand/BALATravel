# BALATravel

Autonomous AI travel planner that builds complete, day-by-day itineraries using an LLM agent with tool-calling capabilities. The agent searches for places, reasons about geography, opening hours, weather, and traveler preferences, then constructs a schedule a real person can follow.

## How It Works

The core of BALATravel is **CentralMind** — an autonomous agent loop that:

1. **Searches** for places via Google Maps (SerpApi) and OpenTripMap, pulling restaurants, museums, landmarks, markets, churches, parks, and nightlife
2. **Reasons** about the traveler's profile (interests, pace, dietary restrictions, mobility) and trip context (dates, budget, accommodation location, weather forecast)
3. **Builds the itinerary** activity by activity using `place_item` calls — deciding what goes where, for how long, and why
4. **Self-checks** the schedule before finalizing: verifying lunch/dinner exist, no gaps, no duplicate places, geographic flow makes sense
5. **Self-corrects** when it catches issues — removing bad placements and replacing them

The LLM owns all scheduling decisions. There is no deterministic algorithm — the agent decides durations, activity order, geographic clustering, and category diversity based on its understanding of travel.

## Architecture

```
backend/
  app/
    api/routes/       # REST endpoints (trips, auth, agent, share)
    core/             # Config, database, security
    models/           # SQLAlchemy entities (Trip, Place, ItineraryVersion, etc.)
    schemas/          # Pydantic request/response models
    services/
      central_mind.py   # Autonomous agent loop (CentralMind)
      tool_registry.py  # 20 tools the agent can call
      agent.py          # AgentCoordinator (reactive message handling)
      agent_tools.py    # Tool implementations (search, place, edit)
      workflow.py       # Multi-step workflow orchestration
      providers.py      # Google Maps, SerpApi, OpenTripMap adapters
      routing.py        # Google Routes API integration
      weather.py        # OpenWeather forecast
      llm.py            # LLM chat abstraction (OpenAI-compatible)
      planner.py        # Map payload builder
      exports.py        # PDF/JSON export
      shares.py         # Shareable trip links

frontend/
  app/
    page.tsx            # Landing page
    login/              # Auth
    signup/
    profile/            # User preferences
    trips/new/          # Trip creation wizard
    trips/[id]/         # Planner workspace (map + itinerary)
    history/            # Past trips
```

## Agent Tools

The LLM agent has access to 20 tools:

| Tool | Purpose |
|------|---------|
| `search_places_by_interest` | Search Google Maps with descriptive queries |
| `search_places_general` | Broad OSM + OpenTripMap discovery |
| `get_weather_forecast` | Weather conditions for trip dates |
| `estimate_route` | Travel time between two coordinates |
| `list_saved_places` | Review all saved places with hours, location, ratings |
| `get_day_context` | Weather + placed items + remaining places sorted by distance |
| `start_itinerary` | Create empty schedule |
| `place_item` | Place an activity at a specific date/time (auto-calculates travel) |
| `get_day_schedule` | View items placed on a specific day |
| `finalize_itinerary` | Validate and finalize the schedule |
| `update_item` / `remove_item` / `insert_item` | Edit existing items |
| `reorder_day` | Optimize a day's sequence by proximity |
| `check_route` | Check travel time before committing |
| `finish` | Signal completion |

## Quick Start

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

### Environment

Copy `backend/.env` and configure:

```env
# LLM (OpenAI-compatible endpoint)
OPENAI_BASE_URL=https://your-llm-endpoint/openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0

# Search providers
SERPAPI_API_KEY=...          # Google Maps place search
OPENTRIPMAP_API_KEY=...     # Place enrichment
GOOGLE_ROUTES_API_KEY=...   # Travel time calculation
OPENWEATHER_API_KEY=...     # Weather forecasts

# Optional: OpenRouter as fallback LLM
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=...
```

Frontend: set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api` in `frontend/.env.local`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Get JWT tokens |
| POST | `/api/trips` | Create a trip |
| POST | `/api/trips/{id}/search` | Search flights, hotels, places |
| POST | `/api/trips/{id}/itinerary/generate` | Trigger autonomous planning |
| POST | `/api/trips/{id}/itinerary/replan` | Rebuild itinerary |
| POST | `/api/trips/{id}/agent/message` | Chat with the agent (reactive edits) |
| GET | `/api/trips/{id}/workspace` | Full workspace state |
| GET | `/api/trips/{id}/map` | Map markers + routes |
| POST | `/api/trips/{id}/export/{format}` | Export PDF/JSON |
| POST | `/api/trips/{id}/share` | Create shareable link |

## How the Agent Plans

When triggered, the CentralMind agent follows this structure:

```
Search (4-6 diverse queries)
  → List saved places (review the pool)
    → Get weather forecast
      → Start itinerary
        → For each day:
            Get day context (weather, proximity, remaining places)
            Place entire day in one batch:
              Morning: cultural sites, museums (09:00-12:00)
              Lunch: restaurant (12:30-14:00)
              Afternoon: markets, churches, parks (14:30-18:00)
              Evening filler: walk, viewpoint, bar (18:00-19:30)
              Dinner: restaurant (19:30-21:00)
        → Self-check all days
        → Fix issues
        → Finalize
```

The agent enforces:
- Lunch AND dinner every day
- No gaps >1h between activities
- No same-category back-to-back
- No repeated places across days
- Geographic clustering (minimize transit)
- All trip days covered (inclusive date range)

## Testing

```bash
cd backend
pytest tests/ -v
```

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy, SQLite
- **Frontend:** Next.js 15, React 19, MapLibre GL, TypeScript
- **LLM:** Any OpenAI-compatible endpoint (tested with Claude Sonnet 4.5 on Bedrock)
- **Search:** SerpApi (Google Maps), OpenTripMap, Nominatim
- **Routing:** Google Routes API
- **Weather:** OpenWeather API
