# Cloning and running this repo yourself

This is a single-branch, single-maintainer project — there's no complex
branching model to learn. If you found this from a portfolio and want to
run it locally or poke around the code, here's the fast path.

## Clone it

```bash
git clone https://github.com/trshipesdev/hvac.git
cd hvac
```

Or, if you want your own copy to modify and push changes to (rather than
just running it locally), fork it first on GitHub, then clone your fork:

```bash
git clone https://github.com/<your-username>/hvac.git
cd hvac
```

## Run it

```bash
./setup.sh
# fill in backend/.env — see docs/INSTALLATION.md
./run.sh
```

That's the whole loop — no build step beyond what `run.sh` already does,
no Docker required.

## What's actually in the repo

- `backend/` — FastAPI app. Each concern is its own module (`bill_parser.py`,
  `honeywell_parser.py`, `attribution.py`, `anomalies.py`, `resideo.py`,
  `openmeteo.py`, etc.) rather than one giant file, even though `server.py`
  itself is large since it's the single FastAPI router for the whole API.
- `frontend/` — Create React App (via CRACO) + Tailwind. One page per route
  under `src/pages/`, shared UI primitives (`Panel`, `Metric`,
  `SeverityPill`, `GroupedTable`) under `src/components/`.
- `docs/` — this folder.
- No CI/test-runner config is wired up publicly yet; `backend/tests/` has a
  pytest suite that exercises the API against a real (local) MongoDB.

## What's intentionally not in the repo

`.gitignore` excludes:
- `.env` files (real credentials — only `.env.example` templates are
  tracked)
- `.mongo-data/` (the local database directory `run.sh` creates — this is
  real personal usage data, never meant to be shared)
- Real utility bill PDFs / Green Button XML exports used for local testing
  — these live outside the repo entirely, not just gitignored

If you clone this and want to try it with your own data, drop your bill
PDFs and Green Button export anywhere outside the repo and upload them
through the app's Ingest page — nothing about the pipeline assumes a
specific utility, thermostat vendor, or number of HVAC units.

## Contributing

This is a personal portfolio project, not looking for external
contributions right now — but issues/questions are welcome via GitHub
Issues if you're using it yourself and hit something confusing.
