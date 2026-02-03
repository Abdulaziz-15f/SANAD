"""
PV Module Datasheet Extraction.

Extracts key electrical parameters from PV module datasheets:
    - Voc (Open Circuit Voltage)
    - Isc (Short Circuit Current)
    - Vmp (Voltage at Max Power)
    - Imp (Current at Max Power)
    - Pmax (Maximum Power)
    - Temperature Coefficients
    - Module dimensions
    - Certifications
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.extract.pdf_render import render_pdf_to_images
from core.extract.sld_extract import _load_paddle_ocr, _ensure_rgb_array
from core.extract.image_preprocess import preprocess_for_ocr


@dataclass
class PVModuleSpecs:
    """Extracted PV module specifications."""
    
    # Identification
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    
    # Electrical (STC: 1000W/m², 25°C, AM1.5)
    pmax_w: Optional[float] = None
    voc_v: Optional[float] = None
    isc_a: Optional[float] = None
    vmp_v: Optional[float] = None
    imp_a: Optional[float] = None
    efficiency_percent: Optional[float] = None
    
    # Temperature Coefficients
    temp_coeff_voc_percent_c: Optional[float] = None  # %/°C (negative)
    temp_coeff_isc_percent_c: Optional[float] = None  # %/°C (positive)
    temp_coeff_pmax_percent_c: Optional[float] = None  # %/°C (negative)
    
    # Operating conditions
    noct_c: Optional[float] = None  # Nominal Operating Cell Temperature
    max_system_voltage_v: Optional[float] = None
    max_series_fuse_a: Optional[float] = None
    
    # Physical
    length_mm: Optional[float] = None
    width_mm: Optional[float] = None
    weight_kg: Optional[float] = None
    
    # Certifications
    certifications: List[str] = field(default_factory=list)
    
    # Extraction metadata
    confidence: float = 0.0
    notes: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)


def extract_pv_datasheet(pdf_bytes: bytes) -> PVModuleSpecs:
    """
    Extract PV module specifications from datasheet PDF.
    
    Args:
        pdf_bytes: Raw PDF bytes
    
    Returns:
        PVModuleSpecs with extracted values
    """
    # Render PDF to images
    pages = render_pdf_to_images(pdf_bytes, target_dpi=300)
    
    if not pages:
        return PVModuleSpecs(notes="Failed to render PDF")
    
    # OCR all pages
    ocr = _load_paddle_ocr()
    all_text = []
    
    for page in pages[:3]:  # First 3 pages should have specs
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
    
    # Join all text for pattern matching
    text = "\n".join(all_text)
    
    return _parse_pv_datasheet_text(text)


def _parse_pv_datasheet_text(text: str) -> PVModuleSpecs:
    """Parse extracted text to find PV module parameters."""
    
    specs = PVModuleSpecs()
    
    # Normalize text
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    
    # ----------------------------
    # Extract: Pmax
    # ----------------------------
    pmax_patterns = [
        r"(?:Pmax|P\s*max|Maximum\s*Power|Rated\s*Power)\s*[:=]?\s*(\d{2,4})\s*(?:Wp?|W)",
        r"(\d{3,4})\s*Wp?\b",
    ]
    for pat in pmax_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.pmax_w = float(m.group(1))
            specs.evidence["pmax"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Voc
    # ----------------------------
    voc_patterns = [
        r"(?:Voc|V\s*oc|Open\s*Circuit\s*Voltage)\s*[:=]?\s*(\d{2,3}\.?\d*)\s*V",
        r"Voc\s*\(V\)\s*[:=]?\s*(\d{2,3}\.?\d*)",
    ]
    for pat in voc_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.voc_v = float(m.group(1))
            specs.evidence["voc"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Isc
    # ----------------------------
    isc_patterns = [
        r"(?:Isc|I\s*sc|Short\s*Circuit\s*Current)\s*[:=]?\s*(\d{1,2}\.?\d*)\s*A",
        r"Isc\s*\(A\)\s*[:=]?\s*(\d{1,2}\.?\d*)",
    ]
    for pat in isc_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.isc_a = float(m.group(1))
            specs.evidence["isc"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Vmp
    # ----------------------------
    vmp_patterns = [
        r"(?:Vmp|V\s*mp|Vmpp|Voltage\s*at\s*Max\s*Power)\s*[:=]?\s*(\d{2,3}\.?\d*)\s*V",
    ]
    for pat in vmp_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.vmp_v = float(m.group(1))
            specs.evidence["vmp"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Imp
    # ----------------------------
    imp_patterns = [
        r"(?:Imp|I\s*mp|Impp|Current\s*at\s*Max\s*Power)\s*[:=]?\s*(\d{1,2}\.?\d*)\s*A",
    ]
    for pat in imp_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.imp_a = float(m.group(1))
            specs.evidence["imp"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Temperature Coefficient Voc
    # ----------------------------
    tc_voc_patterns = [
        r"(?:β\s*Voc|Temp.*Coeff.*Voc|Voc.*Temp.*Coeff)\s*[:=]?\s*(-?\d+\.?\d*)\s*%?\s*/?\s*°?C",
        r"(-0\.\d{2,3})\s*%\s*/\s*°?C\s*(?:Voc)?",
    ]
    for pat in tc_voc_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            # Normalize to %/°C
            if abs(val) > 1:
                val = val  # Already in %/°C form like -0.29
            specs.temp_coeff_voc_percent_c = val
            specs.evidence["temp_coeff_voc"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Max System Voltage
    # ----------------------------
    max_v_patterns = [
        r"(?:Max(?:imum)?\s*System\s*Voltage)\s*[:=]?\s*(\d{3,4})\s*V",
        r"(\d{3,4})\s*V\s*(?:DC)?\s*(?:max|maximum)",
    ]
    for pat in max_v_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            specs.max_system_voltage_v = float(m.group(1))
            specs.evidence["max_system_voltage"] = m.group(0)
            break
    
    # ----------------------------
    # Extract: Certifications
    # ----------------------------
    cert_patterns = [
        r"IEC\s*61215",
        r"IEC\s*61730",
        r"UL\s*1703",
        r"CE\b",
        r"MCS\b",
    ]
    for pat in cert_patterns:
        if re.search(pat, text, re.IGNORECASE):
            specs.certifications.append(re.search(pat, text, re.IGNORECASE).group(0))
    
    # ----------------------------
    # Calculate confidence
    # ----------------------------
    found_count = sum([
        specs.voc_v is not None,
        specs.isc_a is not None,
        specs.pmax_w is not None,
        specs.temp_coeff_voc_percent_c is not None,
    ])
    specs.confidence = found_count / 4.0
    
    # Build notes
    missing = []
    if specs.voc_v is None:
        missing.append("Voc")
    if specs.isc_a is None:
        missing.append("Isc")
    if specs.temp_coeff_voc_percent_c is None:
        missing.append("Temp Coeff")
    
    if missing:
        specs.notes = f"Missing: {', '.join(missing)}"
    else:
        specs.notes = "All key parameters extracted"
    
    return specs