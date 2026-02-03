"""
Session state management for SANAD.
Supports both single and multiple file uploads.
"""
from __future__ import annotations

import streamlit as st
from typing import Any, Dict, List
import pandas as pd


# -------------------------------------------------------------------
# Default State Values
# -------------------------------------------------------------------
DEFAULT_STATE = {
    "stage": 1,
    
    # Site selection
    "place": None,
    "lat": None,
    "lon": None,
    "geo_results": None,
    
    # Weather/Climate data
    "current_temp": None,
    "current_wind_speed": None,
    "tmin": None,
    "tmax": None,
    "max_wind_speed": None,
    "tmin_method": None,
    
    # Document uploads (supports single and multiple files)
    "uploads": {
        "sld": {"name": None, "bytes": None, "files": []},
        "pv_datasheet": {"name": None, "bytes": None, "files": []},
        "inverter_datasheet": {"name": None, "bytes": None, "files": []},
        "protection": {"name": None, "bytes": None, "files": []},
        "cable_sizing": {"name": None, "bytes": None, "df": None, "files": []},
        "pv_report": {"name": None, "bytes": None, "files": []},
    },
    
    # Extraction results
    "extraction": {
        "sld": None,
        "pv_module": None,
        "inverter": None,
        "cables": None,
        "merged": None,
    },
    
    # Analysis results
    "analysis": {
        "checks": [],
        "critical_issues": [],
        "warnings": [],
        "info": [],
        "overall_status": None,
        "critical_count": 0,
        "warning_count": 0,
        "info_count": 0,
    },
    
    "extraction_complete": False,
    "analysis_complete": False,
    "review_result": None,
}


def _deep_copy_dict(d: dict) -> dict:
    """Deep copy a nested dict."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _deep_copy_dict(v)
        elif isinstance(v, list):
            result[k] = v.copy()
        else:
            result[k] = v
    return result


def init_state() -> None:
    """Initialize session state with defaults."""
    for key, default_value in DEFAULT_STATE.items():
        if key not in st.session_state:
            if isinstance(default_value, dict):
                st.session_state[key] = _deep_copy_dict(default_value)
            elif isinstance(default_value, list):
                st.session_state[key] = default_value.copy()
            else:
                st.session_state[key] = default_value


def reset_all() -> None:
    """Reset all session state to defaults."""
    for key, default_value in DEFAULT_STATE.items():
        if isinstance(default_value, dict):
            st.session_state[key] = _deep_copy_dict(default_value)
        elif isinstance(default_value, list):
            st.session_state[key] = default_value.copy()
        else:
            st.session_state[key] = default_value


# -------------------------------------------------------------------
# Single File Upload
# -------------------------------------------------------------------
def set_upload(key: str, name: str, data: bytes, df=None) -> None:
    """Store single uploaded file."""
    if "uploads" not in st.session_state:
        st.session_state["uploads"] = _deep_copy_dict(DEFAULT_STATE["uploads"])
    
    if key not in st.session_state["uploads"]:
        st.session_state["uploads"][key] = {"name": None, "bytes": None, "files": []}
    
    st.session_state["uploads"][key]["name"] = name
    st.session_state["uploads"][key]["bytes"] = data
    st.session_state["uploads"][key]["files"] = [{"name": name, "bytes": data}]
    
    if df is not None:
        st.session_state["uploads"][key]["df"] = df
        st.session_state["uploads"][key]["files"][0]["df"] = df
    
    # Reset extraction when new file uploaded
    st.session_state["extraction_complete"] = False
    st.session_state["analysis_complete"] = False


# -------------------------------------------------------------------
# Multiple File Upload - IMPROVED
# -------------------------------------------------------------------
def set_multiple_uploads(key: str, files_data: List[Dict[str, Any]]) -> None:
    """
    Store multiple uploaded files.
    
    Args:
        key: Upload key (e.g., "pv_datasheet")
        files_data: List of dicts with {"name": str, "bytes": bytes, "df": optional}
    """
    if "uploads" not in st.session_state:
        st.session_state["uploads"] = _deep_copy_dict(DEFAULT_STATE["uploads"])
    
    if key not in st.session_state["uploads"]:
        st.session_state["uploads"][key] = {"name": None, "bytes": None, "files": []}
    
    # Store all files
    st.session_state["uploads"][key]["files"] = files_data
    
    # Backwards compatibility: set first file as primary
    if files_data:
        first = files_data[0]
        st.session_state["uploads"][key]["name"] = first.get("name")
        st.session_state["uploads"][key]["bytes"] = first.get("bytes")
        if "df" in first:
            st.session_state["uploads"][key]["df"] = first["df"]
    else:
        st.session_state["uploads"][key]["name"] = None
        st.session_state["uploads"][key]["bytes"] = None
    
    # Reset extraction when new files uploaded
    st.session_state["extraction_complete"] = False
    st.session_state["analysis_complete"] = False


def get_multiple_uploads(key: str) -> List[Dict[str, Any]]:
    """Get all uploaded files for a key."""
    return st.session_state.get("uploads", {}).get(key, {}).get("files", [])


def clear_upload(key: str) -> None:
    """Clear a specific upload."""
    if "uploads" in st.session_state and key in st.session_state["uploads"]:
        st.session_state["uploads"][key] = {"name": None, "bytes": None, "files": []}
        st.session_state["extraction_complete"] = False
        st.session_state["analysis_complete"] = False


def get_upload(key: str) -> dict:
    """Get upload data by key (returns first file for backwards compatibility)."""
    return st.session_state.get("uploads", {}).get(key, {"name": None, "bytes": None, "files": []})


def is_upload_ready(key: str) -> bool:
    """Check if upload has data (at least one file)."""
    upload = get_upload(key)
    files = upload.get("files", [])
    if files:
        return len(files) > 0 and files[0].get("bytes") is not None
    return upload.get("bytes") is not None


def all_required_uploads_ready() -> bool:
    """Check if all required uploads are present."""
    required = ["sld", "pv_datasheet", "inverter_datasheet", "cable_sizing"]
    return all(is_upload_ready(k) for k in required)


# -------------------------------------------------------------------
# Extraction Helpers
# -------------------------------------------------------------------
def set_extraction(key: str, data: Any) -> None:
    """Store extraction result."""
    if "extraction" not in st.session_state:
        st.session_state["extraction"] = _deep_copy_dict(DEFAULT_STATE["extraction"])
    st.session_state["extraction"][key] = data


def get_extraction(key: str) -> Any:
    """Get extraction result."""
    return st.session_state.get("extraction", {}).get(key)


# -------------------------------------------------------------------
# Analysis Helpers
# -------------------------------------------------------------------
def set_analysis_results(
    checks: list,
    critical: list,
    warnings: list,
    info: list,
    status: str,
) -> None:
    """Store analysis results."""
    st.session_state["analysis"] = {
        "checks": checks,
        "critical_issues": critical,
        "warnings": warnings,
        "info": info,
        "overall_status": status,
        "critical_count": len(critical),
        "warning_count": len(warnings),
        "info_count": len(info),
    }
    st.session_state["analysis_complete"] = True


def get_analysis() -> Dict[str, Any]:
    """Get analysis results."""
    return st.session_state.get("analysis", DEFAULT_STATE["analysis"])
