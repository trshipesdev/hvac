"""Monthly HVAC zone-runtime report parser — direct Anthropic Claude Haiku 4.5
(universal, no vendor-specific templates).

Accepts a PDF or image export of a monthly energy/runtime report (e.g. a
Honeywell Home "Your <Month> Energy Report" email) and extracts real
per-zone runtime data for downstream cost attribution. Not tied to any
specific vendor's layout, zone naming, or number of zones.
"""
import os
import json
import base64
import logging
from typing import Dict, Any
import anthropic
import pdfplumber
import io

logger = logging.getLogger(__name__)

MODEL = os.environ.get("HONEYWELL_PARSER_MODEL", "claude-haiku-4-5-20251001")


def _get_api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


SYSTEM_PROMPT = """You extract structured data from a monthly HVAC "Energy Report" PDF
(e.g. a Honeywell Home "Your <Month> Energy Report" email, or an equivalent report from
any other thermostat/HVAC vendor). The home has one or more independently-controlled
zones (rooms/floors/areas each with its own thermostat). Zone names are user-defined and
vary per household — examples include "Upstairs", "Downstairs", "Main Floor", "Basement",
"Zone 1", "Bedroom Wing". Do NOT assume any specific zone name or that there are exactly
two zones; read whatever names and however many zones actually appear in the document.

For each zone, the report typically shows data for two time periods, side-by-side or
stacked: the current/most-recent reporting month, and the same calendar month one year
earlier (a "compared to last year" block). Extract both when present. If only one period
appears for a zone, omit the other period's object entirely (do not fabricate it).

For each period, extract:
- year (4-digit integer), month (integer 1-12)
- outdoor_avg_hi_f, outdoor_avg_lo_f: average outdoor high/low temperature in Fahrenheit,
  as plain numbers (strip ° and any unit text)
- total_runtime_hours: total hours the HVAC system ran
- heating_hours, cooling_hours: the breakdown of runtime into heating vs cooling
  (these need not sum exactly to total_runtime_hours; extract whatever the document states)
- equipment_off_hours: hours equipment was off
- avg_indoor_temp_heating_f: average indoor temperature during the heating period
- avg_indoor_temp_cooling_f: average indoor temperature during the cooling period
- is_estimated: true if the document contains any disclaimer near this period indicating
  the thermostat was offline or the data is estimated (e.g. an asterisk/footnote such as
  "estimated because your thermostat was offline part of the month"); false otherwise

Use null for any field not present in the document. Never guess or infer a numeric value
that is not explicitly printed. Do not hallucinate zones, periods, or numbers.

Respond with STRICT JSON only — no markdown code fences, no commentary — matching exactly
this schema:

{
  "report_label": string|null,
  "zones": [
    {
      "zone_name": string,
      "current": {
        "year": integer, "month": integer,
        "outdoor_avg_hi_f": float|null, "outdoor_avg_lo_f": float|null,
        "total_runtime_hours": float|null,
        "heating_hours": float|null, "cooling_hours": float|null,
        "equipment_off_hours": float|null,
        "avg_indoor_temp_heating_f": float|null, "avg_indoor_temp_cooling_f": float|null,
        "is_estimated": boolean
      } | null,
      "prior_year": { ...same shape as current... } | null
    }
  ]
}
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


def parse_honeywell_report(file_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    """Send a monthly zone-runtime report to Claude Haiku 4.5, return parsed JSON dict.

    Uses PDF document attachment when possible; otherwise falls back to
    extracted text via pdfplumber.
    """
    if not _get_api_key():
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = anthropic.Anthropic(api_key=_get_api_key())

    content = []
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
        text = _pdf_bytes_to_text(file_bytes)
        if not text.strip():
            raise ValueError("Unable to extract any content from file")
        content.append({"type": "text", "text": f"Report text (extracted):\n\n{text}"})

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
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Honeywell parser returned non-JSON: %s", text[:500])
        raise ValueError(f"Honeywell parser output was not valid JSON: {e}") from e

    if not isinstance(data.get("zones"), list):
        raise ValueError("Honeywell parser output missing 'zones' array")

    return data
