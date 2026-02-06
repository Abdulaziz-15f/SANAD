"""
Pipeline 1+2+3: Document Extraction Engine.

Uses Google Gemini Vision for document extraction.
"""
from __future__ import annotations

import io
import os
import re
import json
import logging
import warnings
import time
import base64
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import fitz  # PyMuPDF
from PIL import Image

# Suppress noisy logs
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "1"
warnings.filterwarnings("ignore")
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("paddle").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _normalize_model(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _parse_filename_hints(filename: str | None) -> dict:
    """
    Heuristic hints from attachment filename: inverter/module model, counts, wattage.
    Non-blocking: returns empty hints on failure.
    """
    hints = {}
    if not filename:
        return hints
    name = filename.rsplit("/", 1)[-1]
    upper = name.upper()

    # Model-like tokens (alnum with dashes/underscores)
    model_match = re.findall(r"[A-Z0-9]{3,}(?:[-_][A-Z0-9]{2,}){0,3}", upper)
    if model_match:
        # Keep the longest token as generic model hint
        hints["model_hint"] = max(model_match, key=len)

    # Power hints like 615W / 100KTL / 150K / 150000
    w_match = re.search(r"(\d{3,4})\s*W[P]?", upper)
    if w_match:
        try:
            hints["pmax_hint_w"] = float(w_match.group(1))
        except Exception:
            pass

    kw_match = re.search(r"(\d{2,4})\s*K(?:W|TL)", upper)
    if kw_match:
        try:
            hints["inverter_kw_hint"] = float(kw_match.group(1))
        except Exception:
            pass

    count_match = re.search(r"(\d{1,3})[Xx](?:INV|INVERTER|PCS)", upper)
    if count_match:
        try:
            hints["count_hint"] = int(count_match.group(1))
        except Exception:
            pass

    return hints


def _extract_basic_text_fields(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Lightweight, deterministic text parsing from PDF (no AI/OCR).
    Tries to pull a few common SLD/datasheet fields via regex.
    """
    out: Dict[str, Any] = {}
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() or "" for page in doc)
        doc.close()
    except Exception:
        return out

    # Inverter DC max (e.g., "DC max voltage 1100 V")
    m = re.search(r"(dc\s*max|max\s*dc).*?(\d{3,4})\s*v", text, re.IGNORECASE)
    if m:
        out["inverter_dc_max_voltage_v"] = float(m.group(2))

    # Modules per string (e.g., "26 modules per string")
    m = re.search(r"(\d{1,3})\s+(modules?|panels?)\s+per\s+string", text, re.IGNORECASE)
    if m:
        out["modules_per_string"] = int(m.group(1))

    # Strings per MPPT (e.g., "2 strings per MPPT")
    m = re.search(r"(\d{1,3})\s+strings?\s+per\s+mppt", text, re.IGNORECASE)
    if m:
        out["strings_per_mppt"] = int(m.group(1))

    # Total strings (e.g., "Total strings: 124")
    m = re.search(r"total\s+strings[:\s]+(\d{1,4})", text, re.IGNORECASE)
    if m:
        out["total_strings"] = int(m.group(1))

    # PV module model (simplistic capture of alnum-dash tokens near "module")
    m = re.search(r"module[^A-Za-z0-9]{0,10}([A-Z0-9][A-Z0-9\-_/]{5,})", text, re.IGNORECASE)
    if m:
        out["pv_module_model"] = m.group(1).strip()

    # Inverter model (tokens near "inverter")
    m = re.search(r"inverter[^A-Za-z0-9]{0,10}([A-Z0-9][A-Z0-9\-_/]{5,})", text, re.IGNORECASE)
    if m:
        out["inverter_model"] = m.group(1).strip()

    return out


def _dxf_to_images(dxf_bytes: bytes, dpi: int = 300, max_pages: int = 3) -> List[bytes]:
    """
    Render DXF to PNG images for vision/OCR.
    Soft-dependency on ezdxf + matplotlib; returns [] on any failure.
    """
    try:
        import ezdxf
        from ezdxf.addons.drawing import matplotlib as ezdxf_matplotlib
        import matplotlib.pyplot as plt
    except Exception:
        return []

    images: List[bytes] = []
    try:
        doc = ezdxf.readzip(io.BytesIO(dxf_bytes)) if dxf_bytes[:2] == b"PK" else ezdxf.read(io.BytesIO(dxf_bytes))
        msp = doc.modelspace()
        fig = plt.figure()
        ax = fig.add_axes([0, 0, 1, 1])
        ctx = ezdxf_matplotlib.MatplotlibBackend(ax)
        ezdxf.addons.drawing.RenderContext(doc).set_current_layout(msp)
        ezdxf.addons.drawing.Drawing.render_layout(msp, ctx)
        # adjust size for DPI
        fig.set_dpi(dpi)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, transparent=True)
        buf.seek(0)
        images.append(buf.getvalue())
        plt.close(fig)
    except Exception:
        return []

    return images[:max_pages]


# -------------------------------------------------------------------
# Extraction Result Models
# -------------------------------------------------------------------
@dataclass
class InverterInfo:
    """Individual inverter information."""
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    capacity_kw: Optional[float] = None
    count: int = 1


@dataclass
class SLDExtraction:
    """Data extracted from Single Line Diagram."""
    system_capacity_kw: Optional[float] = None
    inverter_model: Optional[str] = None
    inverter_manufacturer: Optional[str] = None
    inverter_dc_max_voltage_v: Optional[float] = None
    inverter_count: Optional[int] = None
    inverter_capacity_kw: Optional[float] = None
    inverters: List[InverterInfo] = field(default_factory=list)
    modules_per_string: Optional[int] = None
    strings_per_mppt: Optional[int] = None
    total_strings: Optional[int] = None
    total_modules: Optional[int] = None
    dc_cable_size_mm2: Optional[float] = None
    ac_cable_size_mm2: Optional[float] = None
    dc_fuse_rating_a: Optional[float] = None
    ac_breaker_rating_a: Optional[float] = None
    pv_module_model: Optional[str] = None
    pv_module_power_w: Optional[float] = None
    confidence: float = 0.0
    source: str = "unknown"
    raw_text: str = ""
    notes: str = ""


@dataclass
class PVModuleExtraction:
    """Data extracted from PV module datasheet."""
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    pmax_w: Optional[float] = None
    voc_v: Optional[float] = None
    isc_a: Optional[float] = None
    vmp_v: Optional[float] = None
    imp_a: Optional[float] = None
    temp_coeff_voc: Optional[float] = None
    temp_coeff_pmax: Optional[float] = None
    max_system_voltage_v: Optional[float] = None
    confidence: float = 0.0
    source: str = "unknown"
    notes: str = ""


@dataclass
class InverterExtraction:
    """Data extracted from inverter datasheet."""
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    dc_max_voltage_v: Optional[float] = None
    mppt_voltage_min_v: Optional[float] = None
    mppt_voltage_max_v: Optional[float] = None
    mppt_count: Optional[int] = None
    strings_per_mppt: Optional[int] = None
    ac_rated_power_kw: Optional[float] = None
    max_efficiency: Optional[float] = None
    confidence: float = 0.0
    source: str = "unknown"
    notes: str = ""


@dataclass
class CableExtraction:
    """Data extracted from cable sizing calculations."""
    dc_cable_size_mm2: Optional[float] = None
    ac_cable_size_mm2: Optional[float] = None
    dc_voltage_drop_percent: Optional[float] = None
    ac_voltage_drop_percent: Optional[float] = None
    total_voltage_drop_percent: Optional[float] = None
    confidence: float = 0.0
    notes: str = ""


@dataclass
class MergedExtraction:
    """Combined extraction from all documents."""
    # System
    system_capacity_kw: Optional[float] = None
    location: Optional[str] = None
    tmin_c: Optional[float] = None
    tmax_c: Optional[float] = None
    
    # PV Module
    module_model: Optional[str] = None
    module_pmax_w: Optional[float] = None
    module_voc_v: Optional[float] = None
    module_isc_a: Optional[float] = None
    module_vmp_v: Optional[float] = None
    module_imp_a: Optional[float] = None
    temp_coeff_voc: Optional[float] = None
    
    # Inverter
    inverter_model: Optional[str] = None
    inverter_dc_max_voltage_v: Optional[float] = None
    inverter_mppt_min_v: Optional[float] = None
    inverter_mppt_max_v: Optional[float] = None
    inverter_ac_power_kw: Optional[float] = None
    inverter_count: Optional[int] = None
    mppt_count: Optional[int] = None
    
    # String Configuration
    modules_per_string: Optional[int] = None
    strings_per_mppt: Optional[int] = None
    total_strings: Optional[int] = None
    # Environment
    current_wind_speed: Optional[float] = None  # km/h
    max_wind_speed: Optional[float] = None      # km/h
    
    # Cables
    dc_cable_size_mm2: Optional[float] = None
    ac_cable_size_mm2: Optional[float] = None
    dc_voltage_drop_percent: Optional[float] = None
    ac_voltage_drop_percent: Optional[float] = None
    
    # Metadata
    confidence: float = 0.0
    notes: str = ""


# -------------------------------------------------------------------
# Gemini Vision Extractor
# -------------------------------------------------------------------
class GeminiVisionExtractor:
    """Uses Google Gemini for document extraction."""
    
    def __init__(self, model: str | None = None):
        """
        Model priority (fallback if a model fails at runtime):
        1) explicit `model` argument
        2) env `GEMINI_MODEL`
        3) gemini-2.5-pro (robust, widely available)
        4) gemini-1.5-pro (stable legacy)
        5) gemini-1.5-flash (budget fallback)
        """
        env_model = os.getenv("GEMINI_MODEL")
        preferred = [model, env_model, "gemini-2.5-pro", "gemini-1.5-pro", "gemini-1.5-flash"]
        self.model_candidates = [m for m in preferred if m]
        self.model = self.model_candidates[0]
        self._client = None
        logger.info(f"GeminiVisionExtractor initialized with model priority: {self.model_candidates}")
    
    def _get_client(self):
        if self._client is None:
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("No GOOGLE_API_KEY found in environment")
            
            from google import genai
            self._client = genai.Client(api_key=api_key)
        return self._client
    
    def _pdf_to_images(self, pdf_bytes: bytes, dpi: int = 200, max_pages: int = 3) -> List[bytes]:
        """Convert PDF to PNG images."""
        images = []
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            
            for page_idx in range(min(len(doc), max_pages)):
                page = doc.load_page(page_idx)
                pix = page.get_pixmap(matrix=matrix)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Resize if too large (Gemini limit)
                max_dim = 4096
                if img.width > max_dim or img.height > max_dim:
                    scale = min(max_dim / img.width, max_dim / img.height)
                    new_size = (int(img.width * scale), int(img.height * scale))
                    img = img.resize(new_size, Image.LANCZOS)
                
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                images.append(buf.getvalue())
                
                logger.info(f"Page {page_idx + 1}: {len(buf.getvalue()) / 1024:.1f} KB")
            
            doc.close()
        except Exception as e:
            logger.error(f"PDF to images failed: {e}")
        
        return images

    def _render_images(self, file_bytes: bytes, file_name: str | None, dpi: int, max_pages: int) -> List[bytes]:
        """
        Render bytes to images, supporting PDF (default) and optional DXF.
        If DXF conversion fails or yields no pages, fall back to PDF rendering.
        """
        # quick byte sniff for DXF: ASCII "0\nSECTION" near start
        is_dxf_bytes = (
            file_bytes[:12].upper().startswith(b"0\nSECTION")
            or b"ACAD" in file_bytes[:64]
            or b"AUTOCAD BINARY DXF" in file_bytes[:64].upper()
            or file_bytes[:6].upper().startswith(b"AC10")
        )
        if (file_name and file_name.lower().endswith(".dxf")) or is_dxf_bytes:
            imgs = _dxf_to_images(file_bytes, dpi=dpi, max_pages=max_pages)
            if imgs:
                return imgs
            logger.warning("DXF render produced no images; attempting PDF fallback")
            # try PDF fallback in case the file is mislabeled or convertible by fitz
            pdf_imgs = self._pdf_to_images(file_bytes, dpi=dpi, max_pages=max_pages)
            if pdf_imgs:
                logger.info("PDF fallback succeeded for DXF input")
                return pdf_imgs
            return []
        # empty or invalid stream guard
        if not file_bytes:
            logger.error("Empty file bytes provided; cannot render images")
            return []
        # primary PDF attempt
        pdf_imgs = self._pdf_to_images(file_bytes, dpi=dpi, max_pages=max_pages)
        if pdf_imgs:
            return pdf_imgs
        # fallback: try DXF in case the file was mislabeled
        dxf_imgs = _dxf_to_images(file_bytes, dpi=dpi, max_pages=max_pages)
        if dxf_imgs:
            logger.info("PDF render failed; DXF fallback succeeded")
            return dxf_imgs
        return []
    
    def _parse_json(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        if not text:
            return {}
        
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from: {text[:200]}")
            return {}
    
    def _to_int(self, value) -> Optional[int]:
        """Convert value to integer, handling floats and None."""
        if value is None:
            return None
        try:
            return int(round(float(value)))
        except (ValueError, TypeError):
            return None
    
    def _call_gemini(self, prompt: str, images: List[bytes] = None) -> str:
        """Call Gemini API with optional images, retries, and model fallback."""
        from google.genai import types

        contents = []
        if images:
            for img_bytes in images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
        contents.append(prompt)

        max_retries = 3

        for model_name in self.model_candidates:
            self.model = model_name
            client = self._get_client()

            for attempt in range(max_retries):
                try:
                    logger.info(f"Calling Gemini model: {self.model} (attempt {attempt + 1})")
                    response = client.models.generate_content(
                        model=self.model,
                        contents=contents,
                    )
                    result = response.text
                    logger.info(f"Gemini response length: {len(result)} chars")
                    return result
                    
                except Exception as e:
                    error_str = str(e)
                    
                    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                        wait_time = 35
                        if attempt < max_retries - 1:
                            logger.warning(f"Rate limited. Waiting {wait_time}s before retry (model={self.model})...")
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"Rate limit exceeded after {max_retries} attempts (model={self.model})")
                    else:
                        logger.error(f"Gemini API error (model={self.model}): {e}")
                # try next model after retries fail
            logger.info(f"Falling back to next model after failures: {self.model}")

        return ""
        
        return ""
    
    def extract_sld(self, pdf_bytes: bytes, file_name: str | None = None) -> SLDExtraction:
        """Extract data from SLD using Gemini."""
        result = SLDExtraction()
        
        try:
            hints = _parse_filename_hints(file_name)
            # Higher DPI and more pages to maximize detail for OCR/vision extraction (slower but richer).
            # Prev: dpi=320, max_pages=4
            images = self._render_images(pdf_bytes, file_name, dpi=360, max_pages=5)
            if not images:
                result.notes = "Failed to render PDF"
                return result
            
            prompt = f"""You are an expert solar PV engineer analyzing a Single Line Diagram (SLD).

