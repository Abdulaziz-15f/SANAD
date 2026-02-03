"""
Inverter Datasheet Extraction.

Extracts key specifications from inverter datasheets:
    - DC input specifications (Vmax, MPPT range, Imax)
    - AC output specifications (Power, Voltage, Frequency)
    - Efficiency ratings
    - Protection features
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.extract.pdf_render import render_pdf_to_images
from core.extract.sld_extract import _load_paddle_ocr, _ensure_rgb_array
from core.extract.image_preprocess import preprocess_for_ocr


@dataclass
class InverterSpecs:
    """Extracted inverter specifications."""
    
    # Identification
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    
    # DC Input
    dc_max_voltage_v: Optional[float] = None
    dc_mppt_voltage_min_v: Optional[float] = None
    dc_mppt_voltage_max_v: Optional[float] = None
    dc_start_voltage_v: Optional[float] = None
    dc_max_current_a: Optional[float] = None
    dc_max_current_per_mppt_a: Optional[float] = None
    mppt_count: Optional[int] = None
    strings_per_mppt: Optional[int] = None
    
    # AC Output
    ac_rated_power_kw: Optional[float] = None
    ac_max_power_kva: Optional[float] = None
    ac_voltage_v: Optional[float] = None
    ac_frequency_hz: Optional[float] = None
    ac_max_current_a: Optional[float] = None
    power_factor_range: Optional[str] = None
    thd_percent: Optional[float] = None
    
    # Efficiency
    max_efficiency_percent: Optional[float] = None
    euro_efficiency_percent: Optional[float] = None
    cec_efficiency_percent: Optional[float] = None
    
    # Protection
    anti_islanding: bool = True
    dc_reverse_polarity: bool = False
    surge_protection_dc: Optional[str] = None
    surge_protection_ac: Optional[str] = None
    ground_fault_monitoring: bool = False
    
    # Physical
    weight_kg: Optional[float] = None
    ip_rating: Optional[str] = None
    operating_temp_min_c: Optional[float] = None
    operating_temp_max_c: Optional[float] = None
    
    # Certifications
    certifications: List[str] = field(default_factory=list)
    
    # Extraction metadata
    confidence: float = 0.0
    notes: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)


def extract_inverter_datasheet(pdf_bytes: bytes) -> InverterSpecs:
    """
    Extract inverter specifications from datasheet PDF.
    
    Args:
        pdf_bytes: Raw PDF bytes
    
    Returns:
        InverterSpecs with extracted values
    """
    # Render PDF to images
    pages = render_pdf_to_images(pdf_bytes, target_dpi=300)
    
    if not pages:
        return InverterSpecs(notes="Failed to render PDF")
    
    # OCR all pages
    ocr = _load_paddle_ocr()
    all_text = []
    
    for page in pages[:4]:  # First 4 pages should have specs
        img = preprocess_for_ocr(page.image)
        arr = _ensure_rgb_array(img)
        
        try:
            result = ocr.ocr(arr)
            if result and result[0]:
                for block in result[0]:
                    if len(block) == 2:
                        _, text_conf = block
                        if isinstance(text_conf, tuple):
                            text, _ = text_conf
                            all_text.append(str(text).strip())
        except Exception:
            continue
    
    text = "\n".join(all_text)
    return _parse_inverter_text(text)


def _parse_inverter_text(text: str) -> InverterSpecs:
    """Parse extracted text to find inverter parameters."""
    
    specs = InverterSpecs()
    
    # Normalize text
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    
    # ----------------------------
    # Extract: DC Max Voltage
    # ----------------------------
    dc_vmax_patterns = [
        r"(?:Max(?:imum)?\.?\s*DC\s*Voltage|DC\s*Max\s*Voltage|Vdc\s*max)\s*[:=]?\s*(\d{3,4})\s*V",
        r"(\d{3,4})\s*V\s*(?:DC)?\s*(?:max|maximum)",
    ]
    for pat in dc_vmax_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.dc_max_voltage_v = float(m.group(1))
            specs.evidence["dc_max_voltage"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: MPPT Voltage Range
    # ----------------------------
    mppt_patterns = [
        r"(?:MPPT\s*(?:Voltage\s*)?Range)\s*[:=]?\s*(\d{2,4})\s*[-–]\s*(\d{2,4})\s*V",
        r"(?:MPPT)\s*(\d{2,4})\s*V?\s*[-–to]\s*(\d{2,4})\s*V",
    ]
    for pat in mppt_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.dc_mppt_voltage_min_v = float(m.group(1))
            specs.dc_mppt_voltage_max_v = float(m.group(2))
            specs.evidence["mppt_range"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Number of MPPTs
    # ----------------------------
    mppt_count_patterns = [
        r"(?:Number\s*of\s*MPPTs?|MPPT\s*(?:trackers?|qty))\s*[:=]?\s*(\d{1,2})",
        r"(\d{1,2})\s*MPPTs?",
    ]
    for pat in mppt_count_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.mppt_count = int(m.group(1))
            specs.evidence["mppt_count"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: AC Rated Power
    # ----------------------------
    ac_power_patterns = [
        r"(?:Rated\s*(?:AC\s*)?(?:Output\s*)?Power|AC\s*Nominal\s*Power|Pac)\s*[:=]?\s*(\d{2,4})\s*kW",
        r"(\d{2,4})\s*kW\s*(?:AC|rated|nominal)",
    ]
    for pat in ac_power_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.ac_rated_power_kw = float(m.group(1))
            specs.evidence["ac_rated_power"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Efficiency
    # ----------------------------
    eff_patterns = [
        r"(?:Max(?:imum)?\s*Efficiency)\s*[:=]?\s*(\d{2}\.?\d*)\s*%",
        r"η\s*max\s*[:=]?\s*(\d{2}\.?\d*)\s*%",
    ]
    for pat in eff_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.max_efficiency_percent = float(m.group(1))
            specs.evidence["efficiency"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: IP Rating
    # ----------------------------
    ip_pattern = r"\b(IP\s*\d{2})\b"
    m = re.search(ip_pattern, text, re.IGNORECASE)
    if m:
        specs.ip_rating = m.group(1).replace(" ", "")
        specs.evidence["ip_rating"] = m.group(0)
    
    # ----------------------------
    # Extract: Operating Temperature
    # ----------------------------
    temp_patterns = [
        r"(?:Operating\s*Temp(?:erature)?)\s*[:=]?\s*(-?\d{1,2})\s*[-–to]+\s*(\+?\d{2})\s*°?C",
    ]
    for pat in temp_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.operating_temp_min_c = float(m.group(1))
            specs.operating_temp_max_c = float(m.group(2))
            specs.evidence["operating_temp"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Model (common inverter models)
    # ----------------------------
    model_patterns = [
        r"(SUN2000-\d{2,3}KTL-M\d)",
        r"(SUN2000-\d{2,3}K-MG\d)",
        r"(SYMO\s*\d{1,2}\.\d)",
        r"(Sunny\s*Tripower\s*\d+)",
    ]
    for pat in model_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.model = m.group(1)
            specs.evidence["model"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Certifications
    # ----------------------------
    cert_patterns = [
        r"IEC\s*62109",
        r"IEC\s*61727",
        r"EN\s*50549",
        r"VDE\s*AR-N\s*4105",
        r"G98|G99|G100",
        r"CE\b",
    ]
    for pat in cert_patterns:
        if re.search(pat, text, re.IGNORECASE):
            specs.certifications.append(
                re.search(pat, text, re.IGNORECASE).group(0)
            )
    
    # ----------------------------
    # Calculate confidence
    # ----------------------------
    found_count = sum([
        specs.dc_max_voltage_v is not None,
        specs.dc_mppt_voltage_min_v is not None,
        specs.ac_rated_power_kw is not None,
        specs.mppt_count is not None,
    ])
    specs.confidence = found_count / 4.0
    
    # Build notes
    missing = []
    if specs.dc_max_voltage_v is None:
        missing.append("DC Max Voltage")
    if specs.dc_mppt_voltage_min_v is None:
        missing.append("MPPT Range")
    if specs.ac_rated_power_kw is None:
        missing.append("AC Power")
    
    if missing:
        specs.notes = f"Missing: {', '.join(missing)}"
    else:
        specs.notes = "All key parameters extracted"
    
    return specs