from __future__ import annotations

import hashlib
import io
from typing import Any, Dict, Optional

import streamlit as st

from core.report import generate_sanad_report, now_date_str
from core.parsers.bom_signals import extract_bom_signals
from core.review import (
    compare_bom_vs_sld,
    climate_voltage_check,
    saudi_standards_snapshot,
    run_ac_voltage_drop_review,
)
from core.extract.sld_extract import extract_sld_signals_from_pdf


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _status_to_streamlit(level: str):
    """Maps internal check levels to Streamlit alert components."""
    if level == "PASS":
        return st.success
    if level == "WARN":
        return st.warning
    if level == "FAIL":
        return st.error
    return st.info


def _sha256(data: bytes) -> str:
    """Stable hash used to cache OCR results for the same uploaded PDF."""
    return hashlib.sha256(data).hexdigest()


def _run_sld_ocr_all_pages(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Runs OCR across all PDF pages (best accuracy for scanned SLDs).
    Uses a progress callback to keep the UI responsive.

    Notes:
      - We avoid st.cache_data here because we want live progress updates.
      - Caching is handled in session_state by PDF hash in render_stage2().
    """
    bar = st.progress(0, text="Starting OCR…")

    def progress_cb(done: int, total: int):
        pct = int((done / max(total, 1)) * 100)
        bar.progress(pct, text=f"OCR running… page {done}/{total}")

    res = extract_sld_signals_from_pdf(
        pdf_bytes,
        target_dpi=300,
        progress_cb=progress_cb,
    )

    bar.empty()

    # Normalize into the shape expected by compare/check functions.
    return {
        "inverter_vmax": res.inverter_vmax,
        "modules_per_string": res.modules_per_string,
        "inverter_labels": getattr(res, "inverter_labels", []),
        "notes": res.notes,
        "evidence": res.evidence,
    }


# -------------------------------------------------------------------
# Stage 2: Engineering Review + Report Export
# -------------------------------------------------------------------
def render_stage2() -> None:
    """
    Stage 2: Runs engineering checks and generates the final report.
    Inputs are expected to be present in st.session_state from Stage 1.
    """

    st.markdown('<div class="sg-h2">Engineering Review</div>', unsafe_allow_html=True)

    # ----------------------------
    # Load inputs from session state
    # ----------------------------
    place = st.session_state.get("place")
    lat = st.session_state.get("lat")
    lon = st.session_state.get("lon")
    tmin = st.session_state.get("tmin")

    sld_pdf_bytes: Optional[bytes] = st.session_state.get("sld_pdf_bytes")
    bom_df = st.session_state.get("bom_df")

    ac_cable_bytes: Optional[bytes] = st.session_state.get("ac_cable_bytes")
    ac_cable_name: Optional[str] = st.session_state.get("ac_cable_name")

    # Defensive guard (Stage 1 should already prevent reaching Stage 2 without these)
    if not all(
        [
            place,
            lat is not None,
            lon is not None,
            tmin is not None,
            sld_pdf_bytes,
            bom_df is not None,
            ac_cable_bytes,  # required
        ]
    ):
        st.error("Missing inputs. Go back to Stage 1 and upload the required files.")
        return

    # ----------------------------
    # 1) Extract BoM signals
    # ----------------------------
    bom_sig = extract_bom_signals(bom_df)

    # ----------------------------
    # 2) Extract SLD signals (OCR all pages) with manual caching
    # ----------------------------
    st.markdown('<div class="sg-h2">SLD Extraction</div>', unsafe_allow_html=True)

    sld_hash = _sha256(sld_pdf_bytes)
    cached = st.session_state.get("sld_sig_cache")

    if (
        isinstance(cached, dict)
        and cached.get("hash") == sld_hash
        and isinstance(cached.get("data"), dict)
    ):
        sld_sig = cached["data"]
        st.success("Using cached SLD OCR results (no re-run).")
    else:
        st.info("Running OCR on all SLD pages for maximum extraction accuracy…")
        sld_sig = _run_sld_ocr_all_pages(sld_pdf_bytes)
        st.session_state["sld_sig_cache"] = {"hash": sld_hash, "data": sld_sig}
        st.success("SLD OCR finished.")

    # Quick visibility of extracted values
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"- **Detected inverter DC max (SLD)**: {sld_sig.get('inverter_vmax')}")
        st.write(f"- **Detected modules/string (SLD)**: {sld_sig.get('modules_per_string')}")
    with c2:
        st.write(f"- **Notes**: {sld_sig.get('notes')}")
        inv_labels = sld_sig.get("inverter_labels") or []
        if inv_labels:
            st.write(f"- **Inverter labels detected**: {len(inv_labels)} (e.g., {', '.join(inv_labels[:5])})")

    # Evidence is useful for debugging OCR extraction and showing transparency in the report.
    evidence = sld_sig.get("evidence") or {}
    if evidence:
        with st.expander("Show extraction evidence"):
            for field, ev in evidence.items():
                st.write(f"**{field}**")
                st.write(f"- page: {ev.get('page')}")
                st.write(f"- conf: {ev.get('conf')}")
                st.write(f"- text: {ev.get('text')}")
                st.markdown("---")

    st.markdown("<br>", unsafe_allow_html=True)

    # ----------------------------
    # 3) Consistency check (BoM vs SLD)
    # ----------------------------
    bom_sld_status = compare_bom_vs_sld(bom_sig, sld_sig)

    # ----------------------------
    # 4) Climate / Tmin overvoltage check
    # ----------------------------
    climate_status, climate_numbers, climate_recs = climate_voltage_check(bom_sig, tmin)
    climate_ok = climate_status.level == "PASS"

    # ----------------------------
    # 5) Standards snapshot (high-level list of pass/gaps)
    # ----------------------------
    compliant_points, gaps_points = saudi_standards_snapshot(climate_ok, bom_sld_status.level)

    # ----------------------------
    # 6) AC voltage drop check (required input)
    # ----------------------------
    ac_vd_result = run_ac_voltage_drop_review(
        io.BytesIO(ac_cable_bytes),
        inv_limit_pct=3.0,
        comb_limit_pct=1.5,
    )

    # Store results for report export (and future UI expansions)
    st.session_state["review_result"] = {
        "place": place,
        "lat": lat,
        "lon": lon,
        "tmin": tmin,
        "bom_sig": bom_sig,
        "sld_sig": sld_sig,
        "bom_sld_status": bom_sld_status,
        "climate_status": climate_status,
        "climate_numbers": climate_numbers,
        "climate_recs": climate_recs,
        "compliant_points": compliant_points,
        "gaps_points": gaps_points,
        "ac_vd_result": ac_vd_result,
        "ac_cable_name": ac_cable_name,
        "run_date": now_date_str(),
    }

    # ----------------------------
    # UI: KPIs
    # ----------------------------
    st.markdown('<div class="sg-h2">Key Results</div>', unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Site Tmin (°C)", f"{tmin:.1f}")
    with k2:
        st.metric("Modules/String (BoM)", str(bom_sig.get("modules_per_string")))
    with k3:
        st.metric("Inverter DC Max (BoM)", f"{bom_sig.get('inverter_vmax'):.0f} V")
    with k4:
        sld_vmax = sld_sig.get("inverter_vmax")
        st.metric("Inverter DC Max (SLD)", f"{float(sld_vmax):.0f} V" if sld_vmax else "—")

    st.markdown("<br>", unsafe_allow_html=True)

    # ----------------------------
    # UI: Checks
    # ----------------------------
    st.markdown('<div class="sg-h2">Checks</div>', unsafe_allow_html=True)

    _status_to_streamlit(bom_sld_status.level)(bom_sld_status.title)
    for line in bom_sld_status.details:
        st.write(f"- {line}")

    st.markdown("<br>", unsafe_allow_html=True)

    _status_to_streamlit(climate_status.level)(climate_status.title)
    for line in climate_status.details:
        st.write(f"- {line}")

    with st.expander("Show calculation details"):
        for k, v in climate_numbers.items():
            st.write(f"- **{k}**: {v}")

        if climate_recs:
            st.markdown("**Recommendations:**")
            for r in climate_recs:
                st.write(f"- {r}")

    st.markdown("<br>", unsafe_allow_html=True)

    # ----------------------------
    # UI: AC voltage drop
    # ----------------------------
    st.markdown('<div class="sg-h2">AC Voltage Drop</div>', unsafe_allow_html=True)

    kpis = ac_vd_result["kpis"]
    issues = ac_vd_result["issues"]

    st.write(f"- **Max inverter VD%**: {kpis['max_inverter_vd_pct']:.2f}% (limit 3.00%)")
    st.write(f"- **Max combiner→MDB VD%**: {kpis['max_combiner_vd_pct']:.2f}% (limit 1.50%)")
    st.write(f"- **Runs**: {kpis['inverter_runs_count']} inverter runs, {kpis['combiner_runs_count']} combiner runs")

    if len(issues) == 0:
        st.success("PASS — Voltage drop values are within limits.")
    else:
        st.warning(f"FOUND {len(issues)} voltage drop issues")
        with st.expander("Show issues"):
            for it in issues:
                st.write(f"- **{it.severity}** — {it.title}")
                st.caption(it.description)

    st.markdown("<br>", unsafe_allow_html=True)

    # ----------------------------
    # UI: Compliance snapshot
    # ----------------------------
    st.markdown('<div class="sg-h2">Compliance Snapshot</div>', unsafe_allow_html=True)

    with st.expander("Compliant points"):
        for p in compliant_points:
            st.write(f"- {p}")

    with st.expander("Gaps / actions"):
        for g in gaps_points:
            st.write(f"- {g}")

    # ----------------------------
    # Export: PDF report
    # ----------------------------
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sg-h2">Export</div>', unsafe_allow_html=True)

    pdf_bytes = generate_sanad_report(st.session_state["review_result"])

    st.download_button(
        label="Download SANAD Report (PDF)",
        data=pdf_bytes,
        file_name=f"SANAD_Report_{now_date_str()}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