ATTACHMENT FILENAME (may hint the component model): {file_name or "N/A"}
MODEL HINT (parsed): {hints.get('model_hint', 'N/A')}
POWER HINTS: Pmax={hints.get('pmax_hint_w', 'N/A')} W, Inverter kW={hints.get('inverter_kw_hint', 'N/A')}
COUNT HINT: {hints.get('count_hint', 'N/A')}

TASK: Extract ALL technical specifications from this engineering drawing.
Be exhaustive and take your time; prefer completeness over speed. Use any text, symbols, or tables you can infer.

Look carefully for:
1. SYSTEM CAPACITY - Total kW or MW (e.g., "1.5 MW", "500 kW")
2. INVERTER MODEL - Exact model number (e.g., "SUN2000-100KTL-M2")
3. INVERTER COUNT - How many inverters total (INTEGER)
4. PV MODULE MODEL - Panel model (e.g., "JAM72S30-545/MR")
5. MODULE POWER - Watts per panel (e.g., 545W)
6. MODULES PER STRING - Number of panels in series per string (INTEGER, usually 10-30)
7. STRINGS PER MPPT - How many strings per MPPT input (INTEGER)
8. TOTAL STRINGS - Total number of strings in system (MUST BE INTEGER)
9. TOTAL MODULES - Total number of PV modules (INTEGER)
10. CABLE SIZES - DC and AC cable sizes in mm²

