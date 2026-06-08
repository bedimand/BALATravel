# Deploying BALATravel

The backend (FastAPI), frontend (Next.js), and a managed Postgres database all
deploy to **Render** from this one repo, defined in [`render.yaml`](./render.yaml).

| Component | Render name | Type | Notes |
|-----------|-------------|------|-------|
| Backend (FastAPI) | `balatravel-api` | Web (Python) | Persistent process — runs the background workflow threads |
| Frontend (Next.js) | `balatravel-web` | Web (Node) | Runs `next start` (server-rendered `/trips/[id]` needs a live Node server) |
| Database | `balatravel-db` | Postgres | Managed; persists across deploys (free tier expires in 30 days, see §3) |

Everything runs on Render's **free tier** (no cost). See §3 for the database
caveat.

> **Why one host for both?** Render runs persistent Node *and* Python services,
> so a single Blueprint deploys both together — one dashboard, one repo. (Netlify
> and AWS Amplify can host the Next.js frontend, but neither can host this
> backend: their serverless functions can't run the long-lived
> `threading.Thread` workers or keep a SQLite file.)

---

## 1. Deploy the Blueprint

1. Push this repo to GitHub.
2. Render Dashboard → **New → Blueprint** → connect this repo. Render reads
   `render.yaml` and proposes the two web services (`balatravel-api`,
   `balatravel-web`) plus the Postgres database (`balatravel-db`). The database's
   connection string is injected into the backend's `DATABASE_URL` automatically —
   you don't set it by hand.
3. It will prompt for the env vars marked `sync: false` (they're intentionally
   not in the repo). You can leave the two cross-reference URLs blank for now and
   set them in step 2 — fill in the rest:
   - **Backend:** `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`,
     `SERPAPI_API_KEY`, `GOOGLE_ROUTES_API_KEY`, `OPENWEATHER_API_KEY`,
     `OPENTRIPMAP_API_KEY` (optional). `SECRET_KEY` is auto-generated.
   - **Frontend:** `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` (and `NEXT_PUBLIC_API_URL`,
     set in step 2).
4. Apply. Both services build. Note the two URLs Render assigns, e.g.
   - `https://balatravel-api.onrender.com`
   - `https://balatravel-web.onrender.com`
5. Check the backend: `https://balatravel-api.onrender.com/health` → `{"status":"ok"}`.

---

## 2. Wire the two services together

The browser talks to the backend directly, so this is a normal cross-origin
setup — both URLs must be **public** ones, and CORS must allow the frontend.

1. **Frontend → backend.** On `balatravel-web`, set
   `NEXT_PUBLIC_API_URL = https://balatravel-api.onrender.com/api`
   (note the **`/api`** suffix). This value is baked in at build time, so trigger
   a redeploy of `balatravel-web` after setting it.
2. **Backend → allow the frontend.** On `balatravel-api`, set
   `CORS_ORIGINS = https://balatravel-web.onrender.com,http://localhost:3000`
   (comma-separated, no trailing slash; keep localhost for local dev). Render
   redeploys automatically.

> Do **not** use Render's internal service URL for `NEXT_PUBLIC_API_URL` — that
> URL only resolves server-side inside Render, but these fetches run in the
> user's browser. Always use the public `onrender.com` URL.

---

## 3. Database — managed Postgres (read this)

The Blueprint provisions a managed Postgres database (`balatravel-db`) and injects
its connection string into the backend's `DATABASE_URL`. Data **persists across
deploys and restarts** — accounts and trips stick around. The schema auto-creates
on first boot (`Base.metadata.create_all`). The app rewrites Render's
`postgres://` URL to the `postgresql+psycopg://` form the driver expects, so no
manual URL editing is needed.

> ⚠️ **Render's free Postgres tier is deleted ~30 days after creation** (Render
> emails a warning first). For a project that must outlive a month:
> - **Upgrade `balatravel-db`** to a paid plan in the Render dashboard, or
> - **Switch to an external free Postgres** (Neon / Supabase, which don't expire):
>   create a database there, remove the `databases:` block + the `fromDatabase`
>   wiring from `render.yaml`, and set `DATABASE_URL` on `balatravel-api` to that
>   provider's connection string. No code change — the driver and URL handling are
>   already in place.

> Free Render **web services** also sleep after ~15 min idle (first request after
> waking takes ~30–50s). The database does not sleep, so data is safe; only the
> first request is slow.

> **Local development** still uses SQLite by default (`sqlite:///./balatravel.db`
> from `.env`) — the Postgres setup only applies where `DATABASE_URL` points at
> Postgres. Both paths are supported by the same code.

---

## 4. Verify end-to-end

1. Open the `balatravel-web` URL → **Criar conta** → sign up.
2. You should land on **Minhas Viagens** (the JWT is stored in `localStorage`).
3. Create a trip; reload — the session and the trip persist.
4. In browser devtools → Network, confirm requests hit your
   `balatravel-api.onrender.com/api/...` URL and return 200 (no CORS errors).
5. Log out (Minha conta → Sair) → you're sent back to `/login`.

### Common issues
- **CORS error in console** → `CORS_ORIGINS` on the backend doesn't exactly match
  the frontend origin (check `https`, no trailing slash).
- **Frontend calls `localhost:8000`** → `NEXT_PUBLIC_API_URL` wasn't set before
  the frontend build; set it and redeploy `balatravel-web`.
- **Data gone after ~30 days** → the free Postgres tier was deleted; see §3 to
  upgrade or move to an external Postgres.
- **First request very slow** → the free web service was asleep; it wakes in
  ~30–50s (the database itself does not sleep).
- **Backend won't start / DB connection errors** → confirm `balatravel-db`
  finished provisioning before the backend deployed; redeploy `balatravel-api`.

---

## Environment variable reference

**Backend (`balatravel-api`):** `DATABASE_URL` (auto-injected from
`balatravel-db`), `SECRET_KEY`, `CORS_ORIGINS`, `OPENAI_API_KEY`,
`OPENAI_BASE_URL`, `OPENAI_MODEL`, `SERPAPI_API_KEY`, `GOOGLE_ROUTES_API_KEY`,
`OPENWEATHER_API_KEY`, `OPENTRIPMAP_API_KEY`. See [`.env.example`](./.env.example).

**Frontend (`balatravel-web`):** `NEXT_PUBLIC_API_URL`,
`NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`.
See [`frontend/.env.local.example`](./frontend/.env.local.example).
