"""Anomaly detection — 5 detectors.

1. extended_runtime: compressor on > 45 min without actual reaching setpoint (+/-1F).
2. overnight_draw: compressor on 12am-5am when outdoor <75F.
3. efficiency_regression: rolling 7d avg kwh/runtime_hour trending up > 15%.
4. weather_disproportion: daily kWh > 1.5x expected from cooling degree hours.
5. setpoint_gap_widening: 7-day avg (actual - setpoint) growing +0.5F vs prior 7-day.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import statistics


def _group_by_day(readings: List[Dict[str, Any]], key: str = "ts") -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in readings:
        d = r[key].date().isoformat()
        out.setdefault(d, []).append(r)
    return out


def detect_extended_runtime(
    unit_id: str, readings: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Runs where compressor stayed on >45 min but temp didn't reach setpoint (+/-1F)."""
    anomalies = []
    run_start = None
    run_reached = False
    for r in sorted(readings, key=lambda x: x["ts"]):
        if r.get("compressor_on"):
            if run_start is None:
                run_start = r["ts"]
                run_reached = False
            sp = r.get("setpoint_f")
            at = r.get("actual_temp_f")
            if sp is not None and at is not None and abs(at - sp) <= 1.0:
                run_reached = True
        else:
            if run_start is not None:
                dur = (r["ts"] - run_start).total_seconds() / 60.0
                if dur >= 45 and not run_reached:
                    sev = "critical" if dur >= 90 else "warning"
                    anomalies.append({
                        "unit_id": unit_id,
                        "type": "extended_runtime",
                        "severity": sev,
                        "ts_start": run_start,
                        "ts_end": r["ts"],
                        "title": f"Extended runtime — {int(dur)} min without hitting setpoint",
                        "description": (
                            f"Compressor ran for {int(dur)} minutes but indoor "
                            f"temperature never reached the setpoint. May indicate "
                            f"undersized capacity, low refrigerant, or dirty coil."
                        ),
                        "context": {"duration_min": round(dur, 1)},
                    })
                run_start = None
                run_reached = False
    return anomalies


