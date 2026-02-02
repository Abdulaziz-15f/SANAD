from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd


def _smart_find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Find a column by trying multiple candidate names (case-insensitive)."""
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.lower()
        if key in cols:
            return cols[key]
    return None


def extract_bom_signals(df: pd.DataFrame) -> Dict:
    """
    Extracts the minimum set of signals needed for PV electrical checks.
    Uses safe defaults if the BoM doesn't include the expected columns.
    """
    c_voc = _smart_find_col(df, ["Voc_STC", "Voc", "Module_Voc", "PV_Voc"])
    c_tc = _smart_find_col(df, ["TempCoeff", "Temp_Coeff", "Voc_TempCoeff", "TempCoeff_Voc"])
    c_mps = _smart_find_col(df, ["ModulesPerString", "Modules_per_string", "MPS", "PanelsPerString"])
    c_inv = _smart_find_col(df, ["Inverter_Vmax", "InverterVmax", "DC_Vmax", "Vmax_DC"])
    c_inv_name = _smart_find_col(df, ["Inverter", "InverterModel", "INV_Model", "Inverter_Model"])

    voc_stc = float(df[c_voc].dropna().iloc[0]) if c_voc and not df[c_voc].dropna().empty else 49.5
    temp_coeff = float(df[c_tc].dropna().iloc[0]) if c_tc and not df[c_tc].dropna().empty else -0.0029
    mps = int(df[c_mps].dropna().iloc[0]) if c_mps and not df[c_mps].dropna().empty else 22
    inverter_vmax = float(df[c_inv].dropna().iloc[0]) if c_inv and not df[c_inv].dropna().empty else 1100.0
    inverter_name = (
        str(df[c_inv_name].dropna().iloc[0])
        if c_inv_name and not df[c_inv_name].dropna().empty
        else "Inverter model not specified"
    )

    # Normalize percent coefficients into decimal form (e.g. -0.23% -> -0.0023)
    if abs(temp_coeff) > 0.05:
        temp_coeff = temp_coeff / 100.0

    return {
        "voc_stc": voc_stc,
        "temp_coeff": temp_coeff,
        "modules_per_string": mps,
        "inverter_vmax": inverter_vmax,
        "inverter_name": inverter_name,
        "meta": {
            "voc_source": c_voc or "DEFAULT",
            "tc_source": c_tc or "DEFAULT",
            "mps_source": c_mps or "DEFAULT",
            "vmax_source": c_inv or "DEFAULT",
            "invname_source": c_inv_name or "DEFAULT",
        },
    }
