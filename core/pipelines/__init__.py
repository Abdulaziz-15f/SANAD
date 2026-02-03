"""
SANAD Pipelines Package.
"""
from core.pipelines.extraction_pipeline import (
    run_full_extraction,
    merge_extractions,
    MergedExtraction,
    SLDExtraction,
    PVModuleExtraction,
    InverterExtraction,
    CableExtraction,
    CableExtractor,
    GeminiVisionExtractor,
    OCRExtractor,
    AIMergeEngine,
)

from core.pipelines.analysis_pipeline import (
    run_analysis_pipeline,
    AnalysisResult,
    Issue,
    Severity,
)

from core.pipelines.report_generator import (
    generate_report,
    SANADReportBuilder,
)

__all__ = [
    # Extraction
    "run_full_extraction",
    "merge_extractions",
    "MergedExtraction",
    "SLDExtraction",
    "PVModuleExtraction",
    "InverterExtraction",
    "CableExtraction",
    "CableExtractor",
    "GeminiVisionExtractor",
    "OCRExtractor",
    "AIMergeEngine",
    # Analysis
    "run_analysis_pipeline",
    "AnalysisResult",
    "Issue",
    "Severity",
    # Report
    "generate_report",
    "SANADReportBuilder",
]