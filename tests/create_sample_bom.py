"""
Run this script once to create a sample BoM Excel file for testing.
"""
import pandas as pd
from pathlib import Path

def create_sample_bom():
    data = {
        "Item": [1, 2, 3, 4, 5],
        "Description": [
            "PV Module - JA Solar JAM72S30-545/MR",
            "Inverter - Huawei SUN2000-100KTL-M2",
            "DC Cable - 6mm²",
            "AC Cable - 95mm²",
            "Mounting Structure",
        ],
        "Quantity": [2200, 20, 5000, 800, 2200],
        "Unit": ["pcs", "pcs", "m", "m", "sets"],
        # Key electrical parameters for PV checks
        "Voc_STC": [49.5, None, None, None, None],
        "TempCoeff": [-0.29, None, None, None, None],  # %/°C
        "ModulesPerString": [22, None, None, None, None],
        "Inverter_Vmax": [None, 1100, None, None, None],
        "InverterModel": [None, "SUN2000-100KTL-M2", None, None, None],
    }

    df = pd.DataFrame(data)
    
    output_path = Path(__file__).parent / "Sample_BoM.xlsx"
    df.to_excel(output_path, index=False, sheet_name="BoM")
    print(f"Created: {output_path}")
    return output_path


if __name__ == "__main__":
    create_sample_bom()