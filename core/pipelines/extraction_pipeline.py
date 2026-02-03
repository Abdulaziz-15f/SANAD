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
    mppt_count: Optional[int] = None
    
    # String Configuration
    modules_per_string: Optional[int] = None
    strings_per_mppt: Optional[int] = None
    total_strings: Optional[int] = None
    
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
    
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model
        self._client = None
        logger.info(f"GeminiVisionExtractor initialized with model: {self.model}")
    
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
        """Call Gemini API with optional images and automatic retry."""
        client = self._get_client()
        
        from google.genai import types
        
        contents = []
        if images:
            for img_bytes in images:
                contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
        contents.append(prompt)
        
        # Retry logic for rate limits
        max_retries = 3
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
                
                # Check if it's a rate limit error
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    wait_time = 35
                    if attempt < max_retries - 1:
                        logger.warning(f"Rate limited. Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Rate limit exceeded after {max_retries} attempts")
                        return ""
                else:
                    logger.error(f"Gemini API error: {e}")
                    return ""
        
        return ""
    
    def extract_sld(self, pdf_bytes: bytes) -> SLDExtraction:
        """Extract data from SLD using Gemini."""
        result = SLDExtraction()
        
        try:
            images = self._pdf_to_images(pdf_bytes, dpi=300, max_pages=2)
            if not images:
                result.notes = "Failed to render PDF"
                return result
            
            prompt = """You are an expert solar PV engineer analyzing a Single Line Diagram (SLD).

TASK: Extract ALL technical specifications from this engineering drawing.

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

Return ONLY valid JSON:
{
    "system_capacity_kw": <number or null>,
    "inverter_model": "<exact model or null>",
    "inverter_manufacturer": "<company or null>",
    "inverter_count": <INTEGER or null>,
    "pv_module_model": "<exact model or null>",
    "pv_module_power_w": <number or null>,
    "modules_per_string": <INTEGER or null>,
    "strings_per_mppt": <INTEGER or null>,
    "total_strings": <INTEGER or null>,
    "total_modules": <INTEGER or null>,
    "dc_cable_size_mm2": <number or null>,
    "ac_cable_size_mm2": <number or null>,
    "confidence": <0.0 to 1.0>,
    "notes": "<observations>"
}"""
            
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
            result.source = "gemini_vision"
            
            logger.info(f"SLD extraction complete: {result.inverter_model}, {result.modules_per_string} MPS")
            
        except Exception as e:
            result.notes = f"Extraction error: {str(e)}"
            result.confidence = 0.0
            logger.error(f"SLD extraction failed: {e}")
        
        return result
    
    def extract_pv_datasheet(self, pdf_bytes: bytes) -> PVModuleExtraction:
        """Extract data from PV module datasheet using Gemini."""
        result = PVModuleExtraction()
        
        try:
            images = self._pdf_to_images(pdf_bytes, dpi=250, max_pages=2)
            if not images:
                result.notes = "Failed to render PDF"
                return result
            
            prompt = """You are an expert solar PV engineer analyzing a PV module datasheet.

TASK: Extract the electrical specifications at STC (Standard Test Conditions: 1000W/m², 25°C, AM1.5).

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
{
    "manufacturer": "<company name or null>",
    "model": "<full model number or null>",
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
}"""
            
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
    
    def extract_inverter_datasheet(self, pdf_bytes: bytes) -> InverterExtraction:
        """Extract data from inverter datasheet using Gemini."""
        result = InverterExtraction()
        
        try:
            images = self._pdf_to_images(pdf_bytes, dpi=250, max_pages=2)
            if not images:
                result.notes = "Failed to render PDF"
                return result
            
            prompt = """You are an expert solar PV engineer analyzing an inverter datasheet.

TASK: Extract the DC input and AC output specifications.

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
{
    "manufacturer": "<company name or null>",
    "model": "<full model number or null>",
    "dc_max_voltage_v": <Volts as number>,
    "mppt_voltage_min_v": <Volts as number>,
    "mppt_voltage_max_v": <Volts as number>,
    "mppt_count": <INTEGER number>,
    "strings_per_mppt": <INTEGER number>,
    "ac_rated_power_kw": <kW as number>,
    "max_efficiency": <percent as number like 98.6>,
    "confidence": <0.0 to 1.0>,
    "notes": "<observations>"
}"""
            
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
                
                if "dc" in col_lower and "voltage" in col_lower and "drop" in col_lower:
                    vals = df[col].dropna()
                    if len(vals) > 0:
                        result.dc_voltage_drop_percent = float(vals.max())
                
                if "ac" in col_lower and "voltage" in col_lower and "drop" in col_lower:
                    vals = df[col].dropna()
                    if len(vals) > 0:
                        result.ac_voltage_drop_percent = float(vals.max())
                
                if "vd%" in col_lower or "voltage drop(%)" in col_lower:
                    vals = df[col].dropna()
                    if len(vals) > 0:
                        max_vd = float(vals.max())
                        if result.ac_voltage_drop_percent is None:
                            result.ac_voltage_drop_percent = max_vd
            
            if result.dc_voltage_drop_percent and result.ac_voltage_drop_percent:
                result.total_voltage_drop_percent = (
                    result.dc_voltage_drop_percent + result.ac_voltage_drop_percent
                )
            elif result.ac_voltage_drop_percent:
                result.total_voltage_drop_percent = result.ac_voltage_drop_percent
            
            result.confidence = 0.8 if result.ac_voltage_drop_percent else 0.3
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
) -> MergedExtraction:
    """Merge all extractions into a single unified structure."""
    
    merged = MergedExtraction()
    
    # System info from SLD
    merged.system_capacity_kw = sld.system_capacity_kw
    merged.modules_per_string = sld.modules_per_string
    merged.strings_per_mppt = sld.strings_per_mppt or inverter.strings_per_mppt
    merged.total_strings = sld.total_strings
    
    # PV Module (prefer datasheet, fallback to SLD)
    merged.module_model = pv_module.model or sld.pv_module_model
    merged.module_voc_v = pv_module.voc_v
    merged.module_isc_a = pv_module.isc_a
    merged.module_vmp_v = pv_module.vmp_v
    merged.module_imp_a = pv_module.imp_a
    merged.module_pmax_w = pv_module.pmax_w or sld.pv_module_power_w
    merged.temp_coeff_voc = pv_module.temp_coeff_voc
    
    # Inverter (prefer datasheet, fallback to SLD)
    merged.inverter_model = inverter.model or sld.inverter_model
    merged.inverter_dc_max_voltage_v = inverter.dc_max_voltage_v
    merged.inverter_mppt_min_v = inverter.mppt_voltage_min_v
    merged.inverter_mppt_max_v = inverter.mppt_voltage_max_v
    merged.inverter_ac_power_kw = inverter.ac_rated_power_kw
    merged.mppt_count = inverter.mppt_count
    
    # Cables
    merged.dc_cable_size_mm2 = cables.dc_cable_size_mm2 or sld.dc_cable_size_mm2
    merged.ac_cable_size_mm2 = cables.ac_cable_size_mm2 or sld.ac_cable_size_mm2
    merged.dc_voltage_drop_percent = cables.dc_voltage_drop_percent
    merged.ac_voltage_drop_percent = cables.ac_voltage_drop_percent
    
    # Location & Climate
    merged.location = location
    merged.tmin_c = tmin
    merged.tmax_c = tmax
    
    # Calculate confidence
    confidences = [sld.confidence, pv_module.confidence, inverter.confidence, cables.confidence]
    merged.confidence = sum(confidences) / len(confidences)
    
    # Validate
    merged = validate_extraction(merged)
    
    return merged


# -------------------------------------------------------------------
# Main Pipeline: Run Full Extraction
# -------------------------------------------------------------------
def run_full_extraction(
    pdf_bytes: bytes,
    doc_type: str,
    use_ocr: bool = False,
    ocr_timeout: int = 45,
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
        result = extractor.extract_sld(pdf_bytes)
    elif doc_type == "pv":
        result = extractor.extract_pv_datasheet(pdf_bytes)
    elif doc_type == "inverter":
        result = extractor.extract_inverter_datasheet(pdf_bytes)
    else:
        raise ValueError(f"Unknown doc_type: {doc_type}")
    
    # Run OCR if enabled and Vision confidence is low
    ocr_text = ""
    if use_ocr and result.confidence < 0.7:
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