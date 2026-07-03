"""HVAC Efficiency Analyzer — FastAPI entrypoint."""
from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Header, Depends, Query, Response
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import os
import io
import logging

from models import (
    Property, PropertyUpdate, HvacUnit, HvacUnitCreate,
    EnergyInterval, ThermostatReading, WeatherReading,
    AnomalyFlag, BillPeriod, BillPeriodCreate, RatePeriod,
    serialize_doc, deserialize_doc, new_id, now_utc,
)
from pydantic import BaseModel
import greenbutton
import noaa
import resideo
import attribution
import anomalies as anomalies_mod
import report as report_mod
import bill_parser
import bill_anomalies

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="HVAC Efficiency Analyzer")
api = APIRouter(prefix="/api")

PASSPHRASE = os.environ.get("API_PASSPHRASE", "changeme")


# ---------- Auth (passphrase header) ----------

async def require_passphrase(x_api_passphrase: Optional[str] = Header(default=None)):
    if not PASSPHRASE:
        return True
    if x_api_passphrase != PASSPHRASE:
        raise HTTPException(status_code=401, detail="Invalid or missing passphrase")
    return True


@api.get("/auth/check")
async def auth_check(x_api_passphrase: Optional[str] = Header(default=None)):
    if not PASSPHRASE:
        return {"authenticated": True, "auth_required": False}
    ok = (x_api_passphrase == PASSPHRASE)
    return {"authenticated": ok, "auth_required": True}


@api.get("/health")
async def health():
    return {"status": "ok", "time": now_utc().isoformat()}


# ---------- Property ----------

DATE_FIELDS = ["created_at", "updated_at", "ts", "ts_start", "ts_end", "start", "end",
               "detected_at", "attributed_at", "detected_at"]


async def _get_property() -> Property:
    doc = await db.property.find_one({}, {"_id": 0})
    if not doc:
        prop = Property(rate_usd_per_kwh=float(os.environ.get("DEFAULT_RATE_USD_PER_KWH", 0.14)))
        await db.property.insert_one(serialize_doc(prop.model_dump()))
        return prop
    doc = deserialize_doc(doc, DATE_FIELDS)
    return Property(**doc)


@api.get("/property", response_model=Property, dependencies=[Depends(require_passphrase)])
async def get_property():
    return await _get_property()


@api.put("/property", response_model=Property, dependencies=[Depends(require_passphrase)])
async def update_property(update: PropertyUpdate):
    prop = await _get_property()
    data = prop.model_dump()
    for k, v in update.model_dump(exclude_unset=True).items():
        data[k] = v
    data["updated_at"] = now_utc()
    prop2 = Property(**data)
    await db.property.replace_one({"id": prop.id}, serialize_doc(prop2.model_dump()), upsert=True)
    return prop2


# ---------- Units ----------

@api.get("/units", response_model=List[HvacUnit], dependencies=[Depends(require_passphrase)])
async def list_units():
    docs = await db.hvac_units.find({}, {"_id": 0}).to_list(50)
    return [HvacUnit(**deserialize_doc(d, DATE_FIELDS)) for d in docs]


@api.post("/units", response_model=HvacUnit, dependencies=[Depends(require_passphrase)])
async def create_unit(payload: HvacUnitCreate):
    existing = await db.hvac_units.count_documents({})
    default_color = "#3b82f6" if existing == 0 else "#8b5cf6"
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    data.setdefault("color", default_color)
    unit = HvacUnit(**data)
    await db.hvac_units.insert_one(serialize_doc(unit.model_dump()))
    return unit


@api.put("/units/{unit_id}", response_model=HvacUnit, dependencies=[Depends(require_passphrase)])
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


@api.delete("/units/{unit_id}", dependencies=[Depends(require_passphrase)])
async def delete_unit(unit_id: str):
    await db.hvac_units.delete_one({"id": unit_id})
    return {"deleted": unit_id}


# ---------- Green Button ingest ----------

