"""Utility bill parser — direct Anthropic Claude Haiku 4.5 (universal, no vendor-specific templates).

Accepts PDF or image bill, extracts a rich structured payload useful for cost
analysis + attribution.
"""
import os
import json
import base64
import logging
from typing import Dict, Any, Optional
import anthropic
import pdfplumber
import io

logger = logging.getLogger(__name__)

MODEL = os.environ.get("BILL_PARSER_MODEL", "claude-haiku-4-5-20251001")


def _get_api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


# Back-compat alias for the debug health endpoint
API_KEY = property(lambda self: _get_api_key())

SYSTEM_PROMPT = """You are a utility bill extraction engine. You receive a residential
electricity bill (any US utility — Dominion, Duke, ConEd, PG&E, etc.). Extract every
useful field for downstream cost + usage analysis. Output STRICT JSON only, no prose.

If a field is missing on the bill, return null (not "N/A", not ""). All money in USD
as float. All kWh as float. All dates as ISO-8601 (YYYY-MM-DD). Do NOT invent values.

Schema:
{
  "utility_name": string|null,
  "account_number": string|null,
  "service_address": string|null,
  "meter_number": string|null,
  "rate_schedule": string|null,
  "billing_period_start": string|null,
  "billing_period_end": string|null,
  "bill_date": string|null,
  "due_date": string|null,
  "days_in_period": integer|null,
  "total_kwh": float|null,
  "total_cost": float|null,
  "total_amount_due": float|null,
  "past_due_balance": float|null,
  "effective_rate_per_kwh": float|null,
  "previous_meter_reading": float|null,
  "current_meter_reading": float|null,
  "average_daily_kwh": float|null,
  "average_daily_cost": float|null,
  "tier_breakdown": [
    {"tier_name": string, "kwh": float|null, "rate_per_kwh": float|null, "amount": float|null}
  ] | null,
  "line_items": [
    {"description": string, "amount": float, "category": "generation|distribution|transmission|fuel|tax|fee|credit|other"}
  ] | null,
  "usage_history": [
    {"month": string, "kwh": float}
  ] | null,
  "temperature_avg_f": float|null,
  "temperature_prior_avg_f": float|null,
  "notes": string|null
}

total_cost is THIS period's electricity usage cost only — sum the non-fee
line_items (generation/distribution/transmission/fuel/tax categories),
excluding any "fee" category items and excluding any carried-over past-due
balance. total_amount_due is the full amount the bill asks you to pay,
which may include total_cost PLUS late fees PLUS a past-due balance carried
from a prior unpaid bill — do not conflate the two. past_due_balance is
whatever dollar amount the bill explicitly shows as carried over/still owed
from a previous billing period; null if the bill shows no such balance.

Compute effective_rate_per_kwh as total_cost / total_kwh if both are present and
the bill doesn't explicitly show it.
"""


def _pdf_bytes_to_text(pdf_bytes: bytes, max_pages: int = 6) -> str:
    """Fallback text extraction (used only if PDF is too large for Anthropic)."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = pdf.pages[:max_pages]
            return "\n\n---PAGE BREAK---\n\n".join(p.extract_text() or "" for p in pages)
    except Exception as e:
        logger.warning("pdfplumber failed: %s", e)
        return ""


def parse_bill(file_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    """Send bill to Claude Haiku 4.5, return parsed JSON dict.

    Uses PDF document attachment when possible; otherwise falls back to
    extracted text via pdfplumber.
    """
    if not _get_api_key():
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=_get_api_key())

    content = []
    # Prefer sending PDF as document (native Claude PDF support)
    if mime_type == "application/pdf" and len(file_bytes) <= 32 * 1024 * 1024:
        content.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(file_bytes).decode(),
            },
        })
    elif mime_type.startswith("image/"):
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64.standard_b64encode(file_bytes).decode(),
            },
        })
    else:
        # text fallback
        text = _pdf_bytes_to_text(file_bytes)
        if not text.strip():
            raise ValueError("Unable to extract any content from file")
        content.append({"type": "text", "text": f"Bill text (extracted):\n\n{text}"})

    content.append({
        "type": "text",
        "text": "Extract the schema. Output ONLY JSON, no markdown fences, no commentary.",
    })

    msg = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    text = text.strip()
    # Strip potential ```json fences
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Bill parser returned non-JSON: %s", text[:500])
        raise ValueError(f"Bill parser output was not valid JSON: {e}") from e

    # Compute effective rate if missing
    if not data.get("effective_rate_per_kwh"):
        tk = data.get("total_kwh")
        tc = data.get("total_cost")
        if tk and tc and tk > 0:
            data["effective_rate_per_kwh"] = round(tc / tk, 4)

    return data
