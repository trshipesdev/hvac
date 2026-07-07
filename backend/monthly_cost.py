"""Real-data monthly cost comparison across HVAC units/zones.

Deliberately independent of attribution.py: that module splits kWh across
units using per-interval thermostat readings that are currently MOCK data
(until real Resideo OAuth access lands). This module instead allocates each
month's REAL Green-Button kWh/cost across however many units are configured
using REAL monthly runtime-hour data (parsed from Honeywell/vendor energy
reports) — no synthetic curves, no dependency on mock thermostat data.

Nothing here assumes a fixed number of units/zones or a fixed date range.
"""
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Tuple

MonthKey = Tuple[int, int]  # (year, month)


def bucket_intervals_by_month(intervals: List[Dict[str, Any]]) -> Dict[MonthKey, List[Dict[str, Any]]]:
    """Group Green Button intervals by (year, month) of their ts_start.

    Intervals within a few hours of a month boundary are bucketed by
    whatever timezone ts_start already carries (UTC throughout this app);
    negligible for monthly totals.
    """
    buckets: Dict[MonthKey, List[Dict[str, Any]]] = defaultdict(list)
    for iv in intervals:
        ts = iv["ts_start"]
        buckets[(ts.year, ts.month)].append(iv)
    return buckets


def month_totals(month_intervals: List[Dict[str, Any]], rate_lookup: Callable[[datetime], float]) -> Tuple[float, float]:
    """Return (total_kwh, total_cost) for a month's intervals.

    Prefers each interval's already-attributed cost (base_load_cost + sum of
    unit_cost) so dollar totals match exactly what the rest of the app
    reports for the same range; falls back to kwh * rate_lookup for any
    interval that hasn't been through attribution yet.
    """
    total_kwh = 0.0
    total_cost = 0.0
    for iv in month_intervals:
        kwh = iv.get("kwh", 0.0)
        total_kwh += kwh
        if iv.get("attributed_at"):
            total_cost += iv.get("base_load_cost", 0.0) + sum((iv.get("unit_cost") or {}).values())
        else:
            total_cost += kwh * rate_lookup(iv["ts_start"])
    return round(total_kwh, 3), round(total_cost, 2)


def group_zone_rows_by_month(zone_rows: List[Dict[str, Any]]) -> Dict[MonthKey, List[Dict[str, Any]]]:
    """Group stored HoneywellZoneMonth rows by (year, month)."""
    buckets: Dict[MonthKey, List[Dict[str, Any]]] = defaultdict(list)
    for row in zone_rows:
        buckets[(row["year"], row["month"])].append(row)
    return buckets


def compute_unit_cost_comparison(
    zone_rows_by_month: Dict[MonthKey, List[Dict[str, Any]]],
    interval_buckets: Dict[MonthKey, List[Dict[str, Any]]],
    rate_lookup: Callable[[datetime], float],
) -> List[Dict[str, Any]]:
    """For every month with zone-runtime data, allocate that month's real
    Green-Button kWh/cost across units by their real runtime-hour share.

    Works for any number of units/zones and any date range — a month with
    zone data but no matching Green-Button intervals still returns runtime
    comparison (allocated_kwh/cost simply come out as 0), so this degrades
    gracefully rather than erroring when a full year of billing history
    isn't available yet (e.g. for prior-year comparison rows).

    Deliberately does NOT compute a "$/runtime-hour" field: under proportional
    allocation (allocated_cost = share_of_hours * total_cost), that quotient
    always reduces to total_cost / sum_of_all_units_hours for every unit in
    the same month — a tautology, not a real efficiency signal. Telling
    which unit draws more power per hour it runs requires independently
    metered per-unit power, which this workaround does not have (that's the
    real Resideo API gap). What this CAN answer honestly, from real runtime
    hours and real billed kWh/cost, is which unit accounts for more of the
    bill — that's `allocated_cost`/`share_pct` below.
    """
    out: List[Dict[str, Any]] = []
    for (year, month), rows in sorted(zone_rows_by_month.items()):
        ivs = interval_buckets.get((year, month), [])
        total_kwh, total_cost = month_totals(ivs, rate_lookup)

        matched_rows = [r for r in rows if r.get("unit_id")]
        sum_hours = sum(r.get("total_runtime_hours") or 0.0 for r in matched_rows)

        month_out: Dict[str, Any] = {
            "year": year,
            "month": month,
            "total_kwh": total_kwh,
            "total_cost": total_cost,
            "units": [],
            "unmatched_zones": [],
        }
        for r in rows:
            if not r.get("unit_id"):
                month_out["unmatched_zones"].append(r["zone_name"])
                continue
            hours = r.get("total_runtime_hours") or 0.0
            share = (hours / sum_hours) if sum_hours > 0 else 0.0
            allocated_kwh = round(share * total_kwh, 3)
            allocated_cost = round(share * total_cost, 2)
            month_out["units"].append({
                "unit_id": r["unit_id"],
                "zone_name": r["zone_name"],
                "runtime_hours": hours,
                "share_pct": round(share * 100, 1),
                "allocated_kwh": allocated_kwh,
                "allocated_cost": allocated_cost,
                "heating_hours": r.get("heating_hours"),
                "cooling_hours": r.get("cooling_hours"),
                "equipment_off_hours": r.get("equipment_off_hours"),
                "is_estimated": r.get("is_estimated", False),
            })
        out.append(month_out)
    return out
