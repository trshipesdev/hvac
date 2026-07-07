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


def _local_day_key(ts: datetime, tz) -> str:
    """Calendar-day grouping key in the property's local time — a UTC-date
    key would silently group readings that are on different local days
    (or the same local day across a UTC midnight boundary) into the wrong
    bucket, and would later mislabel the resulting anomaly's date."""
    return ts.astimezone(tz).date().isoformat()


def _local_midnight_to_utc(date_str: str, tz) -> datetime:
    """A day/month-level anomaly's ts_start is a calendar-date LABEL, not a
    genuine instant — construct it as local midnight of that date (in the
    property's timezone) converted to UTC, so displaying it with a real
    timezone-aware formatter round-trips back to the intended calendar day
    instead of shifting to the previous day at some odd evening hour."""
    naive = datetime.fromisoformat(date_str)
    return naive.replace(tzinfo=tz).astimezone(timezone.utc)


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
    tz=timezone.utc,
) -> List[Dict[str, Any]]:
    """Rolling daily kWh/runtime_hour trending up > 15%."""
    daily_kwh: Dict[str, float] = {}
    for iv in intervals:
        d = _local_day_key(iv["ts_start"], tz)
        daily_kwh[d] = daily_kwh.get(d, 0) + iv.get("unit_kwh", {}).get(unit_id, 0.0)
    daily_runtime: Dict[str, float] = {}
    for r in readings:
        if r.get("compressor_on") and r.get("runtime_seconds"):
            d = _local_day_key(r["ts"], tz)
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
            "ts_start": _local_midnight_to_utc(ratios[-6][0], tz),
            "ts_end": _local_midnight_to_utc(ratios[-1][0], tz),
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
    tz=timezone.utc,
) -> List[Dict[str, Any]]:
    """Cooling degree hours-based expectation. Flag days where kWh > 1.5x normal."""
    # daily cooling degree hours
    cdh: Dict[str, float] = {}
    for w in weather:
        if w.get("outdoor_temp_f") is None:
            continue
        d = _local_day_key(w["ts"], tz)
        cdh[d] = cdh.get(d, 0) + max(0, w["outdoor_temp_f"] - base_temp_f)

    # daily unit kwh
    daily_kwh: Dict[str, float] = {}
    for iv in intervals:
        d = _local_day_key(iv["ts_start"], tz)
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
            ts0 = _local_midnight_to_utc(d, tz)
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
    unit_id: str, readings: List[Dict[str, Any]], tz=timezone.utc
) -> List[Dict[str, Any]]:
    """7-day avg (actual - setpoint) widening vs prior 7-day."""
    day_gaps: Dict[str, List[float]] = {}
    for r in readings:
        sp = r.get("setpoint_f")
        at = r.get("actual_temp_f")
        if sp is None or at is None or not r.get("compressor_on"):
            continue
        d = _local_day_key(r["ts"], tz)
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
            "ts_start": _local_midnight_to_utc(days[0], tz),
            "ts_end": _local_midnight_to_utc(days[-1], tz),
            "title": f"Setpoint gap widened by {delta:.1f}°F",
            "description": (
                f"Average indoor-vs-setpoint gap grew {delta:.1f}°F over the "
                f"recent window. The unit is struggling to maintain target temp."
            ),
            "context": {"recent_avg_gap": round(statistics.mean(recent), 2), "prior_avg_gap": round(statistics.mean(prior), 2), "delta": round(delta, 2)},
        }]
    return []