IMPORTANT RULES:
- All counts (strings, modules, inverters) MUST be INTEGERS, not decimals
- If you calculate total_strings, ROUND to nearest integer
- Look for text near inverter symbols
- Check tables and schedules
- If a value is unclear, estimate and note it in "notes"

Return ONLY valid JSON:
{{
    "system_capacity_kw": <number or null>,
    "inverter_model": "<exact model or null>",
    "inverter_manufacturer": "<company or null>",
    "inverter_count": <INTEGER or null>,
    "inverters": [{{"model": "<model>", "count": <int or null>, "ac_power_kw": <number or null>}}],
    "pv_module_model": "<exact model or null>",
    "pv_module_power_w": <number or null>,
    "modules": [{{"model": "<model>", "pmax_w": <number or null>, "count": <int or null>}}],
    "modules_per_string": <INTEGER or null>,
    "strings_per_mppt": <INTEGER or null>,
    "total_strings": <INTEGER or null>,
    "total_modules": <INTEGER or null>,
    "dc_cable_size_mm2": <number or null>,
    "ac_cable_size_mm2": <number or null>,
    "confidence": <0.0 to 1.0>,
    "notes": "<observations>"
}}"""
            
            response = self._call_gemini(prompt, images)
            data = self._parse_json(response)
            
            if not data:
                result.notes = "Gemini returned no parseable data"
                return result
            
            result.system_capacity_kw = data.get("system_capacity_kw")
            result.inverter_model = data.get("inverter_model")
            result.inverter_manufacturer = data.get("inverter_manufacturer")
            result.inverter_count = self._to_int(data.get("inverter_count"))
            result.inverter_capacity_kw = data.get("inverter_capacity_kw")
            result.pv_module_model = data.get("pv_module_model")
            result.pv_module_power_w = data.get("pv_module_power_w")
            result.modules_per_string = self._to_int(data.get("modules_per_string"))
            result.strings_per_mppt = self._to_int(data.get("strings_per_mppt"))
            result.total_strings = self._to_int(data.get("total_strings"))
            result.total_modules = self._to_int(data.get("total_modules"))
            result.dc_cable_size_mm2 = data.get("dc_cable_size_mm2")
            result.ac_cable_size_mm2 = data.get("ac_cable_size_mm2")
            result.confidence = data.get("confidence", 0.5)
            result.notes = data.get("notes", "")

            # Handle multi-inverter/module arrays
            inv_list = data.get("inverters") or []
            if inv_list:
                best = max(inv_list, key=lambda x: (x.get("count") or 0, x.get("ac_power_kw") or 0))
                result.inverter_model = best.get("model") or result.inverter_model
                result.inverter_capacity_kw = best.get("ac_power_kw") or result.inverter_capacity_kw
                result.inverter_count = self._to_int(best.get("count")) or result.inverter_count

            mod_list = data.get("modules") or []
            if mod_list:
                bestm = max(mod_list, key=lambda x: x.get("count") or 0)
                result.pv_module_model = bestm.get("model") or result.pv_module_model
                result.pv_module_power_w = bestm.get("pmax_w") or result.pv_module_power_w
                # derive total_modules if count present
                if not result.total_modules and bestm.get("count"):
                    result.total_modules = self._to_int(bestm.get("count"))
            result.source = "gemini_vision"
            
            logger.info(f"SLD extraction complete: {result.inverter_model}, {result.modules_per_string} MPS")
            
        except Exception as e:
            result.notes = f"Extraction error: {str(e)}"
            result.confidence = 0.0
            logger.error(f"SLD extraction failed: {e}")
        
        return result
    
    def extract_pv_datasheet(self, pdf_bytes: bytes, file_name: str | None = None) -> PVModuleExtraction:
        """Extract data from PV module datasheet using Gemini."""
        result = PVModuleExtraction()
        
        try:
            hints = _parse_filename_hints(file_name)
            # Slightly higher DPI and page span for richer OCR on datasheets.
            # Prev: dpi=280, max_pages=3
            images = self._render_images(pdf_bytes, file_name, dpi=320, max_pages=4)
            if not images:
                result.notes = "Failed to render PDF"
                return result
            
            prompt = f"""You are an expert solar PV engineer analyzing a PV module datasheet.

