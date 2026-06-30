"""NOAA CDO API client (Climate Data Online v2)."""
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

NOAA_BASE = "https://www.ncei.noaa.gov/cdo-web/api/v2"
TOKEN = os.environ.get("NOAA_TOKEN", "")


async def find_stations(zip_code: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Find nearby stations for a zip code."""
    if not TOKEN:
        return []
    url = f"{NOAA_BASE}/stations"
    params = {
        "locationid": f"ZIP:{zip_code}",
        "limit": limit,
        "datasetid": "GHCND",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, headers={"token": TOKEN}, params=params)
        if r.status_code != 200:
            logger.warning("NOAA stations lookup failed: %s %s", r.status_code, r.text[:200])
            return []
        data = r.json()
    return data.get("results", [])


async def fetch_daily_temps(
    station_id: str, start: datetime, end: datetime
) -> List[Dict[str, Any]]:
    """Fetch daily TMAX/TMIN/TAVG for a station. Returns list of {ts, temp_f}."""
    if not TOKEN or not station_id:
        return []
    url = f"{NOAA_BASE}/data"
    params = {
        "datasetid": "GHCND",
        "stationid": station_id,
        "startdate": start.strftime("%Y-%m-%d"),
        "enddate": end.strftime("%Y-%m-%d"),
        "datatypeid": ["TMAX", "TMIN", "TAVG"],
        "units": "standard",  # Fahrenheit
        "limit": 1000,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers={"token": TOKEN}, params=params)
        if r.status_code != 200:
            logger.warning("NOAA data fetch failed: %s %s", r.status_code, r.text[:200])
            return []
        data = r.json()

    # Group by date: pick TAVG or midpoint of TMAX/TMIN
    by_date: Dict[str, Dict[str, float]] = {}
    for row in data.get("results", []):
        date = row["date"][:10]
        dt = row["datatype"]
        v = row["value"]
        by_date.setdefault(date, {})[dt] = v

    out = []
    for date, vals in sorted(by_date.items()):
        if "TAVG" in vals:
            t = vals["TAVG"]
        elif "TMAX" in vals and "TMIN" in vals:
            t = (vals["TMAX"] + vals["TMIN"]) / 2
        elif "TMAX" in vals:
            t = vals["TMAX"]
        elif "TMIN" in vals:
            t = vals["TMIN"]
        else:
            continue
        ts = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        out.append({"ts": ts, "outdoor_temp_f": float(t), "humidity": None})
    return out


def synthesize_hourly_from_daily(
    daily: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Fake hourly readings from daily avg (sinusoidal +/- 10F around mean)."""
    import math
    out = []
    for day in daily:
        ts0 = day["ts"]
        avg = day["outdoor_temp_f"]
        for hour in range(24):
            # peak at 3pm
            offset = 10 * math.sin((hour - 9) * math.pi / 12)
            temp = avg + offset
            out.append({
                "ts": ts0 + timedelta(hours=hour),
                "outdoor_temp_f": round(temp, 1),
                "humidity": None,
            })
    return out


def mock_weather(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Generate synthetic hourly weather when NOAA unavailable."""
    import math
    import random
    random.seed(7)
    out = []
    t = start.replace(minute=0, second=0, microsecond=0)
    while t < end:
        # daily avg swings 65-85F
        day = t.timetuple().tm_yday
        base = 75 + 8 * math.sin(day * math.pi / 90)
        # hourly variation
        hourly = 10 * math.sin((t.hour - 9) * math.pi / 12)
        temp = base + hourly + random.uniform(-2, 2)
        out.append({
            "ts": t,
            "outdoor_temp_f": round(temp, 1),
            "humidity": round(50 + random.uniform(-15, 15), 1),
        })
        t += timedelta(hours=1)
    return out
