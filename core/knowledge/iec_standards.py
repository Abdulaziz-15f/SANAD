"""
IEC Standards for PV Systems.

This module contains fixed IEC standard requirements that don't change.
These are embedded in the system, not uploaded by users.

References:
    - IEC 62548: Design requirements for PV arrays
    - IEC 62109: Safety of power converters
    - IEC 61730: PV module safety qualification
    - IEC 60364-7-712: Electrical installations - PV systems
"""
from __future__ import annotations

from typing import Dict, Any


# -------------------------------------------------------------------
# IEC 62548: PV Array Design Requirements
# -------------------------------------------------------------------
IEC_62548_REQUIREMENTS = {
    "source": "IEC 62548:2016",
    "title": "Photovoltaic (PV) arrays – Design requirements",
    
    "string_sizing": {
        "temperature_reference_c": 25.0,  # STC
        "voc_calculation": {
            "description": "Voc at minimum expected temperature",
            "formula": "Voc_cold = Voc_STC × (1 + βVoc × (Tmin - 25))",
            "requirement": "String Voc at Tmin must be < Inverter max DC voltage"
        },
        "voltage_margin_percent": 5.0,  # Safety margin recommended
    },
    
    "cable_sizing": {
        "dc_voltage_drop_max_percent": 3.0,
        "current_carrying_capacity": {
            "description": "Cable must carry 1.25 × Isc",
            "safety_factor": 1.25
        },
        "insulation_rating": {
            "description": "Cable voltage rating ≥ 1.15 × Voc_max",
            "safety_factor": 1.15
        }
    },
    
    "protection": {
        "string_fuse_rating": {
            "min_factor": 1.5,  # ≥ 1.5 × Isc
            "max_factor": 2.4,  # ≤ 2.4 × Isc (typically)
            "description": "Fuse rating between 1.5×Isc and 2.4×Isc"
        },
        "reverse_current": {
            "description": "Protection required if reverse current > module rating"
        }
    },
    
    "grounding": {
        "equipment_grounding": "Required",
        "functional_grounding": "Depends on inverter type",
        "ground_fault_detection": "Required for systems > 5kW"
    }
}


# -------------------------------------------------------------------
# IEC 62109: Inverter Safety Requirements
# -------------------------------------------------------------------
IEC_62109_REQUIREMENTS = {
    "source": "IEC 62109-1/2:2010",
    "title": "Safety of power converters for PV systems",
    
    "electrical": {
        "isolation_resistance": {
            "min_mohm": 1.0,
            "test_voltage_v": 500
        },
        "leakage_current_max_ma": 30,
        "efficiency_min_percent": 95.0,  # Typical requirement
    },
    
    "protection_functions": {
        "anti_islanding": {
            "required": True,
            "detection_time_max_s": 2.0
        },
        "over_voltage_protection": True,
        "under_voltage_protection": True,
        "over_frequency_protection": True,
        "under_frequency_protection": True,
        "ground_fault_monitoring": True
    }
}


# -------------------------------------------------------------------
# IEC 60364-7-712: Electrical Installation Requirements
# -------------------------------------------------------------------
IEC_60364_712_REQUIREMENTS = {
    "source": "IEC 60364-7-712:2017",
    "title": "Low-voltage electrical installations - PV systems",
    
    "wiring": {
        "dc_cables": {
            "type": "Double insulated or equivalent",
            "uv_resistant": True,
            "temperature_rating_min_c": 90
        },
        "separation": {
            "description": "DC and AC wiring should be separated"
        }
    },
    
    "disconnection": {
        "dc_isolator": {
            "required": True,
            "location": "Near inverter DC input",
            "load_break_capable": True
        },
        "ac_isolator": {
            "required": True,
            "location": "Grid connection point"
        }
    },
    
    "labeling": {
        "dc_warning_labels": True,
        "main_switch_label": True,
        "circuit_diagram_required": True
    }
}


# -------------------------------------------------------------------
# Combined IEC Requirements for Compliance Checking
# -------------------------------------------------------------------
def get_iec_string_voltage_requirement() -> Dict[str, Any]:
    """Get IEC string voltage sizing requirements."""
    return IEC_62548_REQUIREMENTS["string_sizing"]


def get_iec_cable_requirements() -> Dict[str, Any]:
    """Get IEC cable sizing requirements."""
    return IEC_62548_REQUIREMENTS["cable_sizing"]


def get_iec_protection_requirements() -> Dict[str, Any]:
    """Get IEC protection requirements."""
    return {
        **IEC_62548_REQUIREMENTS["protection"],
        **IEC_62109_REQUIREMENTS["protection_functions"]
    }


def get_iec_inverter_requirements() -> Dict[str, Any]:
    """Get IEC inverter requirements."""
    return IEC_62109_REQUIREMENTS