def detect_daily_mode_weather_mismatch(
    unit_id: str,
    readings: List[Dict[str, Any]],
    weather: List[Dict[str, Any]],
    tz=timezone.utc,
) -> List[Dict[str, Any]]:
    """Day-by-day: heat running on a hot day, or cooling running on a cold
    day — the actual "why was the heat on" detective question, at daily
    resolution. Needs a real per-reading `mode` ("heat"/"cool") field.

    Gates on each reading's own `source` (ground truth set by the pipeline
    that produced it — resideo.py/thermostat_estimation.py), not a blanket
    flag for the whole call, since a real household has mixed months: some
    with a parsed Honeywell report (source="estimated"), some without
    (source="mock"), some after Resideo connects (source="resideo"). A day
    made entirely of "mock" readings is pure fabrication with no real
    signal and is always skipped. A day of "estimated" readings is a real
    monthly total calibrated day-by-day against real weather — detected,
    but capped at "warning" (never "critical") and title-prefixed since
    it's inferred, not measured. A day of "resideo" readings is detected
    at full severity.
    """
    daily_minutes: Dict[str, Dict[str, float]] = {}
    daily_source: Dict[str, str] = {}
    for r in readings:
        if not r.get("compressor_on"):
            continue
        mode = r.get("mode")
        if mode not in ("heat", "cool"):
            continue
        d = _local_day_key(r["ts"], tz)
        entry = daily_minutes.setdefault(d, {"heat": 0.0, "cool": 0.0})
        entry[mode] += (r.get("runtime_seconds") or 0.0) / 60.0
        daily_source[d] = r.get("source", "mock")

    daily_weather: Dict[str, Dict[str, float]] = {}
    for w in weather:
        if w.get("outdoor_temp_f") is None:
            continue
        d = _local_day_key(w["ts"], tz)
        entry = daily_weather.setdefault(d, {"hi": w["outdoor_temp_f"], "lo": w["outdoor_temp_f"]})
        entry["hi"] = max(entry["hi"], w["outdoor_temp_f"])
        entry["lo"] = min(entry["lo"], w["outdoor_temp_f"])

    anomalies = []
    for d, minutes in daily_minutes.items():
        source = daily_source.get(d, "mock")
        if source == "mock":
            continue  # pure fabrication, no real signal at all
        w = daily_weather.get(d)
        if not w:
            continue
        ts0 = _local_midnight_to_utc(d, tz)
        estimated = source == "estimated"
        prefix = "Estimated: " if estimated else ""
        if minutes["heat"] >= 60 and w["hi"] >= 80:
            sev = "warning" if estimated else ("critical" if (minutes["heat"] >= 120 or w["hi"] >= 90) else "warning")
            anomalies.append({
                "unit_id": unit_id,
                "type": "mode_weather_mismatch",
                "severity": sev,
                "ts_start": ts0,
                "ts_end": ts0 + timedelta(hours=23, minutes=59),
                "title": f"{prefix}Heat ran {int(minutes['heat'])} min on an {w['hi']:.0f}°F day",
                "description": (
                    f"On {d}, this unit ran heating for {int(minutes['heat'])} minutes while "
                    f"the outdoor high hit {w['hi']:.0f}°F. Check for a stuck mode setting, a "
                    f"scheduling error, or a sensor fault."
                ),
                "context": {"day": d, "heating_minutes": round(minutes["heat"], 1), "outdoor_hi_f": w["hi"], "source": source},
            })
        if minutes["cool"] >= 60 and w["lo"] <= 45:
            sev = "warning" if estimated else ("critical" if (minutes["cool"] >= 120 or w["lo"] <= 35) else "warning")
            anomalies.append({
                "unit_id": unit_id,
                "type": "mode_weather_mismatch",
                "severity": sev,
                "ts_start": ts0,
                "ts_end": ts0 + timedelta(hours=23, minutes=59),
                "title": f"{prefix}AC ran {int(minutes['cool'])} min on a {w['lo']:.0f}°F day",
                "description": (
                    f"On {d}, this unit ran cooling for {int(minutes['cool'])} minutes while "
                    f"the outdoor low hit {w['lo']:.0f}°F. Check for a stuck mode setting, a "
                    f"scheduling error, or a sensor fault."
                ),
                "context": {"day": d, "cooling_minutes": round(minutes["cool"], 1), "outdoor_lo_f": w["lo"], "source": source},
            })
    return anomalies


