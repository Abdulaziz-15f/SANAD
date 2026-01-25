
---

# SANAD PV Design Review Platform

**SANAD (Smart Automated Network for Auditing and Design Compliance)** is an engineering-focused web platform designed to automate early-stage photovoltaic (PV) design reviews.

The system performs intelligent checks on submitted PV designs to detect technical risks, design inconsistencies, and regulatory gaps **before construction or procurement**.

---

##  Project Overview

SANAD provides an automated, location-aware PV design audit by combining:

* Site-specific climate data
* Manufacturer electrical parameters
* Engineering logic based on PV design standards

The platform helps engineers and decision-makers identify potential issues early, reducing redesign cost, safety risks, and approval delays.

---

## Key Features

### 1. Site-Based Climate Analysis

* Search and select project location
* Automatic retrieval of:

  * Current ambient temperature
  * Historical minimum temperature (last 10 years)
* Climate-aware electrical evaluation

### 2. Document Intake

* Upload **Single-Line Diagram (SLD)** (PDF)
* Upload **Bill of Materials (BoM)** (Excel)
* Automatic extraction of key electrical parameters

### 3. Engineering Review (Stage 2)

* **BoM vs SLD consistency check**

  * Detects mismatches in inverter voltage and string configuration
  * Visual status: MATCH / WARNING

* **Cold Weather Overvoltage Assessment**

  * Calculates string voltage at minimum temperature
  * Identifies inverter DC overvoltage risk
  * Generates mitigation recommendations

* **Saudi / IEC Standards Snapshot**

  * Highlights compliant checks
  * Lists gaps requiring engineering validation

### 4. Automated Report Generation

* One-click export of a professional **SANAD Design Review Report (PDF)**
* Includes:

  * Project information
  * Key electrical numbers
  * Risk summary
  * Compliance snapshot
  * Engineering recommendations

---

## Engineering Logic

SANAD applies industry-recognized PV engineering principles, including:

* Temperature-adjusted open-circuit voltage (Voc cold calculation)
* String sizing verification against inverter DC maximum limits
* Conservative design assumptions using historical climate data
* Best-effort SLD text extraction (with OCR readiness)

> Note: Scanned SLD drawings require OCR/Vision modules for full automation.

---

## Project Structure

```
SANAD/
│
├── app.py                     # Main Streamlit application
│
├── core/
│   ├── stage2.py              # Engineering review & UI rendering
│   ├── review.py              # Engineering logic and checks
│   ├── weather.py             # Climate and geocoding services
│   ├── report.py              # PDF report generation
│   ├── theme.py               # UI theme and styling
│   ├── state.py               # Session state management
│   └── ui_components.py       # Reusable UI elements
│
├── data/
│   └── (optional test files)
│
├── requirements.txt
└── README.md
```

---

## Technologies Used

* **Python 3.10+**
* **Streamlit** — interactive engineering interface
* **Pandas / NumPy** — data processing
* **Open-Meteo API** — climate and geolocation data
* **ReportLab** — PDF generation
* **Folium** — site visualization

---

## How to Run the Project

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the application

```bash
streamlit run app.py
```

### 3. Open in browser

```
http://localhost:8501
```

---

## Output Example

* SANAD PV Design Review Report (PDF)
* Engineering summary
* Key electrical numbers
* Compliance snapshot
* Clear recommendations

---

## Intended Users

* PV Design Engineers
* Solar EPC Companies
* Engineering Consultants
* Technical Review Committees
* Renewable Energy Innovation Programs

---

## Disclaimer

This tool provides an **automated preliminary engineering review** intended to support technical decision-making.

SANAD does **not replace detailed engineering design, manufacturer verification, or final authority approval**.

Final responsibility remains with the licensed design engineer and relevant regulatory bodies.

---

## Future Enhancements

* OCR / Vision-based SLD extraction
* AI-assisted design explanation layer
* Multi-inverter and multi-MPPT support
* DC cable sizing and derating automation
* Fire and safety compliance modeling
* Integration with utility approval workflows

---

## Project Status

✅ Functional prototype
✅ Engineering logic validated
✅ Corporate-ready UI
🚧 Advanced automation under future development

---

## Project Name

**SANAD**
*Smart Automated Network for Auditing and Design Compliance*

---

