# HVAC Efficiency Analyzer

A single-user web app that answers a real question: **which of my HVAC units
actually costs more to run, and why?** It fuses real data from multiple
sources — utility bills, Green Button interval exports, thermostat runtime
reports, and weather — into one investigation surface instead of leaving you
to cross-reference a utility website, a thermostat app, and a spreadsheet by
hand.

It's built to work for any number of units and any household — nothing is
hardcoded to a specific number of zones, thermostat vendor, or utility.

## What it actually does

- **Parses utility bills and thermostat runtime reports with Claude** —
  drop in a PDF and it extracts rate schedules, tier breakdowns, past-due
  balances, and monthly per-zone heating/cooling hours. No vendor-specific
  templates; it reads whatever the document says.
- **Splits your real Green Button usage across units** by their real runtime
  share for the month, using whatever thermostat runtime data is available —
  never presenting synthetic data as if it were measured.
- **Pulls real hourly weather** (via [Open-Meteo](https://open-meteo.com),
  free, no API key) for your property's real coordinates, and displays daily
  highs/lows alongside the average so a hot afternoon doesn't get smoothed
  away in a chart.
- **Flags anomalies** — extended runtime without reaching setpoint, overnight
  compressor draw on a mild night, efficiency regression, unusual heating/
  cooling given the actual weather that month — with severity and timestamps
  that respect your property's real local timezone, not a raw UTC label.
- **Is honest about data provenance.** Every thermostat reading is tagged
  `mock` (placeholder), `estimated` (calibrated against a real monthly
  report), or `resideo` (a real live poll) — and the UI never lets an
  inferred number pass as a measured one.

## Current limitations

- **No live thermostat API yet.** Resideo (Honeywell Home) developer access
  is pending approval — their API has no bulk historical endpoint anyway, so
  even once approved it can only poll forward from the moment you connect,
  never backfill the past. Until then, or for any date before you connect,
  thermostat data is either a pure placeholder (`mock`) or calibrated against
  your real monthly runtime-report emails (`estimated`) — both are clearly
  labeled in the UI, never presented as measured.
- **Runtime-hour cost attribution, not per-appliance metering.** There's no
  way to separately meter each HVAC unit from a single Green Button feed —
  usage is split proportionally by runtime share, which is a real, honest
  signal but not a submeter.
- **NOAA integration is a fallback path**, used only if your property's
  coordinates aren't known yet; real weather comes from Open-Meteo once
  they are.

See [docs/ONBOARDING.md](docs/ONBOARDING.md) for what to expect on first run.

## Stack

- **Backend:** FastAPI + Motor (async MongoDB) + APScheduler, Claude Haiku
  4.5 for document parsing, Open-Meteo for weather.
- **Frontend:** React 19 + Recharts + Tailwind (CRACO).

## Quick start

```
./setup.sh   # one-time: venv, deps, .env scaffolding
./run.sh     # starts MongoDB + backend + frontend, opens your browser
```

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for prerequisites, exact
environment variables, and manual setup if you'd rather not use the scripts.

## More docs

- [docs/ONBOARDING.md](docs/ONBOARDING.md) — first-run walkthrough
- [docs/INSTALLATION.md](docs/INSTALLATION.md) — detailed setup
- [docs/GIT_GUIDE.md](docs/GIT_GUIDE.md) — cloning/forking this repo
- [docs/ORACLE_DEPLOYMENT.md](docs/ORACLE_DEPLOYMENT.md) — running it on an
  always-on box instead of your laptop