ATTACHMENT FILENAME (may contain the module model): {file_name or "N/A"}
MODEL HINT (parsed): {hints.get('model_hint', 'N/A')}
Pmax HINT: {hints.get('pmax_hint_w', 'N/A')} W

TASK: Extract the electrical specifications at STC (Standard Test Conditions: 1000W/m², 25°C, AM1.5).
Take your time and capture every numeric spec you can; prefer completeness even if uncertain (note uncertainties).

Look for these values in the "Electrical Characteristics" or "Electrical Data" table:

1. MANUFACTURER - Company name (JA Solar, LONGi, Trina, Canadian Solar)
2. MODEL - Full model number (e.g., "JAM72S30-545/MR", "LR5-66HPH-535M")
3. Pmax - Maximum Power in Watts (e.g., 545W, 550W)
4. Voc - Open Circuit Voltage in Volts (typically 40-55V)
5. Isc - Short Circuit Current in Amps (typically 10-18A)
6. Vmp - Voltage at Maximum Power Point in Volts (typically 35-45V)
7. Imp - Current at Maximum Power Point in Amps (typically 10-15A)
8. Temperature Coefficient of Voc (βVoc) - NEGATIVE, in %/°C (e.g., -0.29%/°C)
9. Temperature Coefficient of Pmax (γPmax) - NEGATIVE, in %/°C (e.g., -0.35%/°C)
10. Maximum System Voltage - Usually 1000V or 1500V DC

CRITICAL:
- Return temp coefficients as numbers like -0.29 (not -0.0029)
- Voc MUST be greater than Vmp
- Isc MUST be greater than Imp

