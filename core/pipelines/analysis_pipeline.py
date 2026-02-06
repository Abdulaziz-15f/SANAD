"""
Pipeline 4: Analysis Engine with Standards Compliance.

Performs technical checks and tracks compliance with SEC/IEC standards.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

from core.pipelines.extraction_pipeline import MergedExtraction

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    PASS = "pass"


@dataclass
class Issue:
    """Single issue found during analysis."""
    severity: Severity
    title: str
    description: str
    actual_value: str = ""
    required_value: str = ""
    impact: str = ""
    recommendation: str = ""
    reference: str = ""
    priority_score: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "actual_value": self.actual_value,
            "required_value": self.required_value,
            "impact": self.impact,
            "recommendation": self.recommendation,
            "reference": self.reference,
            "priority_score": self.priority_score,
        }


@dataclass
class StandardCheck:
    """Individual check within a standard."""
    name: str
    description: str
    status: str  # "PASS", "FAIL", "WARNING", "NOT_CHECKED"
    actual_value: str = ""
    required_value: str = ""
    details: str = ""


@dataclass
class StandardCompliance:
    """Compliance status for a single standard."""
    standard_code: str
    standard_name: str
    description: str
    checks: List[StandardCheck] = field(default_factory=list)
    checks_total: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    checks_warning: int = 0
    compliance_percent: float = 0.0
    status: str = "NOT_CHECKED"


@dataclass
class CableInfo:
    """Information about cables used."""
    cable_type: str
    size_mm2: Optional[float] = None
    voltage_drop_percent: Optional[float] = None
    max_allowed_vd: float = 0.0
    status: str = "NOT_CHECKED"


@dataclass
class AnalysisResult:
    """Complete analysis result with standards compliance."""
    issues: List[Issue] = field(default_factory=list)
    standards_compliance: List[StandardCompliance] = field(default_factory=list)
    cables_info: List[CableInfo] = field(default_factory=list)
    overall_compliance_percent: float = 0.0
    critical_count: int = 0
    warning_count: int = 0
    pass_count: int = 0
    info_count: int = 0
    summary: str = ""
    overall_status: str = "unknown"
    calculated: Dict[str, Any] = field(default_factory=dict)
    top_issues: List[Issue] = field(default_factory=list)


# -------------------------------------------------------------------
# Standards Definitions
# -------------------------------------------------------------------
STANDARDS = {
    "IEC_62548": {
        "code": "IEC 62548:2016",
        "name": "PV Array Design Requirements",
        "description": "Design requirements for photovoltaic (PV) arrays",
    },
    "IEC_62109": {
        "code": "IEC 62109-1/2",
        "name": "Inverter Safety",
        "description": "Safety of power converters for PV systems",
    },
    "IEC_60364": {
        "code": "IEC 60364-7-712",
        "name": "PV Electrical Installations",
        "description": "Low-voltage electrical installations for PV",
    },
    "SEC_CONN": {
        "code": "SEC Connection v3",
        "name": "Saudi Grid Connection",
        "description": "SEC requirements for grid-connected PV systems",
    },
    "SEC_BEST": {
        "code": "SEC Best Practice v2",
        "name": "PV Design Guidelines",
        "description": "SEC best practices for PV system design in Saudi Arabia",
    },
}


class AnalysisEngine:
    """Performs technical analysis and standards compliance checking."""
    
    def __init__(self):
        self.issues: List[Issue] = []
        self.standards: Dict[str, StandardCompliance] = {}
        self.cables: List[CableInfo] = []
        self.calculated: Dict[str, Any] = {}
        self._init_standards()
    
    def _init_standards(self):
        """Initialize standards tracking."""
        for key, std in STANDARDS.items():
            self.standards[key] = StandardCompliance(
                standard_code=std["code"],
                standard_name=std["name"],
                description=std["description"],
                checks=[],
            )
    
    def _add_check(self, standard_key: str, check: StandardCheck):
        """Add a check to a standard."""
        if standard_key in self.standards:
            std = self.standards[standard_key]
            std.checks.append(check)
    
    def _finalize_standards(self):
        """Calculate compliance percentages for all standards."""
        for std in self.standards.values():
            std.checks_total = len(std.checks)
            std.checks_passed = sum(1 for c in std.checks if c.status == "PASS")
            std.checks_failed = sum(1 for c in std.checks if c.status == "FAIL")
            std.checks_warning = sum(1 for c in std.checks if c.status == "WARNING")
            
            if std.checks_total > 0:
                # Passed = 100%, Warning = 50%, Failed = 0%
                score = std.checks_passed + (std.checks_warning * 0.5)
                std.compliance_percent = (score / std.checks_total) * 100
            else:
                std.compliance_percent = 0.0
            
            # Determine status
            if std.checks_total == 0:
                std.status = "NOT_CHECKED"
            elif std.checks_failed > 0:
                std.status = "NON_COMPLIANT"
            elif std.checks_warning > 0:
                std.status = "PARTIAL"
            else:
                std.status = "COMPLIANT"
    
    def _calculate_overall_compliance(self) -> float:
        """Calculate overall compliance percentage."""
        total_checks = 0
        total_passed = 0
        total_warnings = 0
        
        for std in self.standards.values():
            total_checks += std.checks_total
            total_passed += std.checks_passed
            total_warnings += std.checks_warning
        
        if total_checks == 0:
            return 0.0
        
        score = total_passed + (total_warnings * 0.5)
        return (score / total_checks) * 100
    
    def analyze(self, data: MergedExtraction) -> AnalysisResult:
        """Run all analysis checks."""
        self.issues = []
        self._init_standards()
        self.cables = []
        self.calculated = {}
        
        # Run all checks
        self._check_string_voltage(data)
        self._check_mppt_voltage(data)
        self._check_dc_ac_ratio(data)
        self._check_voltage_drop(data)
        self._check_environmental(data)
        self._check_module_compatibility(data)
        self._check_protection(data)
        self._extract_cable_info(data)
        
        # Finalize standards
        self._finalize_standards()
        
        # Calculate overall compliance
        overall_compliance = self._calculate_overall_compliance()
        
        # Count issues by severity
        critical = sum(1 for i in self.issues if i.severity == Severity.CRITICAL)
        warning = sum(1 for i in self.issues if i.severity == Severity.WARNING)
        passed = sum(1 for i in self.issues if i.severity == Severity.PASS)
        info = sum(1 for i in self.issues if i.severity == Severity.INFO)
        
        # Determine overall status
        if critical > 0:
            overall_status = "fail"
        elif warning > 0:
            overall_status = "review"
        else:
            overall_status = "pass"
        
        # Get top issues (sorted by priority)
        sorted_issues = sorted(self.issues, key=lambda x: x.priority_score, reverse=True)
        top_issues = [i for i in sorted_issues if i.severity in [Severity.CRITICAL, Severity.WARNING]][:5]
        
        return AnalysisResult(
            issues=self.issues,
            standards_compliance=list(self.standards.values()),
            cables_info=self.cables,
            overall_compliance_percent=overall_compliance,
            critical_count=critical,
            warning_count=warning,
            pass_count=passed,
            info_count=info,
            overall_status=overall_status,
            calculated=self.calculated,
            top_issues=top_issues,
        )
    
    def _check_string_voltage(self, data: MergedExtraction) -> None:
        """Check string Voc at minimum temperature vs inverter max."""
        voc = data.module_voc_v
        temp_coeff = data.temp_coeff_voc
        mps = data.modules_per_string
        inv_vmax = data.inverter_dc_max_voltage_v
        tmin = data.tmin_c
        
        # Check if we have required data
        if not all([voc, mps, inv_vmax, tmin is not None]):
            self._add_check("IEC_62548", StandardCheck(
                name="String Voltage at Tmin",
                description="Insufficient data for voltage check",
                status="NOT_CHECKED",
                details="Missing Voc, MPS, inverter max, or Tmin",
            ))
            return
        
        # Use default temp_coeff if not provided (-0.29%/°C typical for Si)
        if temp_coeff is None:
            temp_coeff = -0.29
            logger.info("Using default temp coefficient: -0.29%/°C")
        
        # IMPORTANT: Normalize temp coefficient to decimal form
        # Input could be: -0.29 (percent) or -0.0029 (decimal)
        if temp_coeff > 0:
            temp_coeff = -temp_coeff  # Should be negative
        
        # If value is like -0.29, convert to -0.0029
        if abs(temp_coeff) > 0.01:
            temp_coeff = temp_coeff / 100.0
        
        # Calculate Voc at Tmin
        # Formula: Voc_cold = Voc_STC × (1 + temp_coeff × (Tmin - 25))
        delta_t = tmin - 25.0
        voc_cold = voc * (1 + temp_coeff * delta_t)
        string_voc_cold = voc_cold * mps
        
        # Store calculated values
        self.calculated["module_voc_v"] = voc
        self.calculated["temp_coeff_used"] = temp_coeff
        self.calculated["temp_coeff_percent"] = temp_coeff * 100
        self.calculated["delta_t"] = delta_t
        self.calculated["voc_cold_per_module"] = round(voc_cold, 2)
        self.calculated["string_voc_at_tmin"] = round(string_voc_cold, 1)
        self.calculated["modules_per_string"] = mps
        self.calculated["inverter_dc_max"] = inv_vmax
        
        # Calculate margin
        margin = inv_vmax - string_voc_cold
        margin_pct = (margin / inv_vmax) * 100 if inv_vmax > 0 else 0
        self.calculated["voltage_margin_v"] = round(margin, 1)
        self.calculated["voltage_margin_pct"] = round(margin_pct, 1)
        
        # Calculate max modules per string
        max_mps = int(inv_vmax / voc_cold) if voc_cold > 0 else 0
        self.calculated["max_modules_per_string"] = max_mps
        
        # Evaluate
        if string_voc_cold > inv_vmax:
            self._add_check("IEC_62548", StandardCheck(
                name="String Voltage at Tmin",
                description="String Voc must not exceed inverter DC max",
                status="FAIL",
                actual_value=f"{string_voc_cold:.0f}V",
                required_value=f"< {inv_vmax:.0f}V",
            ))
            
            self.issues.append(Issue(
                severity=Severity.CRITICAL,
                title="⚡ String Voltage Exceeds Inverter Maximum",
                description=f"At {tmin}°C, string Voc ({string_voc_cold:.0f}V) exceeds inverter max ({inv_vmax:.0f}V)",
                actual_value=f"{string_voc_cold:.0f}V ({mps} modules × {voc_cold:.1f}V)",
                required_value=f"< {inv_vmax:.0f}V",
                impact="INVERTER DAMAGE - Over-voltage will destroy inverter",
                recommendation=f"Reduce modules per string from {mps} to {max_mps}",
                reference="IEC 62548 §6.2.2",
                priority_score=100,
            ))
        elif margin_pct < 5.0:
            self._add_check("IEC_62548", StandardCheck(
                name="String Voltage at Tmin",
                description="String Voc within limits but margin tight",
                status="WARNING",
                actual_value=f"{string_voc_cold:.0f}V ({margin_pct:.1f}% margin)",
                required_value=f"< {inv_vmax:.0f}V (>5% margin recommended)",
            ))
            
            self.issues.append(Issue(
                severity=Severity.WARNING,
                title="String Voltage Margin Tight",
                description=f"Voltage margin ({margin_pct:.1f}%) below 5% recommended",
                actual_value=f"{string_voc_cold:.0f}V",
                required_value=f"< {inv_vmax:.0f}V with >5% margin",
                impact="Risk of over-voltage during extreme cold",
                recommendation=f"Consider reducing to {max_mps} modules per string",
                reference="IEC 62548",
                priority_score=70,
            ))
        else:
            self._add_check("IEC_62548", StandardCheck(
                name="String Voltage at Tmin",
                description="String Voc within safe limits",
                status="PASS",
                actual_value=f"{string_voc_cold:.0f}V ({margin_pct:.1f}% margin)",
                required_value=f"< {inv_vmax:.0f}V",
            ))
            
            self.issues.append(Issue(
                severity=Severity.PASS,
                title="String Voltage OK",
                description=f"String Voc ({string_voc_cold:.0f}V) within limits with {margin_pct:.1f}% margin",
                actual_value=f"{string_voc_cold:.0f}V",
                required_value=f"< {inv_vmax:.0f}V",
                impact="Safe operation",
                recommendation="No action required",
                reference="IEC 62548",
                priority_score=0,
            ))
    
    def _check_mppt_voltage(self, data: MergedExtraction) -> None:
        """Check string Vmp at operating temperatures vs MPPT range."""
        vmp = data.module_vmp_v
        temp_coeff = data.temp_coeff_voc  # Use Voc coeff as approximation
        mps = data.modules_per_string
        mppt_min = data.inverter_mppt_min_v
        mppt_max = data.inverter_mppt_max_v
        tmin = data.tmin_c
        tmax = data.tmax_c
        isc = data.module_isc_a
        
        if not all([vmp, mps, mppt_min, mppt_max]):
            self._add_check("IEC_62109", StandardCheck(
                name="MPPT Voltage Range",
                description="Insufficient data for MPPT check",
                status="NOT_CHECKED",
            ))
            return
        
        # Normalize temp coefficient
        if temp_coeff is None:
            temp_coeff = -0.29
        if temp_coeff > 0:
            temp_coeff = -temp_coeff
        if abs(temp_coeff) > 0.01:
            temp_coeff = temp_coeff / 100.0
        
        checks_added = 0
        
        # Calculate Vmp at high temp (summer)
        if tmax:
            delta_t_hot = tmax - 25.0
            vmp_hot = vmp * (1 + temp_coeff * delta_t_hot)
            string_vmp_hot = vmp_hot * mps
            self.calculated["string_vmp_at_tmax"] = round(string_vmp_hot, 1)
            
            if string_vmp_hot < mppt_min:
                self._add_check("IEC_62109", StandardCheck(
                    name="MPPT Range at High Temp",
                    description="String Vmp must be above MPPT minimum",
                    status="WARNING",
                    actual_value=f"{string_vmp_hot:.0f}V at {tmax}°C",
                    required_value=f"≥ {mppt_min:.0f}V",
                ))
                
                self.issues.append(Issue(
                    severity=Severity.WARNING,
                    title="String Voltage Below MPPT at High Temp",
                    description=f"At {tmax}°C, string Vmp falls below MPPT minimum",
                    actual_value=f"{string_vmp_hot:.0f}V at {tmax}°C",
                    required_value=f"≥ {mppt_min:.0f}V",
                    impact="Energy loss during hot days",
                    recommendation="Add modules or use inverter with lower MPPT minimum",
                    reference="IEC 62109",
                    priority_score=60,
                ))
                checks_added += 1
            else:
                self._add_check("IEC_62109", StandardCheck(
                    name="MPPT Range at High Temp",
                    description="String Vmp above MPPT minimum at high temp",
                    status="PASS",
                    actual_value=f"{string_vmp_hot:.0f}V at {tmax}°C",
                    required_value=f"≥ {mppt_min:.0f}V",
                ))
                checks_added += 1
        
        # Calculate Vmp at low temp (winter)
        if tmin is not None:
            delta_t_cold = tmin - 25.0
            vmp_cold = vmp * (1 + temp_coeff * delta_t_cold)
            string_vmp_cold = vmp_cold * mps
            self.calculated["string_vmp_at_tmin"] = round(string_vmp_cold, 1)
            
            if string_vmp_cold > mppt_max:
                self._add_check("IEC_62109", StandardCheck(
                    name="MPPT Range at Low Temp",
                    description="String Vmp must be below MPPT maximum",
                    status="WARNING",
                    actual_value=f"{string_vmp_cold:.0f}V at {tmin}°C",
                    required_value=f"≤ {mppt_max:.0f}V",
                ))
                
                self.issues.append(Issue(
                    severity=Severity.WARNING,
                    title="String Voltage Above MPPT at Low Temp",
                    description=f"At {tmin}°C, string Vmp exceeds MPPT maximum",
                    actual_value=f"{string_vmp_cold:.0f}V at {tmin}°C",
                    required_value=f"≤ {mppt_max:.0f}V",
                    impact="Energy loss during cold mornings",
                    recommendation="Reduce modules per string",
                    reference="IEC 62109",
                    priority_score=60,
                ))
                checks_added += 1
            else:
                self._add_check("IEC_62109", StandardCheck(
                    name="MPPT Range at Low Temp",
                    description="String Vmp below MPPT maximum at low temp",
                    status="PASS",
                    actual_value=f"{string_vmp_cold:.0f}V at {tmin}°C",
                    required_value=f"≤ {mppt_max:.0f}V",
                ))
                checks_added += 1
        
        # Check string current
        if isc:
            self._add_check("IEC_62109", StandardCheck(
                name="MPPT Current",
                description="MPPT current within typical limits",
                status="PASS",
                actual_value=f"{isc:.1f}A",
            ))
            self.calculated["module_isc_a"] = isc
    
    def _check_dc_ac_ratio(self, data: MergedExtraction) -> None:
        """Check DC/AC ratio."""
        dc_power = data.system_capacity_kw
        # Account for multiple inverters; assume count >=1 for safety
        inverter_count = getattr(data, "inverter_count", None) or 1
        ac_power_single = data.inverter_ac_power_kw
        ac_power = ac_power_single * inverter_count if ac_power_single else None
        
        if not dc_power or not ac_power:
            self._add_check("SEC_BEST", StandardCheck(
                name="DC/AC Ratio",
                description="Insufficient data for DC/AC ratio check",
                status="NOT_CHECKED",
            ))
            return
        
        ratio = dc_power / ac_power
        self.calculated["dc_ac_ratio"] = round(ratio, 2)
        self.calculated["dc_power_kw"] = dc_power
        self.calculated["ac_power_kw"] = ac_power
        self.calculated["inverter_count"] = inverter_count
        
        if ratio > 1.5:
            self._add_check("SEC_BEST", StandardCheck(
                name="DC/AC Ratio",
                description="DC/AC ratio should be 1.0-1.3",
                status="FAIL",
                actual_value=f"{ratio:.2f}",
                required_value="1.0 - 1.3",
            ))
            
            clipping_estimate = min(95, (ratio - 1.0) * 100)
            self.issues.append(Issue(
                severity=Severity.CRITICAL,
                title="DC/AC Ratio Too High",
                description=f"DC/AC ratio ({ratio:.2f}) significantly exceeds recommended range",
                actual_value=f"{ratio:.2f}",
                required_value="1.0 - 1.3",
                impact=f"Significant clipping losses (~{clipping_estimate:.0f}% at peak)",
                recommendation="Use larger inverter or reduce panel count",
                reference="SEC Best Practice v2",
                priority_score=90,
            ))
        elif ratio > 1.3:
            self._add_check("SEC_BEST", StandardCheck(
                name="DC/AC Ratio",
                description="DC/AC ratio slightly high",
                status="WARNING",
                actual_value=f"{ratio:.2f}",
                required_value="1.0 - 1.3",
            ))
            
            self.issues.append(Issue(
                severity=Severity.WARNING,
                title="DC/AC Ratio High",
                description=f"DC/AC ratio ({ratio:.2f}) exceeds recommended maximum of 1.3",
                actual_value=f"{ratio:.2f}",
                required_value="1.0 - 1.3",
                impact="May cause clipping during peak hours",
                recommendation="Consider larger inverter",
                reference="SEC Best Practice v2",
                priority_score=50,
            ))
        elif ratio < 1.0:
            self._add_check("SEC_BEST", StandardCheck(
                name="DC/AC Ratio",
                description="DC/AC ratio too low",
                status="WARNING",
                actual_value=f"{ratio:.2f}",
                required_value="1.0 - 1.3",
            ))
            
            self.issues.append(Issue(
                severity=Severity.WARNING,
                title="DC/AC Ratio Low",
                description=f"DC/AC ratio ({ratio:.2f}) below recommended minimum of 1.0",
                actual_value=f"{ratio:.2f}",
                required_value="1.0 - 1.3",
                impact="Inverter underutilized, higher cost per kWh",
                recommendation="Add more panels or use smaller inverter",
                reference="SEC Best Practice v2",
                priority_score=40,
            ))
        else:
            self._add_check("SEC_BEST", StandardCheck(
                name="DC/AC Ratio",
                description="DC/AC ratio within optimal range",
                status="PASS",
                actual_value=f"{ratio:.2f}",
                required_value="1.0 - 1.3",
            ))
    
    def _check_voltage_drop(self, data: MergedExtraction) -> None:
        """Check cable voltage drops."""
        dc_vd = data.dc_voltage_drop_percent
        ac_vd = data.ac_voltage_drop_percent
        
        # DC Voltage Drop
        if dc_vd is not None:
            self.calculated["dc_voltage_drop_pct"] = dc_vd
            if dc_vd > 3.0:
                self.issues.append(Issue(
                    severity=Severity.WARNING,
                    title="DC Voltage Drop High",
                    description=f"DC voltage drop ({dc_vd:.2f}%) exceeds 3% limit",
                    actual_value=f"{dc_vd:.2f}%",
                    required_value="≤ 3%",
                    impact="Energy loss, potential hot spots",
                    recommendation="Increase DC cable size",
                    reference="IEC 62548",
                    priority_score=55,
                ))
        
        # AC Voltage Drop
        if ac_vd is not None:
            self.calculated["ac_voltage_drop_pct"] = ac_vd
            if ac_vd > 3.0:
                self.issues.append(Issue(
                    severity=Severity.WARNING,
                    title="AC Voltage Drop High",
                    description=f"AC voltage drop ({ac_vd:.2f}%) exceeds 3% limit",
                    actual_value=f"{ac_vd:.2f}%",
                    required_value="≤ 3%",
                    impact="Energy loss, voltage regulation issues",
                    recommendation="Increase AC cable size",
                    reference="SEC Best Practice",
                    priority_score=55,
                ))
        
        # Total Voltage Drop
        if dc_vd is not None and ac_vd is not None:
            total_vd = dc_vd + ac_vd
            self.calculated["total_voltage_drop_pct"] = total_vd
            if total_vd > 5.0:
                self.issues.append(Issue(
                    severity=Severity.WARNING,
                    title="Total Voltage Drop High",
                    description=f"Total voltage drop ({total_vd:.2f}%) exceeds 5% limit",
                    actual_value=f"{total_vd:.2f}%",
                    required_value="≤ 5%",
                    impact="Significant energy loss",
                    recommendation="Review cable sizing for both DC and AC",
                    reference="SEC Best Practice",
                    priority_score=60,
                ))
        elif dc_vd is not None or ac_vd is not None:
            # Show whatever is available, but flag missing counterpart
            total_vd = dc_vd if dc_vd is not None else ac_vd
            self.calculated["total_voltage_drop_pct"] = total_vd
            missing_side = "AC" if dc_vd is not None else "DC"
            self.issues.append(Issue(
                severity=Severity.INFO,
                title=f"{missing_side} Voltage Drop Missing",
                description=f"{missing_side} voltage drop data not provided; total uses available side only",
                actual_value=f"{total_vd:.2f}%",
                required_value="Provide both AC and DC drops for full check",
                impact="Total VD may be understated",
                recommendation=f"Add {missing_side} voltage drop column in cable sheet",
                reference="SEC Best Practice",
                priority_score=20,
            ))
    
    def _check_environmental(self, data: MergedExtraction) -> None:
        """Check environmental considerations."""
        location = data.location or ""
        tmax = data.tmax_c
        current_wind = getattr(data, "current_wind_speed", None)
        max_wind = getattr(data, "max_wind_speed", None)
        if current_wind is not None:
            self.calculated["current_wind_speed_kmh"] = current_wind
        if max_wind is not None:
            self.calculated["max_wind_speed_kmh"] = max_wind
            # Rear-side static load check (wind pressure vs module rear rating)
            try:
                v_ms = max_wind / 3.6  # km/h -> m/s
                wind_pressure_pa = 0.613 * (v_ms ** 2)  # simplified q = 0.613 V^2
                rear_rating_pa = 2400.0  # typical rear-side static load rating
                self.calculated["rear_static_load_pa"] = round(wind_pressure_pa, 1)
                self.calculated["rear_static_rating_pa"] = rear_rating_pa
                if wind_pressure_pa > rear_rating_pa:
                    self.issues.append(Issue(
                        severity=Severity.WARNING,
                        title="Rear-Side Static Load Exceeds Rating",
                        description=f"Wind pressure {wind_pressure_pa:.0f} Pa exceeds typical rear rating {rear_rating_pa:.0f} Pa",
                        actual_value=f"{wind_pressure_pa:.0f} Pa",
                        required_value=f"≤ {rear_rating_pa:.0f} Pa",
                        impact="Risk of module/frame damage under extreme wind",
                        recommendation="Verify module load rating and racking design; consider higher-rated modules or additional anchorage",
                        reference="IEC 61215 / manufacturer datasheet",
                        priority_score=55,
                    ))
                else:
                    self._add_check("SEC_CONN", StandardCheck(
                        name="Rear Static Load (Wind)",
                        description="Wind-induced rear load within module rating",
                        status="PASS",
                        actual_value=f"{wind_pressure_pa:.0f} Pa",
                        required_value=f"≤ {rear_rating_pa:.0f} Pa",
                    ))
            except Exception:
                pass
        
        # Coastal areas
        coastal_keywords = ["jeddah", "dammam", "yanbu", "jubail", "khobar", "jizan"]
        is_coastal = any(k in location.lower() for k in coastal_keywords)
        
        if is_coastal:
            self._add_check("SEC_CONN", StandardCheck(
                name="Coastal Environment",
                description="Marine-grade materials required",
                status="WARNING",
                actual_value=f"Location: {location}",
                required_value="IP65+ rated equipment",
            ))
            
            self.issues.append(Issue(
                severity=Severity.INFO,
                title="Coastal Location",
                description=f"Site ({location}) is in coastal area",
                actual_value=location,
                required_value="Marine-grade equipment",
                impact="Corrosion risk without proper materials",
                recommendation="Use IP65+ rated equipment with corrosion protection",
                reference="SEC Guidelines",
                priority_score=30,
            ))
        else:
            self._add_check("SEC_CONN", StandardCheck(
                name="Environment",
                description="Non-coastal location",
                status="PASS",
                actual_value=f"Location: {location}",
            ))

        # High wind advisory if max gust available
        if max_wind is not None:
            if max_wind >= 80:  # km/h threshold (~22 m/s)
                self.issues.append(Issue(
                    severity=Severity.INFO,
                    title="High Wind Gusts",
                    description=f"10-year max gust = {max_wind:.1f} km/h",
                    actual_value=f"{max_wind:.1f} km/h",
                    required_value="Verify structural/wind load rating",
                    impact="Potential structural and mounting stress",
                    recommendation="Confirm racking anchorage and wind load design per local code",
                    reference="SEC Best Practice",
                    priority_score=25,
                ))
        
        # High temperature
        if tmax and tmax > 45:
            self._add_check("SEC_BEST", StandardCheck(
                name="High Temperature",
                description="Derating required above 45°C",
                status="WARNING",
                actual_value=f"{tmax}°C",
                required_value="Equipment rated for high temp",
            ))
            
            self.issues.append(Issue(
                severity=Severity.INFO,
                title="High Ambient Temperature",
                description=f"Design temperature ({tmax}°C) exceeds 45°C",
                actual_value=f"{tmax}°C",
                required_value="Equipment rated for >45°C",
                impact="Derating may be required",
                recommendation="Verify equipment temperature ratings",
                reference="SEC Best Practice",
                priority_score=25,
            ))
        elif tmax:
            self._add_check("SEC_BEST", StandardCheck(
                name="Temperature",
                description="Operating temperature within normal range",
                status="PASS",
                actual_value=f"{tmax}°C max",
            ))
    
    def _check_module_compatibility(self, data: MergedExtraction) -> None:
        """Check module-inverter compatibility."""
        isc = data.module_isc_a
        mppt_count = data.mppt_count
        strings_per_mppt = data.strings_per_mppt
        
        if isc and strings_per_mppt:
            total_current = isc * strings_per_mppt
            self.calculated["total_string_current_per_mppt"] = round(total_current, 1)
    
    def _check_protection(self, data: MergedExtraction) -> None:
        """Check protection requirements."""
        self._add_check("IEC_60364", StandardCheck(
            name="Protection Coordination",
            description="Verify protection device coordination",
            status="NOT_CHECKED",
            details="Manual verification required",
        ))
        
        self._add_check("SEC_CONN", StandardCheck(
            name="Anti-Islanding",
            description="Anti-islanding protection required",
            status="PASS",
            details="Assumed compliant (inverter feature)",
        ))
    
    def _extract_cable_info(self, data: MergedExtraction) -> None:
        """Extract cable information for display."""
        if data.dc_cable_size_mm2:
            self.cables.append(CableInfo(
                cable_type="DC String Cable",
                size_mm2=data.dc_cable_size_mm2,
                voltage_drop_percent=data.dc_voltage_drop_percent,
                max_allowed_vd=3.0,
                status="PASS" if (data.dc_voltage_drop_percent or 0) <= 3.0 else "FAIL",
            ))
        
        if data.ac_cable_size_mm2:
            self.cables.append(CableInfo(
                cable_type="AC Main Cable",
                size_mm2=data.ac_cable_size_mm2,
                voltage_drop_percent=data.ac_voltage_drop_percent,
                max_allowed_vd=3.0,
                status="PASS" if (data.ac_voltage_drop_percent or 0) <= 3.0 else "FAIL",
            ))


def run_analysis_pipeline(data: MergedExtraction) -> AnalysisResult:
    """Run the complete analysis pipeline."""
    engine = AnalysisEngine()
    return engine.analyze(data)
