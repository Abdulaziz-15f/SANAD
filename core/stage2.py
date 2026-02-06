"""
Stage 2: AI Extraction + Compliance Review.
"""
from __future__ import annotations

import os
import logging
import warnings
import traceback
from typing import List

from dotenv import load_dotenv
load_dotenv()

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "1"
warnings.filterwarnings("ignore")
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("paddle").setLevel(logging.ERROR)

import streamlit as st
import pandas as pd

from core.state import (
    get_upload,
    get_multiple_uploads,
    set_extraction,
    get_extraction,
    set_analysis_results,
    get_analysis,
)
from core.pipelines.extraction_pipeline import (
    MergedExtraction,
    run_full_extraction,
    CableExtractor,
    merge_extractions,
    SLDExtraction,
    PVModuleExtraction,
    InverterExtraction,
)
from core.pipelines.analysis_pipeline import (
    run_analysis_pipeline,
    Severity,
)
from core.pipelines.bom_builder import build_bom_from_extraction
from core.pipelines.bom_generator import generate_bom_file


def render_stage2():
    """Render Stage 2: Extraction + Review."""
    st.markdown('<div class="sg-h2">Design Review</div>', unsafe_allow_html=True)
    
    if not st.session_state.get("extraction_complete"):
        _render_extraction_step()
    else:
        _render_review_results()


def _render_extraction_step():
    """Render the extraction step."""
    st.markdown("### Document Analysis")
    
    upload_info = [
        ("sld", "SLD", True),
        ("pv_datasheet", "PV Datasheet", True),
        ("inverter_datasheet", "Inverter Datasheet", True),
        ("cable_sizing", "Cable Sizing", True),
    ]
    
    cols = st.columns(4)
    for i, (key, name, is_multiple) in enumerate(upload_info):
        with cols[i]:
            if is_multiple:
                files = get_multiple_uploads(key)
                if files:
                    st.success(f"✓ {name}")
                    st.caption(f"{len(files)} file(s)")
                else:
                    st.error(f"✗ {name}")
            else:
                upload = get_upload(key)
                if upload.get("bytes"):
                    st.success(f"✓ {name}")
                else:
                    st.error(f"✗ {name}")
    
    st.markdown("---")
    
    use_ocr = st.checkbox(
        "Enable OCR Pipeline (slower but more accurate)",
        value=False,
        help="OCR extracts raw text from PDFs. Enable if Vision alone doesn't work."
    )
    
    if st.button("🔬 Analyze Documents", type="primary", use_container_width=True):
        _run_extraction_with_progress(use_ocr=use_ocr)


