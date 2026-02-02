import pandas as pd
import streamlit as st

from core.state import init_state, reset_all
from core.theme import apply_theme
from core.ui_components import header, render_map, weather_summary
from core.weather import fetch_current_weather, fetch_design_climate, geocode_list


# -------------------------------------------------------------------
# Page / App Setup
# -------------------------------------------------------------------
st.set_page_config(
    page_title="SANAD — PV Design Intake",
    page_icon="SANAD",
    layout="wide",
    initial_sidebar_state="collapsed",
)

apply_theme()
init_state()

# Stage routing (1 = intake, 2 = review)
st.session_state.setdefault("stage", 1)

header("SANAD")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _clear_upload_state(name_key: str, bytes_key: str) -> None:
    """
    Clear stored file info when the user removes an upload.
    This prevents stale bytes from remaining in session_state across reruns.
    """
    st.session_state[name_key] = None
    st.session_state[bytes_key] = None


# -------------------------------------------------------------------
# Stage 1: Site Selection + Document Upload
# -------------------------------------------------------------------
if st.session_state["stage"] == 1:
    left, right = st.columns([1.05, 0.95], gap="large")

    # ----------------------------
    # Left: Site selection
    # ----------------------------
    with left:
        st.markdown('<div class="sg-h2">Site selection</div>', unsafe_allow_html=True)

        q = st.text_input(
            "Search (city / region)",
            placeholder="NEOM, Tabuk, Riyadh, Jeddah, Makkah",
        )

        a, b = st.columns([1, 1])

        with a:
            st.markdown('<div class="sg-btn-primary">', unsafe_allow_html=True)
            if st.button("Search", use_container_width=True, type="secondary"):
                if not q.strip():
                    st.warning("Enter a city/region name.")
                else:
                    try:
                        st.session_state["geo_results"] = geocode_list(q.strip(), count=5)
                    except Exception as e:
                        st.session_state["geo_results"] = None
                        st.error(f"Search failed: {e}")
            st.markdown("</div>", unsafe_allow_html=True)

        with b:
            st.markdown('<div class="sg-btn-ghost">', unsafe_allow_html=True)
            if st.button("Reset", use_container_width=True):
                # Single reset point so we don't accidentally wipe uploads on Streamlit reruns.
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
                "Select result",
                options,
                index=0,
                label_visibility="collapsed",
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
            preview_place = f"{name}, {admin1}, {country}" if admin1 else f"{name}, {country}"
            zoom = 7
        elif st.session_state.get("lat") is not None and st.session_state.get("lon") is not None:
            preview_lat = float(st.session_state["lat"])
            preview_lon = float(st.session_state["lon"])
            preview_place = st.session_state.get("place")
            zoom = 7
        else:
            preview_lat, preview_lon = 24.7136, 46.6753
            preview_place = None
            zoom = 5

        render_map(preview_lat, preview_lon, preview_place, height=320, zoom=zoom)

        # Persist selected site
        st.markdown('<div class="sg-btn-clean">', unsafe_allow_html=True)
        if st.button("Set site", use_container_width=True, disabled=(selected_idx is None)):
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

            # Fetch current weather (temp + wind)
            try:
                current = fetch_current_weather(lat, lon)
                st.session_state["current_temp"] = current.get("current_temp")
                st.session_state["current_wind_speed"] = current.get("wind_speed")
            except Exception:
                st.session_state["current_temp"] = None
                st.session_state["current_wind_speed"] = None

            # Fetch design climate data (Tmin, Tmax, max wind)
            try:
                climate = fetch_design_climate(lat, lon, years=10)
                st.session_state["tmin"] = climate.get("tmin")
                st.session_state["tmax"] = climate.get("tmax")
                st.session_state["max_wind_speed"] = climate.get("max_wind_speed")
                st.session_state["tmin_method"] = climate.get("method", "")
            except Exception:
                st.session_state["tmin"] = None
                st.session_state["tmax"] = None
                st.session_state["max_wind_speed"] = None
                st.session_state["tmin_method"] = "Archive: failed to derive climate data"

            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # ----------------------------
    # Right: Uploads + Weather
    # ----------------------------
    with right:
        st.markdown('<div class="sg-h2">Input documents</div>', unsafe_allow_html=True)

        # Required uploads for Stage 2
        sld = st.file_uploader("Single-Line Diagram (PDF) — required", type=["pdf"])
        bom = st.file_uploader("Bill of Materials (Excel) — required", type=["xlsx", "xls"])
        ac_cable = st.file_uploader(
            "AC Cable Sizing / Voltage Drop (Excel) — required",
            type=["xlsx", "xls"],
        )

        # --- SLD storage (bytes) ---
        if sld is not None:
            st.session_state["sld_pdf_name"] = sld.name
            st.session_state["sld_pdf_bytes"] = sld.getvalue()
        else:
            _clear_upload_state("sld_pdf_name", "sld_pdf_bytes")

        # --- BoM storage (dataframe) ---
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
                st.error(f"Failed to read BoM Excel: {e}")
        else:
            st.session_state["bom_name"] = None
            st.session_state["bom_df"] = None

        # --- AC cable sizing storage (bytes) ---
        if ac_cable is not None:
            st.session_state["ac_cable_name"] = ac_cable.name
            st.session_state["ac_cable_bytes"] = ac_cable.getvalue()
            st.success("AC Cable Sizing Excel loaded successfully.")
        else:
            _clear_upload_state("ac_cable_name", "ac_cable_bytes")

        st.markdown('<div class="sg-divider"></div>', unsafe_allow_html=True)

        # Weather summary for context + climate data visibility
        weather_summary(
            st.session_state.get("place"),
            st.session_state.get("current_temp"),
            st.session_state.get("tmin"),
            st.session_state.get("tmin_method"),
            tmax=st.session_state.get("tmax"),
            max_wind_speed=st.session_state.get("max_wind_speed"),
            current_wind_speed=st.session_state.get("current_wind_speed"),
        )

        # --- Manual Tmin fallback if auto-fetch failed ---
        if st.session_state.get("place") and st.session_state.get("tmin") is None:
            st.warning("⚠️ Could not fetch historical Tmin automatically. Please enter manually.")
            manual_tmin = st.number_input(
                "Design Tmin (°C) — lowest expected temperature",
                min_value=-20.0,
                max_value=50.0,
                value=5.0,
                step=0.5,
                help="Enter the lowest temperature expected at this site (used for overvoltage check)",
            )
            if st.button("Set Manual Tmin"):
                st.session_state["tmin"] = manual_tmin
                st.session_state["tmin_method"] = "Manual entry by user"
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # Continue gating (all required inputs must exist)
        ready = all(
            [
                st.session_state.get("place"),
                st.session_state.get("lat") is not None,
                st.session_state.get("lon") is not None,
                st.session_state.get("tmin") is not None,
                st.session_state.get("sld_pdf_bytes") is not None,
                st.session_state.get("bom_df") is not None,
                st.session_state.get("ac_cable_bytes") is not None,
            ]
        )

        st.markdown('<div class="sg-btn-primary">', unsafe_allow_html=True)
        if st.button("Continue", use_container_width=True, disabled=not ready):
            st.session_state["stage"] = 2
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# -------------------------------------------------------------------
# Stage 2: Review + Export
# -------------------------------------------------------------------
elif st.session_state["stage"] == 2:
    # Import here to avoid circular imports during Streamlit reruns
    from core.stage2 import render_stage2

    # Run the actual review UI + report export
    render_stage2()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sg-btn-ghost">', unsafe_allow_html=True)
    if st.button("Back to Stage 1", use_container_width=True):
        st.session_state["stage"] = 1
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