Return ONLY valid JSON:
{{
    "manufacturer": "<company name or null>",
    "model": "<full model number or null>",
    "modules": [{{"model": "<model>", "pmax_w": <number or null>, "count": <int or null>}}],
    "pmax_w": <Watts as number>,
    "voc_v": <Volts as number>,
    "isc_a": <Amps as number>,
    "vmp_v": <Volts as number>,
    "imp_a": <Amps as number>,
    "temp_coeff_voc": <number like -0.29>,
    "temp_coeff_pmax": <number like -0.35>,
    "max_system_voltage_v": <Volts as number>,
    "confidence": <0.0 to 1.0>,
    "notes": "<observations>"
}}"""
            
            response = self._call_gemini(prompt, images)
            data = self._parse_json(response)
            
            if not data:
                result.notes = "Gemini returned no parseable data"
                return result
            
            result.manufacturer = data.get("manufacturer")
            result.model = data.get("model")
            result.pmax_w = data.get("pmax_w")
            result.voc_v = data.get("voc_v")
            result.isc_a = data.get("isc_a")
            result.vmp_v = data.get("vmp_v")
            result.imp_a = data.get("imp_a")
            result.temp_coeff_voc = data.get("temp_coeff_voc")
            result.temp_coeff_pmax = data.get("temp_coeff_pmax")
            result.max_system_voltage_v = data.get("max_system_voltage_v")
            result.confidence = data.get("confidence", 0.5)
            result.notes = data.get("notes", "")
            result.source = "gemini_vision"
            # Multi-module array support
            mod_list = data.get("modules") or []
            if mod_list:
                best = max(mod_list, key=lambda x: x.get("count") or 0)
                result.model = best.get("model") or result.model
                result.pmax_w = best.get("pmax_w") or result.pmax_w

            # Validate: Voc should be > Vmp
            if result.voc_v and result.vmp_v and result.voc_v < result.vmp_v:
                result.voc_v, result.vmp_v = result.vmp_v, result.voc_v
                result.notes += " [Swapped Voc/Vmp]"
            
            # Validate: Isc should be > Imp
            if result.isc_a and result.imp_a and result.isc_a < result.imp_a:
                result.isc_a, result.imp_a = result.imp_a, result.isc_a
                result.notes += " [Swapped Isc/Imp]"
            
            logger.info(f"PV extraction complete: {result.model}, Voc={result.voc_v}V")
            
        except Exception as e:
            result.notes = f"Extraction error: {str(e)}"
            logger.error(f"PV extraction failed: {e}")
        
        return result
    
    def extract_inverter_datasheet(self, pdf_bytes: bytes, file_name: str | None = None) -> InverterExtraction:
        """Extract data from inverter datasheet using Gemini."""
        result = InverterExtraction()
        
        try:
            hints = _parse_filename_hints(file_name)
            # Higher DPI and more pages to capture scattered inverter specs.
            # Prev: dpi=280, max_pages=3
            images = self._render_images(pdf_bytes, file_name, dpi=320, max_pages=4)
            if not images:
                result.notes = "Failed to render PDF"
                return result
            
            prompt = f"""You are an expert solar PV engineer analyzing an inverter datasheet.

ATTACHMENT FILENAME (may contain the inverter model): {file_name or "N/A"}
MODEL HINT (parsed): {hints.get('model_hint', 'N/A')}
AC POWER HINT (kW): {hints.get('inverter_kw_hint', 'N/A')}
COUNT HINT: {hints.get('count_hint', 'N/A')}

TASK: Extract the DC input and AC output specifications.
Be thorough and capture optional specs even if they appear in footnotes or side tables.

Look for these values:

1. MANUFACTURER - Company name (Huawei, Sungrow, SMA, Growatt)
2. MODEL - Full model number (e.g., "SUN2000-100KTL-M2", "SG110CX")
3. Maximum DC Input Voltage - Usually 1100V or 1500V
4. MPPT Voltage Range - Min and Max operating voltage (e.g., "200V - 1000V")
5. Number of MPP Trackers - How many MPPT inputs (e.g., 10, 12)
6. Max Strings per MPPT - Maximum strings per MPPT input (e.g., 2, 4)
7. AC Rated Output Power - In kW (e.g., 100kW, 110kW)
8. Maximum Efficiency - Peak efficiency percentage (e.g., 98.6%)

