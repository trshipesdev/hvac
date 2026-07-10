# Installation

## Prerequisites

- **Python 3.10+** (the setup script auto-detects the newest available
  `python3.13`/`python3.12`/`python3.11`/`python3.10`/`python3` — on macOS
  the default `python3` is often too old, so install a newer one if needed:
  `brew install python@3.11`)
- **Node.js** + **Yarn** (the setup script will enable Yarn via corepack, or
  install it via npm, if it's missing)
- **MongoDB** (`brew tap mongodb/brew && brew install mongodb-community` on
  macOS)
- An **Anthropic API key** ([console.anthropic.com](https://console.anthropic.com/))
  — required for bill and zone-report parsing, the core of the app
- Optional: a free **NOAA CDO token** ([ncdc.noaa.gov](https://www.ncdc.noaa.gov/cdo-web/token))
  — only used as a fallback if your property's coordinates aren't known yet

## One-command setup

```bash
./setup.sh
```

This creates `backend/venv`, installs Python + Node dependencies, and
copies `backend/.env.example` → `backend/.env` and
`frontend/.env.example` → `frontend/.env` if they don't already exist. It
will **not** overwrite an existing `.env`.

Then fill in `backend/.env`:

```
ANTHROPIC_API_KEY=          # required
NOAA_TOKEN=                 # optional fallback, see above
RESIDEO_CLIENT_ID=          # optional, once you have Resideo developer access
RESIDEO_CLIENT_SECRET=      # optional
```

`MONGO_URL`, `DB_NAME`, `DEFAULT_RATE_USD_PER_KWH`, `RESIDEO_MOCK_MODE`, and
`CORS_ORIGINS` already have sensible local-dev defaults in the template —
change them only if you know you need to.

## Running it

```bash
./run.sh
```

This starts a local MongoDB (`--dbpath .mongo-data`, gitignored — your real
data never leaves your machine or gets committed), the FastAPI backend on
port 8000, and the React dev server on port 3000 (which opens your browser
automatically). `Ctrl-C` stops all three cleanly.

If a port is already in use from a previous run that didn't shut down
cleanly, `run.sh` detects and frees it automatically.

## Manual setup (without the scripts)

```bash
# Backend
cd backend
python3.11 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in ANTHROPIC_API_KEY at minimum
mongod --dbpath ../.mongo-data --port 27017 &
venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd frontend
yarn install
cp .env.example .env
yarn start
```

## Verifying it worked

```bash
curl http://localhost:8000/api/health
# {"status":"ok","time":"..."}
```

Then open http://localhost:3000 — you should land on the Dashboard with an
empty-state message, not an error. See
[ONBOARDING.md](ONBOARDING.md) for what to do next.
