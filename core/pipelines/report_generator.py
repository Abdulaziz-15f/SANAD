"""
Stage 3: PDF Report Generator.

Generates comprehensive compliance reports with ALL data from the review.
"""
from __future__ import annotations
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
    ListFlowable,
    ListItem,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

from core.pipelines.extraction_pipeline import MergedExtraction
from core.pipelines.analysis_pipeline import AnalysisResult, Issue, Severity, StandardCompliance


# -------------------------------------------------------------------
# Color Scheme (SANAD Brand)
# -------------------------------------------------------------------
COLORS = {
    "primary": colors.HexColor("#1a5f2a"),
    "secondary": colors.HexColor("#2d8f45"),
    "accent": colors.HexColor("#4CAF50"),
    "critical": colors.HexColor("#dc3545"),
    "warning": colors.HexColor("#ffc107"),
    "info": colors.HexColor("#17a2b8"),
    "pass": colors.HexColor("#28a745"),
    "light_gray": colors.HexColor("#f8f9fa"),
    "dark_gray": colors.HexColor("#343a40"),
    "text": colors.HexColor("#212529"),
    "white": colors.white,
}


# -------------------------------------------------------------------
# Custom Styles
# -------------------------------------------------------------------
def get_custom_styles():
    """Create custom styles for the report."""
    styles = getSampleStyleSheet()
    
    def add_style(name, **kwargs):
        if name not in styles.byName:
            styles.add(ParagraphStyle(name=name, **kwargs))
    
    add_style('ReportTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=COLORS["primary"],
        alignment=TA_CENTER,
        spaceAfter=20,
        spaceBefore=20,
    )
    
    add_style('SectionHeader',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=COLORS["primary"],
        spaceBefore=15,
        spaceAfter=10,
        fontName='Helvetica-Bold',
    )
    
    add_style('SubsectionHeader',
        parent=styles['Heading3'],
        fontSize=11,
        textColor=COLORS["secondary"],
        spaceBefore=10,
        spaceAfter=5,
        fontName='Helvetica-Bold',
    )
    
    add_style('SANADBody',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=6,
        leading=12,
    )
    
    add_style('SmallText',
        parent=styles['Normal'],
        fontSize=8,
        spaceAfter=4,
        leading=10,
    )
    
    add_style('CriticalText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=COLORS["critical"],
        spaceAfter=4,
        fontName='Helvetica-Bold',
    )
    
    add_style('WarningText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor("#856404"),
        spaceAfter=4,
        fontName='Helvetica-Bold',
    )
    
    add_style('PassText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=COLORS["pass"],
        spaceAfter=4,
        fontName='Helvetica-Bold',
    )
    
    add_style('InfoText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=COLORS["info"],
        spaceAfter=4,
    )
    
    add_style('TableHeader',
        parent=styles['Normal'],
        fontSize=9,
        textColor=COLORS["white"],
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    
    add_style('TableCell',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_LEFT,
    )
    
    add_style('TableCellCenter',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
    )
    
    add_style('Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor("#999999"),
        alignment=TA_CENTER,
    )
    
    add_style('StatusPass',
        parent=styles['Normal'],
        fontSize=18,
        textColor=COLORS["pass"],
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    
    add_style('StatusReview',
        parent=styles['Normal'],
        fontSize=18,
        textColor=colors.HexColor("#856404"),
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    
    add_style('StatusFail',
        parent=styles['Normal'],
        fontSize=18,
        textColor=COLORS["critical"],
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    
    return styles


# -------------------------------------------------------------------
# Report Builder
# -------------------------------------------------------------------
class SANADReportBuilder:
    """Builds comprehensive PDF compliance reports."""
    
    def __init__(
        self,
        merged: MergedExtraction,
        analysis: AnalysisResult,
        calculated: Dict[str, Any],
        project_name: str = "PV System Design Review",
        standards_compliance: List[StandardCompliance] = None,
    ):
        self.merged = merged
        self.analysis = analysis
        self.calculated = calculated
        self.project_name = project_name
        self.standards_compliance = standards_compliance or []
        self.styles = get_custom_styles()
        self.elements = []
    
    def build(self) -> bytes:
        """Build the complete PDF report."""
        buffer = io.BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.5*cm,
            leftMargin=1.5*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
        )
        
        self.elements = []
        
        # Build sections
        self._add_cover_page()
        self._add_executive_summary()
        self._add_key_calculations()
        self._add_system_specifications()
        self._add_standards_compliance()
        self._add_all_issues()
        self._add_detailed_calculations()
        self._add_standards_reference()
        
        # Build PDF
        doc.build(
            self.elements,
            onFirstPage=self._add_header_footer,
            onLaterPages=self._add_header_footer
        )
        
        buffer.seek(0)
        return buffer.getvalue()
    
    def _add_header_footer(self, canvas, doc):
        """Add header and footer to each page."""
        canvas.saveState()
        
        # Header
        canvas.setFillColor(COLORS["primary"])
        canvas.setFont('Helvetica-Bold', 10)
        canvas.drawString(1.5*cm, A4[1] - 1.2*cm, "SANAD")
        
        canvas.setFillColor(COLORS["dark_gray"])
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(A4[0] - 1.5*cm, A4[1] - 1.2*cm, "PV Design Compliance Report")
        
        # Header line
        canvas.setStrokeColor(COLORS["primary"])
        canvas.setLineWidth(0.5)
        canvas.line(1.5*cm, A4[1] - 1.5*cm, A4[0] - 1.5*cm, A4[1] - 1.5*cm)
        
        # Footer
        canvas.setFillColor(COLORS["dark_gray"])
        canvas.setFont('Helvetica', 8)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        canvas.drawString(1.5*cm, 1*cm, f"Generated: {date_str}")
        canvas.drawCentredString(A4[0]/2, 1*cm, self.project_name[:50])
        canvas.drawRightString(A4[0] - 1.5*cm, 1*cm, f"Page {doc.page}")
        
        # Footer line
        canvas.line(1.5*cm, 1.3*cm, A4[0] - 1.5*cm, 1.3*cm)
        
        canvas.restoreState()
    
    def _add_cover_page(self):
        """Add cover page with overall status."""
        self.elements.append(Spacer(1, 2*cm))
        
        # Logo/Title
        self.elements.append(Paragraph(
            "SANAD",
            ParagraphStyle(
                name='CoverLogo',
                fontSize=48,
                textColor=COLORS["primary"],
                alignment=TA_CENTER,
                fontName='Helvetica-Bold',
                spaceAfter=10,
            )
        ))
        
        self.elements.append(Paragraph(
            "Smart Automated Network for Auditing and Design Compliance",
            ParagraphStyle(
                name='CoverTagline',
                fontSize=11,
                textColor=COLORS["secondary"],
                alignment=TA_CENTER,
                spaceAfter=30,
            )
        ))
        
        self.elements.append(HRFlowable(
            width="60%",
            thickness=2,
            color=COLORS["primary"],
            spaceBefore=10,
            spaceAfter=30,
        ))
        
        # Report title
        self.elements.append(Paragraph(
            "PV System Design<br/>Compliance Report",
            self.styles['ReportTitle']
        ))
        
        self.elements.append(Spacer(1, 1*cm))
        
        # Project info table
        project_info = [
            ["Project:", self.project_name or "N/A"],
            ["Location:", self.merged.location or "N/A"],
            ["Review Date:", datetime.now().strftime("%B %d, %Y")],
            ["System Capacity:", f"{self.merged.system_capacity_kw:.0f} kWp" if self.merged.system_capacity_kw else "N/A"],
            ["Design Temp Range:", f"{self.merged.tmin_c}°C to {self.merged.tmax_c}°C" if self.merged.tmin_c is not None else "N/A"],
        ]
        
        project_table = Table(project_info, colWidths=[4*cm, 10*cm])
        project_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), COLORS["dark_gray"]),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        self.elements.append(project_table)
        
        self.elements.append(Spacer(1, 1.5*cm))
        
        # Overall status
        status = self.analysis.overall_status
        if status == "pass":
            status_text = "✓ DESIGN APPROVED"
            status_style = 'StatusPass'
            status_color = COLORS["pass"]
        elif status == "review":
            status_text = "⚠ REVIEW REQUIRED"
            status_style = 'StatusReview'
            status_color = COLORS["warning"]
        else:
            status_text = "✗ DESIGN REJECTED"
            status_style = 'StatusFail'
            status_color = COLORS["critical"]
        
        self.elements.append(Paragraph(status_text, self.styles[status_style]))
        
        # Compliance percentage
        compliance_pct = self.analysis.overall_compliance_percent
        self.elements.append(Spacer(1, 0.5*cm))
        self.elements.append(Paragraph(
            f"Overall Compliance: {compliance_pct:.0f}%",
            ParagraphStyle(
                name='CompliancePct',
                fontSize=14,
                textColor=status_color,
                alignment=TA_CENTER,
            )
        ))
        
        self.elements.append(PageBreak())
    
    def _add_executive_summary(self):
        """Add executive summary section."""
        self.elements.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
        self.elements.append(HRFlowable(width="100%", thickness=1, color=COLORS["primary"]))
        self.elements.append(Spacer(1, 0.3*cm))
        
        # Issue counts
        summary_data = [
            ["Metric", "Count", "Status"],
            ["Critical Issues", str(self.analysis.critical_count), 
             "FAIL" if self.analysis.critical_count > 0 else "PASS"],
            ["Warnings", str(self.analysis.warning_count), 
             "REVIEW" if self.analysis.warning_count > 0 else "PASS"],
            ["Info Items", str(self.analysis.info_count), "INFO"],
            ["Overall Compliance", f"{self.analysis.overall_compliance_percent:.0f}%", 
             "PASS" if self.analysis.overall_compliance_percent >= 80 else "REVIEW"],
        ]
        
        summary_table = Table(summary_data, colWidths=[6*cm, 4*cm, 4*cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS["primary"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLORS["white"]),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            # Color coding for status
            ('BACKGROUND', (2, 1), (2, 1), COLORS["critical"] if self.analysis.critical_count > 0 else COLORS["pass"]),
            ('TEXTCOLOR', (2, 1), (2, 1), COLORS["white"]),
            ('BACKGROUND', (2, 2), (2, 2), COLORS["warning"] if self.analysis.warning_count > 0 else COLORS["pass"]),
            ('BACKGROUND', (2, 3), (2, 3), COLORS["info"]),
            ('TEXTCOLOR', (2, 3), (2, 3), COLORS["white"]),
        ]))
        self.elements.append(summary_table)
        self.elements.append(Spacer(1, 0.5*cm))
    
    def _add_key_calculations(self):
        """Add key calculations section."""
        self.elements.append(Paragraph("Key Calculations", self.styles['SectionHeader']))
        self.elements.append(HRFlowable(width="100%", thickness=1, color=COLORS["primary"]))
        self.elements.append(Spacer(1, 0.3*cm))
        
        calc = self.calculated
        
        # Key metrics table
        key_data = [
            ["Parameter", "Value", "Limit/Target", "Status"],
        ]
        
        # String Voc at Tmin
        voc_tmin = calc.get("string_voc_at_tmin")
        inv_max = self.merged.inverter_dc_max_voltage_v
        margin = calc.get("voltage_margin_pct")
        if voc_tmin and inv_max:
            status = "PASS" if voc_tmin < inv_max else "FAIL"
            key_data.append([
                "String Voc at Tmin",
                f"{voc_tmin:.0f} V",
                f"< {inv_max:.0f} V",
                f"{status} ({margin:.1f}% margin)" if margin else status
            ])
        
        # DC/AC Ratio
        ratio = calc.get("dc_ac_ratio")
        if ratio:
            if ratio > 1.5:
                status = "FAIL"
            elif ratio > 1.3:
                status = "WARNING"
            elif ratio < 1.0:
                status = "WARNING"
            else:
                status = "PASS"
            key_data.append([
                "DC/AC Ratio",
                f"{ratio:.2f}",
                "1.0 - 1.3",
                status
            ])
        
        # String Vmp at Tmax
        vmp_tmax = calc.get("string_vmp_at_tmax")
        mppt_min = self.merged.inverter_mppt_min_v
        if vmp_tmax and mppt_min:
            status = "PASS" if vmp_tmax >= mppt_min else "WARNING"
            key_data.append([
                "String Vmp at Tmax",
                f"{vmp_tmax:.0f} V",
                f"≥ {mppt_min:.0f} V",
                status
            ])
        
        # String Vmp at Tmin
        vmp_tmin = calc.get("string_vmp_at_tmin")
        mppt_max = self.merged.inverter_mppt_max_v
        if vmp_tmin and mppt_max:
            status = "PASS" if vmp_tmin <= mppt_max else "WARNING"
            key_data.append([
                "String Vmp at Tmin",
                f"{vmp_tmin:.0f} V",
                f"≤ {mppt_max:.0f} V",
                status
            ])
        
        # Voltage drops
        dc_vd = calc.get("dc_voltage_drop_pct")
        if dc_vd is not None:
            status = "PASS" if dc_vd <= 3.0 else "WARNING"
            key_data.append(["DC Voltage Drop", f"{dc_vd:.2f}%", "≤ 3.0%", status])
        
        ac_vd = calc.get("ac_voltage_drop_pct")
        if ac_vd is not None:
            status = "PASS" if ac_vd <= 3.0 else "WARNING"
            key_data.append(["AC Voltage Drop", f"{ac_vd:.2f}%", "≤ 3.0%", status])
        
        total_vd = calc.get("total_voltage_drop_pct")
        if total_vd is not None:
            status = "PASS" if total_vd <= 5.0 else "WARNING"
            key_data.append(["Total Voltage Drop", f"{total_vd:.2f}%", "≤ 5.0%", status])
        
        if len(key_data) > 1:
            key_table = Table(key_data, colWidths=[5*cm, 3.5*cm, 3.5*cm, 4*cm])
            key_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), COLORS["primary"]),
                ('TEXTCOLOR', (0, 0), (-1, 0), COLORS["white"]),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            self.elements.append(key_table)
        
        self.elements.append(Spacer(1, 0.5*cm))
    
    def _add_system_specifications(self):
        """Add system specifications section."""
        self.elements.append(Paragraph("System Specifications", self.styles['SectionHeader']))
        self.elements.append(HRFlowable(width="100%", thickness=1, color=COLORS["primary"]))
        self.elements.append(Spacer(1, 0.3*cm))
        
        # Create two-column layout
        col_width = 8*cm
        
        # PV Module specs
        self.elements.append(Paragraph("PV Module", self.styles['SubsectionHeader']))
        
        pv_data = [
            ["Parameter", "Value"],
            ["Model", str(self.merged.module_model or "N/A")],
            ["Pmax", f"{self.merged.module_pmax_w} W" if self.merged.module_pmax_w else "N/A"],
            ["Voc", f"{self.merged.module_voc_v} V" if self.merged.module_voc_v else "N/A"],
            ["Isc", f"{self.merged.module_isc_a} A" if self.merged.module_isc_a else "N/A"],
            ["Vmp", f"{self.merged.module_vmp_v} V" if self.merged.module_vmp_v else "N/A"],
            ["Imp", f"{self.merged.module_imp_a} A" if self.merged.module_imp_a else "N/A"],
            ["Temp Coeff (Voc)", f"{self.merged.temp_coeff_voc}%/°C" if self.merged.temp_coeff_voc else "N/A"],
        ]
        
        pv_table = Table(pv_data, colWidths=[4.5*cm, 4*cm])
        pv_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS["secondary"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLORS["white"]),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        self.elements.append(pv_table)
        self.elements.append(Spacer(1, 0.3*cm))
        
        # Inverter specs
        self.elements.append(Paragraph("Inverter", self.styles['SubsectionHeader']))
        
        inv_data = [
            ["Parameter", "Value"],
            ["Model", str(self.merged.inverter_model or "N/A")],
            ["DC Max Voltage", f"{self.merged.inverter_dc_max_voltage_v} V" if self.merged.inverter_dc_max_voltage_v else "N/A"],
            ["MPPT Min", f"{self.merged.inverter_mppt_min_v} V" if self.merged.inverter_mppt_min_v else "N/A"],
            ["MPPT Max", f"{self.merged.inverter_mppt_max_v} V" if self.merged.inverter_mppt_max_v else "N/A"],
            ["AC Power", f"{self.merged.inverter_ac_power_kw} kW" if self.merged.inverter_ac_power_kw else "N/A"],
            ["MPPT Count", str(self.merged.mppt_count) if self.merged.mppt_count else "N/A"],
        ]
        
        inv_table = Table(inv_data, colWidths=[4.5*cm, 4*cm])
        inv_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS["secondary"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLORS["white"]),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        self.elements.append(inv_table)
        self.elements.append(Spacer(1, 0.3*cm))
        
        # System configuration
        self.elements.append(Paragraph("System Configuration", self.styles['SubsectionHeader']))
        
        sys_data = [
            ["Parameter", "Value"],
            ["System Capacity", f"{self.merged.system_capacity_kw:.0f} kW" if self.merged.system_capacity_kw else "N/A"],
            ["Modules per String", str(self.merged.modules_per_string or "N/A")],
            ["Strings per MPPT", str(self.merged.strings_per_mppt or "N/A")],
            ["Total Strings", str(int(self.merged.total_strings) if self.merged.total_strings else "N/A")],
            ["Location", str(self.merged.location or "N/A")],
            ["Design Tmin", f"{self.merged.tmin_c}°C" if self.merged.tmin_c is not None else "N/A"],
            ["Design Tmax", f"{self.merged.tmax_c}°C" if self.merged.tmax_c is not None else "N/A"],
        ]
        
        sys_table = Table(sys_data, colWidths=[4.5*cm, 4*cm])
        sys_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS["secondary"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLORS["white"]),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        self.elements.append(sys_table)
        
        # Cables section
        if self.merged.dc_cable_size_mm2 or self.merged.ac_cable_size_mm2:
            self.elements.append(Spacer(1, 0.3*cm))
            self.elements.append(Paragraph("Cables", self.styles['SubsectionHeader']))
            
            cable_data = [["Parameter", "Value"]]
            if self.merged.dc_cable_size_mm2:
                cable_data.append(["DC Cable Size", f"{self.merged.dc_cable_size_mm2} mm²"])
            if self.merged.ac_cable_size_mm2:
                cable_data.append(["AC Cable Size", f"{self.merged.ac_cable_size_mm2} mm²"])
            if self.merged.dc_voltage_drop_percent:
                cable_data.append(["DC Voltage Drop", f"{self.merged.dc_voltage_drop_percent:.2f}%"])
            if self.merged.ac_voltage_drop_percent:
                cable_data.append(["AC Voltage Drop", f"{self.merged.ac_voltage_drop_percent:.2f}%"])
            
            cable_table = Table(cable_data, colWidths=[4.5*cm, 4*cm])
            cable_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), COLORS["secondary"]),
                ('TEXTCOLOR', (0, 0), (-1, 0), COLORS["white"]),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            self.elements.append(cable_table)
        
        self.elements.append(Spacer(1, 0.5*cm))
    
    def _add_standards_compliance(self):
        """Add detailed standards compliance section."""
        self.elements.append(PageBreak())
        self.elements.append(Paragraph("Standards Compliance", self.styles['SectionHeader']))
        self.elements.append(HRFlowable(width="100%", thickness=1, color=COLORS["primary"]))
        self.elements.append(Spacer(1, 0.3*cm))
        
        # Overall compliance bar
        pct = self.analysis.overall_compliance_percent
        if pct >= 80:
            status_text = "COMPLIANT"
            status_color = COLORS["pass"]
        elif pct >= 50:
            status_text = "PARTIAL COMPLIANCE"
            status_color = COLORS["warning"]
        else:
            status_text = "NON-COMPLIANT"
            status_color = COLORS["critical"]
        
        self.elements.append(Paragraph(
            f"<b>Overall: {status_text} ({pct:.0f}%)</b>",
            ParagraphStyle(
                name='OverallCompliance',
                fontSize=12,
                textColor=status_color,
                spaceAfter=10,
            )
        ))
        
        # Individual standards
        standards = self.standards_compliance or self.analysis.standards_compliance
        
        for std in standards:
            if std.checks_total == 0:
                continue
            
            # Standard header
            if std.status == "COMPLIANT":
                status_icon = "✓"
                header_color = COLORS["pass"]
            elif std.status == "PARTIAL":
                status_icon = "⚠"
                header_color = COLORS["warning"]
            elif std.status == "NON_COMPLIANT":
                status_icon = "✗"
                header_color = COLORS["critical"]
            else:
                status_icon = "○"
                header_color = COLORS["dark_gray"]
            
            self.elements.append(Paragraph(
                f"<b>{status_icon} {std.standard_code}</b> - {std.standard_name} ({std.compliance_percent:.0f}%)",
                ParagraphStyle(
                    name=f'StdHeader_{std.standard_code}',
                    fontSize=10,
                    textColor=header_color,
                    spaceBefore=8,
                    spaceAfter=4,
                )
            ))
            
            self.elements.append(Paragraph(
                f"<i>{std.description}</i>",
                self.styles['SmallText']
            ))
            
            # Checks table
            if std.checks:
                check_data = [["Check", "Value", "Required", "Status"]]
                
                for check in std.checks:
                    if check.status == "PASS":
                        status = "✓ PASS"
                    elif check.status == "WARNING":
                        status = "⚠ WARN"
                    elif check.status == "FAIL":
                        status = "✗ FAIL"
                    else:
                        status = "○ N/A"
                    
                    check_data.append([
                        check.name[:30],
                        check.actual_value[:20] if check.actual_value else "-",
                        check.required_value[:20] if check.required_value else "-",
                        status
                    ])
                
                check_table = Table(check_data, colWidths=[5*cm, 4*cm, 4*cm, 2.5*cm])
                check_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), COLORS["light_gray"]),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('ALIGN', (3, 0), (3, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                    ('TOPPADDING', (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ]))
                self.elements.append(check_table)
            
            # Summary
            self.elements.append(Paragraph(
                f"Passed: {std.checks_passed} | Warnings: {std.checks_warning} | Failed: {std.checks_failed}",
                self.styles['SmallText']
            ))
        
        self.elements.append(Spacer(1, 0.5*cm))
    
    def _add_all_issues(self):
        """Add ALL issues section (not just top 5)."""
        self.elements.append(Paragraph("All Issues & Findings", self.styles['SectionHeader']))
        self.elements.append(HRFlowable(width="100%", thickness=1, color=COLORS["primary"]))
        self.elements.append(Spacer(1, 0.3*cm))
        
        # Get ALL issues
        all_issues = self.analysis.issues
        
        # Separate by severity
        critical_issues = [i for i in all_issues if i.severity == Severity.CRITICAL]
        warning_issues = [i for i in all_issues if i.severity == Severity.WARNING]
        info_issues = [i for i in all_issues if i.severity == Severity.INFO]
        pass_issues = [i for i in all_issues if i.severity == Severity.PASS]
        
        # Critical Issues
        if critical_issues:
            self.elements.append(Paragraph("Critical Issues", self.styles['CriticalText']))
            for i, issue in enumerate(critical_issues, 1):
                self._add_issue_detail(issue, i, "critical")
        
        # Warnings
        if warning_issues:
            self.elements.append(Spacer(1, 0.3*cm))
            self.elements.append(Paragraph("Warnings", self.styles['WarningText']))
            for i, issue in enumerate(warning_issues, 1):
                self._add_issue_detail(issue, i, "warning")
        
        # Info
        if info_issues:
            self.elements.append(Spacer(1, 0.3*cm))
            self.elements.append(Paragraph("Information", self.styles['InfoText']))
            for i, issue in enumerate(info_issues, 1):
                self._add_issue_detail(issue, i, "info")
        
        # Passed checks
        if pass_issues:
            self.elements.append(Spacer(1, 0.3*cm))
            self.elements.append(Paragraph("Passed Checks", self.styles['PassText']))
            for i, issue in enumerate(pass_issues, 1):
                self._add_issue_brief(issue, i)
        
        if not all_issues:
            self.elements.append(Paragraph("✓ No issues found.", self.styles['SANADBody']))
        
        self.elements.append(Spacer(1, 0.5*cm))
    
    def _add_issue_detail(self, issue: Issue, num: int, severity: str):
        """Add detailed issue entry."""
        if severity == "critical":
            prefix = "🔴"
            style = self.styles['CriticalText']
        elif severity == "warning":
            prefix = "🟡"
            style = self.styles['WarningText']
        else:
            prefix = "🔵"
            style = self.styles['InfoText']
        
        self.elements.append(Paragraph(
            f"<b>{prefix} #{num}: {issue.title}</b>",
            ParagraphStyle(
                name=f'Issue_{num}',
                fontSize=9,
                textColor=style.textColor,
                spaceBefore=4,
                spaceAfter=2,
            )
        ))
        
        # Issue details table
        details = []
        if issue.actual_value:
            details.append(["Actual:", issue.actual_value])
        if issue.required_value:
            details.append(["Required:", issue.required_value])
        if issue.impact:
            details.append(["Impact:", issue.impact])
        if issue.reference:
            details.append(["Reference:", issue.reference])
        if issue.recommendation:
            details.append(["Recommendation:", issue.recommendation])
        
        if details:
            detail_table = Table(details, colWidths=[3*cm, 12*cm])
            detail_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ]))
            self.elements.append(detail_table)
        
        if issue.description:
            self.elements.append(Paragraph(
                f"<i>{issue.description}</i>",
                ParagraphStyle(
                    name=f'IssueDesc_{num}',
                    fontSize=8,
                    textColor=colors.grey,
                    leftIndent=15,
                    spaceAfter=4,
                )
            ))
    
    def _add_issue_brief(self, issue: Issue, num: int):
        """Add brief passed check entry."""
        self.elements.append(Paragraph(
            f"✓ {issue.title}: {issue.actual_value or issue.description}",
            ParagraphStyle(
                name=f'PassedCheck_{num}',
                fontSize=8,
                textColor=COLORS["pass"],
                leftIndent=10,
                spaceAfter=2,
            )
        ))
    
    def _add_detailed_calculations(self):
        """Add all calculated values."""
        self.elements.append(PageBreak())
        self.elements.append(Paragraph("Detailed Calculations", self.styles['SectionHeader']))
        self.elements.append(HRFlowable(width="100%", thickness=1, color=COLORS["primary"]))
        self.elements.append(Spacer(1, 0.3*cm))
        
        calc_data = [["Parameter", "Value"]]
        
        for key, value in self.calculated.items():
            # Skip internal keys
            if key.startswith("_"):
                continue
            
            # Format the key nicely
            nice_key = key.replace("_", " ").title()
            
            # Format the value
            if isinstance(value, float):
                nice_value = f"{value:.4f}" if abs(value) < 1 else f"{value:.2f}"
            else:
                nice_value = str(value)
            
            calc_data.append([nice_key, nice_value])
        
        if len(calc_data) > 1:
            calc_table = Table(calc_data, colWidths=[8*cm, 6*cm])
            calc_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), COLORS["primary"]),
                ('TEXTCOLOR', (0, 0), (-1, 0), COLORS["white"]),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            self.elements.append(calc_table)
        else:
            self.elements.append(Paragraph("No calculations available.", self.styles['SANADBody']))
        
        self.elements.append(Spacer(1, 0.5*cm))
    
    def _add_standards_reference(self):
        """Add standards reference section."""
        self.elements.append(Paragraph("Applicable Standards Reference", self.styles['SectionHeader']))
        self.elements.append(HRFlowable(width="100%", thickness=1, color=COLORS["primary"]))
        self.elements.append(Spacer(1, 0.3*cm))
        
        standards_data = [
            ["Standard", "Description", "Application"],
            ["IEC 62548:2016", "PV Array Design Requirements", "String sizing, voltage limits, cable sizing"],
            ["IEC 62109-1/2", "Inverter Safety Requirements", "DC input limits, MPPT range, protection"],
            ["IEC 60364-7-712", "PV Electrical Installations", "Wiring, disconnection, labeling"],
            ["SEC Connection v3", "Saudi Grid Connection Standards", "Power factor, frequency, anti-islanding"],
            ["SEC Best Practice v2", "PV Design Guidelines", "DC/AC ratio, cable sizing, environmental"],
        ]
        
        standards_table = Table(standards_data, colWidths=[3.5*cm, 5*cm, 6*cm])
        standards_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COLORS["primary"]),
            ('TEXTCOLOR', (0, 0), (-1, 0), COLORS["white"]),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        self.elements.append(standards_table)
        
        # Add formulas used
        self.elements.append(Spacer(1, 0.5*cm))
        self.elements.append(Paragraph("Calculation Formulas", self.styles['SubsectionHeader']))
        
        formulas = [
            "• Voc at Tmin = Voc_STC × [1 + (TempCoeff/100) × (Tmin - 25)]",
            "• String Voc = Voc_module × Modules_per_string",
            "• DC/AC Ratio = DC_capacity_kW / AC_inverter_kW",
            "• Voltage Margin = (Inverter_max - String_Voc) / Inverter_max × 100%",
        ]
        
        for formula in formulas:
            self.elements.append(Paragraph(formula, self.styles['SmallText']))
        
        self.elements.append(Spacer(1, 1*cm))
        
        # Disclaimer
        self.elements.append(Paragraph(
            "<b>Disclaimer:</b> This report is generated automatically based on extracted data. "
            "Manual verification is recommended for critical design decisions.",
            ParagraphStyle(
                name='Disclaimer',
                fontSize=8,
                textColor=colors.grey,
                alignment=TA_CENTER,
            )
        ))


# -------------------------------------------------------------------
# Main Function
# -------------------------------------------------------------------
def generate_report(
    merged: MergedExtraction,
    analysis: AnalysisResult,
    calculated: Dict[str, Any],
    project_name: str = "PV System Design Review",
    standards_compliance: List[StandardCompliance] = None,
) -> bytes:
    """
    Generate comprehensive PDF compliance report.
    
    Args:
        merged: Merged extraction data
        analysis: Analysis results
        calculated: Calculated values dict
        project_name: Project name for cover page
        standards_compliance: List of standard compliance objects
    
    Returns:
        PDF bytes
    """
    builder = SANADReportBuilder(
        merged=merged,
        analysis=analysis,
        calculated=calculated,
        project_name=project_name,
        standards_compliance=standards_compliance,
    )
    
    return builder.build()