Return ONLY valid JSON:
{{
    "manufacturer": "<company name or null>",
    "model": "<full model number or null>",
    "inverters": [{{"model": "<model>", "count": <int or null>, "ac_power_kw": <number or null>}}],
    "dc_max_voltage_v": <Volts as number>,
    "mppt_voltage_min_v": <Volts as number>,
    "mppt_voltage_max_v": <Volts as number>,
    "mppt_count": <INTEGER number>,
    "strings_per_mppt": <INTEGER number>,
    "ac_rated_power_kw": <kW as number>,
    "max_efficiency": <percent as number like 98.6>,
    "confidence": <0.0 to 1.0>,
    "notes": "<observations>"
}}"""
            
            response = self._call_gemini(prompt, images)
            data = self._parse_json(response)
            
            if not data:
                result.notes = "Gemini returned no parseable data"
                return result
            
            result.manufacturer = data.get("manufacturer")
            result.model = data.get("model")
            result.dc_max_voltage_v = data.get("dc_max_voltage_v")
            result.mppt_voltage_min_v = data.get("mppt_voltage_min_v")
            result.mppt_voltage_max_v = data.get("mppt_voltage_max_v")
            result.mppt_count = self._to_int(data.get("mppt_count"))
            result.strings_per_mppt = self._to_int(data.get("strings_per_mppt"))
            result.ac_rated_power_kw = data.get("ac_rated_power_kw")
            result.max_efficiency = data.get("max_efficiency")
            result.confidence = data.get("confidence", 0.5)
            result.notes = data.get("notes", "")
            result.source = "gemini_vision"
            # Multi-inverter array support
            inv_list = data.get("inverters") or []
            if inv_list:
                best = max(inv_list, key=lambda x: (x.get("count") or 0, x.get("ac_power_kw") or 0))
                result.model = best.get("model") or result.model
                result.ac_rated_power_kw = best.get("ac_power_kw") or result.ac_rated_power_kw
                result.count = self._to_int(best.get("count")) or result.count

            logger.info(f"Inverter extraction complete: {result.model}, DC Max={result.dc_max_voltage_v}V")
            
        except Exception as e:
            result.notes = f"Extraction error: {str(e)}"
            logger.error(f"Inverter extraction failed: {e}")
        
        return result


# -------------------------------------------------------------------
# Cable Extractor (Excel)
# -------------------------------------------------------------------
class CableExtractor:
    """Extracts data from cable sizing Excel files."""
    
    def extract(self, df) -> CableExtraction:
        result = CableExtraction()
        
        if df is None or (hasattr(df, 'empty') and df.empty):
            result.notes = "No DataFrame provided"
            return result
        
        try:
            df.columns = [str(c) for c in df.columns]
            
            for col in df.columns:
                col_lower = col.lower()
                # DC patterns
                if ("dc" in col_lower and "voltage" in col_lower and "drop" in col_lower) or re.search(r"(vd|Δv).*dc", col_lower):
                    vals = df[col].dropna()
                    if len(vals) > 0:
                        result.dc_voltage_drop_percent = float(vals.max())
                
                # AC patterns
                if ("ac" in col_lower and "voltage" in col_lower and "drop" in col_lower) or re.search(r"(vd|Δv).*ac", col_lower):
                    vals = df[col].dropna()
                    if len(vals) > 0:
                        result.ac_voltage_drop_percent = float(vals.max())
                
                # Generic percentage column
                if "vd%" in col_lower or "voltage drop(%)" in col_lower or "voltage drop %" in col_lower:
                    vals = df[col].dropna()
                    if len(vals) > 0:
                        max_vd = float(vals.max())
                        if result.ac_voltage_drop_percent is None and result.dc_voltage_drop_percent is None:
                            result.ac_voltage_drop_percent = max_vd
            
            if result.dc_voltage_drop_percent and result.ac_voltage_drop_percent:
                result.total_voltage_drop_percent = (
                    result.dc_voltage_drop_percent + result.ac_voltage_drop_percent
                )
            elif result.ac_voltage_drop_percent:
                result.total_voltage_drop_percent = result.ac_voltage_drop_percent
            elif result.dc_voltage_drop_percent:
                result.total_voltage_drop_percent = result.dc_voltage_drop_percent
            
            result.confidence = 0.8 if (result.ac_voltage_drop_percent or result.dc_voltage_drop_percent) else 0.3
            result.notes = "Extracted from Excel"
            
        except Exception as e:
            result.notes = f"Extraction error: {str(e)}"
            logger.error(f"Cable extraction failed: {e}")
        
        return result


# -------------------------------------------------------------------
# OCR Extractor (Fallback)
# -------------------------------------------------------------------
class OCRExtractor:
    """Extract text using PaddleOCR (fallback)."""
    
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self._ocr = None
    
    def _get_ocr(self):
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
                self._ocr = PaddleOCR(use_angle_cls=True, lang="en")
            except Exception as e:
                logger.warning(f"PaddleOCR init failed: {e}")
        return self._ocr
    
    def _pdf_to_images(self, pdf_bytes: bytes, dpi: int = 200) -> List[Image.Image]:
        images = []
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            
            for page_idx in range(min(len(doc), 3)):
                page = doc.load_page(page_idx)
                pix = page.get_pixmap(matrix=matrix)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)
            
            doc.close()
        except Exception as e:
            logger.error(f"PDF to images failed: {e}")
        
        return images
    
    def extract_text(self, pdf_bytes: bytes) -> str:
        ocr = self._get_ocr()
        if ocr is None:
            return ""
        
        images = self._pdf_to_images(pdf_bytes, dpi=200)
        if not images:
            return ""
        
        all_text = []
        
        def ocr_single_image(img: Image.Image) -> str:
            try:
                import numpy as np
                arr = np.array(img.convert("RGB"))
                result = ocr.ocr(arr)
                if result and result[0]:
                    return " ".join([line[1][0] for line in result[0] if line[1]])
            except Exception as e:
                logger.warning(f"OCR failed: {e}")
            return ""
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            for img in images:
                try:
                    future = executor.submit(ocr_single_image, img)
                    text = future.result(timeout=self.timeout)
                    if text:
                        all_text.append(text)
                except FuturesTimeoutError:
                    logger.warning("OCR timeout")
                except Exception as e:
                    logger.warning(f"OCR error: {e}")
        
        return "\n".join(all_text)


# -------------------------------------------------------------------
# AI Merge Engine
# -------------------------------------------------------------------
class AIMergeEngine:
    """Merges OCR and Vision results using AI."""
    
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                from google import genai
                self._client = genai.Client(api_key=api_key)
        return self._client
    
    def _call_ai(self, prompt: str) -> str:
        client = self._get_client()
        if not client:
            return ""
        
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            logger.error(f"AI merge error: {e}")
            return ""
    
    def _parse_json(self, text: str) -> dict:
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
        try:
            return json.loads(text)
        except:
            return {}
    
    def merge_pv_extractions(self, ocr_text: str, vision_result: PVModuleExtraction) -> PVModuleExtraction:
        if not ocr_text or vision_result.confidence > 0.8:
            return vision_result
        
        prompt = f"""I have two sources of data from a PV module datasheet:

SOURCE 1 (OCR Text):
{ocr_text[:2000]}

