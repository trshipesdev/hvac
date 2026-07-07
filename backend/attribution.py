"""Attribution engine — split whole-home energy across HVAC units.

Rules:
- If only one unit's compressor was on during the interval -> full HVAC portion to that unit.
- If both were on -> split proportionally by runtime seconds.
- If neither was on -> everything goes to base_load.
- Base load is estimated per interval as the minimum kWh observed when no compressor
  was running in a rolling window; falls back to 0.15 kWh (small home baseline).
"""
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Iterable, Tuple
import statistics


def _index_readings(readings: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[datetime]]:
    """Sort once per unit so each interval's lookup is a bisect (O(log n))
    instead of a full linear scan. A linear scan per interval is O(intervals
    x readings) — fine for a 30-day window, but a full year of 5-min
    readings (~100k+) makes that billions of comparisons and hangs the
    single-threaded event loop for minutes."""
    sorted_readings = sorted(readings, key=lambda r: r["ts"])
    return sorted_readings, [r["ts"] for r in sorted_readings]


def _readings_in_interval(
    sorted_readings: List[Dict[str, Any]], ts_list: List[datetime], start: datetime, end: datetime
) -> List[Dict[str, Any]]:
    lo = bisect_left(ts_list, start)
    hi = bisect_left(ts_list, end)
    return sorted_readings[lo:hi]


def _runtime_seconds(readings: Iterable[Dict[str, Any]]) -> float:
    return sum((r.get("runtime_seconds") or 0.0) for r in readings if r.get("compressor_on"))


def estimate_base_load(
    intervals: List[Dict[str, Any]], readings_by_unit: Dict[str, List[Dict[str, Any]]]
) -> float:
    """Baseline load per 15-min interval — median of intervals where no unit compressor ran."""
    indexed = {uid: _index_readings(readings) for uid, readings in readings_by_unit.items()}
    idle_kwh = []
    for iv in intervals:
        start = iv["ts_start"]
        end = iv["ts_end"]
        any_on = False
        for sorted_readings, ts_list in indexed.values():
            for r in _readings_in_interval(sorted_readings, ts_list, start, end):
                if r.get("compressor_on"):
                    any_on = True
                    break
            if any_on:
                break
        if not any_on:
            idle_kwh.append(iv["kwh"])
    if not idle_kwh:
        return 0.15
    return max(0.05, statistics.median(idle_kwh))


def attribute(
    intervals: List[Dict[str, Any]],
    readings_by_unit: Dict[str, List[Dict[str, Any]]],
    rate_usd_per_kwh: float,
    rate_lookup=None,
) -> List[Dict[str, Any]]:
    """Mutates intervals in place with per-unit attribution and returns them.

    rate_lookup: optional callable(ts) -> float. If provided, used per interval;
    otherwise falls back to the scalar rate_usd_per_kwh.
    """
    base_per_interval = estimate_base_load(intervals, readings_by_unit)
    indexed = {uid: _index_readings(readings) for uid, readings in readings_by_unit.items()}

    for iv in intervals:
        start = iv["ts_start"]
        end = iv["ts_end"]
        rate = rate_lookup(start) if rate_lookup else rate_usd_per_kwh
        unit_runtime: Dict[str, float] = {}
        for unit_id, (sorted_readings, ts_list) in indexed.items():
            sub = _readings_in_interval(sorted_readings, ts_list, start, end)
            unit_runtime[unit_id] = _runtime_seconds(sub)

        total_kwh = iv["kwh"]
        base_kwh = min(base_per_interval, total_kwh)
        hvac_kwh = max(0.0, total_kwh - base_kwh)

        total_runtime = sum(unit_runtime.values())
        unit_kwh: Dict[str, float] = {}
        if total_runtime <= 0:
            for uid in unit_runtime:
                unit_kwh[uid] = 0.0
            base_kwh = total_kwh
            hvac_kwh = 0.0
        else:
            for uid, secs in unit_runtime.items():
                unit_kwh[uid] = round(hvac_kwh * (secs / total_runtime), 4)

        iv["unit_kwh"] = unit_kwh
        iv["base_load_kwh"] = round(base_kwh, 4)
        iv["unit_cost"] = {uid: round(k * rate, 4) for uid, k in unit_kwh.items()}
        iv["base_load_cost"] = round(base_kwh * rate, 4)
        iv["effective_rate"] = rate
        iv["attributed_at"] = datetime.now(timezone.utc)

    return intervals


def summarize_by_unit(
    intervals: List[Dict[str, Any]],
    unit_ids: List[str],
    readings_by_unit: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, float]]:
    """Aggregate kWh, cost, runtime_hours per unit across all intervals."""
    result: Dict[str, Dict[str, float]] = {}
    for uid in unit_ids:
        kwh = sum(iv.get("unit_kwh", {}).get(uid, 0.0) for iv in intervals)
        cost = sum(iv.get("unit_cost", {}).get(uid, 0.0) for iv in intervals)
        readings = readings_by_unit.get(uid, [])
        runtime = sum((r.get("runtime_seconds") or 0.0) for r in readings if r.get("compressor_on"))
        runtime_h = runtime / 3600.0
        eff = (kwh / runtime_h) if runtime_h > 0 else 0.0
        # Least-trustworthy source present wins the label shown to the user —
        # any real reading in the window still gets flagged if the rest of
        # the window is only mock/estimated, so the caveat never disappears
        # just because some of the window happens to be real.
        sources = {r.get("source", "mock") for r in readings}
        if "mock" in sources:
            primary_source = "mock"
        elif "estimated" in sources:
            primary_source = "estimated"
        elif sources:
            primary_source = "resideo"
        else:
            primary_source = None
        result[uid] = {
            "kwh": round(kwh, 3),
            "cost": round(cost, 2),
            "runtime_hours": round(runtime_h, 2),
            "kwh_per_runtime_hour": round(eff, 3),
            "primary_source": primary_source,
        }
    result["_base_load"] = {
        "kwh": round(sum(iv.get("base_load_kwh", 0.0) for iv in intervals), 3),
        "cost": round(sum(iv.get("base_load_cost", 0.0) for iv in intervals), 2),
        "runtime_hours": 0.0,
        "kwh_per_runtime_hour": 0.0,
    }
    return result