@api.post("/ingest/green-button", dependencies=[Depends(require_passphrase)])
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


@api.get("/ingest/sample-xml", dependencies=[Depends(require_passphrase)])
async def sample_xml():
    """Return a downloadable sample Green Button XML for testing."""
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=10)
    xml = greenbutton.generate_sample_xml(start, days=10, interval_min=15)
    return StreamingResponse(io.BytesIO(xml), media_type="application/xml",
                             headers={"Content-Disposition": 'attachment; filename="sample-green-button.xml"'})


# ---------- Weather (NOAA) ----------

@api.post("/ingest/noaa", dependencies=[Depends(require_passphrase)])
async def ingest_noaa(days: int = 30):
    prop = await _get_property()
    if not prop.noaa_station_id:
        raise HTTPException(400, "NOAA station not configured on property")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    daily = await noaa.fetch_daily_temps(prop.noaa_station_id, start, end)
    if not daily:
        # fallback: synthesize
        daily_records = noaa.mock_weather(start, end)
    else:
        daily_records = noaa.synthesize_hourly_from_daily(daily)

    inserted = 0
    for r in daily_records:
        exists = await db.weather.find_one({"ts": r["ts"].isoformat()}, {"_id": 0, "id": 1})
        if exists:
            continue
        w = WeatherReading(**r)
        await db.weather.insert_one(serialize_doc(w.model_dump()))
        inserted += 1
    return {"inserted": inserted, "range_days": days, "source": "noaa" if daily else "synthetic"}


@api.get("/noaa/stations", dependencies=[Depends(require_passphrase)])
async def noaa_stations(zip_code: str):
    return await noaa.find_stations(zip_code)


# ---------- Resideo ----------

@api.get("/resideo/status", dependencies=[Depends(require_passphrase)])
async def resideo_status():
    return resideo.oauth_status()


@api.post("/resideo/sync", dependencies=[Depends(require_passphrase)])
async def resideo_sync(days: int = 10):
    """Fetch thermostat data. In mock mode, generate deterministic samples."""
    units = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    if not units:
        raise HTTPException(400, "No HVAC units configured")
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days)
    inserted = 0
    for idx, u in enumerate(units):
        readings = resideo.mock_thermostat_series(u["id"], idx, start, end, interval_min=5)
        for r in readings:
            exists = await db.thermostat_readings.find_one(
                {"unit_id": r["unit_id"], "ts": r["ts"].isoformat()}, {"_id": 0, "id": 1}
            )
            if exists:
                continue
            tr = ThermostatReading(**r)
            await db.thermostat_readings.insert_one(serialize_doc(tr.model_dump()))
            inserted += 1
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


@api.get("/rate-periods", response_model=List[RatePeriod], dependencies=[Depends(require_passphrase)])
async def list_rate_periods():
    docs = await _load_rate_periods()
    return [RatePeriod(**d) for d in docs]


@api.post("/attribution/run", dependencies=[Depends(require_passphrase)])
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
    for iv in intervals:
        await db.energy_intervals.replace_one({"id": iv["id"]}, serialize_doc(iv), upsert=False)
    return {"attributed": len(intervals), "start": start.isoformat(), "end": end.isoformat()}


# ---------- Anomaly detection ----------

@api.post("/anomalies/run", dependencies=[Depends(require_passphrase)])
async def run_anomaly_detection(days: int = 30):
    units_docs = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    intervals = await _load_intervals(start, end)
    weather = await _load_weather(start, end)

    # Clear previous UN-acknowledged HVAC anomalies in the window; keep acknowledged ones
    await db.anomalies.delete_many({
        "ts_start": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        "acknowledged": {"$ne": True},
        "category": {"$ne": "bill"},
    })

    total = 0
    for u in units_docs:
        readings = await _load_readings(u["id"], start, end)
        found = anomalies_mod.run_all(u["id"], readings, intervals, weather)
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