def detect_zone_mode_weather_mismatch(zone_row: Dict[str, Any], tz=timezone.utc) -> List[Dict[str, Any]]:
    """Month-level: this zone's own real heating/cooling hours vs. that same
    report's own real outdoor avg hi/lo — both already real data from the
    same Honeywell email, so this works today (no Resideo needed). Coarser
    than a daily "why was heat on this afternoon" check, but a real signal:
    flags a whole month of unusual heating/cooling given how warm/cold it
    actually was.
    """
    year, month = zone_row.get("year"), zone_row.get("month")
    heating = zone_row.get("heating_hours")
    cooling = zone_row.get("cooling_hours")
    hi, lo = zone_row.get("outdoor_avg_hi_f"), zone_row.get("outdoor_avg_lo_f")
    if not year or not month:
        return []
    # ts0/ts1 are calendar-month LABELS, not instants — anchor them at local
    # midnight of the 1st (converted to UTC) so displaying with a real
    # timezone-aware formatter round-trips back to the intended month
    # instead of shifting into the last day of the prior month.
    ts0 = datetime(year, month, 1).replace(tzinfo=tz).astimezone(timezone.utc)
    next_month_naive = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    next_month = next_month_naive.replace(tzinfo=tz).astimezone(timezone.utc)
    ts1 = next_month - timedelta(seconds=1)
    zone_label = zone_row.get("zone_name", "This zone")

    anomalies = []
    if heating is not None and lo is not None and heating >= 10 and lo >= 65:
        sev = "critical" if (heating >= 30 or lo >= 70) else "warning"
        anomalies.append({
            "unit_id": zone_row.get("unit_id"),
            "type": "zone_mode_weather_mismatch",
            "severity": sev,
            "ts_start": ts0, "ts_end": ts1,
            "title": f"{zone_label} heated {heating:.0f} hrs in a month with {lo:.0f}°F overnight lows",
            "description": (
                f"{zone_label} logged {heating:.0f} hours of heating in {year}-{month:02d}, "
                f"a month whose overnight lows averaged {lo:.0f}°F — mild enough that heating "
                f"shouldn't have been running much. Check the schedule and mode settings."
            ),
            "context": {"year": year, "month": month, "heating_hours": heating, "outdoor_avg_lo_f": lo},
        })
    if cooling is not None and hi is not None and cooling >= 10 and hi <= 60:
        sev = "critical" if (cooling >= 30 or hi <= 50) else "warning"
        anomalies.append({
            "unit_id": zone_row.get("unit_id"),
            "type": "zone_mode_weather_mismatch",
            "severity": sev,
            "ts_start": ts0, "ts_end": ts1,
            "title": f"{zone_label} cooled {cooling:.0f} hrs in a month with {hi:.0f}°F daytime highs",
            "description": (
                f"{zone_label} logged {cooling:.0f} hours of cooling in {year}-{month:02d}, "
                f"a month whose daytime highs averaged {hi:.0f}°F — cool enough that cooling "
                f"shouldn't have been running much. Check the schedule and mode settings."
            ),
            "context": {"year": year, "month": month, "cooling_hours": cooling, "outdoor_avg_hi_f": hi},
        })
    return anomalies


def run_all(
    unit_id: str,
    readings: List[Dict[str, Any]],
    intervals: List[Dict[str, Any]],
    weather: List[Dict[str, Any]],
    tz=timezone.utc,
) -> List[Dict[str, Any]]:
    all_anom = []
    all_anom += detect_extended_runtime(unit_id, readings)
    all_anom += detect_overnight_draw(unit_id, readings, weather)
    all_anom += detect_efficiency_regression(unit_id, intervals, readings, tz=tz)
    all_anom += detect_weather_disproportion(unit_id, intervals, weather, tz=tz)
    all_anom += detect_setpoint_gap_widening(unit_id, readings, tz=tz)
    all_anom += detect_daily_mode_weather_mismatch(unit_id, readings, weather, tz=tz)  # self-gates by each day's reading source
    return all_anom
