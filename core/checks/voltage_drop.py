from typing import List, Tuple
from core.models import InverterCableRun, CombinerCableRun, Issue

def check_voltage_drop(
    inverter_runs: List[InverterCableRun],
    combiner_runs: List[CombinerCableRun],
    inverter_vd_limit_pct: float = 3.0,
    combiner_vd_limit_pct: float = 1.5,
) -> List[Issue]:
    issues: List[Issue] = []

    for run in inverter_runs:
        if run.voltage_drop_pct > inverter_vd_limit_pct:
            issues.append(Issue(
                code="AC_VD_INV",
                severity="MAJOR",
                title=f"High AC voltage drop on {run.inverter}",
                description=(
                    f"{run.inverter} -> {run.combiner} voltage drop is {run.voltage_drop_pct:.2f}% "
                    f"(limit {inverter_vd_limit_pct:.2f}%). Cable {run.cable_size_mm2} mm², "
                    f"length {run.length_m:.0f} m, I={run.current_a:.1f} A."
                ),
                evidence=run.__dict__
            ))

    for run in combiner_runs:
        if run.voltage_drop_pct > combiner_vd_limit_pct:
            issues.append(Issue(
                code="AC_VD_COMB",
                severity="MAJOR",
                title=f"High AC voltage drop from {run.combiner} to MDB",
                description=(
                    f"{run.combiner} -> MDB voltage drop is {run.voltage_drop_pct:.2f}% "
                    f"(limit {combiner_vd_limit_pct:.2f}%). Cable {run.cable_desc}, "
                    f"length {run.length_m:.0f} m, I={run.current_a:.0f} A."
                ),
                evidence=run.__dict__
            ))

    return issues
