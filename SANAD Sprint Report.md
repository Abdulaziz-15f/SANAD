# SANAD Sprint Report
**Date:** February 3, 2026  
**Branch:** `feature/M7medBranch`  
**Team:** SANAD

---

## 📋 Executive Summary

SANAD (Smart Automated Network for Auditing and Design Compliance) is a web application that automates PV solar system design review. This sprint delivered a working 2-stage pipeline that accepts project documents and generates compliance reports.

---

## ✅ Completed Features

### Stage 1: Project Intake
| Feature | Status | Description |
|---------|--------|-------------|
| Site Selection | ✅ Done | Search + interactive map (Folium) |
| Weather Data | ✅ Done | Current temp, Tmin/Tmax from Open-Meteo API |
| Manual Tmin Fallback | ✅ Done | User input when API fails |
| File Uploads | ✅ Done | SLD PDF, BoM Excel, AC Cable Excel |

### Stage 2: Engineering Review
| Feature | Status | Description |
|---------|--------|-------------|
| SLD OCR Extraction | ✅ Done | PaddleOCR on all PDF pages |
| BoM Signal Parsing | ✅ Done | Extract Voc, temp coeff, modules/string |
| BoM vs SLD Check | ✅ Done | Compare inverter Vmax, modules/string |
| Cold Weather Check | ✅ Done | Voc at Tmin vs inverter DC max |
| AC Voltage Drop | ✅ Done | Parse Excel, check 3%/1.5% limits |
| PDF Report | ✅ Done | ReportLab-generated compliance report |

---

## 🛠️ Technical Implementation

### Architecture
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Stage 1       │     │   Stage 2       │     │   Output        │
│   (Intake)      │ ──▶ │   (Review)      │ ──▶ │   (Report)      │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ • Site search   │     │ • OCR extraction│     │ • PDF report    │
│ • Weather API   │     │ • BoM parsing   │     │ • Compliance    │
│ • File uploads  │     │ • Rule checks   │     │   snapshot      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Tech Stack
| Component | Technology | Purpose |
|-----------|------------|---------|
| Frontend | Streamlit 1.41 | Web UI |
| OCR | PaddleOCR 2.7+ | Text extraction from SLD |
| PDF Rendering | PyMuPDF (fitz) | Convert PDF to images |
| Excel Parsing | Pandas + openpyxl | BoM & AC cable data |
| Report Gen | ReportLab | PDF output |
| Weather API | Open-Meteo | Climate data |
| Maps | Folium | Site selection |

### Key Files Modified/Created
```
core/
├── review.py          # Engineering check functions (REWRITTEN)
├── stage2.py          # Stage 2 render logic
├── report.py          # PDF report generation
├── weather.py         # Open-Meteo API integration
├── ui_components.py   # Reusable UI components
├── extract/
│   ├── sld_extract.py # OCR pipeline (FIXED for PaddleOCR 2.7+)
│   ├── pdf_render.py  # PDF to image conversion
│   └── image_preprocess.py # Image prep for OCR
├── parsers/
│   ├── bom_signals.py # BoM Excel extraction
│   └── ac_cable_sizing.py # AC cable Excel parsing
└── checks/
    └── voltage_drop.py # VD limit checks
```

---

## 🐛 Bugs Fixed

| Issue | Root Cause | Fix |
|-------|------------|-----|
| `set_page_config` error | `review.py` was duplicate of `app.py` | Rewrote as pure logic module |
| `show_log` parameter error | PaddleOCR 2.7 API change | Removed deprecated parameter |
| `cls=True` parameter error | PaddleOCR 2.7 API change | Set `use_angle_cls` at init only |
| `tuple index out of range` | Image not RGB format | Added `_ensure_rgb_array()` |
| `target_dpi` not accepted | Missing parameter in function | Added to `render_pdf_to_images()` |
| Circular import | `review.py` importing `stage2.py` | Lazy import in `app.py` |

---

## 📊 Test Files

| File | Location | Purpose |
|------|----------|---------|
| Sample BoM | `tests/Sample_BoM.xlsx` | Test BoM parsing |
| AC Cable Sizing | `tests/AC Cable_Sizing_Equations.xlsx` | Test VD checks |
| SLD PDF | `data/pdfs/Schematic system1-Model.pdf` | Test OCR extraction |

---

## 🚀 How to Run

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
streamlit run app.py

# 4. In browser:
#    - Search for a city (e.g., "Jeddah")
#    - Set the site
#    - Enter manual Tmin if needed (e.g., 5.0)
#    - Upload the 3 required files
#    - Click "Continue to Review"
```

---

## 📈 Next Steps (Backlog)

| Priority | Task | Effort |
|----------|------|--------|
| P1 | DC cable sizing verification | Medium |
| P1 | Improve OCR regex patterns for more SLD formats | Medium |
| P2 | LLM agent for intelligent report writing | High |
| P2 | Vision model for diagram symbol recognition | High |
| P3 | Multi-language support (Arabic) | Medium |
| P3 | Export to Excel format | Low |


---

## 📎 Attachments

- Generated Report: `tests/SANAD_Report_2026-02-03.pdf`
- Branch: `feature/pv-design-review-pipeline`

---

*Generated: February 3, 2026*