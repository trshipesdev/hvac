"""Real hourly historical weather via Open-Meteo — free, no API key, no
signup, lat/long-based (ERA5 reanalysis). Replaces the old approach of
faking an hourly curve around a single NOAA daily average: this is real
per-hour temperature, not synthesized.

https://open-meteo.com/en/docs/historical-weather-api
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
import httpx

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


async def fetch_hourly_temps(lat: float, lon: float, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Real hourly outdoor temperature (°F) for the given coordinates and
    date range. Returns [] on any failure — caller decides the fallback."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "hourly": "temperature_2m",
        "temperature_unit": "fahrenheit",
        "timezone": "UTC",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(ARCHIVE_URL, params=params)
        if r.status_code != 200:
            logger.warning("Open-Meteo fetch failed: %s %s", r.status_code, r.text[:200])
            return []
        data = r.json()

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    out = []
    for t, v in zip(times, temps):
        if v is None:
            continue
        ts = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        out.append({"ts": ts, "outdoor_temp_f": float(v), "humidity": None, "source": "open-meteo"})
    return out