def _run_extraction_with_progress(use_ocr: bool = False):
    """Run extraction with all pipelines."""
    
    progress = st.progress(0, text="Starting extraction...")
    log_container = st.container()
    
    try:
        # Get uploads
        def _pick_file(files, preferred_exts=("dxf", "pdf")):
            if not files:
                return {}
            # prioritize preferred extensions in order
            for ext in preferred_exts:
                for f in files:
                    name = f.get("name", "").lower()
                    if name.endswith(f".{ext}"):
                        return f
            # fallback first with bytes
            for f in files:
                if f.get("bytes"):
                    return f
            return files[0]

        sld_files = get_multiple_uploads("sld")
        sld = _pick_file(sld_files)
        pv_files = get_multiple_uploads("pv_datasheet") or []
        inv_files = get_multiple_uploads("inverter_datasheet") or []
        cable_files = get_multiple_uploads("cable_sizing") or []
        
        location = st.session_state.get("place", "")
        tmin = st.session_state.get("tmin", 0)
        tmax = st.session_state.get("tmax", 50)
        
        # Check API key
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            st.error("❌ GOOGLE_API_KEY not found in .env file!")
            st.code("Add to .env file:\nGOOGLE_API_KEY=your_key_here")
            return
        
        with log_container:
            st.info(f"🔑 API Key: {api_key[:8]}...{api_key[-4:]}")
        
        # ===== STEP 1: SLD =====
        progress.progress(10, text="[1/4] Processing SLD...")
        sld_data = SLDExtraction()
        
        if sld.get("bytes"):
            with log_container:
                st.info("🔍 Extracting SLD...")
            try:
                sld_data = run_full_extraction(
                    sld["bytes"],
                    doc_type="sld",
                    file_name=sld.get("name"),
                    use_ocr=use_ocr,
                    ocr_timeout=75,  # prev 60s
                )
                with log_container:
                    st.success(f"✅ SLD: Capacity={sld_data.system_capacity_kw}kW, MPS={sld_data.modules_per_string}, Inverter={sld_data.inverter_model}")
            except Exception as e:
                with log_container:
                    st.warning(f"⚠️ SLD error: {str(e)[:100]}")
                    st.code(traceback.format_exc()[:500])
        
        # ===== STEP 2: PV Datasheets =====
        progress.progress(30, text="[2/4] Processing PV Datasheets...")
        pv_extractions: list[PVModuleExtraction] = []
        
        for i, pv_file in enumerate(pv_files):
            if pv_file.get("bytes"):
                with log_container:
                    st.info(f"🔍 Extracting PV Datasheet {i+1}/{len(pv_files)}...")
                try:
                    pv_ext = run_full_extraction(
                        pv_file["bytes"],
                        doc_type="pv",
                        file_name=pv_file.get("name"),
                        use_ocr=use_ocr,
                        ocr_timeout=75,  # prev 45s
                    )
                    pv_extractions.append(pv_ext)
                    with log_container:
                        st.success(f"  ✅ PV {i+1}: Model={pv_ext.model}, Voc={pv_ext.voc_v}V, Pmax={pv_ext.pmax_w}W, TempCoeff={pv_ext.temp_coeff_voc}")
                except Exception as e:
                    with log_container:
                        st.warning(f"  ⚠️ PV {i+1} error: {str(e)[:80]}")
        
        # Merge PV extractions
        pv_data = _merge_pv_extractions(pv_extractions)
        
        # ===== STEP 3: Inverter Datasheets =====
        progress.progress(55, text="[3/4] Processing Inverter Datasheets...")
        inv_extractions: list[InverterExtraction] = []
        
        for i, inv_file in enumerate(inv_files):
            if inv_file.get("bytes"):
                with log_container:
                    st.info(f"🔍 Extracting Inverter Datasheet {i+1}/{len(inv_files)}...")
                try:
                    inv_ext = run_full_extraction(
                        inv_file["bytes"],
                        doc_type="inverter",
                        file_name=inv_file.get("name"),
                        use_ocr=use_ocr,
                        ocr_timeout=75,  # prev 45s
                    )
                    inv_extractions.append(inv_ext)
                    with log_container:
                        st.success(f"  ✅ Inverter {i+1}: Model={inv_ext.model}, DC Max={inv_ext.dc_max_voltage_v}V, MPPT={inv_ext.mppt_count}")
                except Exception as e:
                    with log_container:
                        st.warning(f"  ⚠️ Inverter {i+1} error: {str(e)[:80]}")
        
        # Merge inverter extractions
        inverter_data = _merge_inverter_extractions(inv_extractions)
        
        # ===== STEP 4: Cable Sizing =====
        progress.progress(75, text="[4/4] Processing Cable Sizing...")
        
        combined_df = None
        for cable_file in cable_files:
            df = cable_file.get("df")
            if df is not None and not df.empty:
                if combined_df is None:
                    combined_df = df
                else:
                    combined_df = pd.concat([combined_df, df], ignore_index=True)
        
        cable_data = CableExtractor().extract(combined_df)
        with log_container:
            st.success(f"✅ Cables: DC VD={cable_data.dc_voltage_drop_percent}%, AC VD={cable_data.ac_voltage_drop_percent}%")
        
        # ===== MERGE ALL =====
        progress.progress(85, text="Merging extractions...")
        
        merged = merge_extractions(
            sld=sld_data,
            pv_module=pv_data,
            inverter=inverter_data,
            cables=cable_data,
            location=location,
            tmin=tmin,
            tmax=tmax,
            current_wind=st.session_state.get("current_wind_speed"),
            max_wind=st.session_state.get("max_wind_speed"),
        )
        
        # Debug output
        with st.expander("🔍 Debug: Final Extracted Values", expanded=True):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**SLD:**")
                st.write(f"- Capacity: {sld_data.system_capacity_kw} kW")
                st.write(f"- MPS: {sld_data.modules_per_string}")
                st.write(f"- Inverter: {sld_data.inverter_model}")
                st.write(f"- PV Module: {sld_data.pv_module_model}")
                st.write(f"- Confidence: {sld_data.confidence:.1%}")
            
            with col2:
                st.markdown("**PV Module:**")
                st.write(f"- Model: {pv_data.model}")
                st.write(f"- Voc: {pv_data.voc_v} V")
                st.write(f"- Isc: {pv_data.isc_a} A")
                st.write(f"- Pmax: {pv_data.pmax_w} W")
                st.write(f"- Temp Coeff: {pv_data.temp_coeff_voc}")
                st.write(f"- Confidence: {pv_data.confidence:.1%}")
            
            with col3:
                st.markdown("**Inverter:**")
                st.write(f"- Model: {inverter_data.model}")
                st.write(f"- DC Max: {inverter_data.dc_max_voltage_v} V")
                st.write(f"- MPPT Range: {inverter_data.mppt_voltage_min_v}-{inverter_data.mppt_voltage_max_v} V")
                st.write(f"- MPPT Count: {inverter_data.mppt_count}")
                st.write(f"- AC Power: {inverter_data.ac_rated_power_kw} kW")
                st.write(f"- Confidence: {inverter_data.confidence:.1%}")
            
            st.markdown("---")
            st.markdown("**Merged Result:**")
            st.json({
                "module_voc_v": merged.module_voc_v,
                "module_isc_a": merged.module_isc_a,
                "module_pmax_w": merged.module_pmax_w,
                "temp_coeff_voc": merged.temp_coeff_voc,
                "inverter_dc_max_v": merged.inverter_dc_max_voltage_v,
                "inverter_mppt_min": merged.inverter_mppt_min_v,
                "inverter_mppt_max": merged.inverter_mppt_max_v,
                "modules_per_string": merged.modules_per_string,
                "location": merged.location,
                "tmin": merged.tmin_c,
                "tmax": merged.tmax_c,
            })
        
        set_extraction("merged", merged)
        st.session_state["extraction_complete"] = True
        
        # ===== ANALYSIS =====
        progress.progress(90, text="Running compliance analysis...")
        
        analysis = run_analysis_pipeline(merged)
        
        set_analysis_results(
            checks=[i.to_dict() for i in analysis.issues],
            critical=[i.to_dict() for i in analysis.issues if i.severity == Severity.CRITICAL],
            warnings=[i.to_dict() for i in analysis.issues if i.severity == Severity.WARNING],
            info=[i.to_dict() for i in analysis.issues if i.severity == Severity.INFO],
            status=analysis.overall_status,
        )
        
        st.session_state["calculated_values"] = analysis.calculated
        st.session_state["top_issues"] = [i.to_dict() for i in analysis.top_issues]
        
        # Store standards compliance (NEW!)
        st.session_state["standards_compliance"] = analysis.standards_compliance
        st.session_state["overall_compliance_pct"] = analysis.overall_compliance_percent
        
        progress.progress(100, text="✅ Complete!")
        
        # Don't rerun immediately - let user see debug info
        if st.button("View Results →", type="primary"):
            st.rerun()
    
    except Exception as e:
        progress.empty()
        st.error(f"❌ Analysis failed: {str(e)}")
        st.code(traceback.format_exc())