@api.get("/anomalies", response_model=List[AnomalyFlag], dependencies=[Depends(require_passphrase)])
async def list_anomalies(
    unit_id: Optional[str] = None,
    severity: Optional[str] = None,
    type: Optional[str] = None,
    category: Optional[str] = None,
    include_acknowledged: bool = False,
    limit: int = 500,
):
    q: Dict[str, Any] = {}
    if unit_id:
        q["unit_id"] = unit_id
    if severity:
        q["severity"] = severity
    if type:
        q["type"] = type
    if category:
        q["category"] = category
    if not include_acknowledged:
        q["acknowledged"] = {"$ne": True}
    docs = await db.anomalies.find(q, {"_id": 0}).sort("ts_start", -1).to_list(limit)
    return [AnomalyFlag(**deserialize_doc(d, DATE_FIELDS)) for d in docs]


class AckPayload(BaseModel):
    ack_note: Optional[str] = None


@api.post("/anomalies/{anomaly_id}/ack", dependencies=[Depends(require_passphrase)])
async def acknowledge_anomaly(anomaly_id: str, payload: AckPayload = AckPayload()):
    result = await db.anomalies.update_one(
        {"id": anomaly_id},
        {"$set": {"acknowledged": True, "acknowledged_at": now_utc().isoformat(), "ack_note": payload.ack_note}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Anomaly not found")
    return {"acknowledged": anomaly_id}


@api.post("/anomalies/{anomaly_id}/unack", dependencies=[Depends(require_passphrase)])
async def unack_anomaly(anomaly_id: str):
    await db.anomalies.update_one(
        {"id": anomaly_id},
        {"$set": {"acknowledged": False, "acknowledged_at": None, "ack_note": None}},
    )
    return {"unacknowledged": anomaly_id}


# ---------- Dashboard aggregates ----------

@api.get("/dashboard/timeline", dependencies=[Depends(require_passphrase)])
async def dashboard_timeline(
    days: int = 7,
    bucket: str = "hour",  # hour | day
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
):
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
        if bucket == "day":
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:00")

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
            b["outdoor_temp_f"] = round(sum(temps) / len(temps), 1)
        elif isinstance(temps, list):
            b.pop("outdoor_temp_f", None)

    series = sorted(buckets.values(), key=lambda x: x["ts"])
    units_meta = [{"id": u["id"], "name": u["name"], "color": u.get("color", "#3b82f6")} for u in units_docs]
    return {"series": series, "units": units_meta, "bucket": bucket, "days": days}


@api.get("/dashboard/summary", dependencies=[Depends(require_passphrase)])
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
    active_anomalies = await db.anomalies.count_documents(
        {"ts_start": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
    )
    critical_anomalies = await db.anomalies.count_documents(
        {"ts_start": {"$gte": start.isoformat(), "$lte": end.isoformat()}, "severity": "critical"}
    )
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

@api.get("/dashboard/yoy", dependencies=[Depends(require_passphrase)])
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


@api.get("/dashboard/drilldown", dependencies=[Depends(require_passphrase)])
async def timeline_drilldown(ts: str, bucket: str = "hour"):
    """Return raw intervals + thermostat activity + weather + anomalies for a bucket."""
    if bucket == "day":
        start = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)
    else:
        start = datetime.fromisoformat(ts.replace(" ", "T")).replace(tzinfo=timezone.utc)
        end = start + timedelta(hours=1)

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


@api.get("/dashboard/data-status", dependencies=[Depends(require_passphrase)])
async def data_status():
    intervals_count = await db.energy_intervals.count_documents({})
    readings_count = await db.thermostat_readings.count_documents({})
    weather_count = await db.weather.count_documents({})
    latest_iv = await db.energy_intervals.find_one({}, {"_id": 0}, sort=[("ts_start", -1)])
    latest_r = await db.thermostat_readings.find_one({}, {"_id": 0}, sort=[("ts", -1)])
    latest_w = await db.weather.find_one({}, {"_id": 0}, sort=[("ts", -1)])
    return {
        "energy_intervals": intervals_count,
        "thermostat_readings": readings_count,
        "weather_readings": weather_count,
        "latest_energy_ts": latest_iv["ts_start"] if latest_iv else None,
        "latest_thermostat_ts": latest_r["ts"] if latest_r else None,
        "latest_weather_ts": latest_w["ts"] if latest_w else None,
        "resideo": resideo.oauth_status(),
    }


# ---------- Bill periods ----------

@api.get("/bills", response_model=List[BillPeriod], dependencies=[Depends(require_passphrase)])
async def list_bills():
    docs = await db.bill_periods.find({}, {"_id": 0}).sort("start", -1).to_list(100)
    return [BillPeriod(**deserialize_doc(d, DATE_FIELDS)) for d in docs]


@api.post("/bills", response_model=BillPeriod, dependencies=[Depends(require_passphrase)])
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


@api.delete("/bills/{bill_id}", dependencies=[Depends(require_passphrase)])
async def delete_bill(bill_id: str):
    await db.bill_periods.delete_one({"id": bill_id})
    return {"deleted": bill_id}


# ---------- Bill PDF upload + AI parse ----------

@api.post("/bills/parse", dependencies=[Depends(require_passphrase)])
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


@api.post("/bills/confirm", response_model=BillPeriod, dependencies=[Depends(require_passphrase)])
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

    # Run bill anomaly detector
    prior_rps = await _load_rate_periods()
    prior_before = [rp for rp in prior_rps if rp["start"] < start]
    bill_anoms = bill_anomalies.detect_bill_anomalies(p, bp.id, prior_before)
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
        prop = await _get_property()
        data = prop.model_dump()
        data["rate_usd_per_kwh"] = rate
        data["updated_at"] = now_utc()
        prop2 = Property(**data)
        await db.property.replace_one({"id": prop.id}, serialize_doc(prop2.model_dump()), upsert=True)

    return bp


@api.post("/bills/bulk-parse", dependencies=[Depends(require_passphrase)])
async def bulk_parse(files: List[UploadFile] = File(...)):
    """Parse multiple bill PDFs and auto-confirm each. Returns per-file result."""
    results = []
    for f in files:
        try:
            raw = await f.read()
            mime = f.content_type or "application/pdf"
            parsed = bill_parser.parse_bill(raw, mime)
            # Confirm inline
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


# ---------- Export ----------

@api.get("/export/csv", dependencies=[Depends(require_passphrase)])
async def export_csv(days: int = 30):
    units = await db.hvac_units.find({}, {"_id": 0}).to_list(10)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    intervals = await _load_intervals(start, end)
    csv_text = report_mod.intervals_to_csv(intervals, units)
    return StreamingResponse(io.BytesIO(csv_text.encode()), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="hvac-intervals.csv"'})


@api.get("/export/pdf", dependencies=[Depends(require_passphrase)])
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


# ---------- Pipeline (one-click convenience) ----------

@api.post("/pipeline/run", dependencies=[Depends(require_passphrase)])
async def run_pipeline(days: int = 14):
    """Convenience: sync thermostats + weather, run attribution, run anomalies."""
    r1 = await resideo_sync(days)
    r2 = None
    try:
        r2 = await ingest_noaa(days)
    except HTTPException:
        # fall back to synthetic weather
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        weather = noaa.mock_weather(start, end)
        for w in weather:
            exists = await db.weather.find_one({"ts": w["ts"].isoformat()}, {"_id": 0, "id": 1})
            if exists:
                continue
            await db.weather.insert_one(serialize_doc(WeatherReading(**w).model_dump()))
        r2 = {"inserted": len(weather), "source": "synthetic"}
    r3 = await run_attribution(days)
    r4 = await run_anomaly_detection(days)
    return {"thermostats": r1, "weather": r2, "attribution": r3, "anomalies": r4}


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
