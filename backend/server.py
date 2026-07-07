"""HVAC Efficiency Analyzer — FastAPI entrypoint."""
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')  # must run before local modules that read env vars at import time

from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReplaceOne
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
import io
import re
import logging
from collections import defaultdict

from models import (
    Property, PropertyUpdate, HvacUnit, HvacUnitCreate,
    EnergyInterval, ThermostatReading, WeatherReading,
    AnomalyFlag, BillPeriod, BillPeriodCreate, RatePeriod, ResideoTokens,
    serialize_doc, deserialize_doc, new_id, now_utc,
)
from pydantic import BaseModel
import greenbutton
import noaa
import resideo
import tzresolve
import thermostat_estimation
import openmeteo
import attribution
import anomalies as anomalies_mod
import report as report_mod
import bill_parser
import bill_anomalies
import honeywell_parser
import monthly_cost

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="HVAC Efficiency Analyzer")
api = APIRouter(prefix="/api")


@api.get("/auth/check")
async def auth_check():
    # Single-user local app — no login/passphrase.
    return {"authenticated": True, "auth_required": False}


@api.get("/health")
async def health():
    return {"status": "ok", "time": now_utc().isoformat()}


# ---------- Property ----------

DATE_FIELDS = ["created_at", "updated_at", "ts", "ts_start", "ts_end", "start", "end",
               "detected_at", "attributed_at", "expires_at"]


async def _get_property() -> Property:
    doc = await db.property.find_one({}, {"_id": 0})
    if not doc:
        prop = Property(rate_usd_per_kwh=float(os.environ.get("DEFAULT_RATE_USD_PER_KWH", 0.14)))
        await db.property.insert_one(serialize_doc(prop.model_dump()))
        return prop
    doc = deserialize_doc(doc, DATE_FIELDS)
    return Property(**doc)


@api.get("/property", response_model=Property)
async def get_property():
    return await _get_property()


@api.put("/property", response_model=Property)
async def update_property(update: PropertyUpdate):
    prop = await _get_property()
    data = prop.model_dump()
    for k, v in update.model_dump(exclude_unset=True).items():
        data[k] = v
    # Auto-derive timezone whenever lat/long become known and no explicit
    # timezone is set yet — covers the manual Settings station-picker path
    # (the bill-upload auto-locate path derives it directly in
    # _auto_locate_from_bill, but this makes it work even for a user who
    # never uploads a bill and only searches NOAA stations from Settings).
    if not data.get("timezone") and data.get("latitude") is not None and data.get("longitude") is not None:
        tz = tzresolve.derive_timezone(data["latitude"], data["longitude"])
        if tz:
            data["timezone"] = tz
    data["updated_at"] = now_utc()
    prop2 = Property(**data)
    await db.property.replace_one({"id": prop.id}, serialize_doc(prop2.model_dump()), upsert=True)
    return prop2


# ---------- Units ----------

@api.get("/units", response_model=List[HvacUnit])
async def list_units():
    docs = await db.hvac_units.find({}, {"_id": 0}).to_list(50)
    return [HvacUnit(**deserialize_doc(d, DATE_FIELDS)) for d in docs]


@api.post("/units", response_model=HvacUnit)
async def create_unit(payload: HvacUnitCreate):
    existing = await db.hvac_units.count_documents({})
    default_color = "#3b82f6" if existing == 0 else "#8b5cf6"
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    data.setdefault("color", default_color)
    unit = HvacUnit(**data)
    await db.hvac_units.insert_one(serialize_doc(unit.model_dump()))
    return unit


