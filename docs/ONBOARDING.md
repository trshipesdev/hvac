# Onboarding — what to expect on first run

This walks through what actually happens the first time you open the app,
so nothing is surprising.

## 1. First launch

Run `./setup.sh` once, then `./run.sh` (see
[INSTALLATION.md](INSTALLATION.md) if you haven't yet). Your browser opens
to the Dashboard. With no data uploaded, you'll see a "No data yet — click
Sync to seed the pipeline" message and empty KPI cards — this is correct,
not an error. Nothing is pre-populated with sample data pretending to be
yours.

## 2. Add at least two HVAC units

Go to **Settings → HVAC Units** and add each unit you want tracked
separately (name, floor/zone label, tonnage if you know it, a color for the
charts). Two is the minimum for the app's per-unit comparisons to be
meaningful, but there's no hardcoded limit — add as many as you actually
have.

## 3. Upload your real data (Ingest page)

The **Ingest** page is where every real data source comes in:

- **Green Button XML** — your utility's standard interval-usage export
  (15-minute or hourly whole-home kWh). Most utilities let you download this
  from your account portal. This is the foundation everything else attaches
  cost to.
- **Utility bills** (PDF or image, one at a time or in bulk) — parsed by
  Claude directly from the document, no manual data entry. It extracts the
  rate schedule, tier breakdown, and flags things like past-due balances or
  late fees so they don't get counted as real electricity cost.
- **Thermostat zone reports** (PDF or image, bulk-upload supported) — if
  your thermostat vendor emails you a monthly runtime summary (e.g. a
  Honeywell Home "Your `<Month>` Energy Report"), upload it here. This is
  real per-zone runtime data used to calibrate the per-unit cost split until
  a live thermostat API connection exists.

After uploading, check the **Data coverage** table at the bottom of Ingest —
it shows which months have Green Button data, a bill, and/or a zone report,
so gaps are visible instead of silently producing a flat/empty chart later.
Click **Backfill full history** to run attribution and anomaly detection
across everything you've uploaded, not just a recent window.

## 4. Let it auto-locate your timezone and weather station

Once you upload a bill with a real service address, the app automatically:
- extracts your ZIP code,
- finds the nearest real NOAA weather station (for backward-compatible
  fallback) and your real coordinates,
- derives your IANA timezone from those coordinates (e.g.
  `America/New_York`) — no manual entry.

You can see and override the detected timezone under **Settings → Property**
if it's ever wrong. Weather itself comes from Open-Meteo (real hourly data,
no key needed) once coordinates are known.

## 5. Understand the data-quality badges

Because there's no live thermostat connection yet, you'll see labels like
"estimated · calibrated to real reports" on unit runtime cards, and
"Estimated:" prefixes on some anomaly titles. This is intentional — it means
that number is inferred from your real monthly zone reports, not measured
live. Once Resideo API access is approved and connected (Settings →
Integrations), these upgrade to real live data automatically, with zero
further setup.

## 6. Check Anomalies and set your alert preferences

The **Anomalies** page lists everything the detectors have found, filterable
by category/type/severity/unit. If some categories are noisy for you (e.g.
late-fee reminders every billing cycle), go to **Settings → Dashboard
Alerts** and uncheck what you don't want surfaced on the Dashboard's KPI
count — unchecked types still exist and stay visible on the full Anomalies
page, they're just muted from the at-a-glance view.
