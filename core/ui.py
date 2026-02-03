import importlib.util
import json
import tempfile
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="SLD Reader", layout="centered")
st.title("SLD Image Text Reader")
st.write("Upload an SLD image and extract all readable text from it.")

CURRENT_DIR = Path(__file__).resolve().parent
ENGINE_FILE = CURRENT_DIR / "ocr_engine.py"

if not ENGINE_FILE.exists():
    st.error(f"Missing file: {ENGINE_FILE.name}")
    st.stop()

spec = importlib.util.spec_from_file_location("ocr_engine", str(ENGINE_FILE))
ocr_engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ocr_engine)
extract_text = ocr_engine.extract_text

uploaded_file = st.file_uploader(
    "Upload image (JPG / PNG)", type=["jpg", "jpeg", "png"]
)

if uploaded_file:
    suffix = "." + uploaded_file.name.split(".")[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.read())
        image_path = tmp.name

    if st.button("Extract Text"):
        with st.spinner("Processing image..."):
            result = extract_text(
                image_path=image_path,
                engine="easy",
                lang_mode="en+ar",
                min_conf=0.0,
                save_json=None,
            )

        st.success(f"Extracted {result['count']} text items")

        for i, item in enumerate(result["texts"], start=1):
            st.write(f"{i}. {item['text']}")

        json_bytes = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")

        st.download_button(
            label="Download JSON",
            data=json_bytes,
            file_name="sld_text.json",
            mime="application/json",
        )

def display_bom_download(bom_path: str):
    """Display a download button for the BoM file."""
    with open(bom_path, "rb") as bom_file:
        st.download_button(
            label="📥 Download BoM",
            data=bom_file,
            file_name="Generated_BoM.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
