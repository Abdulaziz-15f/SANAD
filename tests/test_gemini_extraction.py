"""
Test Gemini extraction with multi-pass approach.
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

PDF_DIR = Path("/Users/mohammedalharbi/Documents/HACKATHONS/UTURETHON/SANAD/data/pdfs")


def test_api_connection():
    """Test basic Gemini API connection."""
    print("=" * 60)
    print("SANAD Gemini Extraction Test (MULTI-PASS)")
    print("=" * 60)
    
    print("\n[Test 1] API Key Check")
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: No API key found")
        return False
    print(f"OK: API Key found: {api_key[:10]}...{api_key[-4:]}")
    
    print("\n[Test 2] Gemini API Connection")
    try:
        from google import genai
        
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Say: SANAD ready!"
        )
        print(f"OK: {response.text}")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def test_pdf_extraction():
    """Test PDF extraction with multi-pass approach."""
    print("\n[Test 3] SLD Extraction (400 DPI + Cropped Sections)")
    
    if not PDF_DIR.exists():
        print(f"ERROR: PDF directory not found: {PDF_DIR}")
        return False
    
    sld_pdf = PDF_DIR / "Schematic system1-Model.pdf"
    if not sld_pdf.exists():
        test_pdfs = list(PDF_DIR.glob("*.pdf"))
        sld_pdf = test_pdfs[0] if test_pdfs else None
    
    if not sld_pdf:
        print("ERROR: No PDF found")
        return False
    
    print(f"Testing: {sld_pdf.name}")
    print("Pass 1: Full page at 400 DPI...")
    
    try:
        from core.pipelines.extraction_pipeline import GeminiVisionExtractor
        
        extractor = GeminiVisionExtractor(model="gemini-2.5-flash")
        
        pdf_bytes = sld_pdf.read_bytes()
        result = extractor.extract_sld(pdf_bytes)
        
        print(f"\n{'='*60}")
        print("SLD EXTRACTION RESULTS")
        print("=" * 60)
        
        print(f"\n[SYSTEM INFO]")
        print(f"  Capacity: {result.system_capacity_kw} kW")
        print(f"  Confidence: {result.confidence:.1%}")
        
        print(f"\n[INVERTERS]")
        if result.inverters:
            for i, inv in enumerate(result.inverters, 1):
                model_str = inv.model if inv.model else "NOT FOUND"
                print(f"  [{i}] {inv.count}x {inv.capacity_kw}kW")
                print(f"      Model: {model_str}")
                print(f"      Manufacturer: {inv.manufacturer or 'Unknown'}")
            print(f"  Total Inverters: {result.inverter_count}")
        else:
            print(f"  Model: {result.inverter_model or 'NOT FOUND'}")
            print(f"  Count: {result.inverter_count}")
            print(f"  Capacity: {result.inverter_capacity_kw} kW")
        
        print(f"\n[PV MODULES]")
        print(f"  Model: {result.pv_module_model or 'NOT FOUND'}")
        print(f"  Power: {result.pv_module_power_w}W" if result.pv_module_power_w else "  Power: Not found")
        
        print(f"\n[STRING CONFIGURATION]")
        print(f"  Modules/String: {result.modules_per_string}")
        print(f"  Strings/MPPT: {result.strings_per_mppt}")
        print(f"  Total Strings: {result.total_strings}")
        print(f"  Total Modules: {result.total_modules}")
        
        print(f"\n[CABLES]")
        print(f"  DC Cable: {result.dc_cable_size_mm2} mm2")
        print(f"  AC Cable: {result.ac_cable_size_mm2} mm2")
        
        print(f"\n[PROTECTION]")
        print(f"  DC Fuse: {result.dc_fuse_rating_a} A")
        print(f"  AC Breaker: {result.ac_breaker_rating_a} A")
        
        if result.raw_text:
            print(f"\n[NOTES]")
            # Truncate long notes
            notes = result.raw_text[:600] + "..." if len(result.raw_text) > 600 else result.raw_text
            print(f"  {notes}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    api_ok = test_api_connection()
    
    if api_ok:
        test_pdf_extraction()
    else:
        print("\nERROR: Cannot continue - API error")
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)