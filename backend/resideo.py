"""Resideo/Honeywell thermostat integration (mock mode until OAuth approved)."""
import os
import math
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

MOCK_MODE = os.environ.get("RESIDEO_MOCK_MODE", "true").lower() == "true"


def is_mock() -> bool:
    return MOCK_MODE or not os.environ.get("RESIDEO_CLIENT_ID")


def oauth_status() -> Dict[str, Any]:
    return {
        "mock_mode": is_mock(),
        "client_id_configured": bool(os.environ.get("RESIDEO_CLIENT_ID")),
        "message": (
            "Running in MOCK mode. Resideo developer approval is pending "
            "(1-2 week SLA). Configure RESIDEO_CLIENT_ID / RESIDEO_CLIENT_SECRET "
            "in backend/.env and set RESIDEO_MOCK_MODE=false to switch to live."
            if is_mock()
            else "Live Resideo credentials detected."
        ),
    }


def mock_thermostat_series(
    unit_id: str,
    unit_index: int,
    start: datetime,
    end: datetime,
    interval_min: int = 5,
) -> List[Dict[str, Any]]:
    """Generate deterministic thermostat readings for a unit.

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
        })
        t += dt
    return out


def build_oauth_url() -> str:
    """Placeholder for the OAuth authorization URL."""
    client_id = os.environ.get("RESIDEO_CLIENT_ID", "")
    if not client_id:
        return ""
    # Resideo OAuth 2.0 authorize endpoint
    return (
        f"https://api.honeywell.com/oauth2/authorize?"
        f"response_type=code&client_id={client_id}&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
    )