def _merge_pv_extractions(extractions: list) -> PVModuleExtraction:
    """Merge multiple PV module extractions."""
    if not extractions:
        return PVModuleExtraction()
    if len(extractions) == 1:
        return extractions[0]
    
    best = max(extractions, key=lambda x: x.confidence)
    
    for ext in extractions:
        if best.voc_v is None and ext.voc_v:
            best.voc_v = ext.voc_v
        if best.isc_a is None and ext.isc_a:
            best.isc_a = ext.isc_a
        if best.vmp_v is None and ext.vmp_v:
            best.vmp_v = ext.vmp_v
        if best.imp_a is None and ext.imp_a:
            best.imp_a = ext.imp_a
        if best.pmax_w is None and ext.pmax_w:
            best.pmax_w = ext.pmax_w
        if best.temp_coeff_voc is None and ext.temp_coeff_voc:
            best.temp_coeff_voc = ext.temp_coeff_voc
        if best.model is None and ext.model:
            best.model = ext.model
        if best.manufacturer is None and ext.manufacturer:
            best.manufacturer = ext.manufacturer
    
    return best


def _merge_inverter_extractions(extractions: list) -> InverterExtraction:
    """Merge multiple inverter extractions."""
    if not extractions:
        return InverterExtraction()
    if len(extractions) == 1:
        return extractions[0]
    
    best = max(extractions, key=lambda x: x.confidence)
    
    for ext in extractions:
        if best.dc_max_voltage_v is None and ext.dc_max_voltage_v:
            best.dc_max_voltage_v = ext.dc_max_voltage_v
        if best.mppt_voltage_min_v is None and ext.mppt_voltage_min_v:
            best.mppt_voltage_min_v = ext.mppt_voltage_min_v
        if best.mppt_voltage_max_v is None and ext.mppt_voltage_max_v:
            best.mppt_voltage_max_v = ext.mppt_voltage_max_v
        if best.mppt_count is None and ext.mppt_count:
            best.mppt_count = ext.mppt_count
        if best.ac_rated_power_kw is None and ext.ac_rated_power_kw:
            best.ac_rated_power_kw = ext.ac_rated_power_kw
        if best.model is None and ext.model:
            best.model = ext.model
        if best.strings_per_mppt is None and ext.strings_per_mppt:
            best.strings_per_mppt = ext.strings_per_mppt
    
    return best


