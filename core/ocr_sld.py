# core/ocr_sld.py
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

# PyMuPDF is the most reliable way to render PDF pages to images without external poppler.
# pip install pymupdf
import fitz  # type: ignore


@dataclass(frozen=True)
class OcrToken:
    text: str
    conf: float
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)


def _try_extract_selectable_text(pdf_bytes: bytes, max_pages: int = 2) -> str:
    """Fast path: if the PDF has selectable text, use it (much cleaner than OCR)."""
    try:
        import PyPDF2  # type: ignore

        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        chunks: List[str] = []
        for i in range(min(len(reader.pages), max_pages)):
            chunks.append(reader.pages[i].extract_text() or "")
        return "\n".join(chunks).strip()
    except Exception:
        return ""


def _render_pdf_to_images(pdf_bytes: bytes, max_pages: int = 2, dpi: int = 300) -> List[Image.Image]:
    """
    Render PDF pages into PIL images.
    AutoCAD drawings usually need high DPI (300–400) to OCR cleanly.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: List[Image.Image] = []

    zoom = dpi / 72.0  # PDF points are 72 DPI
    mat = fitz.Matrix(zoom, zoom)

    for i in range(min(doc.page_count, max_pages)):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append(img)

    return images


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """
    Drawings often have faint text and grid backgrounds.
    This preprocessing is simple but effective:
    - grayscale
    - autocontrast
    - upscale a bit (helps OCR)
    """
    gray = img.convert("L")
    gray = ImageOps.autocontrast(gray)

    # upscale ~1.5x (OCR likes larger text)
    w, h = gray.size
    gray = gray.resize((int(w * 1.5), int(h * 1.5)))

    return gray


def _ocr_images(images: List[Image.Image]) -> List[OcrToken]:
    """
    OCR backend:
    - Prefer PaddleOCR for technical drawings (better on small text), fallback to EasyOCR.
    We return tokens with bbox + confidence.
    """
    # Try PaddleOCR first
    try:
        from paddleocr import PaddleOCR  # type: ignore

        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        tokens: List[OcrToken] = []

        for img in images:
            proc = _preprocess_for_ocr(img)
            result = ocr.ocr(_pil_to_numpy(proc), cls=True)

            # PaddleOCR format:
            # result = [ [ [points], (text, conf) ], ... ]
            for page in result:
                for item in page:
                    pts = item[0]
                    text, conf = item[1]
                    x1 = int(min(p[0] for p in pts))
                    y1 = int(min(p[1] for p in pts))
                    x2 = int(max(p[0] for p in pts))
                    y2 = int(max(p[1] for p in pts))
                    t = (text or "").strip()
                    if t:
                        tokens.append(OcrToken(text=t, conf=float(conf), bbox=(x1, y1, x2, y2)))

        return tokens

    except Exception:
        pass

    # Fallback EasyOCR
    try:
        import easyocr  # type: ignore

        reader = easyocr.Reader(["en"], gpu=False)
        tokens: List[OcrToken] = []

        for img in images:
            proc = _preprocess_for_ocr(img)
            # EasyOCR: [ (bbox, text, conf), ... ]
            result = reader.readtext(_pil_to_numpy(proc))
            for bbox, text, conf in result:
                x_coords = [int(p[0]) for p in bbox]
                y_coords = [int(p[1]) for p in bbox]
                x1, y1, x2, y2 = min(x_coords), min(y_coords), max(x_coords), max(y_coords)
                t = (text or "").strip()
                if t:
                    tokens.append(OcrToken(text=t, conf=float(conf), bbox=(x1, y1, x2, y2)))

        return tokens

    except Exception as e:
        raise RuntimeError("No OCR engine available. Install paddleocr or easyocr.") from e


def _pil_to_numpy(img: Image.Image):
    import numpy as np  # type: ignore

    return np.array(img)


def _normalize_ocr_text(s: str) -> str:
    """
    Normalize common OCR weirdness in engineering drawings.
    """
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_signals_from_text(text: str) -> Dict[str, Any]:
    """
    Extract the key signals we care about from OCR/text.
    This is intentionally conservative: only returns values when we have strong matches.
    """
    out: Dict[str, Any] = {
        "inverter_models": [],
        "inverter_vmax": None,
        "modules_per_string": None,
        "notes": "",
        "evidence": {},
    }

    t = _normalize_ocr_text(text)

    # Inverter models you actually have in your project:
    # SUN2000-100KTL-M2
    # SUN2000-150K-MG0
    inv_model_patterns = [
        r"\bSUN2000-\d{2,3}KTL-M2\b",
        r"\bSUN2000-150K-MG0\b",
        r"\bSUN2000-\d{2,3}K\b",  # loose fallback
    ]
    models = set()
    for pat in inv_model_patterns:
        for m in re.finditer(pat, t, flags=re.IGNORECASE):
            models.add(m.group(0).upper())
    if models:
        out["inverter_models"] = sorted(models)
        out["evidence"]["inverter_models"] = out["inverter_models"]

    # DC max voltage / Vmax patterns
    vmax_patterns = [
        r"(?:DC\s*MAX|DC\s*MAXIMUM|MAX\s*DC|VDC\s*MAX|V\s*MAX|VMAX)\s*[:=]?\s*(\d{3,4})\s*V",
        r"(\d{3,4})\s*V\s*(?:DC\s*MAX|VDC\s*MAX|MAX\s*DC)",
        r"\b1100\b\s*V\b",  # common for Huawei
    ]
    for pat in vmax_patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            val = m.group(1) if m.lastindex else "1100"
            out["inverter_vmax"] = float(val)
            out["evidence"]["inverter_vmax"] = f"match: {m.group(0)}"
            break

    # Modules per string (often written as "Modules/String", "Modules per string", "MPS")
    mps_patterns = [
        r"(?:MODULES\s*/\s*STRING|MODULES\s*PER\s*STRING|MOD\s*/\s*STR)\s*[:=]?\s*(\d{1,3})",
        r"\bMPS\b\s*[:=]?\s*(\d{1,3})",
    ]
    for pat in mps_patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            out["modules_per_string"] = int(m.group(1))
            out["evidence"]["modules_per_string"] = f"match: {m.group(0)}"
            break

    return out


def extract_sld_signals_from_pdf_bytes(pdf_bytes: bytes, max_pages: int = 2) -> Dict[str, Any]:
    """
    Unified extraction:
    1) Try selectable PDF text
    2) If weak/empty -> OCR (AI) on rendered pages
    3) Extract signals with patterns

    Returns a dict compatible with your review.py expectations.
    """
    # 1) Selectable text attempt
    text = _try_extract_selectable_text(pdf_bytes, max_pages=max_pages)

    # Heuristic: if we got enough text, use it; otherwise do OCR
    if len(text) < 80:
        images = _render_pdf_to_images(pdf_bytes, max_pages=max_pages, dpi=350)
        tokens = _ocr_images(images)

        joined = "\n".join(_normalize_ocr_text(t.text) for t in tokens)
        sig = _extract_signals_from_text(joined)
        sig["notes"] = "Extracted via OCR (image-based SLD)."
        return sig

    sig = _extract_signals_from_text(text)
    sig["notes"] = "Extracted via selectable PDF text."
    return sig

