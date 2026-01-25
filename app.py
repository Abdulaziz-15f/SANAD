import pandas as pd

import streamlit as st
from core.report import generate_sanad_report, now_date_str
from core.review import (
    climate_voltage_check,
    compare_bom_vs_sld,
    extract_bom_signals,
    saudi_standards_snapshot,
    try_extract_from_sld,
)
from core.stage2 import render_stage2
from core.state import init_state, reset_all
from core.theme import apply_theme
from core.ui_components import header, render_map, weather_summary
from core.weather import fetch_current_temp, fetch_design_tmin, geocode_list

# Page config
st.set_page_config(
    page_title="SANAD — PV Design Intake",
    page_icon="SANAD",
    layout="wide",
    initial_sidebar_state="collapsed",
)

apply_theme()
init_state()

# IMPORTANT
st.session_state.setdefault("stage", 1)

header("SANAD")


def status_badge(level: str) -> str:
    if level == "PASS":
        return '<span class="sg-chip">MATCH</span>'
    if level == "WARN":
        return '<span class="sg-chip">WARNING</span>'
    if level == "FAIL":
        return '<span class="sg-chip">CRITICAL</span>'
    return '<span class="sg-chip">INFO</span>'


def level_to_streamlit(level: str):
    if level == "PASS":
        return st.success
    if level == "WARN":
        return st.warning
    if level == "FAIL":
        return st.error
    return st.info



if st.session_state["stage"] == 1:
    left, right = st.columns([1.05, 0.95], gap="large")

 
    with left:
        st.markdown('<div class="sg-h2">Site selection</div>', unsafe_allow_html=True)

        q = st.text_input(
            "Search (city / region)", placeholder="NEOM, Tabuk, Riyadh, Jeddah, Makkah"
        )

        a, b = st.columns([1, 1])
        with a:
            st.markdown('<div class="sg-btn-primary">', unsafe_allow_html=True)
            if st.button("Search", use_container_width=True, type="secondary"):
                if not q.strip():
                    st.warning("Enter a city/region name.")
                else:
                    try:
                        st.session_state["geo_results"] = geocode_list(
                            q.strip(), count=5
                        )
                    except Exception as e:
                        st.session_state["geo_results"] = None
                        st.error(f"Search failed: {e}")
            st.markdown("</div>", unsafe_allow_html=True)

        with b:
            st.markdown('<div class="sg-btn-ghost">', unsafe_allow_html=True)
            if st.button("Reset", use_container_width=True):
                reset_all()
                st.session_state["stage"] = 1
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        results = st.session_state.get("geo_results") or []
        options = []
        for it in results:
            name = it.get("name")
            admin1 = it.get("admin1")
            country = it.get("country")
            label = f"{name}, {admin1}, {country}" if admin1 else f"{name}, {country}"
            options.append(label)

        selected_idx = None
        if options:
            selected_label = st.selectbox(
                "Select result", options, index=0, label_visibility="collapsed"
            )
            selected_idx = options.index(selected_label)

        # Preview location on map
        if selected_idx is not None:
            it = results[selected_idx]
            preview_lat = float(it.get("latitude"))
            preview_lon = float(it.get("longitude"))
            name = it.get("name")
            admin1 = it.get("admin1")
            country = it.get("country")
            preview_place = (
                f"{name}, {admin1}, {country}" if admin1 else f"{name}, {country}"
            )
            zoom = 7
        elif (
            st.session_state.get("lat") is not None
            and st.session_state.get("lon") is not None
        ):
            preview_lat = float(st.session_state["lat"])
            preview_lon = float(st.session_state["lon"])
            preview_place = st.session_state.get("place")
            zoom = 7
        else:
            preview_lat, preview_lon = 24.7136, 46.6753
            preview_place = None
            zoom = 5

        # Smaller map (no background box)
        render_map(preview_lat, preview_lon, preview_place, height=320, zoom=zoom)

        # Set site
        st.markdown('<div class="sg-btn-clean">', unsafe_allow_html=True)
        if st.button(
            "Set site", use_container_width=True, disabled=(selected_idx is None)
        ):
            it = results[selected_idx]
            lat = float(it.get("latitude"))
            lon = float(it.get("longitude"))
            name = it.get("name")
            admin1 = it.get("admin1")
            country = it.get("country")
            place = f"{name}, {admin1}, {country}" if admin1 else f"{name}, {country}"

            st.session_state["place"] = place
            st.session_state["lat"] = lat
            st.session_state["lon"] = lon

            try:
                st.session_state["current_temp"] = fetch_current_temp(lat, lon)
            except Exception:
                st.session_state["current_temp"] = None

            try:
                tmin, method = fetch_design_tmin(lat, lon, years=10)
                st.session_state["tmin"] = tmin
                st.session_state["tmin_method"] = method
            except Exception:
                st.session_state["tmin"] = None
                st.session_state["tmin_method"] = "Archive: failed to derive Tmin"

            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

   
    # Inputs + Weather
    
    with right:
        st.markdown('<div class="sg-h2">Input documents</div>', unsafe_allow_html=True)

        sld = st.file_uploader("Single-Line Diagram (PDF)", type=["pdf"])
        bom = st.file_uploader("Bill of Materials (Excel)", type=["xlsx", "xls"])

        if sld is not None:
            st.session_state["sld_pdf_name"] = sld.name
            st.session_state["sld_pdf_bytes"] = sld.getvalue()

        if bom is not None:
            st.session_state["bom_name"] = bom.name
            try:
                df = pd.read_excel(bom)
                st.session_state["bom_df"] = df
                st.success("BoM loaded successfully.")
                with st.expander("Preview (first 10 rows)"):
                    st.dataframe(df.head(10), use_container_width=True)
            except Exception as e:
                st.session_state["bom_df"] = None
                st.error(f"Failed to read Excel: {e}")

        st.markdown('<div class="sg-divider"></div>', unsafe_allow_html=True)

        weather_summary(
            st.session_state.get("place"),
            st.session_state.get("current_temp"),
            st.session_state.get("tmin"),
            st.session_state.get("tmin_method"),
        )

        st.markdown("<br>", unsafe_allow_html=True)

        ready = all(
            [
                st.session_state.get("place"),
                st.session_state.get("lat") is not None,
                st.session_state.get("lon") is not None,
                st.session_state.get("tmin") is not None,
                st.session_state.get("sld_pdf_bytes") is not None,
                st.session_state.get("bom_df") is not None,
            ]
        )

        st.markdown('<div class="sg-btn-primary">', unsafe_allow_html=True)
        if st.button(
            "Continue",
            use_container_width=True,
            disabled=not ready,
        ):
            st.session_state["stage"] = 2
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


elif st.session_state["stage"] == 2:
    from core.stage2 import render_stage2

    render_stage2()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sg-btn-ghost">', unsafe_allow_html=True)
    if st.button("Back to Stage 1", use_container_width=True):
        st.session_state["stage"] = 1
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
