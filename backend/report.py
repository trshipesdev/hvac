"""CSV / PDF export with embedded chart."""
import csv
import io
from datetime import datetime
from typing import List, Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


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
            iv.get("kwh"), iv.get("base_load_kwh"), iv.get("base_load_cost"),
        ]
        for u in units:
            row.append(iv.get("unit_kwh", {}).get(u["id"], 0))
            row.append(iv.get("unit_cost", {}).get(u["id"], 0))
        writer.writerow(row)
    return output.getvalue()


def _render_timeline_png(intervals: List[Dict[str, Any]], units: List[Dict[str, Any]]) -> bytes:
    """Render a daily-bucketed stacked area chart as PNG bytes."""
    daily: Dict[str, Dict[str, float]] = {}
    for iv in intervals:
        d = iv["ts_start"].strftime("%Y-%m-%d") if isinstance(iv["ts_start"], datetime) else iv["ts_start"][:10]
        b = daily.setdefault(d, {"base": 0.0})
        b["base"] += iv.get("base_load_kwh", 0.0)
        for uid, kwh in iv.get("unit_kwh", {}).items():
            b[uid] = b.get(uid, 0.0) + kwh
    if not daily:
        return b""
    days = sorted(daily.keys())

    fig, ax = plt.subplots(figsize=(8, 3), dpi=140)
    fig.patch.set_facecolor("#F7F5F0")
    ax.set_facecolor("#FFFFFF")

    base_series = [daily[d]["base"] for d in days]
    stacks = [base_series]
    labels = ["Base load"]
    colors_list = ["#94A3B8"]
    for u in units:
        s = [daily[d].get(u["id"], 0.0) for d in days]
        stacks.append(s)
        labels.append(u["name"])
        colors_list.append(u.get("color", "#4A6B53"))

    ax.stackplot(days, stacks, labels=labels, colors=colors_list, alpha=0.85, edgecolor="white", linewidth=0.5)
    ax.set_ylabel("kWh", fontsize=8, color="#5E6C64")
    ax.tick_params(axis="both", labelsize=7, colors="#5E6C64")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E2E0D8")
    ax.spines["bottom"].set_color("#E2E0D8")
    ax.grid(axis="y", linestyle="--", color="#E2E0D8", alpha=0.6)
    if len(days) > 10:
        step = max(1, len(days) // 10)
        ax.set_xticks(days[::step])
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", fontsize=7)
    ax.legend(loc="upper left", fontsize=7, frameon=False)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def build_pdf_report(
    property_info: Dict[str, Any],
    units: List[Dict[str, Any]],
    summary: Dict[str, Dict[str, float]],
    anomalies: List[Dict[str, Any]],
    date_range: str,
    intervals: List[Dict[str, Any]] = None,
    yoy: Dict[str, Any] = None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    styles = getSampleStyleSheet()
    body = []

    body.append(Paragraph("<b>HVAC Efficiency Report</b>", styles["Title"]))
    body.append(Paragraph(f"{property_info.get('name', 'Property')} — {date_range}", styles["Normal"]))
    body.append(Spacer(1, 14))

    # Timeline chart
    if intervals:
        png = _render_timeline_png(intervals, units)
        if png:
            body.append(Image(io.BytesIO(png), width=500, height=180))
            body.append(Spacer(1, 12))

    # YoY
    if yoy and yoy.get("prior_year_kwh"):
        body.append(Paragraph("<b>Year over year</b>", styles["Heading2"]))
        pct = yoy.get("pct_change")
        yoy_row = [["Current 30 days", "Prior year same window", "Change"],
                   [f"{yoy.get('current_kwh', 0):.0f} kWh",
                    f"{yoy.get('prior_year_kwh', 0):.0f} kWh",
                    f"{pct:+.1f}%" if pct is not None else "—"]]
        t = Table(yoy_row, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0EEE7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1E3A2F")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E0D8")),
            ("FONTNAME", (0, 1), (-1, -1), "Courier"),
        ]))
        body.append(t)
        body.append(Spacer(1, 14))

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
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A6B53")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E0D8")),
        ("FONTNAME", (0, 1), (-1, -1), "Courier"),
    ]))
    body.append(tbl)
    body.append(Spacer(1, 18))

    body.append(Paragraph("<b>Anomalies</b>", styles["Heading2"]))
    if not anomalies:
        body.append(Paragraph("No anomalies detected in this period.", styles["Normal"]))
    else:
        # Severity distribution
        from collections import Counter
        sev_count = Counter(a.get("severity", "info") for a in anomalies)
        dist = f"Critical: {sev_count.get('critical', 0)} · Warning: {sev_count.get('warning', 0)} · Info: {sev_count.get('info', 0)}"
        body.append(Paragraph(dist, styles["Normal"]))
        body.append(Spacer(1, 6))
        for a in anomalies[:50]:
            sev = a.get("severity", "info").upper()
            body.append(Paragraph(f"[{sev}] {a.get('title', '')}", styles["Normal"]))
            body.append(Paragraph(a.get("description", ""), styles["BodyText"]))
            body.append(Spacer(1, 6))

    doc.build(body)
    return buf.getvalue()
