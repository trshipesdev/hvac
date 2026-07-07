"""NOAA CDO API client (Climate Data Online v2)."""
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import httpx
import logging

logger = logging.getLogger(__name__)

NOAA_BASE = "https://www.ncei.noaa.gov/cdo-web/api/v2"
TOKEN = os.environ.get("NOAA_TOKEN", "")

STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}


async def _stations_request(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    url = f"{NOAA_BASE}/stations"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, headers={"token": TOKEN}, params=params)
        if r.status_code != 200:
            logger.warning("NOAA stations lookup failed: %s %s", r.status_code, r.text[:200])
            return []
        return r.json().get("results", [])


async def find_stations(zip_code: str, limit: int = 5, state: Optional[str] = None) -> List[Dict[str, Any]]:
    """Find nearby stations for a zip code that actually report temperature.

    GHCND includes many stations that only report precipitation/snow (e.g.
    citizen CoCoRaHS rain gauges) — without filtering by datatypeid=TMAX,
    a "nearest station" pick can silently be one with no usable temperature
    data at all, making fetch_daily_temps always return empty.

    NOAA's ZIP-radius search is tight enough that plenty of real ZIPs (even
    ones near a proper airport station) come back with zero temperature-
    reporting stations. If that happens and a 2-letter state code is given
    (bill parsers already extract one from the service address), fall back
    to a state-wide search sorted by data quality/recency, so this doesn't
    silently leave weather on synthetic forever.
    """
    if not TOKEN:
        return []
    results = await _stations_request({
        "locationid": f"ZIP:{zip_code}",
        "limit": limit,
        "datasetid": "GHCND",
        "datatypeid": "TMAX",
    })
    if results or not state:
        return results

    fips = STATE_FIPS.get(state.strip().upper())
    if not fips:
        return []
    logger.info("No ZIP-radius station with temperature data for %s — falling back to state-wide search (%s)", zip_code, state)
    return await _stations_request({
        "locationid": f"FIPS:{fips}",
        "limit": limit,
        "datasetid": "GHCND",
        "datatypeid": "TMAX",
        "sortfield": "datacoverage",
        "sortorder": "desc",
    })


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
            "source": "synthetic",
        })
        t += timedelta(hours=1)
    return out
