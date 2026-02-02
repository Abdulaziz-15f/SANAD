import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors


def now_date_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _p(text: str, style):
    return Paragraph(text, style)


def _kv_table(rows: List[List[str]]) -> Table:
    t = Table(rows, colWidths=[6.0 * cm, 10.5 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def _section(title: str, story, styles):
    story.append(_p(f"<b>{title}</b>", styles["Heading3"]))
    story.append(Spacer(1, 0.2 * cm))


def _bullet_list(items: List[str], story, styles):
    for it in items:
        story.append(_p(f"• {it}", styles["BodyText"]))
        story.append(Spacer(1, 0.05 * cm))


def generate_sanad_report(review_result: Dict[str, Any]) -> bytes:
    """
    Builds a single PDF report from the Stage 2 review_result dict.
    This keeps report generation simple: Stage2 computes everything, report only formats.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="SANAD PV Design Review Report",
    )

    styles = getSampleStyleSheet()
    story = []

    # --- Header ---
    story.append(_p("<b>SANAD PV Design Review Report</b>", styles["Title"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_p(f"Generated: {review_result.get('run_date', now_date_str())}", styles["BodyText"]))
    story.append(Spacer(1, 0.6 * cm))

    # --- Project summary ---
    _section("Project Summary", story, styles)

    place = review_result.get("place")
    lat = review_result.get("lat")
    lon = review_result.get("lon")
    tmin = review_result.get("tmin")

    bom_sig = review_result.get("bom_sig", {})
    inverter_name = bom_sig.get("inverter_name", "N/A")

    story.append(
        _kv_table(
            [
                ["Field", "Value"],
                ["Site", str(place)],
                ["Coordinates", f"{lat}, {lon}"],
                ["Design Tmin (°C)", f"{tmin:.1f}" if tmin is not None else "N/A"],
                ["Inverter (BoM)", str(inverter_name)],
            ]
        )
    )
    story.append(Spacer(1, 0.6 * cm))

    # --- BoM signals ---
    _section("BoM Signals Used", story, styles)

    story.append(
        _kv_table(
            [
                ["Signal", "Value"],
                ["Voc_STC per module (V)", f"{bom_sig.get('voc_stc', 'N/A')}"],
                ["Voc temp coeff (/°C)", f"{bom_sig.get('temp_coeff', 'N/A')}"],
                ["Modules per string", f"{bom_sig.get('modules_per_string', 'N/A')}"],
                ["Inverter DC max (V)", f"{bom_sig.get('inverter_vmax', 'N/A')}"],
            ]
        )
    )
    story.append(Spacer(1, 0.6 * cm))

    # --- BoM vs SLD ---
    _section("BoM ↔ SLD Consistency", story, styles)
    bom_sld_status = review_result.get("bom_sld_status")
    if bom_sld_status:
        story.append(_p(f"Status: <b>{bom_sld_status.level}</b>", styles["BodyText"]))
        story.append(Spacer(1, 0.15 * cm))
        _bullet_list(bom_sld_status.details, story, styles)
    else:
        story.append(_p("No result available.", styles["BodyText"]))
    story.append(Spacer(1, 0.4 * cm))

    # --- Climate overvoltage ---
    _section("Winter Overvoltage Risk", story, styles)
    climate_status = review_result.get("climate_status")
    climate_numbers = review_result.get("climate_numbers", {})
    climate_recs = review_result.get("climate_recs", [])

    if climate_status:
        story.append(_p(f"Status: <b>{climate_status.level}</b>", styles["BodyText"]))
        story.append(Spacer(1, 0.15 * cm))
        _bullet_list(climate_status.details, story, styles)

        story.append(Spacer(1, 0.15 * cm))
        story.append(_p("<b>Calculation values</b>", styles["BodyText"]))
        story.append(Spacer(1, 0.1 * cm))

        kv_rows = [["Parameter", "Value"]]
        for k, v in climate_numbers.items():
            kv_rows.append([str(k), str(v)])
        story.append(_kv_table(kv_rows))

        if climate_recs:
            story.append(Spacer(1, 0.2 * cm))
            story.append(_p("<b>Recommendations</b>", styles["BodyText"]))
            story.append(Spacer(1, 0.1 * cm))
            _bullet_list(climate_recs, story, styles)
    else:
        story.append(_p("No result available.", styles["BodyText"]))
    story.append(Spacer(1, 0.6 * cm))

    # --- AC voltage drop ---
    _section("AC Voltage Drop", story, styles)
    ac_vd_result = review_result.get("ac_vd_result")

    if not ac_vd_result:
        story.append(_p("No AC Cable Sizing Excel was provided, or parsing failed.", styles["BodyText"]))
    else:
        kpis = ac_vd_result.get("kpis", {})
        issues = ac_vd_result.get("issues", [])

        story.append(
            _kv_table(
                [
                    ["Metric", "Value"],
                    ["Max inverter VD%", f"{kpis.get('max_inverter_vd_pct', 0.0):.2f}% (limit 3.00%)"],
                    ["Max combiner→MDB VD%", f"{kpis.get('max_combiner_vd_pct', 0.0):.2f}% (limit 1.50%)"],
                    ["Inverter runs", str(kpis.get("inverter_runs_count", 0))],
                    ["Combiner runs", str(kpis.get("combiner_runs_count", 0))],
                ]
            )
        )

        story.append(Spacer(1, 0.2 * cm))
        if len(issues) == 0:
            story.append(_p("Result: <b>PASS</b> — within limits.", styles["BodyText"]))
        else:
            story.append(_p(f"Result: <b>ISSUES FOUND</b> — {len(issues)} items.", styles["BodyText"]))
            story.append(Spacer(1, 0.15 * cm))

            # List issues (keep it readable)
            for it in issues[:30]:  # cap to avoid massive reports
                story.append(_p(f"• <b>{it.severity}</b> — {it.title}", styles["BodyText"]))
                story.append(_p(f"{it.description}", styles["BodyText"]))
                story.append(Spacer(1, 0.08 * cm))

            if len(issues) > 30:
                story.append(_p(f"...and {len(issues) - 30} more issues (omitted).", styles["BodyText"]))

    story.append(Spacer(1, 0.6 * cm))

    # --- Compliance snapshot ---
    _section("Compliance Snapshot", story, styles)
    compliant_points = review_result.get("compliant_points", [])
    gaps_points = review_result.get("gaps_points", [])

    story.append(_p("<b>Compliant points</b>", styles["BodyText"]))
    story.append(Spacer(1, 0.1 * cm))
    _bullet_list(compliant_points, story, styles)

    story.append(Spacer(1, 0.2 * cm))
    story.append(_p("<b>Gaps / actions</b>", styles["BodyText"]))
    story.append(Spacer(1, 0.1 * cm))
    _bullet_list(gaps_points, story, styles)

    # Build
    doc.build(story)
    return buf.getvalue()