def _render_standards_compliance(standards: List):
    """Render standards compliance section with details."""
    st.markdown("---")
    st.markdown("### 📋 Standards Compliance")
    
    # Calculate overall
    total_checks = sum(s.checks_total for s in standards)
    passed_checks = sum(s.checks_passed for s in standards)
    overall_pct = (passed_checks / total_checks * 100) if total_checks > 0 else 0
    
    # Overall status bar
    if overall_pct >= 80:
        color = "#28a745"
        status = "✅ COMPLIANT"
    elif overall_pct >= 50:
        color = "#ffc107"
        status = "⚠️ PARTIAL"
    else:
        color = "#dc3545"
        status = "❌ NON-COMPLIANT"
    
    st.markdown(f"""
    <div style="background: linear-gradient(90deg, {color}40 {overall_pct}%, #e0e0e0 {overall_pct}%); 
                padding: 20px; border-radius: 12px; margin-bottom: 25px; border: 2px solid {color};">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h3 style="margin:0; color: #fff;">{status}</h3>
            <span style="font-size: 28px; font-weight: bold; color: #fff;">{overall_pct:.0f}%</span>
        </div>
        <div style="color: rgba(255,255,255,0.8); margin-top: 8px;">
            {passed_checks} of {total_checks} checks passed
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Individual standards
    for std in standards:
        if std.checks_total == 0:
            continue
        
        # Determine status color
        if std.status == "COMPLIANT":
            badge_color = "#28a745"
        elif std.status == "PARTIAL":
            badge_color = "#ffc107"
        elif std.status == "NON_COMPLIANT":
            badge_color = "#dc3545"
        else:
            badge_color = "#6c757d"
        
        with st.expander(f"**{std.standard_code}** - {std.standard_name} ({std.compliance_percent:.0f}%)"):
            st.markdown(f"*{std.description}*")
            
            # Progress bar
            st.progress(std.compliance_percent / 100)
            
            # Summary
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total", std.checks_total)
            with col2:
                st.metric("Passed", std.checks_passed)
            with col3:
                st.metric("Warnings", std.checks_warning)
            with col4:
                st.metric("Failed", std.checks_failed)
            
            # Individual checks
            if std.checks:
                st.markdown("**Checks:**")
                for check in std.checks:
                    if check.status == "PASS":
                        icon = "✅"
                        border = "#28a745"
                    elif check.status == "WARNING":
                        icon = "⚠️"
                        border = "#ffc107"
                    elif check.status == "FAIL":
                        icon = "❌"
                        border = "#dc3545"
                    else:
                        icon = "⏸️"
                        border = "#6c757d"
                    
                    req_html = f'<div style="font-size: 0.85em; color: #888;">Required: {check.required_value}</div>' if check.required_value else ''
                    
                    st.markdown(f"""
                    <div style="padding: 8px 12px; margin: 4px 0; background: rgba(255,255,255,0.05); 
                                border-radius: 6px; border-left: 3px solid {border};">
                        <div style="display: flex; justify-content: space-between;">
                            <span>{icon} <strong>{check.name}</strong></span>
                            <span style="color: #888;">{check.actual_value}</span>
                        </div>
                        <div style="font-size: 0.85em; color: #aaa;">{check.description}</div>
                        {req_html}
                    </div>
                    """, unsafe_allow_html=True)


def _render_extracted_data(merged: MergedExtraction):
    """Render extracted data with proper formatting."""
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### PV Module")
        st.text(f"Model: {merged.module_model or 'N/A'}")
        st.text(f"Pmax: {merged.module_pmax_w}W" if merged.module_pmax_w else "Pmax: N/A")
        st.text(f"Voc: {merged.module_voc_v}V" if merged.module_voc_v else "Voc: N/A")
        st.text(f"Isc: {merged.module_isc_a}A" if merged.module_isc_a else "Isc: N/A")
        st.text(f"Vmp: {merged.module_vmp_v}V" if merged.module_vmp_v else "Vmp: N/A")
        st.text(f"Temp Coeff: {merged.temp_coeff_voc}%/°C" if merged.temp_coeff_voc else "Temp Coeff: N/A")
    
    with col2:
        st.markdown("#### Inverter")
        st.text(f"Model: {merged.inverter_model or 'N/A'}")
        st.text(f"DC Max: {merged.inverter_dc_max_voltage_v}V" if merged.inverter_dc_max_voltage_v else "DC Max: N/A")
        st.text(f"MPPT Range: {merged.inverter_mppt_min_v}-{merged.inverter_mppt_max_v}V" if merged.inverter_mppt_min_v else "MPPT Range: N/A")
    
    st.markdown("#### System Configuration")
    
    capacity_str = f"{merged.system_capacity_kw:.0f}" if merged.system_capacity_kw else "N/A"
    mps_str = str(merged.modules_per_string) if merged.modules_per_string else "N/A"
    strings_str = str(int(merged.total_strings)) if merged.total_strings else "N/A"
    
    st.text(f"System Capacity: {capacity_str} kW")
    st.text(f"Modules/String: {mps_str}")
    st.text(f"Total Strings: {strings_str}")
    st.text(f"Location: {merged.location or 'N/A'}")
    st.text(f"Design Temp Range: {merged.tmin_c}°C to {merged.tmax_c}°C")
    
    st.markdown("#### Applicable Standards")
    st.markdown("""
    - **IEC 62548:2016** - PV Array Design Requirements
    - **IEC 62109-1/2** - Inverter Safety
    - **SEC Connection v3** - Saudi Grid Connection
    - **SEC Best Practice v2** - PV Design Guidelines
    """)


def _render_review_results():
    """Render the review results."""
    analysis = get_analysis()
    merged = get_extraction("merged")
    calculated = st.session_state.get("calculated_values", {})
    top_issues = st.session_state.get("top_issues", [])
    standards = st.session_state.get("standards_compliance", [])
    
    # Status Banner
    status = analysis.get("overall_status", "unknown")
    
    if status == "pass":
        st.success("✅ **DESIGN APPROVED** - All critical checks passed")
    elif status == "review":
        st.warning("⚠️ **REVIEW REQUIRED** - Issues need attention")
    else:
        st.error("❌ **DESIGN REJECTED** - Critical issues must be fixed")
    
    # Key Metrics
    st.markdown("### Key Calculations")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        voc_cold = calculated.get("string_voc_at_tmin")
        inv_max = merged.inverter_dc_max_voltage_v if merged else None
        delta = f"vs {inv_max}V max" if inv_max else ""
        st.metric("String Voc at Tmin", f"{voc_cold:.0f} V" if voc_cold else "N/A", delta=delta)
    
    with col2:
        margin = calculated.get("voltage_margin_pct")
        st.metric("Voltage Margin", f"{margin:.1f}%" if margin is not None else "N/A")
    
    with col3:
        ratio = calculated.get("dc_ac_ratio")
        st.metric("DC/AC Ratio", f"{ratio:.2f}" if ratio else "N/A")
    
    with col4:
        total_vd = calculated.get("total_voltage_drop_pct")
        st.metric("Total Voltage Drop", f"{total_vd:.2f}%" if total_vd is not None else "N/A")

    # Wind info (info only)
    wind_cols = st.columns(2)
    with wind_cols[0]:
        cw = calculated.get("current_wind_speed_kmh")
        st.metric("Current Wind", f"{cw:.1f} km/h" if cw is not None else "N/A")
    with wind_cols[1]:
        mw = calculated.get("max_wind_speed_kmh")
        st.metric("Max Wind (10y)", f"{mw:.1f} km/h" if mw is not None else "N/A")

    # BoM inline summary (keeps same visual language)
    st.markdown("### Bill of Materials (auto-generated)")
    bom_components = st.session_state.get("bom_components")
    if bom_components is None and merged:
        try:
            bom_components, bom_debug = build_bom_from_extraction(merged)
            st.session_state["bom_components"] = bom_components
            st.session_state["bom_debug"] = bom_debug
        except Exception as e:
            st.warning(f"BoM not available yet: {e}")
            bom_components = []

    if bom_components:
        # Compact summary chips
        q = st.session_state.get("bom_debug", {}).get("quantities", {})
        chips = [
            ("Modules", q.get("modules")),
            ("Strings", q.get("strings")),
            ("Modules/String", q.get("modules_per_string")),
            ("Inverters", q.get("inverters")),
        ]
        chip_cols = st.columns(len(chips))
        for col, (label, value) in zip(chip_cols, chips):
            with col:
                st.metric(label, value if value is not None else "N/A")

        with st.expander("BoM Components", expanded=False):
            st.dataframe(pd.DataFrame(bom_components))
    else:
        st.info("BoM will appear here after generation.")
    
    # Standards Compliance
    if standards:
        _render_standards_compliance(standards)
    
    st.markdown("---")
    
    # Priority Issues
    st.markdown("### 🚨 Priority Issues")
    
    if not top_issues:
        st.success("🎉 No significant issues found!")
    else:
        for i, issue in enumerate(top_issues, 1):
            severity = issue.get("severity", "info")
            
            if severity == "critical":
                icon = "🔴"
            elif severity == "warning":
                icon = "🟡"
            else:
                icon = "🟢"
            
            with st.expander(f"{icon} #{i}: {issue['title']}", expanded=(severity == "critical")):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Actual:** `{issue['actual_value']}`")
                    st.markdown(f"**Required:** `{issue['required_value']}`")
                with col2:
                    st.markdown(f"**Impact:** {issue['impact']}")
                    st.markdown(f"**Reference:** {issue.get('reference', 'N/A')}")
                
                st.markdown(f"**Description:** {issue['description']}")
                st.info(f"💡 **Recommendation:** {issue['recommendation']}")
    
    # Extracted Data
    with st.expander("📊 Extracted Data Summary", expanded=True):
        if merged:
            _render_extracted_data(merged)
    
    # Issue Summary
    st.markdown("### Issue Summary")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Critical", analysis.get("critical_count", 0))
    with col2:
        st.metric("Warnings", analysis.get("warning_count", 0))
    with col3:
        st.metric("Info", analysis.get("info_count", 0))
    
    # Buttons
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📄 Generate PDF Report", type="primary", use_container_width=True):
            _generate_report()
    
    with col2:
        if st.button("📦 Generate BoM (Excel)", use_container_width=True):
            try:
                if not merged:
                    raise ValueError("Extraction data is missing. Run analysis first.")
                components, bom_debug = build_bom_from_extraction(merged)
                bom_bytes = generate_bom_file(components)
                st.session_state["bom_bytes"] = bom_bytes
                st.session_state["bom_components"] = components
                st.session_state["bom_debug"] = bom_debug
                st.success("✅ BoM generated from extracted data.")
            except Exception as e:
                st.error(f"❌ BoM generation failed: {str(e)}")
    
    with col3:
        if st.button("🔄 Re-analyze", use_container_width=True):
            st.session_state["extraction_complete"] = False
            st.rerun()

    if st.session_state.get("bom_bytes"):
        filename = f"SANAD_BoM_{pd.Timestamp.now().strftime('%Y-%m-%d_%H%M')}.xlsx"
        st.download_button(
            label="📥 Download BoM",
            data=st.session_state["bom_bytes"],
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        with st.expander("📋 BoM Preview", expanded=False):
            st.dataframe(pd.DataFrame(st.session_state.get("bom_components", [])))


def _generate_report():
    """Generate PDF report with ALL data."""
    try:
        from core.pipelines.report_generator import generate_report
        from core.pipelines.analysis_pipeline import AnalysisResult, Issue, Severity
        
        merged = get_extraction("merged")
        analysis_data = get_analysis()
        calculated = st.session_state.get("calculated_values", {})
        standards_compliance = st.session_state.get("standards_compliance", [])
        bom_components = st.session_state.get("bom_components")

        # If BoM not generated yet, build it on-the-fly for the report
        if bom_components is None and merged:
            try:
                bom_components, _ = build_bom_from_extraction(merged)
            except Exception:
                bom_components = []
        
        # Reconstruct Issue objects
        issues = [Issue(
            severity=Severity(i["severity"]),
            title=i["title"],
            description=i["description"],
            actual_value=i["actual_value"],
            required_value=i["required_value"],
            impact=i["impact"],
            recommendation=i["recommendation"],
            reference=i.get("reference", ""),
            priority_score=i.get("priority_score", 50),
        ) for i in analysis_data.get("checks", [])]
        
        top_issues = [Issue(
            severity=Severity(i["severity"]),
            title=i["title"],
            description=i["description"],
            actual_value=i["actual_value"],
            required_value=i["required_value"],
            impact=i["impact"],
            recommendation=i["recommendation"],
            reference=i.get("reference", ""),
            priority_score=i.get("priority_score", 50),
        ) for i in st.session_state.get("top_issues", [])]
        
        analysis = AnalysisResult(
            issues=issues,
            critical_count=analysis_data.get("critical_count", 0),
            warning_count=analysis_data.get("warning_count", 0),
            info_count=analysis_data.get("info_count", 0),
            overall_status=analysis_data.get("overall_status", "unknown"),
            top_issues=top_issues,
            calculated=calculated,
            standards_compliance=standards_compliance,
            overall_compliance_percent=st.session_state.get("overall_compliance_pct", 0),
        )
        
        with st.spinner("Generating comprehensive PDF report..."):
            pdf_bytes = generate_report(
                merged=merged,
                analysis=analysis,
                calculated=calculated,
                project_name=st.session_state.get("place", "PV System"),
                standards_compliance=standards_compliance,
                bom_components=bom_components,
            )
            
            from datetime import datetime
            filename = f"SANAD_Report_{datetime.now().strftime('%Y-%m-%d_%H%M')}.pdf"
            
            st.download_button(
                label="📥 Download Complete Report",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
            st.success(f"✅ Report generated: {filename}")
            
    except Exception as e:
        st.error(f"❌ Report generation failed: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