SOURCE 2 (Vision Extraction):
- Model: {vision_result.model}
- Pmax: {vision_result.pmax_w} W
- Voc: {vision_result.voc_v} V
- Isc: {vision_result.isc_a} A
- Vmp: {vision_result.vmp_v} V
- Imp: {vision_result.imp_a} A
- Temp Coeff Voc: {vision_result.temp_coeff_voc}

Merge these sources. Return JSON:
{{
    "model": "<best model name>",
    "pmax_w": <number>,
    "voc_v": <number>,
    "isc_a": <number>,
    "vmp_v": <number>,
    "imp_a": <number>,
    "temp_coeff_voc": <number as decimal>
}}"""
        
        response = self._call_ai(prompt)
        data = self._parse_json(response)
        
        if data:
            vision_result.model = data.get("model") or vision_result.model
            vision_result.pmax_w = data.get("pmax_w") or vision_result.pmax_w
            vision_result.voc_v = data.get("voc_v") or vision_result.voc_v
            vision_result.isc_a = data.get("isc_a") or vision_result.isc_a
            vision_result.vmp_v = data.get("vmp_v") or vision_result.vmp_v
            vision_result.imp_a = data.get("imp_a") or vision_result.imp_a
            vision_result.temp_coeff_voc = data.get("temp_coeff_voc") or vision_result.temp_coeff_voc
            vision_result.source = "merged_ocr_vision"
        
        return vision_result


# -------------------------------------------------------------------
# Validation Function
# -------------------------------------------------------------------
def validate_extraction(merged: MergedExtraction) -> MergedExtraction:
    """Validate and fix common extraction errors."""
    
    if merged.temp_coeff_voc is not None:
        tc = merged.temp_coeff_voc
        
        if tc > 0:
            tc = -abs(tc)
        
        if abs(tc) > 1:
            tc = tc / 100.0
        
        merged.temp_coeff_voc = tc
    
    return merged


# -------------------------------------------------------------------
# Final Merge Function
# -------------------------------------------------------------------
def merge_extractions(
    sld: SLDExtraction,
    pv_module: PVModuleExtraction,
    inverter: InverterExtraction,
    cables: CableExtraction,
    location: str,
    tmin: float,
    tmax: float,
    current_wind: float = None,
    max_wind: float = None,
) -> MergedExtraction:
    """Merge all extractions into a single unified structure.

    Notes:
    - Be defensive: different extractors use slightly different field names.
    - Prefer SLD values, then vision/OCR module/inverter, then cable/BoM fallbacks.
    """
    merged = MergedExtraction()

    # Basic metadata
    merged.location = location or getattr(sld, "location", None)
    merged.tmin_c = tmin if tmin is not None else getattr(sld, "tmin_c", None)
    merged.tmax_c = tmax if tmax is not None else getattr(sld, "tmax_c", None)
    merged.current_wind_speed = current_wind
    merged.max_wind_speed = max_wind

    # --- PV module ---
    # model / electricals
    merged.module_model = getattr(pv_module, "model", None) or getattr(sld, "pv_module_model", None)
    merged.module_pmax_w = getattr(pv_module, "pmax_w", None) or getattr(pv_module, "module_pmax_w", None) or getattr(sld, "pv_module_power_w", None)
    merged.module_voc_v = getattr(pv_module, "voc_v", None) or getattr(pv_module, "module_voc_v", None)
    merged.module_isc_a = getattr(pv_module, "isc_a", None) or getattr(pv_module, "module_isc_a", None)
    merged.module_vmp_v = getattr(pv_module, "vmp_v", None) or getattr(pv_module, "module_vmp_v", None)
    merged.module_imp_a = getattr(pv_module, "imp_a", None) or getattr(pv_module, "module_imp_a", None)

    # temperature coefficient: support both naming conventions
    temp_coeff = None
    for name in ("temp_coeff_voc", "temp_coeff_voc_percent_c", "temp_coeff"):
        temp_coeff = getattr(pv_module, name, None)
        if temp_coeff is not None:
            break
    # normalize percent -> decimal if looks like percent (e.g. -0.29)
    if temp_coeff is not None:
        try:
            tc = float(temp_coeff)
            if abs(tc) > 0.05:  # likely given as percent like -0.29
                tc = tc / 100.0
            merged.temp_coeff_voc = tc
        except Exception:
            merged.temp_coeff_voc = None
    else:
        merged.temp_coeff_voc = getattr(sld, "temp_coeff_voc", None)

    # --- Inverter ---
    merged.inverter_model = getattr(inverter, "model", None) or getattr(sld, "inverter_model", None)
    # DC max voltage (support various names)
    merged.inverter_dc_max_voltage_v = (
        getattr(inverter, "dc_max_voltage_v", None)
        or getattr(inverter, "inverter_dc_max_v", None)
        or getattr(sld, "inverter_vmax", None)
    )
    # MPPT min/max (support variants)
    merged.inverter_mppt_min_v = (
        getattr(inverter, "mppt_voltage_min_v", None)
        or getattr(inverter, "dc_mppt_voltage_min_v", None)
        or getattr(inverter, "mppt_min_v", None)
    )
    merged.inverter_mppt_max_v = (
        getattr(inverter, "mppt_voltage_max_v", None)
        or getattr(inverter, "dc_mppt_voltage_max_v", None)
        or getattr(inverter, "mppt_max_v", None)
    )
    merged.inverter_ac_power_kw = getattr(inverter, "ac_rated_power_kw", None) or getattr(inverter, "ac_power_kw", None) or getattr(sld, "inverter_capacity_kw", None)
    merged.inverter_count = getattr(inverter, "count", None) or getattr(sld, "inverter_count", None)
    merged.mppt_count = getattr(inverter, "mppt_count", None) or getattr(sld, "mppt_count", None) or getattr(sld, "inverter_count", None)

    # --- String configuration (prefer SLD) ---
    merged.modules_per_string = getattr(sld, "modules_per_string", None) or getattr(pv_module, "modules_per_string", None) or getattr(pv_module, "mps", None)
    merged.strings_per_mppt = getattr(sld, "strings_per_mppt", None) or getattr(inverter, "strings_per_mppt", None)
    merged.total_strings = getattr(sld, "total_strings", None)

    # --- Cables / voltage drop ---
    merged.dc_cable_size_mm2 = getattr(cables, "dc_cable_size_mm2", None) or getattr(sld, "dc_cable_size_mm2", None)
    merged.ac_cable_size_mm2 = getattr(cables, "ac_cable_size_mm2", None) or getattr(sld, "ac_cable_size_mm2", None)
    merged.dc_voltage_drop_percent = getattr(cables, "dc_voltage_drop_percent", None) or getattr(cables, "dc_voltage_drop_pct", None)
    merged.ac_voltage_drop_percent = getattr(cables, "ac_voltage_drop_percent", None) or getattr(cables, "ac_voltage_drop_pct", None)

    # --- System capacity fallback ---
    # prefer SLD system capacity, else try PV/module * total modules, else inverter AC power
    merged.system_capacity_kw = getattr(sld, "system_capacity_kw", None)
    if merged.system_capacity_kw is None:
        if merged.module_pmax_w and getattr(merged, "total_strings", None):
            try:
                merged.system_capacity_kw = (merged.module_pmax_w * (getattr(sld, "total_modules", merged.total_strings * (merged.modules_per_string or 0)))) / 1000.0
            except Exception:
                merged.system_capacity_kw = None
    if merged.system_capacity_kw is None:
        merged.system_capacity_kw = merged.inverter_ac_power_kw

    # confidence: average of source confidences where available
    confs = []
    for src in (getattr(sld, "confidence", None), getattr(pv_module, "confidence", None), getattr(inverter, "confidence", None), getattr(cables, "confidence", None)):
        if src is not None:
            try:
                confs.append(float(src))
            except Exception:
                pass
    merged.confidence = sum(confs) / len(confs) if confs else 0.0

    # notes: combine short summaries if present
    notes = []
    for obj in (sld, pv_module, inverter, cables):
        if not obj:
            continue
        n = getattr(obj, "notes", None) or getattr(obj, "notes", "")
        if n:
            notes.append(n)
    merged.notes = " | ".join(notes) if notes else ""

    # Final validation fixes (common issues)
    # ensure temp coeff decimal form
    if merged.temp_coeff_voc is not None and abs(merged.temp_coeff_voc) > 0.05:
        merged.temp_coeff_voc = merged.temp_coeff_voc / 100.0

    return merged


# -------------------------------------------------------------------
# Main Pipeline: Run Full Extraction
# -------------------------------------------------------------------
def run_full_extraction(
    pdf_bytes: bytes,
    doc_type: str,
    file_name: str | None = None,
    use_ocr: bool = False,
    ocr_timeout: int = 75,  # prev default 45s
) -> Union[SLDExtraction, PVModuleExtraction, InverterExtraction]:
    """
    Run extraction using Gemini Vision.
    """
    # Check API key
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found. Please set it in .env file")
    
    extractor = GeminiVisionExtractor()
    logger.info("Using Gemini for extraction")
    
    # Run Vision extraction
    if doc_type == "sld":
        result = extractor.extract_sld(pdf_bytes, file_name=file_name)
    elif doc_type == "pv":
        result = extractor.extract_pv_datasheet(pdf_bytes, file_name=file_name)
    elif doc_type == "inverter":
        result = extractor.extract_inverter_datasheet(pdf_bytes, file_name=file_name)
    else:
        raise ValueError(f"Unknown doc_type: {doc_type}")

    # Low-AI deterministic patch: fill gaps from PDF text if any key fields missing
    low_ai = os.getenv("LOW_AI_MODE", "false").lower() in ("1", "true", "yes")
    if low_ai:
        basic = _extract_basic_text_fields(pdf_bytes)
        if doc_type in ("sld", "inverter"):
            if result.inverter_dc_max_voltage_v is None and basic.get("inverter_dc_max_voltage_v"):
                result.inverter_dc_max_voltage_v = basic["inverter_dc_max_voltage_v"]
            if not result.inverter_model and basic.get("inverter_model"):
                result.inverter_model = basic["inverter_model"]
            if result.modules_per_string is None and basic.get("modules_per_string"):
                result.modules_per_string = basic["modules_per_string"]
            if result.strings_per_mppt is None and basic.get("strings_per_mppt"):
                result.strings_per_mppt = basic["strings_per_mppt"]
            if result.total_strings is None and basic.get("total_strings"):
                result.total_strings = basic["total_strings"]
        if doc_type in ("sld", "pv"):
            if not getattr(result, "pv_module_model", None) and basic.get("pv_module_model"):
                result.pv_module_model = basic["pv_module_model"]
    
    # Run OCR if enabled and Vision confidence is low
    ocr_text = ""
    # Trigger OCR more aggressively for completeness (prev threshold 0.7)
    if use_ocr and result.confidence < 0.85:
        try:
            ocr_extractor = OCRExtractor(timeout=ocr_timeout)
            ocr_text = ocr_extractor.extract_text(pdf_bytes)
            logger.info(f"OCR extracted {len(ocr_text)} chars")
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
    
    # Merge if we have OCR text
    if ocr_text and doc_type == "pv":
        merger = AIMergeEngine()
        result = merger.merge_pv_extractions(ocr_text, result)
    
    return result