@api.put("/units/{unit_id}", response_model=HvacUnit)
async def update_unit(unit_id: str, payload: HvacUnitCreate):
    existing = await db.hvac_units.find_one({"id": unit_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Unit not found")
    data = deserialize_doc(existing, DATE_FIELDS)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is not None:
            data[k] = v
    unit = HvacUnit(**data)
    await db.hvac_units.replace_one({"id": unit_id}, serialize_doc(unit.model_dump()))
    return unit


@api.delete("/units/{unit_id}")
async def delete_unit(unit_id: str):
    await db.hvac_units.delete_one({"id": unit_id})
    return {"deleted": unit_id}


# ---------- Green Button ingest ----------

@api.post("/ingest/green-button")
async def ingest_green_button(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        readings = greenbutton.parse_green_button(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not readings:
        raise HTTPException(400, "No interval readings found in file")

    inserted = 0
    skipped = 0
    for r in readings:
        exists = await db.energy_intervals.find_one({"ts_start": r["ts_start"].isoformat()}, {"_id": 0, "id": 1})
        if exists:
            skipped += 1
            continue
        iv = EnergyInterval(ts_start=r["ts_start"], ts_end=r["ts_end"], kwh=r["kwh"])
        await db.energy_intervals.insert_one(serialize_doc(iv.model_dump()))
        inserted += 1

    return {
        "inserted": inserted,
        "skipped": skipped,
        "range_start": readings[0]["ts_start"].isoformat(),
        "range_end": readings[-1]["ts_end"].isoformat(),
    }


@api.get("/ingest/sample-xml")
async def sample_xml():
    """Return a downloadable sample Green Button XML for testing."""
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=10)
    xml = greenbutton.generate_sample_xml(start, days=10, interval_min=15)
    return StreamingResponse(io.BytesIO(xml), media_type="application/xml",
                             headers={"Content-Disposition": 'attachment; filename="sample-green-button.xml"'})


# ---------- Weather ----------

@api.post("/ingest/noaa")
async def ingest_noaa(days: int = 30):
    """Despite the route name (kept for frontend/URL stability), this now
    pulls REAL hourly temperature from Open-Meteo (free, no API key,
    lat/long-based) whenever the property has real coordinates — a genuine
    improvement over the old approach of faking an hourly curve around one
    NOAA daily average. Falls back to that old synthetic approach only when
    lat/long isn't known yet (station search hasn't run), so ingestion never
    just silently does nothing."""
    prop = await _get_property()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    if prop.latitude is not None and prop.longitude is not None:
        records = await openmeteo.fetch_hourly_temps(prop.latitude, prop.longitude, start, end)
        if records:
            inserted = await _insert_new_weather(records)
            return {"inserted": inserted, "range_days": days, "source": "open-meteo"}

    if not prop.noaa_station_id:
        raise HTTPException(400, "Neither property coordinates nor a NOAA station are configured")
    daily = await noaa.fetch_daily_temps(prop.noaa_station_id, start, end)
    if not daily:
        daily_records = noaa.mock_weather(start, end)
        source = "synthetic"
    else:
        daily_records = noaa.synthesize_hourly_from_daily(daily)
        source = "noaa_synthetic"
    for r in daily_records:
        r["source"] = source
    inserted = await _insert_new_weather(daily_records)
    return {"inserted": inserted, "range_days": days, "source": source}


@api.get("/noaa/stations")
async def noaa_stations(zip_code: str):
    return await noaa.find_stations(zip_code)


def _extract_zip_and_state_from_address(address: Optional[str]) -> tuple:
    """Pull a 5-digit ZIP and 2-letter state code out of a free-text US
    service address, e.g. '123 Main St, Charleston, SC 29418'."""
    if not address:
        return None, None
    zip_match = re.search(r"\b(\d{5})(-\d{4})?\b", address)
    zip_code = zip_match.group(1) if zip_match else None
    state_match = re.search(r"\b([A-Z]{2})\b\s+\d{5}", address)
    state = state_match.group(1) if state_match else None
    return zip_code, state


async def _auto_locate_from_bill(parsed: Dict[str, Any]) -> None:
    """If the property doesn't already have a ZIP/NOAA station, derive them
    from this bill's real service address — no manual entry required.

    Station lookup falls back from ZIP-radius to state-wide search (see
    noaa.find_stations) since plenty of real ZIPs have no temperature-
    reporting station within NOAA's tight ZIP boundary — this isn't a
    one-off fix for a single address, it's meant to work for anyone's bill.
    """
    zip_code, state = _extract_zip_and_state_from_address(parsed.get("service_address"))
    if not zip_code:
        return
    prop = await _get_property()
    updates: Dict[str, Any] = {}
    if not prop.zip_code:
        updates["zip_code"] = zip_code
    if not prop.noaa_station_id and os.environ.get("NOAA_TOKEN"):
        try:
            stations = await noaa.find_stations(zip_code, state=state)
            if stations:
                updates["noaa_station_id"] = stations[0]["id"]
                updates["latitude"] = stations[0].get("latitude")
                updates["longitude"] = stations[0].get("longitude")
            else:
                logger.warning("Auto NOAA station lookup found nothing for zip=%s state=%s", zip_code, state)
        except Exception as e:
            logger.warning("Auto NOAA station lookup failed: %s", e)
    if not prop.timezone:
        tz = tzresolve.derive_timezone(
            updates.get("latitude", prop.latitude), updates.get("longitude", prop.longitude), state,
        )
        if tz:
            updates["timezone"] = tz
    if updates:
        data = prop.model_dump()
        data.update(updates)
        data["updated_at"] = now_utc()
        prop2 = Property(**data)
        await db.property.replace_one({"id": prop.id}, serialize_doc(prop2.model_dump()), upsert=True)


# ---------- Resideo ----------

async def _get_resideo_tokens() -> Optional[ResideoTokens]:
    doc = await db.resideo_oauth.find_one({"id": "singleton"}, {"_id": 0})
    if not doc:
        return None
    doc = deserialize_doc(doc, DATE_FIELDS)
    return ResideoTokens(**doc)


async def _store_resideo_tokens(tokens: Dict[str, Any]) -> None:
    doc = ResideoTokens(
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token") or (await _get_resideo_tokens() or ResideoTokens(
            access_token="", refresh_token="", expires_at=now_utc())).refresh_token,
        expires_at=tokens["expires_at"],
    )
    await db.resideo_oauth.replace_one({"id": "singleton"}, serialize_doc(doc.model_dump()), upsert=True)


async def _get_valid_resideo_access_token() -> Optional[str]:
    """Loads the resideo_oauth singleton; None if never connected. Refreshes
    proactively if the access token expires within 60s."""
    tokens = await _get_resideo_tokens()
    if not tokens:
        return None
    if tokens.expires_at <= now_utc() + timedelta(seconds=60):
        try:
            refreshed = await resideo.refresh_access_token(tokens.refresh_token)
            await _store_resideo_tokens(refreshed)
            return refreshed["access_token"]
        except Exception as e:
            logger.warning("Resideo token refresh failed: %s", e)
            return None
    return tokens.access_token


@api.get("/resideo/status")
async def resideo_status():
    tokens = await _get_resideo_tokens()
    return resideo.oauth_status(connected=tokens is not None)


@api.post("/resideo/exchange-code")
async def resideo_exchange_code(payload: Dict[str, str]):
    code = payload.get("code")
    if not code:
        raise HTTPException(400, "Missing code")
    try:
        tokens = await resideo.exchange_code(code)
    except Exception as e:
        raise HTTPException(400, f"Exchange failed: {e}")
    await _store_resideo_tokens(tokens)
    return {"connected": True}


@api.get("/resideo/locations")
async def resideo_locations():
    access_token = await _get_valid_resideo_access_token()
    if not access_token:
        raise HTTPException(401, "Not connected to Resideo yet")
    return await resideo.list_locations(access_token)


async def _insert_new_thermostat_readings(unit_id: str, records: List[Dict[str, Any]]) -> int:
    """Bulk-insert thermostat readings for one unit not already present."""
    if not records:
        return 0
    start_iso = min(r["ts"] for r in records).isoformat()
    end_iso = max(r["ts"] for r in records).isoformat()
    existing = {d["ts"] async for d in db.thermostat_readings.find(
        {"unit_id": unit_id, "ts": {"$gte": start_iso, "$lte": end_iso}}, {"_id": 0, "ts": 1}
    )}
    docs = [serialize_doc(ThermostatReading(**r).model_dump()) for r in records if r["ts"].isoformat() not in existing]
    if not docs:
        return 0
    result = await db.thermostat_readings.insert_many(docs, ordered=False)
    return len(result.inserted_ids)


@api.post("/resideo/sync")
async def resideo_sync(
    days: int = 10, start_iso: Optional[str] = None, end_iso: Optional[str] = None, force_recompute: bool = False,
):
    """Fetch thermostat data. Real Resideo connection (per-unit device+location
    assigned) polls one live snapshot per unit; otherwise falls back to
    Honeywell-report-calibrated estimates, or pure mock if no report exists
    for that unit/month either.

    force_recompute=True clears existing non-real (mock/estimated, or
    legacy readings from before the `source` field existed) readings in the
    window first, so a newly-uploaded Honeywell report can retroactively
    replace old arbitrary mock data with calibrated estimates for the same
    months. Never touches source="resideo" (real) readings.
    """
    units = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    if not units:
        raise HTTPException(400, "No HVAC units configured")
    if start_iso and end_iso:
        start = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        start = end - timedelta(days=days)

    if force_recompute:
        for u in units:
            await db.thermostat_readings.delete_many({
                "unit_id": u["id"],
                "ts": {"$gte": start.isoformat(), "$lt": end.isoformat()},
                "source": {"$ne": "resideo"},
            })

    inserted = 0
    access_token = None if resideo.is_mock() else await _get_valid_resideo_access_token()

    for idx, u in enumerate(units):
        if access_token and u.get("thermostat_device_id") and u.get("resideo_location_id"):
            last = await db.thermostat_readings.find_one(
                {"unit_id": u["id"]}, {"_id": 0, "ts": 1}, sort=[("ts", -1)]
            )
            now = datetime.now(timezone.utc)
            since = min((now - datetime.fromisoformat(last["ts"])).total_seconds(), 3600.0) if last else 0.0
            try:
                snap = await resideo.fetch_thermostat_snapshot(
                    access_token, u["thermostat_device_id"], u["resideo_location_id"]
                )
                readings = [resideo.snapshot_to_reading(u["id"], snap, runtime_seconds=since)]
            except Exception as e:
                logger.warning("Resideo live poll failed for unit %s: %s", u["id"], e)
                readings = []
        else:
            zone_rows = await db.honeywell_zone_months.find({"unit_id": u["id"]}, {"_id": 0}).to_list(200)
            weather_docs = await _load_weather(start - timedelta(days=1), end + timedelta(days=1))
            readings = thermostat_estimation.build_thermostat_series(
                u["id"], idx, start, end, zone_rows, weather_docs, interval_min=5
            )
        inserted += await _insert_new_thermostat_readings(u["id"], readings)
    return {"inserted": inserted, "units": len(units), "mock_mode": resideo.is_mock()}


# ---------- Attribution ----------

async def _load_intervals(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    cursor = db.energy_intervals.find(
        {"ts_start": {"$gte": start.isoformat(), "$lte": end.isoformat()}}, {"_id": 0}
    ).sort("ts_start", 1)
    docs = await cursor.to_list(100000)
    for d in docs:
        d["ts_start"] = datetime.fromisoformat(d["ts_start"])
        d["ts_end"] = datetime.fromisoformat(d["ts_end"])
        if d.get("attributed_at") and isinstance(d["attributed_at"], str):
            d["attributed_at"] = datetime.fromisoformat(d["attributed_at"])
    return docs


async def _load_readings(unit_id: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    cursor = db.thermostat_readings.find(
        {"unit_id": unit_id, "ts": {"$gte": start.isoformat(), "$lte": end.isoformat()}}, {"_id": 0}
    ).sort("ts", 1)
    docs = await cursor.to_list(200000)
    for d in docs:
        d["ts"] = datetime.fromisoformat(d["ts"])
    return docs


async def _load_weather(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    cursor = db.weather.find(
        {"ts": {"$gte": start.isoformat(), "$lte": end.isoformat()}}, {"_id": 0}
    ).sort("ts", 1)
    docs = await cursor.to_list(100000)
    for d in docs:
        d["ts"] = datetime.fromisoformat(d["ts"])
    return docs


async def _insert_new_weather(records: List[Dict[str, Any]]) -> int:
    """Bulk-insert weather readings not already present, one range query
    instead of one find_one per record."""
    if not records:
        return 0
    start_iso = min(r["ts"] for r in records).isoformat()
    end_iso = max(r["ts"] for r in records).isoformat()
    existing = {d["ts"] async for d in db.weather.find(
        {"ts": {"$gte": start_iso, "$lte": end_iso}}, {"_id": 0, "ts": 1}
    )}
    docs = [serialize_doc(WeatherReading(**r).model_dump()) for r in records if r["ts"].isoformat() not in existing]
    if not docs:
        return 0
    result = await db.weather.insert_many(docs, ordered=False)
    return len(result.inserted_ids)


# ---------- Rate periods (time-varying $/kWh) ----------

async def _load_rate_periods() -> List[Dict[str, Any]]:
    docs = await db.rate_periods.find({}, {"_id": 0}).sort("start", 1).to_list(500)
    for d in docs:
        for f in ("start", "end", "created_at"):
            if isinstance(d.get(f), str):
                try:
                    d[f] = datetime.fromisoformat(d[f])
                except Exception:
                    pass
    return docs


async def _build_rate_lookup(fallback: float):
    """Return callable(ts) -> rate using rate_periods table + fallback."""
    periods = await _load_rate_periods()
    if not periods:
        return lambda ts: fallback

    def lookup(ts: datetime) -> float:
        for rp in periods:
            if rp["start"] <= ts <= rp["end"]:
                return rp["effective_rate"]
        return fallback
    return lookup


@api.get("/rate-periods", response_model=List[RatePeriod])
async def list_rate_periods():
    docs = await _load_rate_periods()
    return [RatePeriod(**d) for d in docs]


@api.post("/attribution/run")
async def run_attribution(days: int = 30, start_iso: Optional[str] = None, end_iso: Optional[str] = None):
    prop = await _get_property()
    units_docs = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    if not units_docs:
        raise HTTPException(400, "No units configured")
    if start_iso and end_iso:
        start = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
    intervals = await _load_intervals(start, end)
    if not intervals:
        return {"attributed": 0, "message": "No intervals to attribute"}
    readings_by_unit = {}
    for u in units_docs:
        readings_by_unit[u["id"]] = await _load_readings(u["id"], start, end)

    rate_lookup = await _build_rate_lookup(prop.rate_usd_per_kwh)
    attribution.attribute(intervals, readings_by_unit, prop.rate_usd_per_kwh, rate_lookup=rate_lookup)
    ops = [ReplaceOne({"id": iv["id"]}, serialize_doc(iv), upsert=False) for iv in intervals]
    if ops:
        await db.energy_intervals.bulk_write(ops, ordered=False)
    return {"attributed": len(intervals), "start": start.isoformat(), "end": end.isoformat()}


# ---------- Anomaly detection ----------

@api.post("/anomalies/run")
async def run_anomaly_detection(days: int = 30, start_iso: Optional[str] = None, end_iso: Optional[str] = None):
    prop = await _get_property()
    tz = ZoneInfo(prop.timezone) if prop.timezone else timezone.utc
    units_docs = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    if start_iso and end_iso:
        start = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
    intervals = await _load_intervals(start, end)
    weather = await _load_weather(start, end)

    # Clear previous UN-acknowledged HVAC anomalies in the window; keep acknowledged ones.
    # zone_mode_weather_mismatch is excluded — it's only (re)populated by the
    # Honeywell confirm/rescan path, not by run_all below, so clearing it here
    # would silently erase it on every scheduled run without ever regenerating it.
    await db.anomalies.delete_many({
        "ts_start": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        "acknowledged": {"$ne": True},
        "category": {"$ne": "bill"},
        "type": {"$ne": "zone_mode_weather_mismatch"},
    })

    total = 0
    for u in units_docs:
        readings = await _load_readings(u["id"], start, end)
        found = anomalies_mod.run_all(u["id"], readings, intervals, weather, tz=tz)
        for a in found:
            # Skip if an acknowledged one of same type+unit+day already exists
            exists = await db.anomalies.find_one({
                "unit_id": a["unit_id"], "type": a["type"],
                "ts_start": a["ts_start"].isoformat(),
                "acknowledged": True,
            }, {"_id": 0, "id": 1})
            if exists:
                continue
            flag = AnomalyFlag(**a)
            await db.anomalies.insert_one(serialize_doc(flag.model_dump()))
            total += 1
    return {"anomalies": total, "days": days}


@api.get("/anomalies", response_model=List[AnomalyFlag])
async def list_anomalies(
    unit_id: Optional[str] = None,
    severity: Optional[str] = None,
    type: Optional[str] = None,
    category: Optional[str] = None,
    include_acknowledged: bool = False,
    limit: int = 500,
):
    """`type` accepts a single value or a comma-separated list (e.g.
    'bill_rate_spike,bill_usage_spike') for dashboard-style multi-type
    filtering without needing a separate endpoint."""
    q: Dict[str, Any] = {}
    if unit_id:
        q["unit_id"] = unit_id
    if severity:
        q["severity"] = severity
    if type:
        types = type.split(",")
        q["type"] = {"$in": types} if len(types) > 1 else types[0]
    if category:
        q["category"] = category
    if not include_acknowledged:
        q["acknowledged"] = {"$ne": True}
    docs = await db.anomalies.find(q, {"_id": 0}).sort("ts_start", -1).to_list(limit)
    return [AnomalyFlag(**deserialize_doc(d, DATE_FIELDS)) for d in docs]


class AckPayload(BaseModel):
    ack_note: Optional[str] = None


@api.post("/anomalies/{anomaly_id}/ack")
async def acknowledge_anomaly(anomaly_id: str, payload: AckPayload = AckPayload()):
    result = await db.anomalies.update_one(
        {"id": anomaly_id},
        {"$set": {"acknowledged": True, "acknowledged_at": now_utc().isoformat(), "ack_note": payload.ack_note}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Anomaly not found")
    return {"acknowledged": anomaly_id}


@api.post("/anomalies/{anomaly_id}/unack")
async def unack_anomaly(anomaly_id: str):
    await db.anomalies.update_one(
        {"id": anomaly_id},
        {"$set": {"acknowledged": False, "acknowledged_at": None, "ack_note": None}},
    )
    return {"unacknowledged": anomaly_id}


# ---------- Dashboard aggregates ----------

@api.get("/dashboard/timeline")
async def dashboard_timeline(
    days: int = 7,
    bucket: str = "hour",  # hour | day
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
):
    prop = await _get_property()
    tz = ZoneInfo(prop.timezone) if prop.timezone else timezone.utc
    units_docs = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    if start_iso and end_iso:
        start = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
    intervals = await _load_intervals(start, end)
    weather = await _load_weather(start, end)

    def key_of(ts: datetime) -> str:
        local = ts.astimezone(tz)
        if bucket == "day":
            return local.strftime("%Y-%m-%d")
        return local.strftime("%Y-%m-%d %H:00")

    buckets: Dict[str, Dict[str, Any]] = {}
    for iv in intervals:
        k = key_of(iv["ts_start"])
        b = buckets.setdefault(k, {"ts": k, "total_kwh": 0.0, "base_load": 0.0})
        b["total_kwh"] += iv["kwh"]
        b["base_load"] += iv.get("base_load_kwh", 0.0)
        for uid, kwh in iv.get("unit_kwh", {}).items():
            b[uid] = b.get(uid, 0.0) + kwh

    # weather bucketing
    for w in weather:
        k = key_of(w["ts"])
        if k in buckets and w.get("outdoor_temp_f") is not None:
            buckets[k].setdefault("outdoor_temp_f", []).append(w["outdoor_temp_f"])
    for b in buckets.values():
        temps = b.get("outdoor_temp_f")
        if isinstance(temps, list) and temps:
            # Keep the average for the existing chart line, but averaging
            # away a whole day's real hourly swing hides the actual daily
            # high/low — surface those separately so a genuinely hot
            # afternoon or cold night isn't smoothed out of existence.
            b["outdoor_temp_hi_f"] = round(max(temps), 1)
            b["outdoor_temp_lo_f"] = round(min(temps), 1)
            b["outdoor_temp_f"] = round(sum(temps) / len(temps), 1)
        elif isinstance(temps, list):
            b.pop("outdoor_temp_f", None)

    series = sorted(buckets.values(), key=lambda x: x["ts"])
    units_meta = [{"id": u["id"], "name": u["name"], "color": u.get("color", "#3b82f6")} for u in units_docs]
    return {"series": series, "units": units_meta, "bucket": bucket, "days": days}


@api.get("/dashboard/summary")
async def dashboard_summary(days: int = 7, start_iso: Optional[str] = None, end_iso: Optional[str] = None):
    prop = await _get_property()
    units_docs = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    if start_iso and end_iso:
        start = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
    intervals = await _load_intervals(start, end)
    unit_ids = [u["id"] for u in units_docs]
    readings_by_unit = {u["id"]: await _load_readings(u["id"], start, end) for u in units_docs}

    summary = attribution.summarize_by_unit(intervals, unit_ids, readings_by_unit)
    total_kwh = sum(iv["kwh"] for iv in intervals)
    total_cost = total_kwh * prop.rate_usd_per_kwh

    # Bill anomalies (past-due, late fee, rate/usage spike) represent an
    # ongoing real-world situation tied to a billing period, not "did this
    # happen in the last N days" — so they count as active regardless of the
    # viewing window as long as they're unacknowledged. HVAC anomalies stay
    # windowed since they're tied to specific runtime patterns on specific
    # days. Respects the user's dashboard_anomaly_types mute list either way.
    anomaly_base_filter: Dict[str, Any] = {"acknowledged": {"$ne": True}}
    if prop.dashboard_anomaly_types is not None:
        anomaly_base_filter["type"] = {"$in": prop.dashboard_anomaly_types}
    windowed_or_bill = {
        "$or": [
            {"category": "bill"},
            {"ts_start": {"$gte": start.isoformat(), "$lte": end.isoformat()}},
        ]
    }
    active_anomalies = await db.anomalies.count_documents({**anomaly_base_filter, **windowed_or_bill})
    critical_anomalies = await db.anomalies.count_documents({**anomaly_base_filter, **windowed_or_bill, "severity": "critical"})
    return {
        "days": days,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_kwh": round(total_kwh, 2),
        "total_cost": round(total_cost, 2),
        "rate_usd_per_kwh": prop.rate_usd_per_kwh,
        "units": [
            {
                "id": u["id"],
                "name": u["name"],
                "color": u.get("color", "#3b82f6"),
                **summary.get(u["id"], {}),
            }
            for u in units_docs
        ],
        "base_load": summary.get("_base_load", {}),
        "active_anomalies": active_anomalies,
        "critical_anomalies": critical_anomalies,
    }


# ---------- Year-over-year + drill-down ----------

@api.get("/dashboard/yoy")
async def year_over_year():
    """Compare last 30 days vs same 30-day window a year ago."""
    now = datetime.now(timezone.utc)
    cur_end = now
    cur_start = cur_end - timedelta(days=30)
    prior_end = cur_end - timedelta(days=365)
    prior_start = prior_end - timedelta(days=30)

    async def _range_kwh(s, e):
        cursor = db.energy_intervals.find(
            {"ts_start": {"$gte": s.isoformat(), "$lte": e.isoformat()}},
            {"_id": 0, "kwh": 1},
        )
        docs = await cursor.to_list(200000)
        return round(sum(d["kwh"] for d in docs), 2)

    cur_kwh = await _range_kwh(cur_start, cur_end)
    prior_kwh = await _range_kwh(prior_start, prior_end)
    pct = None
    if prior_kwh > 0:
        pct = round((cur_kwh - prior_kwh) / prior_kwh * 100, 1)
    return {
        "current_kwh": cur_kwh,
        "prior_year_kwh": prior_kwh,
        "pct_change": pct,
        "current_window": {"start": cur_start.isoformat(), "end": cur_end.isoformat()},
        "prior_window": {"start": prior_start.isoformat(), "end": prior_end.isoformat()},
    }


@api.get("/dashboard/drilldown")
async def timeline_drilldown(ts: str, bucket: str = "hour"):
    """Return raw intervals + thermostat activity + weather + anomalies for a bucket.

    `ts` is a bucket key produced by /dashboard/timeline's key_of(), which
    now labels buckets in the property's local time — so it must be
    reinterpreted as local wall time here too, then converted to the UTC
    range the underlying collections are actually keyed by.
    """
    prop = await _get_property()
    tz = ZoneInfo(prop.timezone) if prop.timezone else timezone.utc
    if bucket == "day":
        local_start = datetime.fromisoformat(ts).replace(tzinfo=tz)
        local_end = local_start + timedelta(days=1)
    else:
        local_start = datetime.fromisoformat(ts.replace(" ", "T")).replace(tzinfo=tz)
        local_end = local_start + timedelta(hours=1)
    start = local_start.astimezone(timezone.utc)
    end = local_end.astimezone(timezone.utc)

    intervals = await _load_intervals(start, end)
    units_docs = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    readings_by_unit = {}
    for u in units_docs:
        readings_by_unit[u["id"]] = await _load_readings(u["id"], start, end)

    # Convert datetimes to iso for JSON
    def _dt(v): return v.isoformat() if isinstance(v, datetime) else v
    iv_out = [{k: _dt(v) for k, v in iv.items()} for iv in intervals]
    r_out = {uid: [{k: _dt(v) for k, v in r.items()} for r in rs] for uid, rs in readings_by_unit.items()}
    weather = await _load_weather(start, end)
    w_out = [{k: _dt(v) for k, v in w.items()} for w in weather]

    anom_docs = await db.anomalies.find(
        {"ts_start": {"$lte": end.isoformat()}, "ts_end": {"$gte": start.isoformat()}}, {"_id": 0}
    ).to_list(100)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "bucket": bucket,
        "intervals": iv_out,
        "readings_by_unit": r_out,
        "weather": w_out,
        "anomalies": anom_docs,
        "units": [{"id": u["id"], "name": u["name"], "color": u.get("color", "#3b82f6")} for u in units_docs],
    }


@api.get("/dashboard/data-status")
async def data_status():
    intervals_count = await db.energy_intervals.count_documents({})
    readings_count = await db.thermostat_readings.count_documents({})
    weather_count = await db.weather.count_documents({})
    latest_iv = await db.energy_intervals.find_one({}, {"_id": 0}, sort=[("ts_start", -1)])
    latest_r = await db.thermostat_readings.find_one({}, {"_id": 0}, sort=[("ts", -1)])
    latest_w = await db.weather.find_one({}, {"_id": 0}, sort=[("ts", -1)])
    tokens = await _get_resideo_tokens()
    return {
        "energy_intervals": intervals_count,
        "thermostat_readings": readings_count,
        "weather_readings": weather_count,
        "latest_energy_ts": latest_iv["ts_start"] if latest_iv else None,
        "latest_thermostat_ts": latest_r["ts"] if latest_r else None,
        "latest_weather_ts": latest_w["ts"] if latest_w else None,
        "resideo": resideo.oauth_status(connected=tokens is not None),
    }


@api.get("/coverage")
async def coverage():
    """Month-by-month grid of what data actually exists — Green Button
    interval presence, bill presence, zone-report presence — so gaps are
    visible at a glance instead of discovered by a chart quietly going flat.
    """
    intervals = await db.energy_intervals.find({}, {"_id": 0, "ts_start": 1}).to_list(200000)
    bills = await db.bill_periods.find({}, {"_id": 0, "start": 1, "end": 1}).to_list(500)
    zone_months = await db.honeywell_zone_months.find({}, {"_id": 0, "year": 1, "month": 1}).to_list(2000)
    unit_ids = [u["id"] for u in await db.hvac_units.find({}, {"_id": 0, "id": 1}).to_list(10)]

    months: Dict[str, Dict[str, Any]] = {}

    def _month_key(dt: datetime) -> str:
        return f"{dt.year:04d}-{dt.month:02d}"

    for iv in intervals:
        k = _month_key(datetime.fromisoformat(iv["ts_start"]))
        months.setdefault(k, {"green_button": 0, "bill": False, "zone_reports": 0})
        months[k]["green_button"] += 1

    for b in bills:
        start = datetime.fromisoformat(b["start"])
        end = datetime.fromisoformat(b["end"])
        cur = start.replace(day=1)
        while cur <= end:
            k = _month_key(cur)
            months.setdefault(k, {"green_button": 0, "bill": False, "zone_reports": 0})
            months[k]["bill"] = True
            cur = (cur + timedelta(days=32)).replace(day=1)

    for z in zone_months:
        k = f"{z['year']:04d}-{z['month']:02d}"
        months.setdefault(k, {"green_button": 0, "bill": False, "zone_reports": 0})
        months[k]["zone_reports"] += 1

    rows = []
    for k in sorted(months.keys()):
        m = months[k]
        rows.append({
            "month": k,
            "green_button_intervals": m["green_button"],
            "has_bill": m["bill"],
            "zone_reports": m["zone_reports"],
            "gap": m["green_button"] == 0 and not m["bill"] and m["zone_reports"] == 0,
        })
    return {"months": rows, "total_units": len(unit_ids)}


# ---------- Bill periods ----------

@api.get("/bills", response_model=List[BillPeriod])
async def list_bills():
    docs = await db.bill_periods.find({}, {"_id": 0}).sort("start", -1).to_list(100)
    return [BillPeriod(**deserialize_doc(d, DATE_FIELDS)) for d in docs]


@api.post("/bills", response_model=BillPeriod)
async def create_bill(payload: BillPeriodCreate):
    bp = BillPeriod(**payload.model_dump())
    # compute against attributed intervals
    intervals = await _load_intervals(bp.start, bp.end)
    prop = await _get_property()
    rate = bp.rate_usd_per_kwh or prop.rate_usd_per_kwh
    bp.rate_usd_per_kwh = rate
    bp.computed_kwh = round(sum(iv["kwh"] for iv in intervals), 2)
    bp.computed_cost = round(bp.computed_kwh * rate, 2)
    await db.bill_periods.insert_one(serialize_doc(bp.model_dump()))
    return bp


@api.delete("/bills/{bill_id}")
async def delete_bill(bill_id: str):
    await db.bill_periods.delete_one({"id": bill_id})
    return {"deleted": bill_id}


# ---------- Bill PDF upload + AI parse ----------

@api.post("/bills/parse")
async def parse_uploaded_bill(file: UploadFile = File(...)):
    """Parse a PDF/image bill via Claude Haiku 4.5. Does NOT persist — returns preview."""
    raw = await file.read()
    mime = file.content_type or ("application/pdf" if file.filename.lower().endswith(".pdf") else "application/octet-stream")
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > 32 * 1024 * 1024:
        raise HTTPException(413, "File too large (>32MB)")
    try:
        parsed = bill_parser.parse_bill(raw, mime)
    except Exception as e:
        logger.exception("Bill parse failed")
        raise HTTPException(500, f"Parse failed: {e}")

    # Compute what we'd store + delta vs pipeline-computed
    computed_kwh = None
    computed_cost = None
    prop = await _get_property()
    if parsed.get("billing_period_start") and parsed.get("billing_period_end"):
        try:
            start = datetime.fromisoformat(parsed["billing_period_start"]).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(parsed["billing_period_end"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
            intervals = await _load_intervals(start, end)
            computed_kwh = round(sum(iv["kwh"] for iv in intervals), 2)
            rate = parsed.get("effective_rate_per_kwh") or prop.rate_usd_per_kwh
            computed_cost = round(computed_kwh * rate, 2)
        except Exception as e:
            logger.warning("Reconcile compute failed: %s", e)

    return {
        "parsed": parsed,
        "computed_kwh": computed_kwh,
        "computed_cost": computed_cost,
        "current_property_rate": prop.rate_usd_per_kwh,
    }


class BillConfirm(BaseModel):
    parsed: Dict[str, Any]
    apply_rate: bool = True


@api.post("/bills/confirm", response_model=BillPeriod)
async def confirm_uploaded_bill(payload: BillConfirm):
    p = payload.parsed
    if not p.get("billing_period_start") or not p.get("billing_period_end"):
        raise HTTPException(400, "billing_period_start / billing_period_end are required")
    start = datetime.fromisoformat(p["billing_period_start"]).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(p["billing_period_end"]).replace(tzinfo=timezone.utc)
    rate = p.get("effective_rate_per_kwh")

    intervals = await _load_intervals(start, end + timedelta(days=1))
    computed_kwh = round(sum(iv["kwh"] for iv in intervals), 2) if intervals else None
    computed_cost = round(computed_kwh * rate, 2) if (computed_kwh is not None and rate) else None

    bp = BillPeriod(
        start=start,
        end=end,
        total_kwh=p.get("total_kwh"),
        total_cost=p.get("total_cost"),
        rate_usd_per_kwh=rate,
        computed_kwh=computed_kwh,
        computed_cost=computed_cost,
        notes=(p.get("notes") or "") + f"\n[parsed] utility={p.get('utility_name')} acct={p.get('account_number')} schedule={p.get('rate_schedule')}",
    )
    await db.bill_periods.insert_one(serialize_doc(bp.model_dump()))

    # Store parsed extras separately
    await db.bill_parsed.insert_one(serialize_doc({
        "id": new_id(),
        "bill_period_id": bp.id,
        "parsed": p,
        "created_at": now_utc(),
    }))

    # Insert rate_period so future attribution uses the correct rate for THIS window
    if rate:
        await db.rate_periods.delete_many({
            "start": start.isoformat(),
            "end": end.isoformat(),
        })
        rp = RatePeriod(
            start=start, end=end, effective_rate=rate,
            tiers=p.get("tier_breakdown"),
            source_bill_id=bp.id,
            utility_name=p.get("utility_name"),
        )
        await db.rate_periods.insert_one(serialize_doc(rp.model_dump()))

    # Run bill anomaly detector — includes cross-bill checks (meter reading
    # continuity, billing-period gaps) against whichever bill immediately
    # precedes this one, using its already-stored full parsed payload.
    prior_rps = await _load_rate_periods()
    prior_before = [rp for rp in prior_rps if rp["start"] < start]
    prior_bp = await db.bill_periods.find_one(
        {"start": {"$lt": start.isoformat()}}, {"_id": 0}, sort=[("start", -1)]
    )
    prior_bill_parsed = None
    if prior_bp:
        prior_parsed_doc = await db.bill_parsed.find_one({"bill_period_id": prior_bp["id"]}, {"_id": 0})
        prior_bill_parsed = prior_parsed_doc["parsed"] if prior_parsed_doc else None
    prop = await _get_property()
    prop_tz = ZoneInfo(prop.timezone) if prop.timezone else timezone.utc
    bill_anoms = bill_anomalies.detect_bill_anomalies(p, bp.id, prior_before, prior_bill_parsed, tz=prop_tz)
    for a in bill_anoms:
        exists = await db.anomalies.find_one({
            "category": "bill", "type": a["type"],
            "ts_start": a["ts_start"].isoformat(),
        }, {"_id": 0, "id": 1})
        if exists:
            continue
        flag = AnomalyFlag(**a)
        await db.anomalies.insert_one(serialize_doc(flag.model_dump()))

    # Re-attribute the intervals in this window with the new rate
    if rate:
        try:
            await run_attribution(days=0, start_iso=start.isoformat(), end_iso=end.isoformat())
        except Exception as e:
            logger.warning("Re-attribution after bill confirm failed: %s", e)

    # Optionally apply rate to property (for intervals outside any rate_period)
    if payload.apply_rate and rate:
        data = prop.model_dump()
        data["rate_usd_per_kwh"] = rate
        data["updated_at"] = now_utc()
        prop2 = Property(**data)
        await db.property.replace_one({"id": prop.id}, serialize_doc(prop2.model_dump()), upsert=True)

    # Derive ZIP/NOAA station from this bill's real service address if the
    # property doesn't already have them — no manual entry needed.
    await _auto_locate_from_bill(p)

    return bp


@api.post("/bills/bulk-parse")
async def bulk_parse(files: List[UploadFile] = File(...)):
    """Parse multiple bill PDFs and auto-confirm each. Returns per-file result."""
    results = []
    for f in files:
        try:
            raw = await f.read()
            mime = f.content_type or "application/pdf"
            parsed = bill_parser.parse_bill(raw, mime)
            confirm_resp = await confirm_uploaded_bill(BillConfirm(parsed=parsed, apply_rate=False))
            results.append({
                "filename": f.filename,
                "ok": True,
                "bill_id": confirm_resp.id,
                "utility": parsed.get("utility_name"),
                "period": f"{parsed.get('billing_period_start')} → {parsed.get('billing_period_end')}",
                "total_kwh": parsed.get("total_kwh"),
                "total_cost": parsed.get("total_cost"),
                "effective_rate": parsed.get("effective_rate_per_kwh"),
            })
        except Exception as e:
            results.append({"filename": f.filename, "ok": False, "error": str(e)})
    return {"results": results, "count": len(results)}


@api.post("/bills/rescan-anomalies")
async def rescan_bill_anomalies():
    """Re-run bill anomaly detection across every stored bill in chronological
    order, with correct prior-bill context each time. Useful after the
    detector gains new cross-bill checks (e.g. meter-reading continuity,
    billing-period gaps) so they apply retroactively to bills that were
    already confirmed before the upgrade — no re-upload needed, since each
    bill's full parsed payload is already stored."""
    prop = await _get_property()
    tz = ZoneInfo(prop.timezone) if prop.timezone else timezone.utc
    bill_periods = await db.bill_periods.find({}, {"_id": 0}).sort("start", 1).to_list(500)
    all_rate_periods = await _load_rate_periods()

    new_anomalies = 0
    prior_bill_parsed = None
    for bp in bill_periods:
        parsed_doc = await db.bill_parsed.find_one({"bill_period_id": bp["id"]}, {"_id": 0})
        if not parsed_doc:
            continue
        p = parsed_doc["parsed"]
        start = datetime.fromisoformat(bp["start"]).replace(tzinfo=timezone.utc)
        prior_before = [rp for rp in all_rate_periods if rp["start"] < start]
        anoms = bill_anomalies.detect_bill_anomalies(p, bp["id"], prior_before, prior_bill_parsed, tz=tz)
        for a in anoms:
            exists = await db.anomalies.find_one({
                "category": "bill", "type": a["type"], "ts_start": a["ts_start"].isoformat(),
            }, {"_id": 0, "id": 1})
            if exists:
                continue
            flag = AnomalyFlag(**a)
            await db.anomalies.insert_one(serialize_doc(flag.model_dump()))
            new_anomalies += 1
        prior_bill_parsed = p

    return {"bills_scanned": len(bill_periods), "new_anomalies": new_anomalies}


# ---------- Honeywell / vendor zone-runtime reports ----------
# Real per-zone monthly runtime data (workaround while real Resideo OAuth is
# pending). Deliberately independent of the mock-data attribution pipeline —
# see monthly_cost.py. Not tied to any fixed number of zones/units or to
# "Upstairs"/"Downstairs" specifically; zone names and unit count are
# whatever the parsed report and the user's configured HvacUnits say.

def _normalize_zone_name(name: str) -> str:
    return (name or "").strip().lower()


UNIT_COLOR_PALETTE = ["#3b82f6", "#8b5cf6", "#f59e0b", "#10b981", "#ef4444", "#06b6d4"]


async def _get_or_create_unit_id(zone_name: str, zone_name_normalized: str, units_docs: List[Dict[str, Any]]) -> Optional[str]:
    """Match a zone name to an existing HvacUnit by floor, or create one.

    No manual pre-configuration required — a unit is named/floored after
    whatever zone label the report uses. Only returns None when the zone
    name is genuinely ambiguous (matches more than one existing unit),
    which needs a human to resolve rather than guessing.
    """
    matches = [u for u in units_docs if (u.get("floor") or "").strip().lower() == zone_name_normalized]
    if len(matches) == 1:
        return matches[0]["id"]
    if len(matches) > 1:
        return None
    color = UNIT_COLOR_PALETTE[len(units_docs) % len(UNIT_COLOR_PALETTE)]
    unit = HvacUnit(name=zone_name, floor=zone_name, color=color)
    await db.hvac_units.insert_one(serialize_doc(unit.model_dump()))
    units_docs.append(unit.model_dump())  # so later zones in the same request see it too
    return unit.id


async def _detect_and_store_zone_anomalies(zone_row: Dict[str, Any]) -> int:
    """Run the real, month-level heat/cool-vs-weather check on one zone-month
    row and store any new flags. Dedupes on (unit_id, type, ts_start) like
    the bill-anomaly path."""
    prop = await _get_property()
    tz = ZoneInfo(prop.timezone) if prop.timezone else timezone.utc
    new_count = 0
    for a in anomalies_mod.detect_zone_mode_weather_mismatch(zone_row, tz=tz):
        exists = await db.anomalies.find_one({
            "unit_id": a["unit_id"], "type": a["type"], "ts_start": a["ts_start"].isoformat(),
        }, {"_id": 0, "id": 1})
        if exists:
            continue
        flag = AnomalyFlag(**a)
        await db.anomalies.insert_one(serialize_doc(flag.model_dump()))
        new_count += 1
    return new_count


async def _upsert_zone_period(
    zone_name: str, period: Dict[str, Any], filename: str, units_docs: List[Dict[str, Any]]
) -> Optional[str]:
    """Upsert one (zone, year, month) row from a parsed report period.

    Returns zone_name if it's ambiguous across multiple existing units (so
    the caller can surface it for manual resolution), else None.
    """
    zone_name_normalized = _normalize_zone_name(zone_name)
    unit_id = await _get_or_create_unit_id(zone_name, zone_name_normalized, units_docs)
    year, month = period.get("year"), period.get("month")
    if not year or not month:
        return None
    is_estimated = bool(period.get("is_estimated", False))

    existing = await db.honeywell_zone_months.find_one(
        {"zone_name_normalized": zone_name_normalized, "year": year, "month": month}, {"_id": 0}
    )
    # Reconciliation: prefer non-estimated data over estimated; otherwise last-write-wins.
    if existing and existing.get("is_estimated") and not is_estimated:
        pass  # incoming (better) data wins — fall through to overwrite
    elif existing and not existing.get("is_estimated") and is_estimated:
        # existing is already better quality — keep it, just record this source
        await db.honeywell_zone_months.update_one(
            {"id": existing["id"]}, {"$addToSet": {"source_reports": filename}}
        )
        return zone_name if not existing.get("unit_id") else None

    fields = {
        "zone_name": zone_name, "zone_name_normalized": zone_name_normalized, "unit_id": unit_id,
        "year": year, "month": month,
        "outdoor_avg_hi_f": period.get("outdoor_avg_hi_f"), "outdoor_avg_lo_f": period.get("outdoor_avg_lo_f"),
        "total_runtime_hours": period.get("total_runtime_hours"),
        "heating_hours": period.get("heating_hours"), "cooling_hours": period.get("cooling_hours"),
        "equipment_off_hours": period.get("equipment_off_hours"),
        "avg_indoor_temp_heating_f": period.get("avg_indoor_temp_heating_f"),
        "avg_indoor_temp_cooling_f": period.get("avg_indoor_temp_cooling_f"),
        "is_estimated": is_estimated, "updated_at": now_utc().isoformat(),
    }
    await db.honeywell_zone_months.update_one(
        {"zone_name_normalized": zone_name_normalized, "year": year, "month": month},
        {"$set": fields, "$addToSet": {"source_reports": filename},
         "$setOnInsert": {"id": new_id(), "created_at": now_utc().isoformat()}},
        upsert=True,
    )
    await _detect_and_store_zone_anomalies(fields)
    return zone_name if unit_id is None else None


@api.post("/honeywell/parse")
async def parse_honeywell(file: UploadFile = File(...)):
    """Parse a monthly zone-runtime report PDF/image. Does NOT persist — returns preview."""
    raw = await file.read()
    mime = file.content_type or ("application/pdf" if file.filename.lower().endswith(".pdf") else "application/octet-stream")
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > 32 * 1024 * 1024:
        raise HTTPException(413, "File too large (>32MB)")
    try:
        parsed = honeywell_parser.parse_honeywell_report(raw, mime)
    except Exception as e:
        logger.exception("Honeywell report parse failed")
        raise HTTPException(500, f"Parse failed: {e}")
    return {"parsed": parsed, "filename": file.filename}


class HoneywellConfirm(BaseModel):
    report_label: Optional[str] = None
    zones: List[Dict[str, Any]]
    filename: str = "unknown"


@api.post("/honeywell/confirm")
async def confirm_honeywell(payload: HoneywellConfirm):
    units_docs = await db.hvac_units.find({}, {"_id": 0}).to_list(50)
    zones_processed = 0
    unmatched_zones: List[str] = []
    for zone in payload.zones:
        zone_name = zone.get("zone_name")
        if not zone_name:
            continue
        for kind in ("current", "prior_year"):
            period = zone.get(kind)
            if not period:
                continue
            unmatched = await _upsert_zone_period(zone_name, period, payload.filename, units_docs)
            zones_processed += 1
            if unmatched and unmatched not in unmatched_zones:
                unmatched_zones.append(unmatched)
    return {"ok": True, "zones_processed": zones_processed, "unmatched_zones": unmatched_zones}


@api.post("/honeywell/bulk-parse")
async def bulk_parse_honeywell(files: List[UploadFile] = File(...)):
    """Parse multiple zone-runtime report PDFs and auto-confirm each. Returns per-file result."""
    results = []
    for f in files:
        try:
            raw = await f.read()
            mime = f.content_type or "application/pdf"
            parsed = honeywell_parser.parse_honeywell_report(raw, mime)
            confirm_resp = await confirm_honeywell(HoneywellConfirm(
                report_label=parsed.get("report_label"), zones=parsed.get("zones", []), filename=f.filename,
            ))
            results.append({
                "filename": f.filename, "ok": True,
                "zones_processed": confirm_resp["zones_processed"],
                "unmatched_zones": confirm_resp["unmatched_zones"],
            })
        except Exception as e:
            results.append({"filename": f.filename, "ok": False, "error": str(e)})
    return {"results": results, "count": len(results)}


@api.get("/honeywell/zone-months")
async def list_honeywell_zone_months(unit_id: Optional[str] = None, unmatched_only: bool = False):
    q: Dict[str, Any] = {}
    if unit_id:
        q["unit_id"] = unit_id
    if unmatched_only:
        q["unit_id"] = None
    docs = await db.honeywell_zone_months.find(q, {"_id": 0}).sort([("year", -1), ("month", -1)]).to_list(2000)
    return docs


class ZoneMonthPatch(BaseModel):
    unit_id: str


@api.patch("/honeywell/zone-months/{zone_month_id}")
async def patch_honeywell_zone_month(zone_month_id: str, payload: ZoneMonthPatch):
    result = await db.honeywell_zone_months.update_one(
        {"id": zone_month_id},
        {"$set": {"unit_id": payload.unit_id, "updated_at": now_utc().isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Zone-month row not found")
    return {"updated": zone_month_id}


@api.post("/honeywell/rescan-anomalies")
async def rescan_zone_anomalies():
    """Re-run the heat/cool-vs-weather check across every stored zone-month.
    Applies the detector retroactively to zone reports uploaded before it
    existed — no re-upload needed, since each zone-month's full parsed data
    is already stored."""
    zone_rows = await db.honeywell_zone_months.find({}, {"_id": 0}).to_list(2000)
    new_anomalies = 0
    for row in zone_rows:
        new_anomalies += await _detect_and_store_zone_anomalies(row)
    return {"zone_months_scanned": len(zone_rows), "new_anomalies": new_anomalies}


@api.get("/honeywell/comparison")
async def honeywell_comparison(start_iso: Optional[str] = None, end_iso: Optional[str] = None):
    """The real answer: each unit's runtime-hour share of the month applied to
    that month's real Green-Button kWh/cost. Works for any number of units
    and any date range — defaults to the last 2 years if unspecified."""
    prop = await _get_property()
    if start_iso and end_iso:
        start = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=730)
    intervals = await _load_intervals(start, end)
    zone_rows = await db.honeywell_zone_months.find({}, {"_id": 0}).to_list(2000)
    rate_lookup = await _build_rate_lookup(prop.rate_usd_per_kwh)

    interval_buckets = monthly_cost.bucket_intervals_by_month(intervals)
    zone_buckets = monthly_cost.group_zone_rows_by_month(zone_rows)
    months = monthly_cost.compute_unit_cost_comparison(zone_buckets, interval_buckets, rate_lookup)
    return {"months": months}


# ---------- Export ----------

@api.get("/export/csv")
async def export_csv(days: int = 30):
    units = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    intervals = await _load_intervals(start, end)
    csv_text = report_mod.intervals_to_csv(intervals, units)
    return StreamingResponse(io.BytesIO(csv_text.encode()), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="hvac-intervals.csv"'})


@api.get("/export/pdf")
async def export_pdf(days: int = 30):
    prop = await _get_property()
    units_docs = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    intervals = await _load_intervals(start, end)
    unit_ids = [u["id"] for u in units_docs]
    readings_by_unit = {u["id"]: await _load_readings(u["id"], start, end) for u in units_docs}
    summary = attribution.summarize_by_unit(intervals, unit_ids, readings_by_unit)
    anomaly_docs = await db.anomalies.find(
        {"ts_start": {"$gte": start.isoformat(), "$lte": end.isoformat()}}, {"_id": 0}
    ).sort("severity", 1).to_list(200)

    pdf_bytes = report_mod.build_pdf_report(
        prop.model_dump(),
        units_docs,
        summary,
        anomaly_docs,
        f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
        intervals=intervals,
        yoy=await year_over_year(),
    )
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="hvac-report.pdf"'})


@api.get("/export/bills-csv")
async def export_bills_csv():
    bills = await db.bill_periods.find({}, {"_id": 0}).sort("start", 1).to_list(500)
    for b in bills:
        b["start"] = datetime.fromisoformat(b["start"])
        b["end"] = datetime.fromisoformat(b["end"])
    csv_text = report_mod.bills_to_csv(bills)
    return StreamingResponse(io.BytesIO(csv_text.encode()), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="hvac-bills.csv"'})


@api.get("/export/zone-months-csv")
async def export_zone_months_csv():
    zone_rows = await db.honeywell_zone_months.find({}, {"_id": 0}).to_list(2000)
    units = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    csv_text = report_mod.zone_months_to_csv(zone_rows, units)
    return StreamingResponse(io.BytesIO(csv_text.encode()), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="hvac-zone-months.csv"'})


# ---------- Pipeline (one-click convenience) ----------

@api.post("/pipeline/run")
async def run_pipeline(days: int = 14):
    """Convenience: sync thermostats + weather, run attribution, run anomalies."""
    r1 = await resideo_sync(days)
    r2 = None
    try:
        r2 = await ingest_noaa(days)
    except HTTPException:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        weather = noaa.mock_weather(start, end)
        n = await _insert_new_weather(weather)
        r2 = {"inserted": n, "source": "synthetic"}
    r3 = await run_attribution(days)
    r4 = await run_anomaly_detection(days)
    return {"thermostats": r1, "weather": r2, "attribution": r3, "anomalies": r4}


@api.post("/pipeline/backfill-all")
async def backfill_all():
    """Run the mock-thermostat/attribution/anomaly pipeline across the FULL
    span of whatever Green Button data actually exists — not just a rolling
    recent window — so newly-uploaded historical bills/reports actually get
    reflected everywhere instead of only the last N days."""
    earliest_iv = await db.energy_intervals.find_one({}, {"_id": 0}, sort=[("ts_start", 1)])
    if not earliest_iv:
        raise HTTPException(400, "No Green Button data uploaded yet")
    start = datetime.fromisoformat(earliest_iv["ts_start"])
    end = datetime.now(timezone.utc)
    start_iso, end_iso = start.isoformat(), end.isoformat()

    r1 = await resideo_sync(days=0, start_iso=start_iso, end_iso=end_iso, force_recompute=True)
    try:
        r2 = await ingest_noaa(days=(end - start).days + 1)
    except HTTPException:
        weather = noaa.mock_weather(start, end)
        n = await _insert_new_weather(weather)
        r2 = {"inserted": n, "source": "synthetic"}
    r3 = await run_attribution(days=0, start_iso=start_iso, end_iso=end_iso)
    r4 = await run_anomaly_detection(days=0, start_iso=start_iso, end_iso=end_iso)
    return {"thermostats": r1, "weather": r2, "attribution": r3, "anomalies": r4, "range": {"start": start_iso, "end": end_iso}}


# ---------- Scheduler ----------

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


async def scheduled_poll():
    try:
        units = await db.hvac_units.count_documents({})
        if units == 0:
            return
        logger.info("Scheduled poll — syncing Resideo mock + running pipeline")
        await resideo_sync(1)
        await run_attribution(30)
        await run_anomaly_detection(30)
    except Exception as e:
        logger.exception("Scheduled poll failed: %s", e)


@app.on_event("startup")
async def _startup():
    await db.honeywell_zone_months.create_index(
        [("zone_name_normalized", 1), ("year", 1), ("month", 1)], unique=True
    )
    scheduler.add_job(scheduled_poll, "interval", minutes=15, id="hvac-poll", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started")


@app.on_event("shutdown")
async def _shutdown():
    scheduler.shutdown(wait=False)
    client.close()


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
