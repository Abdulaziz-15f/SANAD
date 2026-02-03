"""
SANAD - Smart Automated Network for Auditing and Design Compliance

Main application entry point.
Multi-stage PV design review pipeline.
"""
import pandas as pd
import streamlit as st

from core.state import (
    init_state, 
    reset_all, 
    set_upload,
    set_multiple_uploads,
    clear_upload, 
    get_upload,
    get_multiple_uploads,
    is_upload_ready,
    all_required_uploads_ready,
)
from core.theme import apply_theme
from core.ui_components import header, render_map, weather_summary
from core.weather import fetch_current_weather, fetch_design_climate, geocode_list


# -------------------------------------------------------------------
# Page / App Setup
# -------------------------------------------------------------------
st.set_page_config(
    page_title="SANAD — PV Design Review",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

apply_theme()
init_state()

header("SANAD")


# -------------------------------------------------------------------
# Upload Configuration
# -------------------------------------------------------------------
UPLOAD_CONFIG = {
    "sld": {
        "label": "Single-Line Diagram (SLD)",
        "type": ["pdf"],
        "required": True,
        "multiple": False,  # SLD = single file only
        "help": "AC/DC Single Line Diagram of the PV system",
    },
    "pv_datasheet": {
        "label": "PV Module Datasheet",
        "type": ["pdf"],
        "required": True,
        "multiple": True,  # Multiple datasheets allowed
        "help": "Manufacturer datasheet(s) with Voc, Isc, temperature coefficients",
    },
    "inverter_datasheet": {
        "label": "Inverter Datasheet",
        "type": ["pdf"],
        "required": True,
        "multiple": True,  # Multiple inverter datasheets allowed
        "help": "Manufacturer datasheet(s) with DC input specs, MPPT range",
    },
    "cable_sizing": {
        "label": "Cable Sizing Calculations",
        "type": ["xlsx", "xls"],
        "required": True,
        "multiple": True,  # Multiple cable sheets allowed
        "help": "AC/DC cable sizing with voltage drop calculations",
    },
    "protection": {
        "label": "Protection System (Optional)",
        "type": ["pdf"],
        "required": False,
        "multiple": True,
        "help": "Protection devices specifications and settings",
    },
    "pv_report": {
        "label": "PV System Report (Optional)",
        "type": ["pdf"],
        "required": False,
        "multiple": True,
        "help": "Design calculations report from PVsyst or similar",
    },
}


# -------------------------------------------------------------------
# Stage 1: Site Selection + Document Upload
# -------------------------------------------------------------------
if st.session_state["stage"] == 1:
    left, right = st.columns([1.05, 0.95], gap="large")

    # ----------------------------
    # Left: Site selection
    # ----------------------------
    with left:
        st.markdown('<div class="sg-h2">Site Selection</div>', unsafe_allow_html=True)

        q = st.text_input(
            "Search (city / region)",
            placeholder="NEOM, Tabuk, Riyadh, Jeddah, Makkah, Dammam",
        )

        col_search, col_reset = st.columns([1, 1])

        with col_search:
            if st.button("🔍 Search", use_container_width=True, type="primary"):
                if not q.strip():
                    st.warning("Enter a city/region name.")
                else:
                    try:
                        st.session_state["geo_results"] = geocode_list(q.strip(), count=5)
                    except Exception as e:
                        st.session_state["geo_results"] = None
                        st.error(f"Search failed: {e}")

        with col_reset:
            if st.button("🔄 Reset All", use_container_width=True):
                reset_all()
                st.rerun()

        # Results dropdown
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
        elif st.session_state.get("lat") is not None:
            preview_lat = float(st.session_state["lat"])
            preview_lon = float(st.session_state["lon"])
            preview_place = st.session_state.get("place")
            zoom = 7
        else:
            preview_lat, preview_lon = 24.7136, 46.6753
            preview_place = None
            zoom = 5

        render_map(preview_lat, preview_lon, preview_place, height=300, zoom=zoom)

        # Set site button
        if st.button("📍 Set Site", use_container_width=True, disabled=(selected_idx is None)):
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
                current = fetch_current_weather(lat, lon)
                st.session_state["current_temp"] = current.get("current_temp")
                st.session_state["current_wind_speed"] = current.get("wind_speed")
            except Exception:
                st.session_state["current_temp"] = None
                st.session_state["current_wind_speed"] = None

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
                st.session_state["tmin_method"] = "Failed to fetch climate data"

            st.rerun()

    # ----------------------------
    # Right: Document Uploads
    # ----------------------------
    with right:
        st.markdown('<div class="sg-h2">Project Documents</div>', unsafe_allow_html=True)
        
        # Required uploads section
        st.markdown("**Required Documents:**")
        
        for key, config in UPLOAD_CONFIG.items():
            if not config["required"]:
                continue
            
            accept_multiple = config.get("multiple", False)
            
            if accept_multiple:
                # Multiple file uploader
                uploaded_files = st.file_uploader(
                    f"{config['label']} — required",
                    type=config["type"],
                    help=config["help"],
                    key=f"upload_{key}",
                    accept_multiple_files=True,
                )
                
                if uploaded_files:
                    files_data = []
                    for uf in uploaded_files:
                        file_bytes = uf.getvalue()
                        file_info = {"name": uf.name, "bytes": file_bytes}
                        
                        # Handle Excel files
                        if key == "cable_sizing":
                            try:
                                df = pd.read_excel(uf)
                                file_info["df"] = df
                            except Exception as e:
                                st.warning(f"Could not read {uf.name}: {e}")
                                file_info["df"] = None
                        
                        files_data.append(file_info)
                    
                    set_multiple_uploads(key, files_data)
                    st.success(f"✓ {len(files_data)} file(s) loaded for {config['label']}")
                else:
                    clear_upload(key)
            else:
                # Single file uploader (SLD only)
                uploaded_file = st.file_uploader(
                    f"{config['label']} — required",
                    type=config["type"],
                    help=config["help"],
                    key=f"upload_{key}",
                    accept_multiple_files=False,
                )
                
                if uploaded_file is not None:
                    file_bytes = uploaded_file.getvalue()
                    set_upload(key, uploaded_file.name, file_bytes)
                    st.success(f"✓ {config['label']} loaded")
                else:
                    clear_upload(key)
        
        # Optional uploads section
        with st.expander("Optional Documents"):
            for key, config in UPLOAD_CONFIG.items():
                if config["required"]:
                    continue
                
                accept_multiple = config.get("multiple", False)
                
                if accept_multiple:
                    uploaded_files = st.file_uploader(
                        config["label"],
                        type=config["type"],
                        help=config["help"],
                        key=f"upload_{key}",
                        accept_multiple_files=True,
                    )
                    
                    if uploaded_files:
                        files_data = []
                        for uf in uploaded_files:
                            files_data.append({
                                "name": uf.name,
                                "bytes": uf.getvalue(),
                            })
                        set_multiple_uploads(key, files_data)
                        st.success(f"✓ {len(files_data)} file(s) loaded")
                    else:
                        clear_upload(key)
                else:
                    uploaded_file = st.file_uploader(
                        config["label"],
                        type=config["type"],
                        help=config["help"],
                        key=f"upload_{key}",
                    )
                    
                    if uploaded_file is not None:
                        set_upload(key, uploaded_file.name, uploaded_file.getvalue())
                        st.success(f"✓ {config['label']} loaded")
                    else:
                        clear_upload(key)

        st.markdown('<div class="sg-divider"></div>', unsafe_allow_html=True)

        # Weather summary
        weather_summary(
            st.session_state.get("place"),
            st.session_state.get("current_temp"),
            st.session_state.get("tmin"),
            st.session_state.get("tmin_method"),
            tmax=st.session_state.get("tmax"),
            max_wind_speed=st.session_state.get("max_wind_speed"),
            current_wind_speed=st.session_state.get("current_wind_speed"),
        )

        # Manual Tmin fallback
        if st.session_state.get("place") and st.session_state.get("tmin") is None:
            st.warning("Could not fetch historical Tmin. Please enter manually.")
            manual_tmin = st.number_input(
                "Design Tmin (C)",
                min_value=-20.0,
                max_value=50.0,
                value=5.0,
                step=0.5,
            )
            if st.button("Set Manual Tmin"):
                st.session_state["tmin"] = manual_tmin
                st.session_state["tmin_method"] = "Manual entry"
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # Check readiness
        ready = all([
            st.session_state.get("place"),
            st.session_state.get("lat") is not None,
            st.session_state.get("tmin") is not None,
            all_required_uploads_ready(),
        ])

        if st.button("Continue to Review", use_container_width=True, disabled=not ready, type="primary"):
            st.session_state["stage"] = 2
            st.rerun()
        
        if not ready:
            missing = []
            if not st.session_state.get("place"):
                missing.append("Site location")
            if st.session_state.get("tmin") is None:
                missing.append("Design Tmin")
            for key, config in UPLOAD_CONFIG.items():
                if config["required"] and not is_upload_ready(key):
                    missing.append(config["label"])
            
            if missing:
                st.info(f"Missing: {', '.join(missing)}")


# -------------------------------------------------------------------
# Stage 2: Review + Export
# -------------------------------------------------------------------
elif st.session_state["stage"] == 2:
    from core.stage2 import render_stage2
    render_stage2()

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Back to Stage 1", use_container_width=True):
        st.session_state["stage"] = 1
        st.rerun()
