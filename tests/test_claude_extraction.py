"""
Debug script for Claude extraction.
"""
import os
import sys
import logging
from pathlib import Path

# Setup logging to see everything
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from core.pipelines.extraction_pipeline import ClaudeVisionExtractor, GeminiVisionExtractor


def test_claude_api():
    """Test Claude API connection."""
    print("\n" + "="*60)
    print("TEST 1: Claude API Connection")
    print("="*60)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set!")
        return False
    
    print(f"✅ API Key found: {api_key[:25]}...")
    
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say 'Claude API working!'"}]
        )
        print(f"✅ Claude Response: {response.content[0].text}")
        return True
    except Exception as e:
        print(f"❌ Claude API Error: {e}")
        return False


def test_pdf_to_images():
    """Test PDF to image conversion."""
    print("\n" + "="*60)
    print("TEST 2: PDF to Image Conversion")
    print("="*60)
    
    pdf_path = Path("data/pdfs/Schematic system1-Model.pdf")
    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        return False, None
    
    print(f"✅ PDF found: {pdf_path}")
    print(f"   Size: {pdf_path.stat().st_size / 1024:.1f} KB")
    
    extractor = ClaudeVisionExtractor()
    pdf_bytes = pdf_path.read_bytes()
    
    images = extractor._pdf_to_images(pdf_bytes, dpi=200, max_pages=1)
    
    if not images:
        print("❌ Failed to convert PDF to images")
        return False, None
    
    print(f"✅ Converted {len(images)} page(s) to images")
    for idx, img_bytes in enumerate(images):
        print(f"   Image {idx + 1}: {len(img_bytes) / 1024:.1f} KB")
    
    return True, images


def test_claude_with_image(images):
    """Test Claude with an image."""
    print("\n" + "="*60)
    print("TEST 3: Claude Vision with Image")
    print("="*60)
    
    if not images:
        print("❌ No images to test")
        return False
    
    extractor = ClaudeVisionExtractor()
    
    # Simple test prompt
    simple_prompt = """Look at this engineering diagram and tell me:
1. What type of diagram is this?
2. Can you see any text or numbers?
3. List any equipment model numbers you can read.

Return your answer as JSON:
{
    "diagram_type": "<type>",
    "has_text": true/false,
    "model_numbers": ["<list of any model numbers you see>"]
}"""
    
    print("Calling Claude with simple prompt...")
    response = extractor._call_claude(simple_prompt, images)
    
    if not response:
        print("❌ Claude returned empty response")
        return False
    
    print(f"✅ Claude response ({len(response)} chars):")
    print("-" * 40)
    print(response[:1000])
    print("-" * 40)
    
    return True


def test_full_sld_extraction():
    """Test full SLD extraction."""
    print("\n" + "="*60)
    print("TEST 4: Full SLD Extraction")
    print("="*60)
    
    pdf_path = Path("data/pdfs/Schematic system1-Model.pdf")
    if not pdf_path.exists():
        print(f"❌ PDF not found")
        return
    
    extractor = ClaudeVisionExtractor()
    result = extractor.extract_sld(pdf_path.read_bytes())
    
    print("\nExtraction Results:")
    print(f"  Source: {result.source}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Notes: {result.notes}")
    print()
    print(f"  System Capacity: {result.system_capacity_kw} kW")
    print(f"  Inverter Model: {result.inverter_model}")
    print(f"  Inverter Count: {result.inverter_count}")
    print(f"  PV Module Model: {result.pv_module_model}")
    print(f"  Module Power: {result.pv_module_power_w} W")
    print(f"  Modules/String: {result.modules_per_string}")
    print(f"  Total Strings: {result.total_strings}")


def test_gemini_fallback():
    """Test Gemini as fallback."""
    print("\n" + "="*60)
    print("TEST 5: Gemini Fallback")
    print("="*60)
    
    gemini_key = os.getenv("GOOGLE_API_KEY")
    if not gemini_key:
        print("❌ GOOGLE_API_KEY not set, skipping Gemini test")
        return
    
    pdf_path = Path("data/pdfs/Schematic system1-Model.pdf")
    if not pdf_path.exists():
        print(f"❌ PDF not found")
        return
    
    try:
        extractor = GeminiVisionExtractor()
        result = extractor.extract_sld(pdf_path.read_bytes())
        
        print("\nGemini Extraction Results:")
        print(f"  Source: {result.source}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Inverter Model: {result.inverter_model}")
        print(f"  Modules/String: {result.modules_per_string}")
    except Exception as e:
        print(f"❌ Gemini error: {e}")


if __name__ == "__main__":
    print("\n🔍 SANAD Claude Extraction Debug Tool\n")
    
    # Test 1: API Connection
    api_ok = test_claude_api()
    if not api_ok:
        print("\n⚠️  Fix API key before continuing")
        sys.exit(1)
    
    # Test 2: PDF to Images
    pdf_ok, images = test_pdf_to_images()
    if not pdf_ok:
        print("\n⚠️  Fix PDF path before continuing")
        sys.exit(1)
    
    # Test 3: Claude with Image
    vision_ok = test_claude_with_image(images)
    
    # Test 4: Full Extraction
    test_full_sld_extraction()
    
    # Test 5: Gemini Fallback
    test_gemini_fallback()
    
    print("\n" + "="*60)
    print("DEBUG COMPLETE")
    print("="*60)