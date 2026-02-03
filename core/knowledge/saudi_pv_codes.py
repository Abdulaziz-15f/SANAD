"""
Saudi PV Codes and Standards Database.

Sources:
    - SEC: Saudi Electricity Company Distribution Code
    - MOMAH: Ministry of Municipal and Rural Affairs (Building Regulations)
    - SBC: Saudi Building Code
    - SASO: Saudi Standards Organization (IEC adoptions)

This module provides structured access to compliance rules
for automated design verification.

Note: These are FIXED standards embedded in the system.
      Users do NOT upload these - they are reference data.
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional


# -------------------------------------------------------------------
# SEC Connection Standards
# -------------------------------------------------------------------
SEC_CONNECTION_STANDARDS = {
    "source": "SEC Standards for Connection of Small Scale Solar PV v3",
    "version": "v3",
    "language": "en/ar",
    
    "capacity_categories": {
        "category_1": {
            "name": "Small Scale",
            "max_kw": 2000,
            "voltage_level": "LV",
            "connection": "Simplified",
            "study_required": False
        },
        "category_2": {
            "name": "Medium Scale", 
            "min_kw": 2000,
            "max_kw": 10000,
            "voltage_level": "LV/MV",
            "connection": "Standard",
            "study_required": True
        }
    },
    
    "technical_requirements": {
        "power_factor": {
            "min": 0.95,
            "condition": "at_rated_output",
            "adjustable": True
        },
        "voltage_variation": {
            "max_percent": 5.0,
            "reference": "nominal_voltage"
        },
        "frequency_range": {
            "min_hz": 47.5,
            "max_hz": 51.5,
            "nominal_hz": 50.0
        },
        "dc_injection": {
            "max_percent": 0.5,
            "of": "rated_current"
        },
        "thd_current": {
            "max_percent": 5.0
        },
        "flicker": {
            "pst_max": 1.0,
            "plt_max": 0.65
        }
    },
    
    "protection_settings": {
        "over_voltage": {
            "stage_1": {"threshold_percent": 110, "trip_time_s": 2.0},
            "stage_2": {"threshold_percent": 120, "trip_time_s": 0.16}
        },
        "under_voltage": {
            "stage_1": {"threshold_percent": 85, "trip_time_s": 2.0},
            "stage_2": {"threshold_percent": 50, "trip_time_s": 0.16}
        },
        "over_frequency": {
            "threshold_hz": 51.5,
            "trip_time_s": 0.5
        },
        "under_frequency": {
            "threshold_hz": 47.5,
            "trip_time_s": 0.5
        },
        "anti_islanding": {
            "required": True,
            "detection_time_s": 2.0,
            "method": "active_or_passive"
        },
        "reconnection": {
            "delay_s": 60,
            "voltage_range_percent": [85, 110],
            "frequency_range_hz": [47.5, 51.5]
        }
    },
    
    "metering": {
        "bidirectional": True,
        "accuracy_class": 1.0,
        "communication": "Required for >100kW"
    }
}


# -------------------------------------------------------------------
# SEC Best Practice for PV Design
# -------------------------------------------------------------------
SEC_DESIGN_BEST_PRACTICE = {
    "source": "SEC Best Practice for Designing a PV System v2",
    "version": "v2",
    
    "string_sizing": {
        "temperature_reference_c": 25.0,
        "voc_safety_margin_percent": 5.0,
        "calculation_method": "IEC 62548",
        "temperature_sources": [
            "Historical data (10 years)",
            "ASHRAE 99.6% design temperature",
            "Site-specific measurement"
        ]
    },
    
    "dc_ac_ratio": {
        "min": 1.0,
        "max": 1.3,
        "optimal_saudi": 1.15,
        "justification": "High irradiance in Saudi Arabia supports higher DC/AC ratio"
    },
    
    "cable_sizing": {
        "dc_voltage_drop_max_percent": 3.0,
        "ac_voltage_drop_max_percent": 3.0,
        "total_voltage_drop_max_percent": 5.0,
        "temperature_correction": "Required for cables in high ambient"
    },
    
    "inverter_selection": {
        "efficiency_min_percent": 96.0,
        "mppt_channels": "Match string configuration",
        "dc_voltage_headroom_percent": 10.0
    },
    
    "module_selection": {
        "certification_required": ["IEC 61215", "IEC 61730"],
        "pmax_tolerance": "Positive tolerance preferred",
        "warranty_min_years": {
            "product": 12,
            "performance": 25
        }
    }
}


# -------------------------------------------------------------------
# MOMAH Building Regulations for Solar
# -------------------------------------------------------------------
MOMAH_SOLAR_REGULATIONS = {
    "source": "MOMAH Solar Building Regulations",
    "authority": "Ministry of Municipal and Rural Affairs",
    
    "permit_requirements": {
        "residential": {
            "max_kw_no_permit": 10,
            "permit_required_above": 10
        },
        "commercial": {
            "permit_required": True,
            "structural_assessment": "Required for roof-mounted"
        }
    },
    
    "structural_requirements": {
        "load_calculation": {
            "method": "SBC or ASCE 7",
            "wind_load": "Required",
            "dead_load": "Panel + mounting system weight"
        },
        "roof_assessment": {
            "required_for": "All installations",
            "includes": [
                "Structural capacity verification",
                "Waterproofing integrity",
                "Access requirements"
            ]
        }
    },
    
    "fire_safety": {
        "access_pathways": {
            "min_width_m": 0.9,
            "location": "Ridge and perimeter"
        },
        "setback_from_edge_m": 0.6,
        "fire_classification": "Class C minimum",
        "rapid_shutdown": "Required for systems > 80V DC"
    },
    
    "aesthetics": {
        "historic_areas": "Special approval required",
        "color_restrictions": "May apply in certain zones",
        "height_limits": "Must not exceed building height limit"
    }
}


# -------------------------------------------------------------------
# Environmental Conditions by Region
# -------------------------------------------------------------------
SAUDI_CLIMATE_REGIONS = {
    "central": {
        "cities": ["Riyadh", "Qassim", "Hail", "Al-Kharj", "Buraidah"],
        "climate_type": "hot_arid",
        "design_temp_max_c": 50,
        "design_temp_min_c": 0,
        "extreme_temp_min_c": -5,
        "dust_level": "high",
        "humidity_level": "low",
        "ghi_kwh_m2_day": 6.2,
        "dni_kwh_m2_day": 6.8,
        "recommended_tilt": "latitude",
        "cleaning_frequency_days": 14,
        "soiling_loss_percent": 5,
        "notes": "High dust, extreme temperature range, low humidity"
    },
    "western": {
        "cities": ["Jeddah", "Makkah", "Madinah", "Yanbu", "Taif"],
        "climate_type": "hot_humid_coastal",
        "design_temp_max_c": 48,
        "design_temp_min_c": 15,
        "extreme_temp_min_c": 10,
        "dust_level": "medium",
        "humidity_level": "high",
        "ghi_kwh_m2_day": 5.8,
        "dni_kwh_m2_day": 5.5,
        "corrosion_risk": "high",
        "salt_spray": True,
        "recommended_materials": "marine_grade",
        "cleaning_frequency_days": 21,
        "soiling_loss_percent": 3,
        "notes": "Coastal corrosion, high humidity, salt spray"
    },
    "eastern": {
        "cities": ["Dammam", "Khobar", "Jubail", "Dhahran", "Al-Ahsa", "Hofuf"],
        "climate_type": "hot_humid_coastal",
        "design_temp_max_c": 50,
        "design_temp_min_c": 5,
        "extreme_temp_min_c": 0,
        "dust_level": "high",
        "humidity_level": "high",
        "ghi_kwh_m2_day": 5.5,
        "dni_kwh_m2_day": 5.2,
        "sandstorm_risk": "high",
        "corrosion_risk": "medium",
        "cleaning_frequency_days": 14,
        "soiling_loss_percent": 6,
        "notes": "Sandstorms common, coastal humidity, industrial pollution"
    },
    "southern": {
        "cities": ["Abha", "Khamis Mushait", "Najran", "Jizan", "Baha"],
        "climate_type": "moderate_highland",
        "design_temp_max_c": 35,
        "design_temp_min_c": -2,
        "extreme_temp_min_c": -5,
        "dust_level": "low",
        "humidity_level": "medium",
        "ghi_kwh_m2_day": 6.5,
        "dni_kwh_m2_day": 7.0,
        "altitude_m": 2200,
        "frost_risk": True,
        "cleaning_frequency_days": 30,
        "soiling_loss_percent": 2,
        "notes": "Best climate for PV, possible frost, high altitude"
    },
    "northern": {
        "cities": ["Tabuk", "Arar", "Sakaka", "NEOM", "Al-Jouf"],
        "climate_type": "desert_continental",
        "design_temp_max_c": 45,
        "design_temp_min_c": -5,
        "extreme_temp_min_c": -10,
        "dust_level": "medium",
        "humidity_level": "low",
        "ghi_kwh_m2_day": 6.0,
        "dni_kwh_m2_day": 6.5,
        "frost_risk": True,
        "snow_possible": True,
        "cleaning_frequency_days": 21,
        "soiling_loss_percent": 3,
        "notes": "Cold winters, frost/snow possible, good solar resource"
    }
}


# -------------------------------------------------------------------
# Wind Load Requirements (SBC)
# -------------------------------------------------------------------
WIND_LOAD_REGIONS = {
    "region_1": {
        "cities": ["Riyadh", "Qassim", "Hail", "Al-Kharj"],
        "basic_wind_speed_ms": 35,
        "exposure_category": "C",
        "description": "Interior desert - moderate wind"
    },
    "region_2": {
        "cities": ["Jeddah", "Makkah", "Madinah", "Taif"],
        "basic_wind_speed_ms": 40,
        "exposure_category": "C",
        "description": "Western region - higher wind near mountains"
    },
    "region_3": {
        "cities": ["Dammam", "Jubail", "Khobar", "Dhahran"],
        "basic_wind_speed_ms": 38,
        "exposure_category": "D",
        "description": "Eastern coastal - consistent wind"
    },
    "region_4": {
        "cities": ["Yanbu", "Jizan", "NEOM", "Coastal areas"],
        "basic_wind_speed_ms": 45,
        "exposure_category": "D",
        "description": "High wind coastal zones"
    },
    "region_5": {
        "cities": ["Tabuk", "Arar", "Northern border"],
        "basic_wind_speed_ms": 42,
        "exposure_category": "C",
        "description": "Northern region - winter storms"
    }
}


# -------------------------------------------------------------------
# Inspection Checklist (From SEC Guidelines)
# -------------------------------------------------------------------
SEC_INSPECTION_CHECKLIST = {
    "source": "SEC Inspection and Testing Guidelines v2",
    
    "visual_inspection": [
        "Module mounting secure and level",
        "No visible damage to modules",
        "Cable management proper (secured, no sharp bends)",
        "DC isolator accessible and labeled",
        "Warning labels in place",
        "Earthing connections visible and secure",
        "Inverter ventilation adequate",
        "AC connection point accessible"
    ],
    
    "electrical_tests": {
        "insulation_resistance": {
            "test_voltage_v": 500,
            "min_resistance_mohm": 1.0,
            "formula": "R_min = 1MΩ × (Voc_max / 500)"
        },
        "earth_continuity": {
            "max_resistance_ohm": 1.0
        },
        "polarity_check": {
            "required": True
        },
        "string_voc_measurement": {
            "tolerance_percent": 5,
            "compare_to": "calculated_value"
        },
        "string_isc_measurement": {
            "tolerance_percent": 10,
            "conditions": "clear_sky"
        }
    },
    
    "commissioning_tests": [
        "Grid connection test",
        "Anti-islanding verification",
        "Power quality measurement",
        "Export limiting verification (if applicable)"
    ]
}


# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------
def get_region_for_city(city: str) -> Dict[str, Any]:
    """
    Find the climate region for a given city.
    
    Args:
        city: City name (case-insensitive, partial match supported)
    
    Returns:
        Region data dict with region name included
    """
    city_lower = city.lower().strip()
    
    for region_name, region_data in SAUDI_CLIMATE_REGIONS.items():
        for region_city in region_data["cities"]:
            if (region_city.lower() in city_lower or 
                city_lower in region_city.lower()):
                return {"region": region_name, **region_data}
    
    # Default to central region (most conservative for temperature)
    return {"region": "central", **SAUDI_CLIMATE_REGIONS["central"]}


def get_wind_speed_for_city(city: str) -> float:
    """
    Get basic wind speed for structural design.
    
    Args:
        city: City name
    
    Returns:
        Wind speed in m/s
    """
    city_lower = city.lower().strip()
    
    for region_data in WIND_LOAD_REGIONS.values():
        for region_city in region_data["cities"]:
            if (region_city.lower() in city_lower or 
                city_lower in region_city.lower()):
                return region_data["basic_wind_speed_ms"]
    
    # Default conservative value
    return 42.0


def get_design_temperatures(city: str) -> Dict[str, float]:
    """
    Get design temperatures for a city.
    
    Returns:
        Dict with tmin, tmax, extreme_tmin
    """
    region = get_region_for_city(city)
    return {
        "tmin": region.get("design_temp_min_c", 0),
        "tmax": region.get("design_temp_max_c", 50),
        "extreme_tmin": region.get("extreme_temp_min_c", -5),
    }


def get_sec_protection_settings() -> Dict[str, Any]:
    """Get SEC protection relay settings."""
    return SEC_CONNECTION_STANDARDS["protection_settings"]


def get_sec_technical_requirements() -> Dict[str, Any]:
    """Get SEC technical requirements."""
    return SEC_CONNECTION_STANDARDS["technical_requirements"]


def get_inspection_checklist() -> Dict[str, Any]:
    """Get SEC inspection checklist."""
    return SEC_INSPECTION_CHECKLIST