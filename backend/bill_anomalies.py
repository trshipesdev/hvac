"""Bill / cost anomaly detectors.

- bill_rate_spike: effective rate jumped >5% vs trailing 3-bill avg
- bill_past_due: notes/context indicate past-due balance
- bill_late_fee: any 'late payment' or 'reconnect' line item
- bill_usage_spike: kWh > 25% above same-month prior year (if available)
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import re
import statistics


def _find_prior_year_same_month(usage_history, current_month: str) -> Optional[float]:
    if not usage_history:
        return None
    try:
        cy, cm = current_month.split("-")
        prior = f"{int(cy) - 1}-{cm}"
    except Exception:
        return None
    for entry in usage_history:
        if entry.get("month", "").startswith(prior):
            return entry.get("kwh")
    return None


def detect_bill_anomalies(
    parsed: Dict[str, Any],
    bill_period_id: str,
    prior_rate_periods: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return list of anomaly dicts derived from a parsed bill."""
    out: List[Dict[str, Any]] = []
    start = parsed.get("billing_period_start")
    end = parsed.get("billing_period_end")
    if not start or not end:
        return out
    try:
        ts_start = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        ts_end = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
    except Exception:
        return out

    # 1. Rate spike vs trailing average
    eff_rate = parsed.get("effective_rate_per_kwh")
    if eff_rate and prior_rate_periods:
        trail = [rp["effective_rate"] for rp in prior_rate_periods[-3:] if rp.get("effective_rate")]
        if trail:
            avg = statistics.mean(trail)
            pct = (eff_rate - avg) / avg if avg else 0
            if pct >= 0.05:
                sev = "critical" if pct >= 0.15 else "warning"
                out.append({
                    "unit_id": None,
                    "category": "bill",
                    "type": "bill_rate_spike",
                    "severity": sev,
                    "ts_start": ts_start,
                    "ts_end": ts_end,
                    "title": f"Rate jumped {pct*100:+.1f}% vs recent bills",
                    "description": (
                        f"Effective rate for this bill is ${eff_rate:.4f}/kWh, up from a "
                        f"trailing average of ${avg:.4f}/kWh across the last {len(trail)} bill(s). "
                        f"Check for rate-schedule changes, riders, or seasonal tiers."
                    ),
                    "context": {"effective_rate": eff_rate, "trailing_avg": round(avg, 4), "pct_change": round(pct, 3)},
                })

    # 2. Past-due
    notes = (parsed.get("notes") or "").lower()
    if re.search(r"past due|pastdue", notes):
        out.append({
            "unit_id": None,
            "category": "bill",
            "type": "bill_past_due",
            "severity": "critical",
            "ts_start": ts_start,
            "ts_end": ts_end,
            "title": "Bill flagged past-due balance",
            "description": parsed.get("notes") or "Bill notes mention a past-due balance.",
            "context": {"raw_notes": parsed.get("notes")},
        })

    # 3. Late fee / reconnect charges
    line_items = parsed.get("line_items") or []
    fee_hits = [li for li in line_items if re.search(r"late|reconnect|penalty", li.get("description", "").lower())]
    if fee_hits:
        total_fees = round(sum(li.get("amount", 0) for li in fee_hits), 2)
        out.append({
            "unit_id": None,
            "category": "bill",
            "type": "bill_late_fee",
            "severity": "warning",
            "ts_start": ts_start,
            "ts_end": ts_end,
            "title": f"${total_fees} in late/reconnect fees this bill",
            "description": "Line items include late-payment or reconnect charges. Consider auto-pay to avoid future fees.",
            "context": {"fees": fee_hits, "total": total_fees},
        })

    # 4. Usage spike vs prior-year same month
    total_kwh = parsed.get("total_kwh")
    if total_kwh and parsed.get("usage_history"):
        current_month = start[:7]
        prior_kwh = _find_prior_year_same_month(parsed["usage_history"], current_month)
        if prior_kwh and prior_kwh > 0:
            pct = (total_kwh - prior_kwh) / prior_kwh
            if pct >= 0.25:
                sev = "critical" if pct >= 0.50 else "warning"
                out.append({
                    "unit_id": None,
                    "category": "bill",
                    "type": "bill_usage_spike",
                    "severity": sev,
                    "ts_start": ts_start,
                    "ts_end": ts_end,
                    "title": f"Usage up {pct*100:+.0f}% vs same month last year",
                    "description": (
                        f"This bill: {total_kwh:.0f} kWh. Same month last year: {prior_kwh:.0f} kWh. "
                        f"Check for HVAC efficiency issues, new appliances, or occupancy changes."
                    ),
                    "context": {"current_kwh": total_kwh, "prior_year_kwh": prior_kwh, "pct_change": round(pct, 3)},
                })

    return out
