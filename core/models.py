from dataclasses import dataclass
from typing import Optional, Dict, Any, List

@dataclass
class InverterCableRun:
    inverter: str
    combiner: str
    length_m: float
    cable_size_mm2: float
    cable_type: str
    current_a: float
    impedance_mV_A_m: float
    voltage_drop_pct: float

@dataclass
class CombinerCableRun:
    combiner: str
    length_m: float
    cable_desc: str
    cable_type: str
    current_a: float
    impedance_mV_A_m: float
    voltage_drop_pct: float

@dataclass
class Issue:
    code: str
    severity: str  # "CRITICAL" | "MAJOR" | "MINOR"
    title: str
    description: str
    evidence: Optional[Dict[str, Any]] = None
