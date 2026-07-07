"""Calibrate synthetic thermostat readings against real Honeywell monthly
zone-runtime totals (HoneywellZoneMonth) when available for a given
unit+month; otherwise fall back to resideo.mock_thermostat_series(). Kept
separate from resideo.py (a thin API/mock-generator client) and from
monthly_cost.py (a different feature — allocating real kWh cost by runtime
share) since this is its own algorithm with its own real-data dependency.

Every reading this module emits is tagged source="estimated" — never
presented as equivalent to source="resideo" (a real live poll). It's
deterministic (no unseeded randomness) so repeated syncs of the same window
produce byte-identical output, matching the idempotent-insert dedup in
_insert_new_thermostat_readings.
"""
import calendar
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import resideo

BALANCE_POINT_F = 65.0  # below this, a day "wants" heating; above, cooling


def _month_bounds(year: int, month: int) -> Tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=calendar.monthrange(year, month)[1])
    return start, end


def _daily_hi_lo(weather: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """date-iso -> {hi, lo} built from already-loaded WeatherReading dicts."""
    by_date: Dict[str, Dict[str, float]] = {}
    for w in weather:
        temp = w.get("outdoor_temp_f")
        if temp is None:
            continue
        d = w["ts"].date().isoformat()
        entry = by_date.setdefault(d, {"hi": temp, "lo": temp})
        entry["hi"] = max(entry["hi"], temp)
        entry["lo"] = min(entry["lo"], temp)
    return by_date


def _seasonal_default(month: int) -> Tuple[float, float]:
    """Rough US seasonal hi/lo fallback for a day with no real weather —
    only used when NOAA data doesn't cover that day; real data always wins."""
    # (hi, lo) by calendar month, mild-climate default
    defaults = {
        1: (50, 32), 2: (54, 35), 3: (62, 42), 4: (70, 50), 5: (78, 58),
        6: (85, 66), 7: (89, 70), 8: (88, 69), 9: (82, 63), 10: (72, 52),
        11: (62, 42), 12: (52, 34),
    }
    return defaults.get(month, (70, 50))


def _heat_hour_weight(hour: int) -> float:
    """Peaks overnight/early morning, trough at midday."""
    import math
    return max(0.0, -math.cos(hour / 24.0 * 2 * math.pi))


def _cool_hour_weight(hour: int) -> float:
    """Peaks midday/afternoon, trough overnight."""
    import math
    return max(0.0, math.cos(hour / 24.0 * 2 * math.pi))


def calibrate_month_series(
    unit_id: str,
    unit_index: int,
    year: int,
    month: int,
    zone_row: Dict[str, Any],
    daily_hi_lo: Dict[str, Dict[str, float]],
    interval_min: int = 5,
) -> List[Dict[str, Any]]:
    """Produce one calendar month of interval_min-spaced readings whose
    summed heat/cool minutes match zone_row's real heating_hours/
    cooling_hours (or, if those are null but total_runtime_hours isn't,
    splits it evenly). Per-day heat/cool weight is a simple degree-day
    proxy from that day's real hi/lo, so cold days absorb more of the real
    heating_hours and warm days absorb more of the real cooling_hours.
    Deterministic: no unseeded randomness.
    """
    start, end = _month_bounds(year, month)
    days_in_month = calendar.monthrange(year, month)[1]

    heating_hours = zone_row.get("heating_hours")
    cooling_hours = zone_row.get("cooling_hours")
    if heating_hours is None and cooling_hours is None:
        total = zone_row.get("total_runtime_hours") or 0.0
        heating_hours = total / 2.0
        cooling_hours = total / 2.0
    heating_hours = heating_hours or 0.0
    cooling_hours = cooling_hours or 0.0

    day_dates = [start + timedelta(days=i) for i in range(days_in_month)]
    heat_weights: Dict[str, float] = {}
    cool_weights: Dict[str, float] = {}
    for d in day_dates:
        diso = d.date().isoformat()
        hl = daily_hi_lo.get(diso)
        hi, lo = (hl["hi"], hl["lo"]) if hl else _seasonal_default(month)
        heat_weights[diso] = max(0.0, BALANCE_POINT_F - lo)
        cool_weights[diso] = max(0.0, hi - BALANCE_POINT_F)
    heat_total_w = sum(heat_weights.values())
    cool_total_w = sum(cool_weights.values())
    # Degree-day weighting can legitimately collapse to zero for a whole
    # month — e.g. no real weather coverage that far back so every day fell
    # through to a mild seasonal default, or the real report itself shows a
    # mismatch month (cooling ran despite a cool month — exactly the kind of
    # thing zone_mode_weather_mismatch is built to flag). Either way, the
    # real reported hours still have to land somewhere: fall back to a flat,
    # even distribution across the month rather than stranding the total.
    if heat_total_w <= 0:
        heat_weights = {d.date().isoformat(): 1.0 for d in day_dates}
        heat_total_w = float(len(day_dates))
    if cool_total_w <= 0:
        cool_weights = {d.date().isoformat(): 1.0 for d in day_dates}
        cool_total_w = float(len(day_dates))

    setpoint_heat = zone_row.get("avg_indoor_temp_heating_f") or 70.0
    setpoint_cool = zone_row.get("avg_indoor_temp_cooling_f") or 74.0

    intervals_per_day = int(24 * 60 / interval_min)
    out: List[Dict[str, Any]] = []

    for d in day_dates:
        diso = d.date().isoformat()
        day_heat_minutes = heating_hours * 60.0 * (heat_weights[diso] / heat_total_w)
        day_cool_minutes = cooling_hours * 60.0 * (cool_weights[diso] / cool_total_w)
        n_heat = round(day_heat_minutes / interval_min)
        n_cool = round(day_cool_minutes / interval_min)

        # Rank this day's interval slots by diurnal shape; deterministic
        # tie-break seeded from unit_index + day-of-year so different units
        # don't all pick identical slots.
        random.seed(1000 + unit_index * 400 + d.timetuple().tm_yday)
        slots = list(range(intervals_per_day))
        heat_ranked = sorted(slots, key=lambda i: (-_heat_hour_weight((i * interval_min) // 60), random.random()))
        heat_on = set(heat_ranked[:n_heat])
        remaining = [i for i in slots if i not in heat_on]
        cool_ranked = sorted(remaining, key=lambda i: (-_cool_hour_weight((i * interval_min) // 60), random.random()))
        cool_on = set(cool_ranked[:n_cool])

        for i in slots:
            t = d + timedelta(minutes=i * interval_min)
            if i in heat_on:
                mode, compressor_on, actual = "heat", True, setpoint_heat - 1.0
            elif i in cool_on:
                mode, compressor_on, actual = "cool", True, setpoint_cool + 1.0
            else:
                mode, compressor_on, actual = "off", False, (setpoint_heat + setpoint_cool) / 2.0
            out.append({
                "unit_id": unit_id,
                "ts": t,
                "setpoint_f": setpoint_heat if mode == "heat" else (setpoint_cool if mode == "cool" else None),
                "actual_temp_f": round(actual, 1),
                "compressor_on": compressor_on,
                # Full interval duration (not the mock generator's arbitrary
                # 0.9 discount) — this reading's whole purpose is to sum back
                # up to the real heating_hours/cooling_hours target exactly.
                "runtime_seconds": interval_min * 60.0 if compressor_on else 0.0,
                "mode": mode,
                "source": "estimated",
            })
    return out


def build_thermostat_series(
    unit_id: str,
    unit_index: int,
    start: datetime,
    end: datetime,
    zone_rows: List[Dict[str, Any]],
    weather: List[Dict[str, Any]],
    interval_min: int = 5,
) -> List[Dict[str, Any]]:
    """Split [start, end) into whole calendar months touched by the range.
    For each month, calibrate against a real HoneywellZoneMonth row if one
    exists for this unit; otherwise fall back to resideo.mock_thermostat_series
    for that sub-range (source="mock"). Filters back down to the requested
    window before returning, even though whole months are computed
    internally — keeps repeated partial-window syncs idempotent.
    """
    zone_by_ym = {(z["year"], z["month"]): z for z in zone_rows if z.get("year") and z.get("month")}
    daily_hi_lo = _daily_hi_lo(weather)

    out: List[Dict[str, Any]] = []
    cur = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    while cur < end:
        y, m = cur.year, cur.month
        month_start, month_end = _month_bounds(y, m)
        zone_row = zone_by_ym.get((y, m))
        has_signal = zone_row and (
            zone_row.get("heating_hours") or zone_row.get("cooling_hours") or zone_row.get("total_runtime_hours")
        )
        if has_signal:
            out.extend(calibrate_month_series(unit_id, unit_index, y, m, zone_row, daily_hi_lo, interval_min))
        else:
            out.extend(resideo.mock_thermostat_series(unit_id, unit_index, month_start, month_end, interval_min))
        cur = month_end

    return [r for r in out if start <= r["ts"] < end]
