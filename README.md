# HVAC Efficiency Analyzer

Single-user web app that fuses utility (Green Button XML), thermostat
(Resideo), and weather (NOAA) data to attribute energy cost per HVAC unit
and flag anomalies.

## Stack

- **Backend:** FastAPI + Motor (MongoDB) + APScheduler
- **Frontend:** React 19 + Recharts + Tailwind

## Backend setup

```
cd backend
pip install -r requirements.txt
```

Create `backend/.env` with:

```
MONGO_URL=mongodb://localhost:27017
DB_NAME=hvac
API_PASSPHRASE=changeme
DEFAULT_RATE_USD_PER_KWH=0.14
ANTHROPIC_API_KEY=
NOAA_TOKEN=
RESIDEO_CLIENT_ID=
RESIDEO_CLIENT_SECRET=
RESIDEO_MOCK_MODE=true
```

```
uvicorn server:app --reload
```

## Frontend setup

```
cd frontend
yarn install
yarn start
```

See [memory/PRD.md](memory/PRD.md) for architecture and product context.
