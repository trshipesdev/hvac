"""Derive an IANA timezone from a property's location — offline, no network call."""
from typing import Optional
from timezonefinder import TimezoneFinder

_tf = TimezoneFinder()  # loads its boundary data once, reused across requests

# Single canonical zone per state, used only when lat/long isn't known yet
# (e.g. a property with a ZIP but no NOAA station/coordinates resolved).
# This is an approximation — split-timezone states (TN, KY, ID, MI, TX, FL,
# IN, ND, SD, NE, KS, OR) and no-DST AZ are wrong for some ZIPs within them;
# the Settings timezone override is the correctness backstop for those.
# Real lat/long via timezonefinder is always preferred when available.
STATE_TZ = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix",
    "AR": "America/Chicago", "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York", "DC": "America/New_York",
    "FL": "America/New_York", "GA": "America/New_York", "HI": "Pacific/Honolulu",
    "ID": "America/Denver", "IL": "America/Chicago", "IN": "America/New_York",
    "IA": "America/Chicago", "KS": "America/Chicago", "KY": "America/New_York",
    "LA": "America/Chicago", "ME": "America/New_York", "MD": "America/New_York",
    "MA": "America/New_York", "MI": "America/New_York", "MN": "America/Chicago",
    "MS": "America/Chicago", "MO": "America/Chicago", "MT": "America/Denver",
    "NE": "America/Chicago", "NV": "America/Los_Angeles", "NH": "America/New_York",
    "NJ": "America/New_York", "NM": "America/Denver", "NY": "America/New_York",
    "NC": "America/New_York", "ND": "America/Chicago", "OH": "America/New_York",
    "OK": "America/Chicago", "OR": "America/Los_Angeles", "PA": "America/New_York",
    "RI": "America/New_York", "SC": "America/New_York", "SD": "America/Chicago",
    "TN": "America/Chicago", "TX": "America/Chicago", "UT": "America/Denver",
    "VT": "America/New_York", "VA": "America/New_York", "WA": "America/Los_Angeles",
    "WV": "America/New_York", "WI": "America/Chicago", "WY": "America/Denver",
}


def derive_timezone(
    lat: Optional[float], lon: Optional[float], state: Optional[str] = None
) -> Optional[str]:
    """Prefer real coordinates (correctly handles AZ no-DST, split-tz states);
    fall back to a per-state approximation only when lat/long is unknown."""
    if lat is not None and lon is not None:
        tz = _tf.timezone_at(lat=lat, lng=lon)
        if tz:
            return tz
    if state:
        return STATE_TZ.get(state.strip().upper())
    return None
