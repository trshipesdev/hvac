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


class HvacUnit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    name: str
    floor: Optional[str] = None  # e.g. "Upstairs" / "Downstairs"
    install_year: Optional[int] = None
    tonnage: Optional[float] = None
    thermostat_device_id: Optional[str] = None  # Resideo device id (or mock)
    color: str = "#3b82f6"
    created_at: datetime = Field(default_factory=now_utc)


class HvacUnitCreate(BaseModel):
    name: str
    floor: Optional[str] = None
    install_year: Optional[int] = None
    tonnage: Optional[float] = None
    thermostat_device_id: Optional[str] = None
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


class WeatherReading(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=new_id)
    ts: datetime
    outdoor_temp_f: Optional[float] = None
    humidity: Optional[float] = None
    source: str = "noaa"


# --- Anomaly ---

AnomalyType = Literal[
    "extended_runtime",
    "overnight_draw",
    "efficiency_regression",
    "weather_disproportion",
    "setpoint_gap_widening",
    "bill_rate_spike",
    "bill_past_due",
    "bill_late_fee",
    "bill_usage_spike",
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
