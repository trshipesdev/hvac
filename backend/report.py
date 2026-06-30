"""CSV / PDF export."""
import csv
import io
from datetime import datetime
from typing import List, Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors


def intervals_to_csv(intervals: List[Dict[str, Any]], units: List[Dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    headers = ["ts_start", "ts_end", "kwh_total", "base_load_kwh", "base_load_cost"]
    for u in units:
        headers.extend([f"{u['name']}_kwh", f"{u['name']}_cost"])
    writer.writerow(headers)
    for iv in intervals:
        row = [
            iv["ts_start"].isoformat() if isinstance(iv["ts_start"], datetime) else iv["ts_start"],
            iv["ts_end"].isoformat() if isinstance(iv["ts_end"], datetime) else iv["ts_end"],
            iv.get("kwh"),
            iv.get("base_load_kwh"),
            iv.get("base_load_cost"),
        ]
        for u in units:
            row.append(iv.get("unit_kwh", {}).get(u["id"], 0))
            row.append(iv.get("unit_cost", {}).get(u["id"], 0))
        writer.writerow(row)
    return output.getvalue()


def build_pdf_report(
    property_info: Dict[str, Any],
    units: List[Dict[str, Any]],
    summary: Dict[str, Dict[str, float]],
    anomalies: List[Dict[str, Any]],
    date_range: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    styles = getSampleStyleSheet()
    body = []

    body.append(Paragraph("<b>HVAC Efficiency Report</b>", styles["Title"]))
    body.append(Paragraph(f"{property_info.get('name', 'Property')} — {date_range}", styles["Normal"]))
    body.append(Spacer(1, 12))

    body.append(Paragraph("<b>Per-Unit Summary</b>", styles["Heading2"]))
    tbl_data = [["Unit", "kWh", "Runtime hrs", "kWh / hr", "Cost (USD)"]]
    for u in units:
        s = summary.get(u["id"], {})
        tbl_data.append([
            u.get("name", ""),
            f"{s.get('kwh', 0):.2f}",
            f"{s.get('runtime_hours', 0):.2f}",
            f"{s.get('kwh_per_runtime_hour', 0):.3f}",
            f"${s.get('cost', 0):.2f}",
        ])
    base = summary.get("_base_load", {})
    tbl_data.append(["Base load", f"{base.get('kwh', 0):.2f}", "—", "—", f"${base.get('cost', 0):.2f}"])
    tbl = Table(tbl_data, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18181b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTNAME", (0, 1), (-1, -1), "Courier"),
    ]))
    body.append(tbl)
    body.append(Spacer(1, 18))

    body.append(Paragraph("<b>Anomalies</b>", styles["Heading2"]))
    if not anomalies:
        body.append(Paragraph("No anomalies detected in this period.", styles["Normal"]))
    else:
        for a in anomalies[:50]:
            sev = a.get("severity", "info").upper()
            body.append(Paragraph(f"[{sev}] {a.get('title', '')}", styles["Normal"]))
            body.append(Paragraph(a.get("description", ""), styles["BodyText"]))
            body.append(Spacer(1, 6))

    doc.build(body)
    return buf.getvalue()
