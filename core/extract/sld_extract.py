from __future__ import annotations

import re
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import numpy as np
from PIL import Image

from core.extract.pdf_render import render_pdf_to_images, RenderedPage
from core.extract.image_preprocess import preprocess_for_ocr


# -------------------------------------------------------------------
# Data Classes
# -------------------------------------------------------------------
@dataclass(frozen=True)
class OcrLine:
    """Single line of OCR output with metadata."""
    text: str
    bbox: List[List[float]]  # 4 corner points
    conf: float
    page_index: int


@dataclass
class SldExtractionResult:
    """Extracted signals from SLD PDF."""
    inverter_vmax: Optional[float]
    modules_per_string: Optional[int]
    inverter_labels: List[str]
    notes: str
    evidence: Dict[str, Dict]  # field -> {page, text, conf}


# -------------------------------------------------------------------
# PaddleOCR Loader
# -------------------------------------------------------------------
def _load_paddle_ocr():
    """
    Lazy import so Streamlit doesn't load OCR model unless needed.
    Compatible with PaddleOCR >= 2.7.0
    """
    # Suppress PaddleOCR logging via environment variable
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

    from paddleocr import PaddleOCR  # type: ignore

    return PaddleOCR(use_angle_cls=True, lang="en")


# -------------------------------------------------------------------
# Image Preparation for OCR
# -------------------------------------------------------------------
def _ensure_rgb_array(img: Image.Image) -> np.ndarray:
    """
    Convert PIL Image to RGB numpy array suitable for PaddleOCR.
    
    PaddleOCR requires:
        - 3D array with shape (height, width, 3)
        - RGB color order
        - uint8 dtype
    """
    # Convert to RGB if not already (handles grayscale, RGBA, etc.)
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    # Convert to numpy array
    arr = np.array(img, dtype=np.uint8)
    
    # Verify shape is correct
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"Image array has unexpected shape: {arr.shape}")
    
    return arr


