"""Quick Report Generation package."""

from __future__ import annotations

from src.quick_report.compiler import (
    DocumentCompiler,
    FakeDocumentCompiler,
    WordComDocumentCompiler,
)
from src.quick_report.composer import QuickReportComposer
from src.quick_report.extractor import DAILY_DATE_FOLDER_PATTERN, QuickReportExtractor
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.transformer import QuickReportTransformer

__all__ = [
    "DAILY_DATE_FOLDER_PATTERN",
    "DocumentCompiler",
    "FakeDocumentCompiler",
    "QuickReportComposer",
    "QuickReportExtractor",
    "QuickReportStationPlan",
    "QuickReportTransformer",
    "WordComDocumentCompiler",
]
