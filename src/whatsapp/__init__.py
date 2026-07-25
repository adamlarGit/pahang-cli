"""WhatsApp report generation deep module."""

from src.whatsapp.generator import (
    QUALIFYING_PDF_PATTERN,
    build_quick_report_batch_confirmation_lines,
    generate_whatsapp_report,
    get_quick_report_batch_option_title,
    is_selectable_quick_report_batch,
    list_qualifying_batch_pdfs,
)
from src.whatsapp.models import (
    WhatsAppReportItem,
    WhatsAppReportResources,
    WhatsAppReportSummary,
)

__all__ = [
    "generate_whatsapp_report",
    "WhatsAppReportResources",
    "WhatsAppReportSummary",
    "WhatsAppReportItem",
    "list_qualifying_batch_pdfs",
    "is_selectable_quick_report_batch",
    "get_quick_report_batch_option_title",
    "build_quick_report_batch_confirmation_lines",
    "QUALIFYING_PDF_PATTERN",
]