# -------------------------------------------------------------------
# OCR Processing
# -------------------------------------------------------------------
def _ocr_pages(
    pages: List[RenderedPage],
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> List[OcrLine]:
    """
    Run OCR on all rendered PDF pages.
    
    Args:
        pages: List of RenderedPage objects from PDF rendering
        progress_cb: Optional callback(current, total) for progress updates
    
    Returns:
        List of OcrLine objects with extracted text
    """
    ocr = _load_paddle_ocr()
    lines: List[OcrLine] = []

    total = len(pages)
    for idx, page in enumerate(pages, start=1):
        if progress_cb:
            progress_cb(idx, total)

        # Preprocess image for better OCR accuracy
        img = preprocess_for_ocr(page.image)
        
        # Ensure image is RGB numpy array for PaddleOCR
        arr = _ensure_rgb_array(img)

        # Run OCR
        try:
            result = ocr.ocr(arr)
        except Exception as e:
            # Log error but continue with other pages
            print(f"OCR failed on page {idx}: {e}")
            continue

        # Parse result - format: [ [ [bbox, (text, conf)], ... ] ]
        if not result or not result[0]:
            continue

        for block in result[0]:
            # Handle different result formats from PaddleOCR versions
            try:
                if len(block) == 2:
                    bbox, text_conf = block
                    if isinstance(text_conf, tuple) and len(text_conf) == 2:
                        text, conf = text_conf
                    else:
                        text, conf = str(text_conf), 0.0
                else:
                    continue
                    
                text = (text or "").strip()
                if not text:
                    continue
                    
                lines.append(
                    OcrLine(
                        text=text,
                        bbox=bbox,
                        conf=float(conf),
                        page_index=page.page_index,
                    )
                )
            except (ValueError, TypeError) as e:
                # Skip malformed blocks
                continue

    return lines


# -------------------------------------------------------------------
# Text Utilities
# -------------------------------------------------------------------
def _join_lines(lines: List[OcrLine]) -> str:
    """Concatenate OCR lines into text blob for regex scanning."""
    lines_sorted = sorted(lines, key=lambda x: x.page_index)
    return "\n".join(f"[p{l.page_index+1}] {l.text}" for l in lines_sorted)


def _find_first(patterns: List[str], text: str) -> Optional[re.Match]:
    """Find first matching pattern in text."""
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m
    return None


def _evidence_for_match(lines: List[OcrLine], match_text: str) -> Optional[OcrLine]:
    """Find the OCR line containing the matched text."""
    needle = match_text.strip().lower()
    for l in lines:
        if needle and needle in l.text.lower():
            return l
    return None


# -------------------------------------------------------------------
# Main Extraction Function
# -------------------------------------------------------------------
def extract_sld_signals_from_pdf(
    pdf_bytes: bytes,
    target_dpi: int = 300,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> SldExtractionResult:
    """
    Extract electrical signals from SLD PDF using OCR.
    
    Args:
        pdf_bytes: Raw bytes of the PDF file
        target_dpi: DPI for rendering (higher = more accurate, slower)
        progress_cb: Optional callback for progress updates
    
    Returns:
        SldExtractionResult with extracted values and evidence
    """
    # Render PDF pages to images
    pages = render_pdf_to_images(pdf_bytes, target_dpi=target_dpi)
    
    # Run OCR on all pages
    lines = _ocr_pages(pages, progress_cb=progress_cb)
    text = _join_lines(lines)

    # Initialize result
    out = SldExtractionResult(
        inverter_vmax=None,
        modules_per_string=None,
        inverter_labels=[],
        notes="",
        evidence={},
    )

    if not lines:
        out.notes = "OCR produced no text. PDF may be blank or render failed."
        return out

    # ----------------------------
    # Extract: Inverter DC max voltage
    # ----------------------------
    vmax_patterns = [
        r"(?:DC\s*MAX|DC\s*MAXIMUM|VDC\s*MAX|MAX\s*DC)\s*[:=]?\s*(\d{3,4})\s*V",
        r"(?:Vmax|V\s*max)\s*[:=]?\s*(\d{3,4})\s*V",
        r"(\d{3,4})\s*V\s*(?:DC\s*MAX|VDC\s*MAX|MAX\s*DC)",
    ]
    m_vmax = _find_first(vmax_patterns, text)
    if m_vmax:
        out.inverter_vmax = float(m_vmax.group(1))
        ev_line = _evidence_for_match(lines, m_vmax.group(0))
        if ev_line:
            out.evidence["inverter_vmax"] = {
                "page": ev_line.page_index + 1,
                "text": ev_line.text,
                "conf": ev_line.conf,
                "bbox": ev_line.bbox,
            }

    # ----------------------------
    # Extract: Modules per string
    # ----------------------------
    mps_patterns = [
        r"(?:MODULES\s*/\s*STRING|MODULES\s*PER\s*STRING|MOD\s*/\s*STR)\s*[:=]?\s*(\d{1,3})",
        r"\bMPS\b\s*[:=]?\s*(\d{1,3})",
    ]
    m_mps = _find_first(mps_patterns, text)
    if m_mps:
        out.modules_per_string = int(m_mps.group(1))
        ev_line = _evidence_for_match(lines, m_mps.group(0))
        if ev_line:
            out.evidence["modules_per_string"] = {
                "page": ev_line.page_index + 1,
                "text": ev_line.text,
                "conf": ev_line.conf,
                "bbox": ev_line.bbox,
            }

    # ----------------------------
    # Extract: Inverter labels
    # ----------------------------
    inv_labels = set()
    for l in lines:
        m = re.findall(r"\bInverter\s*(\d{1,3})\b", l.text, flags=re.IGNORECASE)
        for x in m:
            inv_labels.add(f"Inverter {int(x)}")
    out.inverter_labels = (
        sorted(inv_labels, key=lambda s: int(re.findall(r"\d+", s)[0]))
        if inv_labels
        else []
    )

    # ----------------------------
    # Build notes
    # ----------------------------
    missing = []
    if out.inverter_vmax is None:
        missing.append("Inverter DC max voltage not detected.")
    if out.modules_per_string is None:
        missing.append("Modules per string not detected.")

    if missing:
        out.notes = "OCR ran on all pages. " + " ".join(missing)
    else:
        out.notes = "OCR ran on all pages and key signals were detected."

    return out
