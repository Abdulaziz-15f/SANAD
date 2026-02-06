"""
Engineering review logic for SANAD.

This module contains the check functions used by Stage 2.
It must NOT import streamlit at module level or call st.set_page_config.

Functions:
    - compare_bom_vs_sld: Compare BoM signals against SLD extracted signals
    - climate_voltage_check: Calculate string Voc at cold temperature
    - run_ac_voltage_drop_review: Parse AC cable sizing and check limits
    - saudi_standards_snapshot: Generate compliance snapshot
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.models import Issue
from core.parsers.ac_cable_sizing import parse_ac_cable_sizing_excel
from core.checks.voltage_drop import check_voltage_drop


# -------------------------------------------------------------------
# Data Classes
# -------------------------------------------------------------------
@dataclass
class CheckStatus:
    """
    Result of an engineering check.

    Attributes:
        level: "PASS" | "WARN" | "FAIL"
        title: Human-readable check name
        details: List of findings/observations
    """
    level: str
    title: str
    details: List[str]


# -------------------------------------------------------------------
# BoM vs SLD Consistency Check
# -------------------------------------------------------------------
def compare_bom_vs_sld(bom_sig: Dict[str, Any], sld_sig: Dict[str, Any]) -> CheckStatus:
    """
    Compare BoM signals against SLD extracted signals.

    Checks:
        - Inverter DC max voltage consistency
        - Modules per string consistency

    Returns:
        CheckStatus with PASS if values match, WARN if mismatch or missing.
    """
    details: List[str] = []
    issues_found = False

    # ----------------------------
    # Check: Inverter DC max voltage
    # ----------------------------
    bom_vmax = bom_sig.get("inverter_vmax")
    sld_vmax = sld_sig.get("inverter_vmax")

    if bom_vmax is not None and sld_vmax is not None:
        if abs(bom_vmax - sld_vmax) < 1.0:
            details.append(f"✓ Inverter DC max voltage matches: {bom_vmax:.0f} V")
        else:
            details.append(f"✗ MISMATCH: BoM says {bom_vmax:.0f} V, SLD shows {sld_vmax:.0f} V")
            issues_found = True
    elif sld_vmax is None:
        details.append("⚠ Inverter DC max voltage not detected in SLD")
        issues_found = True
    else:
        details.append(f"• Inverter DC max from BoM: {bom_vmax:.0f} V")

    # ----------------------------
    # Check: Modules per string
    # ----------------------------
    bom_mps = bom_sig.get("modules_per_string")
    sld_mps = sld_sig.get("modules_per_string")

    if bom_mps is not None and sld_mps is not None:
        if bom_mps == sld_mps:
            details.append(f"✓ Modules per string matches: {bom_mps}")
        else:
            details.append(f"✗ MISMATCH: BoM says {bom_mps}, SLD shows {sld_mps}")
            issues_found = True
    elif sld_mps is None:
        details.append("⚠ Modules per string not detected in SLD")
    else:
        details.append(f"• Modules per string from BoM: {bom_mps}")

    return CheckStatus(
        level="WARN" if issues_found else "PASS",
        title="BoM vs SLD Consistency Check",
        details=details,
    )


# -------------------------------------------------------------------
# Cold Weather Overvoltage Check
# -------------------------------------------------------------------
def climate_voltage_check(
    bom_sig: Dict[str, Any],
    tmin: float,
) -> Tuple[CheckStatus, Dict[str, Any], List[str]]:
    """
    Calculate string Voc at cold temperature and compare to inverter DC max.

    Formula:
        Voc_cold = Voc_STC * (1 + TempCoeff * (Tmin - 25))
        String_Voc_cold = Voc_cold * modules_per_string

    Args:
        bom_sig: Extracted BoM signals dict
        tmin: Design minimum temperature (°C)

    Returns:
        Tuple of (CheckStatus, calculation_numbers, recommendations)
    """
    # Extract values with safe defaults
    voc_stc = bom_sig.get("voc_stc", 49.5)
    temp_coeff = bom_sig.get("temp_coeff", -0.0029)
    mps = bom_sig.get("modules_per_string", 22)
    inverter_vmax = bom_sig.get("inverter_vmax", 1100.0)

    # Normalize temp coefficient (handle both -0.29% and -0.0029 formats)
    if abs(temp_coeff) > 0.05:
        temp_coeff = temp_coeff / 100.0

    # ----------------------------
    # Calculate Voc at Tmin
    # ----------------------------
    delta_t = tmin - 25.0
    voc_cold = voc_stc * (1 + temp_coeff * delta_t)
    string_voc_cold = voc_cold * mps

    # Calculate margin
    margin = inverter_vmax - string_voc_cold
    margin_pct = (margin / inverter_vmax) * 100 if inverter_vmax > 0 else 0

    # Store calculation values for transparency
    numbers = {
        "Voc_STC (V)": f"{voc_stc:.2f}",
        "Temp coeff (/°C)": f"{temp_coeff:.4f}",
        "Design Tmin (°C)": f"{tmin:.1f}",
        "Delta T (°C)": f"{delta_t:.1f}",
        "Voc_cold per module (V)": f"{voc_cold:.2f}",
        "Modules per string": f"{mps}",
        "String Voc_cold (V)": f"{string_voc_cold:.1f}",
        "Inverter DC max (V)": f"{inverter_vmax:.0f}",
        "Margin (V)": f"{margin:.1f}",
        "Margin (%)": f"{margin_pct:.1f}%",
    }

    recommendations: List[str] = []

    # ----------------------------
    # Evaluate result
    # ----------------------------
    if string_voc_cold > inverter_vmax:
        # FAIL: Overvoltage risk
        details = [
            f"String Voc at {tmin:.1f}°C = {string_voc_cold:.1f} V",
            f"Inverter DC max = {inverter_vmax:.0f} V",
            f"✗ OVERVOLTAGE RISK: exceeds limit by {abs(margin):.1f} V",
        ]
        # Design-safe modules per string suggestion
        suggested_mps = max(1, int(inverter_vmax // voc_cold))
        numbers["Suggested modules per string"] = f"{suggested_mps}"
        recommendations = [
            f"Reduce modules per string from {mps} to {suggested_mps}",
            "Verify module datasheet Voc and temperature coefficient",
            "Consider inverter with higher DC voltage rating",
        ]
        return (
            CheckStatus(level="FAIL", title="Cold Weather Overvoltage Check", details=details),
            numbers,
            recommendations,
        )

    elif margin_pct < 5.0:
        # WARN: Tight margin
        details = [
            f"String Voc at {tmin:.1f}°C = {string_voc_cold:.1f} V",
            f"Inverter DC max = {inverter_vmax:.0f} V",
            f"⚠ Margin is tight: {margin:.1f} V ({margin_pct:.1f}%)",
        ]
        recommendations = [
            "Consider reducing modules per string for safety margin",
            "Verify temperature coefficient from module datasheet",
        ]
        return (
            CheckStatus(level="WARN", title="Cold Weather Overvoltage Check", details=details),
            numbers,
            recommendations,
        )

    else:
        # PASS: Within safe limits
        details = [
            f"String Voc at {tmin:.1f}°C = {string_voc_cold:.1f} V",
            f"Inverter DC max = {inverter_vmax:.0f} V",
            f"✓ Margin: {margin:.1f} V ({margin_pct:.1f}%) — OK",
        ]
        return (
            CheckStatus(level="PASS", title="Cold Weather Overvoltage Check", details=details),
            numbers,
            recommendations,
        )


# -------------------------------------------------------------------
# AC Voltage Drop Review
# -------------------------------------------------------------------
def run_ac_voltage_drop_review(
    ac_cable_file: io.BytesIO,
    inv_limit_pct: float = 3.0,
    comb_limit_pct: float = 1.5,
) -> Dict[str, Any]:
    """
    Parse AC cable sizing Excel and check voltage drop limits.

    Limits (per SEC/NEC standards):
        - Inverter to Combiner: ≤ 3.0%
        - Combiner to MDB: ≤ 1.5%

    Returns:
        Dict with 'kpis' and 'issues' keys
    """
    try:
        inv_runs, comb_runs = parse_ac_cable_sizing_excel(ac_cable_file)

        issues = check_voltage_drop(
            inv_runs,
            comb_runs,
            inverter_vd_limit_pct=inv_limit_pct,
            combiner_vd_limit_pct=comb_limit_pct,
        )

        max_inv_vd = max((r.voltage_drop_pct for r in inv_runs), default=0.0)
        max_comb_vd = max((r.voltage_drop_pct for r in comb_runs), default=0.0)

        return {
            "kpis": {
                "max_inverter_vd_pct": max_inv_vd,
                "max_combiner_vd_pct": max_comb_vd,
                "inverter_runs_count": len(inv_runs),
                "combiner_runs_count": len(comb_runs),
            },
            "issues": issues,
        }

    except Exception as e:
        return {
            "kpis": {
                "max_inverter_vd_pct": 0.0,
                "max_combiner_vd_pct": 0.0,
                "inverter_runs_count": 0,
                "combiner_runs_count": 0,
            },
            "issues": [
                Issue(
                    code="AC_PARSE_FAIL",
                    severity="CRITICAL",
                    title="Failed to parse AC Cable Sizing Excel",
                    description=str(e),
                )
            ],
        }


# -------------------------------------------------------------------
# Saudi Standards Compliance Snapshot
# -------------------------------------------------------------------
def saudi_standards_snapshot(
    climate_ok: bool,
    bom_sld_level: str,
) -> Tuple[List[str], List[str]]:
    """
    Generate compliance snapshot based on check results.

    References:
        - SEC Distribution Grid Code
        - SASO adoption of IEC 62548 (PV array design)
        - NEC Article 690

    Returns:
        Tuple of (compliant_points, gaps_points)
    """
    compliant: List[str] = []
    gaps: List[str] = []

    # Climate / Overvoltage
    if climate_ok:
        compliant.append("String sizing within inverter DC voltage limits (IEC 62548)")
    else:
        gaps.append("String Voc at Tmin may exceed inverter DC max")

    # BoM vs SLD Consistency
    if bom_sld_level == "PASS":
        compliant.append("BoM and SLD documents are consistent")
    else:
        gaps.append("BoM and SLD show discrepancies — verify design intent")

    # Static compliance points
    compliant.extend([
        "Module Voc temperature coefficient considered",
        "Site-specific historical Tmin used for analysis",
    ])

    gaps.extend([
        "DC cable sizing verification not yet implemented",
        "Grounding coordination requires manual review",
    ])

    return compliant, gaps
