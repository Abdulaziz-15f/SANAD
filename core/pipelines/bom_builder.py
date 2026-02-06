"""
Utility for building a Bill of Materials from extracted project data.

The function maps the extracted values (inverter model, module wattage, string
counts, cable sizes) to the curated catalog stored in
`Project_BOM_With_Instructions.xlsx`, then returns a component list compatible
with `generate_bom_file`.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from difflib import SequenceMatcher

import pandas as pd

from core.pipelines.extraction_pipeline import MergedExtraction


CATALOG_FILENAME = "Project_BOM_With_Instructions.xlsx"


def _catalog_path(catalog_path: str | Path | None) -> Path:
    if catalog_path:
        return Path(catalog_path)
    return Path(__file__).resolve().parents[2] / CATALOG_FILENAME


def _load_catalog(catalog_path: str | Path | None) -> pd.DataFrame:
    path = _catalog_path(catalog_path)
    if not path.exists():
        raise FileNotFoundError(f"Catalog file not found at {path}")
    return pd.read_excel(path)


def _extract_power_from_name(name: str) -> float | None:
    """Pull the wattage number from strings like 'PV Module 615Wp'."""
    if not isinstance(name, str):
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*W", name, flags=re.IGNORECASE)
    return float(m.group(1)) if m else None


def _normalize_model(text: Optional[str]) -> str:
    """Normalize model strings for matching."""
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _score_row(row: Dict, target: str) -> float:
    """Higher score = better match against target model string."""
    model = _normalize_model(row.get("Model Name"))
    t = _normalize_model(target)
    if not model or not t:
        return 0.0
    if model == t:
        return 1.0
    if t in model:
        return 0.9
    if model in t:
        return 0.85
    return SequenceMatcher(None, model, t).ratio() * 0.8


def _estimate_counts(merged: MergedExtraction) -> Dict[str, float]:
    """Best-effort calculation of quantities from extracted values."""
    modules_per_string = merged.modules_per_string
    total_strings = merged.total_strings
    module_pmax = merged.module_pmax_w
    system_kw = merged.system_capacity_kw
    inverter_count = getattr(merged, "inverter_count", None)
    mppt_count = getattr(merged, "mppt_count", None)
    strings_per_mppt = getattr(merged, "strings_per_mppt", None)

    modules_qty = None
    if total_strings and modules_per_string:
        modules_qty = int(total_strings * modules_per_string)
    elif system_kw and module_pmax:
        modules_qty = int(math.ceil((system_kw * 1000) / module_pmax))
        if modules_per_string:
            total_strings = math.ceil(modules_qty / modules_per_string)

    # Prefer explicit inverter count if present
    inverter_qty = inverter_count or 1
    inv_power = merged.inverter_ac_power_kw
    if system_kw and inv_power:
        try:
            derived = max(1, int(math.ceil(system_kw / inv_power)))
            inverter_qty = inverter_qty or derived
        except Exception:
            inverter_qty = 1

    # Infer total strings if missing using MPPT structure
    if total_strings is None and mppt_count and strings_per_mppt:
        total_strings = mppt_count * strings_per_mppt * inverter_qty

    return {
        "modules": modules_qty,
        "modules_per_string": modules_per_string,
        "strings": total_strings,
        "inverters": inverter_qty,
    }


def _select_row(df: pd.DataFrame, keyword: str) -> Dict:
    """
    Return best-matching row using substring + fuzzy score.
    Keeps behavior compatible with prior version but picks the closest match.
    """
    if not keyword:
        return {}
    mask_df = df[df["Model Name"].astype(str).str.contains(keyword, case=False, na=False)]
    candidates = mask_df if not mask_df.empty else df
    best_row = None
    best_score = 0.0
    for _, row in candidates.iterrows():
        s = _score_row(row, keyword)
        if s > best_score:
            best_score = s
            best_row = row
    return best_row.to_dict() if best_row is not None else {}


def _select_module_row(df: pd.DataFrame, target_pmax: float | None) -> Dict:
    modules_df = df[df["Model Name"].astype(str).str.contains("PV Module", case=False, na=False)]
    if modules_df.empty:
        return {}
    if target_pmax is None:
        return modules_df.iloc[0].to_dict()

    def score(row):
        p = _extract_power_from_name(row["Model Name"])
        if p is None:
            return float("inf")
        return abs(p - target_pmax)

    best_idx = modules_df.apply(score, axis=1).idxmin()
    return modules_df.loc[best_idx].to_dict()


def _add_component(components: List[Dict], row: Dict, quantity, unit="pcs", notes: str = ""):
    if not row:
        return

    base_notes = notes or row.get("How to Connect It", "")
    regs = row.get("Relevant Regulations")
    if regs:
        base_notes = f"{base_notes} | Regs: {regs}" if base_notes else f"Regs: {regs}"

    components.append({
        "name": row.get("Model Name", "Component"),
        "description": row.get("Description of the Part", ""),
        "quantity": quantity if quantity is not None else "Verify",
        "unit": unit,
        "notes": base_notes,
    })


def build_bom_from_extraction(
    merged: MergedExtraction,
    catalog_path: str | Path | None = None,
) -> Tuple[List[Dict], Dict[str, Dict]]:
    """
    Build a component list for the project BoM using extracted data.

    Returns:
        components: List of dicts ready for generate_bom_file
        debug: Matching and quantity info for UI/debug
    """
    catalog = _load_catalog(catalog_path)
    components: List[Dict] = []
    quantities = _estimate_counts(merged)
    matches: Dict[str, Dict] = {}

    # Inverter
    inverter_row = _select_row(catalog, merged.inverter_model or "SUN2000")
    matches["inverter"] = inverter_row
    _add_component(
        components,
        inverter_row,
        quantity=quantities["inverters"],
        notes=f"Extracted model: {merged.inverter_model or 'N/A'} | Count source: {'explicit' if getattr(merged, 'inverter_count', None) else 'estimated'}",
    )

    # PV modules
    module_row = _select_module_row(catalog, merged.module_pmax_w)
    matches["module"] = module_row
    _add_component(
        components,
        module_row,
        quantity=quantities["modules"],
        unit="modules",
        notes=f"Pmax: {merged.module_pmax_w or 'N/A'} W",
    )

    # DC cable (per string)
    dc_row = _select_row(catalog, "DC Cable")
    matches["dc_cable"] = dc_row
    dc_notes = f"Size: {merged.dc_cable_size_mm2} mm²" if merged.dc_cable_size_mm2 else ""
    _add_component(
        components,
        dc_row,
        quantity=quantities["strings"] or "Per string run",
        unit="runs",
        notes=dc_notes,
    )

    # AC cable (main feeder)
    ac_row = _select_row(catalog, "AC Cable")
    matches["ac_cable"] = ac_row
    ac_notes = f"Size: {merged.ac_cable_size_mm2} mm²" if merged.ac_cable_size_mm2 else ""
    # Assume one main feeder per inverter as an upper bound; adjust if extraction provides better data later.
    _add_component(
        components,
        ac_row,
        quantity=quantities["inverters"] or 1,
        unit="runs",
        notes=ac_notes,
    )

    # Grounding cable
    ground_row = _select_row(catalog, "Grounding")
    matches["grounding"] = ground_row
    _add_component(components, ground_row, quantity=1, unit="run")

    # Voltage transformer & indicator (site service)
    vt_row = _select_row(catalog, "Transformer")
    matches["voltage_transformer"] = vt_row
    _add_component(components, vt_row, quantity=1)

    vi_row = _select_row(catalog, "Indicator")
    matches["voltage_indicator"] = vi_row
    _add_component(components, vi_row, quantity=1)

    debug = {"quantities": quantities, "matches": matches}
    return components, debug
