"""Bill / cost anomaly detectors.

- bill_rate_spike: effective rate jumped >5% vs trailing 3-bill avg
- bill_past_due: notes/context indicate past-due balance
- bill_late_fee: any 'late payment' or 'reconnect' line item
- bill_usage_spike: kWh > 25% above same-month prior year (if available)
- bill_meter_mismatch: this bill's previous_meter_reading doesn't chain from
  the immediately-prior bill's current_meter_reading (cross-bill check)
- bill_period_gap: a gap or overlap between this bill's start and the
  immediately-prior bill's end (cross-bill check)

The cross-bill checks need the immediately-prior bill's own parsed payload
(fetched from db.bill_parsed by the caller) — no extra AI call is needed,
since every bill is already parsed independently and stored in full.
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import re
import statistics


def _local_midnight_to_utc(date_str: str, tz) -> datetime:
    """A bill period's start/end is a calendar-date LABEL, not a genuine
    instant — construct it as local midnight of that date (in the
    property's timezone) converted to UTC, so displaying it with a real
    timezone-aware formatter round-trips back to the intended date instead
    of shifting to the previous day at some odd evening hour."""
    naive = datetime.fromisoformat(date_str)
    return naive.replace(tzinfo=tz).astimezone(timezone.utc)


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
    prior_bill_parsed: Optional[Dict[str, Any]] = None,
    tz=timezone.utc,
) -> List[Dict[str, Any]]:
    """Return list of anomaly dicts derived from a parsed bill."""
    out: List[Dict[str, Any]] = []
    start = parsed.get("billing_period_start")
    end = parsed.get("billing_period_end")
    if not start or not end:
        return out
    try:
        ts_start = _local_midnight_to_utc(start, tz)
        ts_end = _local_midnight_to_utc(end, tz)
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

    # 2. Past-due — prefer the structured field; fall back to notes regex for
    # bills parsed before that field existed or where it wasn't populated.
    notes = (parsed.get("notes") or "").lower()
    past_due_balance = parsed.get("past_due_balance")
    if (past_due_balance and past_due_balance > 0) or re.search(r"past due|pastdue", notes):
        prior_past_due = (prior_bill_parsed or {}).get("past_due_balance") or 0
        trend = ""
        if past_due_balance and prior_past_due:
            if past_due_balance > prior_past_due:
                trend = f" This is UP from ${prior_past_due:.2f} on the prior bill — the balance is growing, not being paid down."
            elif past_due_balance < prior_past_due:
                trend = f" Down from ${prior_past_due:.2f} on the prior bill — balance is being paid down."
        out.append({
            "unit_id": None,
            "category": "bill",
            "type": "bill_past_due",
            "severity": "critical",
            "ts_start": ts_start,
            "ts_end": ts_end,
            "title": "Bill flagged past-due balance",
            "description": (
                f"${past_due_balance:.2f} carried over from a prior unpaid bill. This is NOT part of "
                f"this period's electricity cost — it's excluded from total_cost/effective_rate_per_kwh.{trend}"
                if past_due_balance else (parsed.get("notes") or "Bill notes mention a past-due balance.")
            ),
            "context": {"past_due_balance": past_due_balance, "prior_past_due_balance": prior_past_due or None, "raw_notes": parsed.get("notes")},
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
            "description": "Line items include late-payment or reconnect charges (excluded from this period's electricity cost). Consider auto-pay to avoid future fees.",
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

    # 5. Cross-bill: meter reading continuity
    if prior_bill_parsed:
        this_prev = parsed.get("previous_meter_reading")
        prior_current = prior_bill_parsed.get("current_meter_reading")
        if this_prev is not None and prior_current is not None:
            diff = abs(this_prev - prior_current)
            if diff > 1.0:
                out.append({
                    "unit_id": None,
                    "category": "bill",
                    "type": "bill_meter_mismatch",
                    "severity": "warning",
                    "ts_start": ts_start,
                    "ts_end": ts_end,
                    "title": f"Meter reading doesn't chain from prior bill (Δ {diff:.1f})",
                    "description": (
                        f"This bill's previous meter reading ({this_prev}) doesn't match the prior "
                        f"bill's current reading ({prior_current}). Could be a parsing error, a meter "
                        f"swap, or an estimated/missed read — worth checking the original PDFs."
                    ),
                    "context": {"this_previous_meter_reading": this_prev, "prior_current_meter_reading": prior_current, "diff": round(diff, 2)},
                })

        # 6. Cross-bill: billing period gap or overlap
        prior_end_str = prior_bill_parsed.get("billing_period_end")
        if prior_end_str:
            try:
                prior_end = _local_midnight_to_utc(prior_end_str, tz)
                gap_days = (ts_start - prior_end).days
                if gap_days > 2:
                    out.append({
                        "unit_id": None,
                        "category": "bill",
                        "type": "bill_period_gap",
                        "severity": "warning",
                        "ts_start": ts_start,
                        "ts_end": ts_end,
                        "title": f"{gap_days}-day gap since prior bill ended",
                        "description": (
                            f"Prior bill ended {prior_end.date()}, this one starts {ts_start.date()} — "
                            f"a {gap_days}-day gap with no billed usage. A bill may be missing."
                        ),
                        "context": {"prior_bill_end": prior_end_str, "this_bill_start": start, "gap_days": gap_days},
                    })
                elif gap_days < -1:
                    out.append({
                        "unit_id": None,
                        "category": "bill",
                        "type": "bill_period_gap",
                        "severity": "warning",
                        "ts_start": ts_start,
                        "ts_end": ts_end,
                        "title": f"Billing period overlaps prior bill by {-gap_days} days",
                        "description": (
                            f"Prior bill ended {prior_end.date()}, this one starts {ts_start.date()} — "
                            f"the periods overlap. Usage/cost may be double-counted across the two bills."
                        ),
                        "context": {"prior_bill_end": prior_end_str, "this_bill_start": start, "overlap_days": -gap_days},
                    })
            except Exception:
                pass

    return out
