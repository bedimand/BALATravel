# Deploying BALATravel

Both the backend (FastAPI) and frontend (Next.js) deploy to **Render** from this
one repo, as two web services defined in [`render.yaml`](./render.yaml).

| Service | Render name | Runtime | Notes |
|---------|-------------|---------|-------|
| Backend (FastAPI) | `balatravel-api` | Python | Persistent process — runs the background workflow threads; stores data in SQLite on a persistent disk |
| Frontend (Next.js) | `balatravel-web` | Node | Runs `next start` (server-rendered `/trips/[id]` needs a live Node server) |

> **Why one host for both?** Render runs persistent Node *and* Python services,
> so a single Blueprint deploys both together — one dashboard, one repo. (Netlify
> would also work for the frontend, but it can't host this backend: its
> serverless functions can't run the long-lived `threading.Thread` workers or
> keep a SQLite file.)

---

## 1. Deploy the Blueprint

1. Push this repo to GitHub.
2. Render Dashboard → **New → Blueprint** → connect this repo. Render reads
   `render.yaml` and proposes **both** services (`balatravel-api` and
   `balatravel-web`).
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

## 3. Database persistence (read this)

`render.yaml` mounts a **persistent disk** at `/var/data` on the backend and
points `DATABASE_URL` at `sqlite:////var/data/balatravel.db`, so accounts and
trips survive redeploys. **Render disks require a paid instance**
(`plan: starter`, ~$7/mo).

**Free-tier fallback** (data resets on every deploy — fine for a throwaway demo):
in `render.yaml`, on `balatravel-api` set `plan: free`, delete the `disk:` block,
and change `DATABASE_URL` to `sqlite:////tmp/balatravel.db`. The schema
auto-creates on boot, so the app still works — it just starts empty after each
deploy/restart.

> Free Render services also **sleep after ~15 min idle**; the first request after
> waking takes ~30–50s. This applies to both the API and the web service on the
> free plan.

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
- **Data gone after a redeploy** → you're on the free tier without a disk (see §3).
- **First request very slow** → free service was asleep; it wakes in ~30–50s.

---

## Environment variable reference

**Backend (`balatravel-api`):** `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS`,
`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `SERPAPI_API_KEY`,
`GOOGLE_ROUTES_API_KEY`, `OPENWEATHER_API_KEY`, `OPENTRIPMAP_API_KEY`.
See [`.env.example`](./.env.example).

**Frontend (`balatravel-web`):** `NEXT_PUBLIC_API_URL`,
`NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`.
See [`frontend/.env.local.example`](./frontend/.env.local.example).