def detect_overnight_draw(
    unit_id: str,
    readings: List[Dict[str, Any]],
    weather: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compressor on 12am-5am on mild nights (<75F outdoor)."""
    weather_by_hour = {w["ts"].replace(minute=0, second=0, microsecond=0): w for w in weather}
    per_night: Dict[str, Dict[str, Any]] = {}
    for r in readings:
        if not r.get("compressor_on"):
            continue
        ts = r["ts"]
        if not (0 <= ts.hour < 5):
            continue
        hour_key = ts.replace(minute=0, second=0, microsecond=0)
        w = weather_by_hour.get(hour_key)
        if w and w.get("outdoor_temp_f") is not None and w["outdoor_temp_f"] < 75:
            night = ts.date().isoformat()
            entry = per_night.setdefault(night, {
                "count": 0,
                "start": ts,
                "end": ts,
                "min_temp": w["outdoor_temp_f"],
            })
            entry["count"] += 1
            entry["end"] = ts
            entry["min_temp"] = min(entry["min_temp"], w["outdoor_temp_f"])
    anomalies = []
    for night, info in per_night.items():
        # need at least 4 readings (~20 min of runtime)
        if info["count"] < 4:
            continue
        sev = "warning" if info["min_temp"] < 68 else "info"
        anomalies.append({
            "unit_id": unit_id,
            "type": "overnight_draw",
            "severity": sev,
            "ts_start": info["start"],
            "ts_end": info["end"],
            "title": f"Overnight compressor draw on mild night ({info['min_temp']:.0f}°F)",
            "description": (
                f"Compressor cycled repeatedly between 12–5am while outdoor was "
                f"only {info['min_temp']:.0f}°F. Suggests short-cycling, ductwork "
                f"issue, or setpoint too aggressive."
            ),
            "context": {"night": night, "readings": info["count"], "min_outdoor_f": info["min_temp"]},
        })
    return anomalies


def detect_efficiency_regression(
    unit_id: str,
    intervals: List[Dict[str, Any]],
    readings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Rolling daily kWh/runtime_hour trending up > 15%."""
    daily_kwh: Dict[str, float] = {}
    for iv in intervals:
        d = iv["ts_start"].date().isoformat()
        daily_kwh[d] = daily_kwh.get(d, 0) + iv.get("unit_kwh", {}).get(unit_id, 0.0)
    daily_runtime: Dict[str, float] = {}
    for r in readings:
        if r.get("compressor_on") and r.get("runtime_seconds"):
            d = r["ts"].date().isoformat()
            daily_runtime[d] = daily_runtime.get(d, 0) + r["runtime_seconds"] / 3600.0

    days = sorted(set(daily_kwh) & set(daily_runtime))
    ratios = []
    for d in days:
        rh = daily_runtime.get(d, 0)
        if rh > 0.5:
            ratios.append((d, daily_kwh[d] / rh))

    if len(ratios) < 6:
        return []

    # Compare last 3 days to prior 3
    recent = [x[1] for x in ratios[-3:]]
    prior = [x[1] for x in ratios[-6:-3]]
    if not prior or not recent:
        return []
    r_mean = statistics.mean(recent)
    p_mean = statistics.mean(prior)
    if p_mean <= 0:
        return []
    pct = (r_mean - p_mean) / p_mean
    if pct >= 0.15:
        sev = "critical" if pct >= 0.30 else "warning"
        return [{
            "unit_id": unit_id,
            "type": "efficiency_regression",
            "severity": sev,
            "ts_start": datetime.fromisoformat(ratios[-6][0]).replace(tzinfo=timezone.utc),
            "ts_end": datetime.fromisoformat(ratios[-1][0]).replace(tzinfo=timezone.utc),
            "title": f"Efficiency down {pct*100:.0f}% — more kWh per hour of cooling",
            "description": (
                f"Recent 3-day average kWh per runtime-hour is {r_mean:.2f}, "
                f"up from {p_mean:.2f} in the prior 3 days ({pct*100:+.0f}%). "
                f"Compressor/coil health may be degrading."
            ),
            "context": {"recent_kwh_per_hr": round(r_mean, 3), "prior_kwh_per_hr": round(p_mean, 3), "pct_change": round(pct, 3)},
        }]
    return []


def detect_weather_disproportion(
    unit_id: str,
    intervals: List[Dict[str, Any]],
    weather: List[Dict[str, Any]],
    base_temp_f: float = 65.0,
) -> List[Dict[str, Any]]:
    """Cooling degree hours-based expectation. Flag days where kWh > 1.5x normal."""
    # daily cooling degree hours
    cdh: Dict[str, float] = {}
    for w in weather:
        if w.get("outdoor_temp_f") is None:
            continue
        d = w["ts"].date().isoformat()
        cdh[d] = cdh.get(d, 0) + max(0, w["outdoor_temp_f"] - base_temp_f)

    # daily unit kwh
    daily_kwh: Dict[str, float] = {}
    for iv in intervals:
        d = iv["ts_start"].date().isoformat()
        daily_kwh[d] = daily_kwh.get(d, 0) + iv.get("unit_kwh", {}).get(unit_id, 0.0)

    days = sorted(set(daily_kwh) & set(cdh))
    pairs = [(d, daily_kwh[d], cdh[d]) for d in days if cdh[d] > 0]
    if len(pairs) < 5:
        return []
    # Least-squares slope through origin: k = sum(y*x)/sum(x*x)
    sxx = sum(p[2] * p[2] for p in pairs)
    sxy = sum(p[1] * p[2] for p in pairs)
    if sxx <= 0:
        return []
    slope = sxy / sxx  # expected kWh per cooling-degree-hour

    anomalies = []
    for d, kwh, c in pairs:
        expected = slope * c
        if expected > 1.0 and kwh > 1.5 * expected:
            over_pct = (kwh - expected) / expected
            sev = "critical" if over_pct >= 1.0 else "warning"
            ts0 = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
            anomalies.append({
                "unit_id": unit_id,
                "type": "weather_disproportion",
                "severity": sev,
                "ts_start": ts0,
                "ts_end": ts0 + timedelta(hours=23, minutes=59),
                "title": f"Energy {over_pct*100:.0f}% above weather-expected",
                "description": (
                    f"On {d}, this unit used {kwh:.1f} kWh vs an expected "
                    f"{expected:.1f} kWh based on {c:.0f} cooling degree hours."
                ),
                "context": {"day": d, "actual_kwh": round(kwh, 2), "expected_kwh": round(expected, 2), "cdh": round(c, 1)},
            })
    return anomalies


def detect_setpoint_gap_widening(
    unit_id: str, readings: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """7-day avg (actual - setpoint) widening vs prior 7-day."""
    day_gaps: Dict[str, List[float]] = {}
    for r in readings:
        sp = r.get("setpoint_f")
        at = r.get("actual_temp_f")
        if sp is None or at is None or not r.get("compressor_on"):
            continue
        d = r["ts"].date().isoformat()
        day_gaps.setdefault(d, []).append(at - sp)

    days = sorted(day_gaps)
    if len(days) < 8:
        return []
    avg_by_day = {d: statistics.mean(g) for d, g in day_gaps.items()}
    recent = [avg_by_day[d] for d in days[-min(7, len(days)//2):]]
    prior = [avg_by_day[d] for d in days[:min(7, len(days)//2)]]
    if not recent or not prior:
        return []
    delta = statistics.mean(recent) - statistics.mean(prior)
    if delta >= 0.5:
        sev = "critical" if delta >= 1.5 else "warning"
        return [{
            "unit_id": unit_id,
            "type": "setpoint_gap_widening",
            "severity": sev,
            "ts_start": datetime.fromisoformat(days[0]).replace(tzinfo=timezone.utc),
            "ts_end": datetime.fromisoformat(days[-1]).replace(tzinfo=timezone.utc),
            "title": f"Setpoint gap widened by {delta:.1f}°F",
            "description": (
                f"Average indoor-vs-setpoint gap grew {delta:.1f}°F over the "
                f"recent window. The unit is struggling to maintain target temp."
            ),
            "context": {"recent_avg_gap": round(statistics.mean(recent), 2), "prior_avg_gap": round(statistics.mean(prior), 2), "delta": round(delta, 2)},
        }]
    return []


def run_all(
    unit_id: str,
    readings: List[Dict[str, Any]],
    intervals: List[Dict[str, Any]],
    weather: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    all_anom = []
    all_anom += detect_extended_runtime(unit_id, readings)
    all_anom += detect_overnight_draw(unit_id, readings, weather)
    all_anom += detect_efficiency_regression(unit_id, intervals, readings)
    all_anom += detect_weather_disproportion(unit_id, intervals, weather)
    all_anom += detect_setpoint_gap_widening(unit_id, readings)
    return all_anom
