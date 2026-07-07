"""Resideo/Honeywell thermostat integration (mock mode until OAuth approved).

Real API notes (developer.honeywellhome.com, verified before building this):
GET /v2/devices/thermostats/{deviceId} is a live CURRENT-MOMENT SNAPSHOT
only — there is no bulk historical/runtime endpoint for thermostats
anywhere in the API. Real data can only ever be built by polling forward
from connection time; it can never backfill past months (that's what the
Honeywell monthly-email workaround — honeywell_parser.py — is for, and it
keeps mattering even after this connects). Access tokens last 599 seconds.
"""
import os
import math
import base64
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

MOCK_MODE = os.environ.get("RESIDEO_MOCK_MODE", "true").lower() == "true"

API_HOST = "https://api.honeywellhome.com"
TOKEN_URL = f"{API_HOST}/oauth2/token"
LOCATIONS_URL = f"{API_HOST}/v2/locations"
THERMOSTAT_URL = f"{API_HOST}/v2/devices/thermostats/{{device_id}}"


def is_mock() -> bool:
    return MOCK_MODE or not os.environ.get("RESIDEO_CLIENT_ID")


def oauth_status(connected: bool = False) -> Dict[str, Any]:
    configured = bool(os.environ.get("RESIDEO_CLIENT_ID"))
    if is_mock():
        message = (
            "Running in MOCK mode. Resideo developer approval is pending "
            "(1-2 week SLA). Configure RESIDEO_CLIENT_ID / RESIDEO_CLIENT_SECRET "
            "in backend/.env and set RESIDEO_MOCK_MODE=false to switch to live."
        )
    elif not connected:
        message = "Credentials configured — click Connect Resideo below to authorize."
    else:
        message = "Live — connected to Resideo."
    return {
        "mock_mode": is_mock(),
        "client_id_configured": configured,
        "connected": connected,
        "oauth_url": build_oauth_url(),
        "message": message,
    }


def mock_thermostat_series(
    unit_id: str,
    unit_index: int,
    start: datetime,
    end: datetime,
    interval_min: int = 5,
) -> List[Dict[str, Any]]:
    """Generate deterministic thermostat readings for a unit — pure
    fabrication, used only when no real Honeywell report exists for this
    unit+month either (see thermostat_estimation.py for the calibrated path).

    unit_index 0 = healthy unit, unit_index 1 = degraded unit (higher runtime).
    """
    random.seed(101 + unit_index)
    out = []
    t = start.replace(second=0, microsecond=0)
    dt = timedelta(minutes=interval_min)
    setpoint = 72.0 if unit_index == 0 else 74.0
    actual = setpoint + 1.0

    while t < end:
        hour = t.hour
        # Outdoor-ish load: peaks midday
        outdoor_pressure = max(0.0, math.sin((hour - 4) * math.pi / 16))
        # Degraded unit has higher runtime probability + wider gap
        if unit_index == 1:
            base_prob = 0.20 + outdoor_pressure * 0.60
            gap_bias = 1.5
        else:
            base_prob = 0.05 + outdoor_pressure * 0.35
            gap_bias = 0.3

        # Overnight anomaly for unit 1 on certain days
        if unit_index == 1 and t.weekday() == 2 and 2 <= hour <= 5:
            base_prob = max(base_prob, 0.55)

        compressor_on = random.random() < base_prob
        runtime_seconds = interval_min * 60 * (0.9 if compressor_on else 0.0)

        # Actual temperature drifts if compressor off during heat
        if compressor_on:
            actual = max(setpoint - 1, actual - 0.4)
        else:
            actual = actual + outdoor_pressure * (0.3 + gap_bias * 0.1)
        actual = max(60.0, min(90.0, actual + random.uniform(-0.15, 0.15)))

        out.append({
            "unit_id": unit_id,
            "ts": t,
            "setpoint_f": setpoint,
            "actual_temp_f": round(actual, 1),
            "compressor_on": compressor_on,
            "runtime_seconds": runtime_seconds,
            "mode": "cool",
            "source": "mock",
        })
        t += dt
    return out


