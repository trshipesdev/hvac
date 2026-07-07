"""Pydantic models for HVAC Efficiency Analyzer."""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --- Property & Units ---

class Property(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    name: str = "My Home"
    address: Optional[str] = None
    zip_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    noaa_station_id: Optional[str] = None  # e.g. GHCND:USW00093738
    rate_usd_per_kwh: float = 0.14
    # Which anomaly types to surface on the Dashboard (KPI count + Recent
    # Anomalies list). None = show every type. Lets a user mute noisy
    # categories (e.g. bill_late_fee/bill_past_due) without losing them —
    # they still exist and are visible on the full Anomalies page either way.
    dashboard_anomaly_types: Optional[List[str]] = None
    timezone: Optional[str] = None  # IANA name, e.g. "America/New_York" — auto-derived from lat/long
    use_24h_time: bool = False
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class PropertyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    zip_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    noaa_station_id: Optional[str] = None
    rate_usd_per_kwh: Optional[float] = None
    dashboard_anomaly_types: Optional[List[str]] = None
    timezone: Optional[str] = None
    use_24h_time: Optional[bool] = None


class HvacUnit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    name: str
    floor: Optional[str] = None  # e.g. "Upstairs" / "Downstairs"
    install_year: Optional[int] = None
    tonnage: Optional[float] = None
    thermostat_device_id: Optional[str] = None  # Resideo device id (or mock)
    resideo_location_id: Optional[str] = None  # Resideo locationId — the API needs both to address a device
    color: str = "#3b82f6"
    created_at: datetime = Field(default_factory=now_utc)


class HvacUnitCreate(BaseModel):
    name: str
    floor: Optional[str] = None
    install_year: Optional[int] = None
    tonnage: Optional[float] = None
    thermostat_device_id: Optional[str] = None
    resideo_location_id: Optional[str] = None
    color: Optional[str] = None


# --- Time series ---

class EnergyInterval(BaseModel):
    """15-minute whole-home energy reading from Green Button."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    ts_start: datetime  # start of interval (utc)
    ts_end: datetime
    kwh: float
    source: str = "green_button"
    # Attribution result (populated by engine)
    unit_kwh: Dict[str, float] = Field(default_factory=dict)  # {unit_id: kwh}
    base_load_kwh: float = 0.0
    unit_cost: Dict[str, float] = Field(default_factory=dict)  # {unit_id: usd}
    base_load_cost: float = 0.0
    attributed_at: Optional[datetime] = None


class ThermostatReading(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    unit_id: str
    ts: datetime
    setpoint_f: Optional[float] = None
    actual_temp_f: Optional[float] = None
    compressor_on: bool = False
    runtime_seconds: Optional[float] = None  # seconds of runtime in this sample window
    mode: Optional[str] = None  # cool/heat/off
    # Ground truth for how trustworthy this reading is: "mock" (pure
    # fabrication, no real data available), "estimated" (calibrated against
    # a real HoneywellZoneMonth report — see thermostat_estimation.py), or
    # "resideo" (a real live poll). Anomaly detection and the dashboard both
    # key off this per-reading, never a blanket assumption for a whole batch.
    source: Literal["mock", "estimated", "resideo"] = "mock"


class ResideoTokens(BaseModel):
    """Internal-only — never returned over the API. Singleton doc, id='singleton'."""
    model_config = ConfigDict(extra="ignore")
    id: str = "singleton"
    access_token: str
    refresh_token: str
    expires_at: datetime
    updated_at: datetime = Field(default_factory=now_utc)


class WeatherReading(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    ts: datetime
    outdoor_temp_f: Optional[float] = None
    humidity: Optional[float] = None
    # "open-meteo" = real hourly observation. "noaa_synthetic" = a real NOAA
    # daily average with a fabricated +/-10F hourly curve around it (legacy
    # approach, kept only as a fallback when coordinates aren't known yet).
    # "synthetic" = fully fabricated, no real signal at all. Default is the
    # least-trustworthy label, not a false claim of being real NOAA data.
    source: str = "synthetic"


# --- Honeywell / vendor thermostat zone-runtime reports ---

class HoneywellZoneMonth(BaseModel):
    """One row per (zone, year, month) — durable storage for real per-zone
    runtime data parsed from monthly thermostat energy-report emails. A
    "report" (the PDF/email) is just the ingestion vehicle, not stored
    itself; this row is the thing that persists."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    zone_name: str  # raw as parsed, e.g. "Upstairs"
    zone_name_normalized: str  # zone_name.strip().lower(), dedupe key
    unit_id: Optional[str] = None  # resolved HvacUnit.id; None if unmatched

    year: int
    month: int  # 1-12

    outdoor_avg_hi_f: Optional[float] = None
    outdoor_avg_lo_f: Optional[float] = None
    total_runtime_hours: Optional[float] = None
    heating_hours: Optional[float] = None
    cooling_hours: Optional[float] = None
    equipment_off_hours: Optional[float] = None
    avg_indoor_temp_heating_f: Optional[float] = None
    avg_indoor_temp_cooling_f: Optional[float] = None
    is_estimated: bool = False  # thermostat offline / estimated caveat

    source_reports: List[str] = Field(default_factory=list)  # contributing filenames


# --- Anomaly ---

AnomalyType = Literal[
    "extended_runtime",
    "overnight_draw",
    "efficiency_regression",
    "weather_disproportion",
    "setpoint_gap_widening",
    "zone_mode_weather_mismatch",
    "mode_weather_mismatch",
    "bill_rate_spike",
    "bill_past_due",
    "bill_late_fee",
    "bill_usage_spike",
    "bill_meter_mismatch",
    "bill_period_gap",
]

Severity = Literal["critical", "warning", "info"]


class AnomalyFlag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    unit_id: Optional[str]
    type: AnomalyType
    severity: Severity
    ts_start: datetime
    ts_end: datetime
    title: str
    description: str
    context: Dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=now_utc)
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    ack_note: Optional[str] = None
    category: str = "hvac"  # "hvac" | "bill"


