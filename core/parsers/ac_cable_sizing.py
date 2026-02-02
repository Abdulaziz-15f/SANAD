import pandas as pd
import re
from typing import List, Tuple
from core.models import InverterCableRun, CombinerCableRun

SHEET_VD = "Percentage Voltage Drop "

def _is_inverter_name(x: str) -> bool:
    return bool(re.match(r"^Inverter\d+$", str(x).strip(), re.IGNORECASE))

def parse_ac_cable_sizing_excel(path_or_file) -> Tuple[List[InverterCableRun], List[CombinerCableRun]]:
    """
    Reads AC Cable_Sizing_Equations.xlsx and extracts:
      - inverter -> combiner runs (VD%)
      - combiner -> MDB runs (VD%)
    """
    df = pd.read_excel(path_or_file, sheet_name=SHEET_VD, header=0)

    
    inv_df = df[df["Inverters"].apply(_is_inverter_name)].copy()

    
    inv_df["Combiner_filled"] = inv_df["Combiner"].ffill()

    #
    col_len_inv = [c for c in inv_df.columns if "INV TO Combiner" in c][0]
    col_len_comb = [c for c in inv_df.columns if "Combiner To MDB" in c][0]

    inverter_runs: List[InverterCableRun] = []
    for _, r in inv_df.iterrows():
        inverter_runs.append(
            InverterCableRun(
                inverter=str(r["Inverters"]).strip(),
                combiner=str(r["Combiner_filled"]).strip(),
                length_m=float(r[col_len_inv]),
                cable_size_mm2=float(r["cable size"]),
                cable_type=str(r["Type Cable"]).strip(),
                current_a=float(r["I max (A)"]),
                impedance_mV_A_m=float(r["Impedance\n[90 oC]"]),
                voltage_drop_pct=float(r["Voltage Drop(%)"]),
            )
        )

    # Combiner->MDB run exists only on the first inverter row of each combiner group
    combiner_rows = inv_df[inv_df["Combiner"].notna()].copy()

    combiner_runs: List[CombinerCableRun] = []
    for _, r in combiner_rows.iterrows():
        combiner_runs.append(
            CombinerCableRun(
                combiner=str(r["Combiner"]).strip(),
                length_m=float(r[col_len_comb]),
                cable_desc=str(r["cable size.1"]).strip(),  
                cable_type=str(r["Type Cable.1"]).strip(),
                current_a=float(r["I max (A).1"]),
                impedance_mV_A_m=float(r["Impedance\n[90 oC].1"]),
                voltage_drop_pct=float(r["Voltage Drop(%).1"]),
            )
        )

    return inverter_runs, combiner_runs
