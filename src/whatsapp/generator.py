"""Generator module for rendering WhatsApp report documents."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate
import pandas as pd

from src.project.environment import ProjectEnvironment
from src.project.storage import get_next_file_number
from src.whatsapp.models import (
    WhatsAppReportItem,
    WhatsAppReportResources,
    WhatsAppReportSummary,
)

QUALIFYING_PDF_PATTERN = re.compile(
    r"^(\d+)\.?\s*(.*?)\s*(?:\((.*?)\))?\.pdf$",
    re.IGNORECASE,
)


def _extract_pe_number(pdf_path: str | Path) -> int:
    match = QUALIFYING_PDF_PATTERN.match(Path(pdf_path).name)
    if match is None:
        raise ValueError(f"Invalid PE PDF filename: {pdf_path}")
    return int(match.group(1))


def list_qualifying_batch_pdfs(batch_dir: str | Path) -> list[Path]:
    """Return sorted qualifying PE PDFs from a quick-report batch folder."""
    batch_path = Path(batch_dir)
    if not batch_path.exists() or not batch_path.is_dir():
        return []

    qualifying_files: list[tuple[int, Path]] = []
    for child in batch_path.iterdir():
        if not child.is_file() or child.suffix.lower() != ".pdf":
            continue

        match = QUALIFYING_PDF_PATTERN.match(child.name)
        if not match:
            continue

        qualifying_files.append((int(match.group(1)), child))

    qualifying_files.sort(key=lambda item: item[0])
    return [path for _, path in qualifying_files]


def is_selectable_quick_report_batch(batch_dir: str | Path) -> bool:
    """Return whether a folder is a selectable quick-report batch."""
    return bool(list_qualifying_batch_pdfs(batch_dir))


def get_quick_report_batch_option_title(batch_dir: str | Path) -> str:
    """Return the selector label for a quick-report folder."""
    batch_path = Path(batch_dir)
    pdf_count = len(list_qualifying_batch_pdfs(batch_path))
    if pdf_count:
        return f"{batch_path.name} ({pdf_count} PDFs)"
    return batch_path.name


def build_quick_report_batch_confirmation_lines(
    root_dir: str | Path, batch_dir: str | Path
) -> list[str]:
    """Return confirmation summary lines for a selected quick-report batch."""
    root_path = Path(root_dir)
    batch_path = Path(batch_dir)
    qualifying_files = list_qualifying_batch_pdfs(batch_path)
    if not qualifying_files:
        return [f"No qualifying PDFs in batch: {batch_path.name}"]

    pe_numbers = [_extract_pe_number(path) for path in qualifying_files]
    try:
        relative_path = " / ".join(batch_path.relative_to(root_path).parts)
    except ValueError:
        relative_path = batch_path.name

    return [
        "Generate WhatsApp report for this batch?",
        f"Batch: {relative_path}",
        f"Qualifying PDFs: {len(qualifying_files)}",
        f"First PE: {pe_numbers[0]}",
        f"Last PE: {pe_numbers[-1]}",
    ]


def _format_report_date(val: Any) -> str | None:
    if pd.isna(val) or val is None or str(val).strip() == "":
        return None
    if hasattr(val, "strftime"):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip().replace("-", "/")
    parts = s.split("/")
    if len(parts) == 3:
        if len(parts[0]) == 4:
            return f"{int(parts[2]):02d}/{int(parts[1]):02d}/{int(parts[0]):04d}"
        elif len(parts[2]) == 4:
            return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{int(parts[2]):04d}"
    return s


def generate_whatsapp_report(
    env_or_resources: ProjectEnvironment | WhatsAppReportResources,
    report_dir: str | Path,
) -> WhatsAppReportSummary:
    """Generate a WhatsApp report docx from PDF filenames and TOTAL PE metadata."""
    if isinstance(env_or_resources, ProjectEnvironment):
        resources = env_or_resources.get_whatsapp_report_resources()
    elif isinstance(env_or_resources, WhatsAppReportResources):
        resources = env_or_resources
    else:
        raise TypeError("env_or_resources must be ProjectEnvironment or WhatsAppReportResources")

    report_dir_path = Path(report_dir)
    if not report_dir_path.exists() or not report_dir_path.is_dir():
        raise FileNotFoundError(f"Directory not found: {report_dir}")

    qualifying_pdfs = list_qualifying_batch_pdfs(report_dir_path)
    if not qualifying_pdfs:
        raise ValueError(f"No qualifying PE PDF files found in {report_dir_path}")

    if not resources.total_pe_path.exists():
        raise FileNotFoundError(f"TOTAL PE workbook not found at {resources.total_pe_path}")

    total_pe_df = pd.read_excel(
        resources.total_pe_path,
        sheet_name="DataCycle1",
        parse_dates=["DATE"],
    )

    items: list[dict[str, str]] = []
    report_date: str | None = None
    station_name: str = "UNKNOWN STATION"

    for pdf_path in qualifying_pdfs:
        match = QUALIFYING_PDF_PATTERN.match(pdf_path.name)
        if not match:
            continue

        prefix_str, stem_name, suffix_str = match.groups()
        prefix_num = int(prefix_str)
        defect_val = suffix_str.strip() if (suffix_str and suffix_str.strip()) else "-"

        pe_matches = total_pe_df[
            total_pe_df["PE NO"].apply(
                lambda x: int(x) if pd.notna(x) and str(x).strip().isdigit() else -1
            ) == prefix_num
        ]

        if not pe_matches.empty:
            row = pe_matches.iloc[0]
            sub_name = str(row["SUBSTATION NAME"]) if pd.notna(row["SUBSTATION NAME"]) and str(row["SUBSTATION NAME"]).strip() else stem_name.strip()
            wo_val = str(row["WO"]).strip() if pd.notna(row["WO"]) else "-"
            if wo_val.endswith(".0"):
                wo_val = wo_val[:-2]

            if report_date is None and pd.notna(row["DATE"]):
                formatted_dt = _format_report_date(row["DATE"])
                if formatted_dt:
                    report_date = formatted_dt
                    fl_number = str(row["FL NUMBER"]).strip() if pd.notna(row["FL NUMBER"]) else ""
                    station_code = fl_number[:4] if len(fl_number) >= 4 else fl_number
                    station_name = resources.station_mapping.get(
                        station_code, f"UNKNOWN ({station_code})"
                    )
        else:
            sub_name = stem_name.strip() if stem_name and stem_name.strip() else f"PE {prefix_num}"
            wo_val = "-"

        item = WhatsAppReportItem(
            name=sub_name,
            defect=defect_val,
            msms=wo_val,
        )
        items.append(item.to_dict())

    if report_date is None:
        raise ValueError("No valid inspection dates found in PE reports")

    context = {
        "date": report_date,
        "station": station_name,
        "items": items,
    }

    doc = DocxTemplate(resources.template_path)
    doc.render(context)

    resources.save_dir.mkdir(parents=True, exist_ok=True)
    next_num = get_next_file_number(resources.save_dir)
    clean_date = report_date.replace("/", "-")
    output_path = resources.save_dir / f"{next_num:02d}. {station_name} {clean_date}.docx"

    doc.save(output_path)

    return WhatsAppReportSummary(
        report_dir=report_dir_path,
        output_path=output_path,
        substations_count=len(items),
    )