# --- Bill period ---

class BillPeriod(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    start: datetime
    end: datetime
    total_kwh: Optional[float] = None
    total_cost: Optional[float] = None
    rate_usd_per_kwh: Optional[float] = None
    computed_kwh: Optional[float] = None
    computed_cost: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=now_utc)


class BillPeriodCreate(BaseModel):
    start: datetime
    end: datetime
    total_kwh: Optional[float] = None
    total_cost: Optional[float] = None
    rate_usd_per_kwh: Optional[float] = None
    notes: Optional[str] = None


class RatePeriod(BaseModel):
    """Time-varying $/kWh derived from parsed bills."""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    start: datetime
    end: datetime
    effective_rate: float
    tiers: Optional[List[Dict[str, Any]]] = None  # from bill: [{tier_name, kwh, rate_per_kwh, amount}]
    source_bill_id: Optional[str] = None
    utility_name: Optional[str] = None
    created_at: datetime = Field(default_factory=now_utc)


# --- Aux ---

class IngestSummary(BaseModel):
    inserted: int
    skipped: int
    range_start: Optional[datetime] = None
    range_end: Optional[datetime] = None


def serialize_doc(doc: dict) -> dict:
    """Convert datetime fields to ISO strings for Mongo storage."""
    out = {}
    for k, v in doc.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = serialize_doc(v)
        elif isinstance(v, list):
            out[k] = [serialize_doc(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


def deserialize_doc(doc: dict, date_fields: List[str] = None) -> dict:
    """Convert known ISO string fields back to datetimes."""
    if not doc:
        return doc
    date_fields = date_fields or []
    out = dict(doc)
    out.pop("_id", None)
    for f in date_fields:
        if f in out and isinstance(out[f], str):
            try:
                out[f] = datetime.fromisoformat(out[f])
            except Exception:
                pass
    return out