def build_oauth_url() -> str:
    """Out-of-band flow — Resideo shows the user a code on-screen rather
    than redirecting a browser back to this app, so no public callback URL
    is needed for a local single-user app."""
    client_id = os.environ.get("RESIDEO_CLIENT_ID", "")
    if not client_id:
        return ""
    return (
        f"{API_HOST}/oauth2/authorize?"
        f"response_type=code&client_id={client_id}&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
    )


def _basic_auth_header() -> Dict[str, str]:
    client_id = os.environ.get("RESIDEO_CLIENT_ID", "")
    client_secret = os.environ.get("RESIDEO_CLIENT_SECRET", "")
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}


def _token_response_to_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    expires_in = int(data.get("expires_in", 599))
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    }


async def exchange_code(code: str) -> Dict[str, Any]:
    """POST /oauth2/token, grant_type=authorization_code."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(TOKEN_URL, headers=_basic_auth_header(), data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        })
        if r.status_code != 200:
            raise ValueError(f"Resideo token exchange failed: {r.status_code} {r.text[:200]}")
        return _token_response_to_dict(r.json())


async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    """POST /oauth2/token, grant_type=refresh_token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(TOKEN_URL, headers=_basic_auth_header(), data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })
        if r.status_code != 200:
            raise ValueError(f"Resideo token refresh failed: {r.status_code} {r.text[:200]}")
        return _token_response_to_dict(r.json())


async def list_locations(access_token: str) -> List[Dict[str, Any]]:
    """GET /v2/locations — raw Resideo payload (locations+devices) for the
    unit-assignment dropdown."""
    client_id = os.environ.get("RESIDEO_CLIENT_ID", "")
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(LOCATIONS_URL, headers={"Authorization": f"Bearer {access_token}"},
                              params={"apikey": client_id})
        if r.status_code != 200:
            logger.warning("Resideo locations fetch failed: %s %s", r.status_code, r.text[:200])
            return []
        return r.json()


async def fetch_thermostat_snapshot(access_token: str, device_id: str, location_id: str) -> Dict[str, Any]:
    """GET /v2/devices/thermostats/{deviceId} — a live current-moment
    snapshot, not a history. See module docstring."""
    client_id = os.environ.get("RESIDEO_CLIENT_ID", "")
    url = THERMOSTAT_URL.format(device_id=device_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {access_token}"},
                              params={"apikey": client_id, "locationId": location_id})
        if r.status_code != 200:
            raise ValueError(f"Resideo thermostat fetch failed: {r.status_code} {r.text[:200]}")
        return r.json()


_MODE_MAP = {"heat": "heat", "cool": "cool", "emergencyheat": "heat"}


def snapshot_to_reading(unit_id: str, snapshot: Dict[str, Any], runtime_seconds: float) -> Dict[str, Any]:
    """Map a real snapshot to our ThermostatReading shape.

    Uses operationStatus.mode (what's ACTUALLY running — "Heat"/"Cool"/
    "EquipmentOff") rather than changeableValues.mode (just the selected
    mode, e.g. "Auto") — the anomaly detector needs real running state.
    """
    op_mode = (snapshot.get("operationStatus", {}) or {}).get("mode", "") or ""
    op_mode_l = op_mode.strip().lower()
    mode = _MODE_MAP.get(op_mode_l)
    compressor_on = mode is not None

    changeable = snapshot.get("changeableValues", {}) or {}
    setpoint_f = None
    if mode == "heat":
        setpoint_f = changeable.get("heatSetpoint")
    elif mode == "cool":
        setpoint_f = changeable.get("coolSetpoint")

    return {
        "unit_id": unit_id,
        "ts": datetime.now(timezone.utc),
        "setpoint_f": setpoint_f,
        "actual_temp_f": snapshot.get("indoorTemperature"),
        "compressor_on": compressor_on,
        "runtime_seconds": runtime_seconds if compressor_on else 0.0,
        "mode": mode or "off",
        "source": "resideo",
    }
