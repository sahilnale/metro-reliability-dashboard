# Metro Reliability Dashboard

An app that shows which LA Metro bus lines run on time, and when they tend
to run late — built from Metro's own live arrival data, not estimates.

Search a route or click a stop on the map to see its on-time percentage,
average delay, and a breakdown by hour of day.

## How it works

```
Metro's live WebSocket feed (real bus positions/delays)
        ↓
Ingestion worker — parses each message, computes
delay = predicted time − scheduled time
        ↓
Postgres (routes, stops, schedules, observations)
        ↓
FastAPI backend — SQL aggregations (on-time %, avg delay, by hour)
        ↓
React map app — search a route or click a stop, see the numbers
```

Route schedules are cached on first use rather than pre-loaded for all 120
routes up front — see `backend/worker/schedule_cache.py` for why.

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, Alembic
- **Ingestion:** Python + `websockets`, consuming Metro's real-time feed
- **Database:** PostgreSQL
- **Frontend:** React, TypeScript, Vite, Leaflet, Recharts
- **Infra:** Docker Compose (local), Vercel + Render + Neon + GitHub Actions (deployed) — all on free tiers

## Running locally

```bash
docker compose up -d db
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
alembic upgrade head

# Terminal 1: the API
uvicorn app.main:app --reload

# Terminal 2: the ingestion worker (holds a live connection, fine for local dev)
python -m worker.stream_worker
```

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Run the test suite with `pytest` from `backend/` (needs the Postgres
container running — it creates its own `metro_test` database).

## Deploying this for free

No platform gives away a free *always-on background worker* anymore, which
is normally what an ingestion pipeline like this needs. The workaround:
GitHub Actions is free and unmetered for public repos, so instead of one
long-lived process, `worker/scheduled_ingest.py` runs as a scheduled job
every ~10 minutes — connect, ingest a burst, exit.

| Piece | Service | Free tier |
|---|---|---|
| Database | [Neon](https://neon.tech) | 1GB/project |
| API | [Render](https://render.com) | Web service, spins down after 15 min idle |
| Ingestion | GitHub Actions | Unlimited minutes on a public repo |
| Frontend | [Vercel](https://vercel.com) | Static hosting |

### 1. Database (Neon)

1. Create a free account at neon.tech, create a project.
2. Copy its connection string (starts with `postgresql://...`) — Neon's
   console gives you one that works directly as `DATABASE_URL` (SQLAlchemy
   accepts the plain `postgresql://` scheme the same as `postgresql+psycopg2://`).
3. Run migrations against it once, from your machine:
   ```bash
   cd backend
   DATABASE_URL="<your neon connection string>" alembic upgrade head
   ```

### 2. Ingestion (GitHub Actions)

1. In the GitHub repo: **Settings → Secrets and variables → Actions**.
2. Add a secret named `DATABASE_URL` with the same Neon connection string.
3. That's it — `.github/workflows/ingest.yml` is already in the repo and
   starts running on its schedule automatically. You can also trigger it
   manually from the Actions tab (`workflow_dispatch`) to seed data right away
   instead of waiting for the next scheduled run.

### 3. API (Render)

1. Create a free account at render.com, connect your GitHub account.
2. **New → Blueprint**, pick this repo — Render reads `render.yaml` at the
   repo root and sets up the service automatically.
3. Set two environment variables on the service (Render's dashboard, not
   the blueprint file, since these are secrets/deploy-specific):
   - `DATABASE_URL` — same Neon connection string
   - `CORS_ORIGINS_RAW` — your Vercel URL once you have it (step 4), e.g.
     `https://your-app.vercel.app` (comma-separate if you add more later)
4. Note the service's URL (something like `https://metro-reliability-api.onrender.com`)
   — the frontend needs it next.

### 4. Frontend (Vercel)

1. Create a free account at vercel.com, **Add New → Project**, pick this repo.
2. Set **Root Directory** to `frontend` in the project settings — Vercel
   auto-detects the Vite framework preset from there.
3. Add an environment variable: `VITE_API_BASE_URL` = your Render API URL
   from step 3.
4. Deploy. Then go back to Render and set `CORS_ORIGINS_RAW` to the Vercel
   URL you just got (step 3.3), since the API needs to allow requests from
   wherever the frontend actually ended up.

### Notes on the free-tier tradeoffs

- **Render's free web service spins down after 15 minutes idle** — the
  first request after a quiet period takes a few extra seconds while it
  wakes back up. Fine for a portfolio demo, not for production traffic.
- **Scheduled ingestion is less dense than the continuous local worker** —
  it captures whatever Metro's feed sends during each ~90-second burst
  every 10 minutes, not literally every update. Still produces solid
  reliability numbers; just don't expect per-second freshness.
- **Neon's 1GB cap**: schedules are cached on demand (see above), so this
  should only become relevant after a long time in production. If it ever
  fills up, the simplest fix is trimming `scheduled_departures` for routes
  that haven't been observed recently.
