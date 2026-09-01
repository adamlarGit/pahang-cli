"""WhatsApp report workflow orchestrator for Pahang CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from docxtpl import DocxTemplate

from src.core.normalizers import format_date_cbm, normalize_for_report
from src.project.environment import ProjectEnvironment
from src.project.storage import get_next_file_number
from src.whatsapp.models import WhatsAppReportResources
from src.workflows.models import WhatsAppReportRequest, WhatsAppReportResult

QUALIFYING_DOCX_PATTERN = re.compile(
    r"^(\d+)\.?\s*(.*?)\s*(?:\((.*?)\))?\.docx$",
    re.IGNORECASE,
)



@dataclass(frozen=True)
class WhatsAppRawTuple:
    """Raw data entities extracted for WhatsApp report workflow."""

    substation_docx_files: list[Path]
    total_pe_df: pd.DataFrame
    resources: WhatsAppReportResources


@dataclass(frozen=True)
class WhatsAppTargetEntity:
    """Target substation record parsed and validated for WhatsApp report."""

    substation_number: int
    substation_name: str
    defect: str
    msms: str
    raw_date: Any
    fl_number: str


@dataclass(frozen=True)
class WhatsAppReportPlan:
    """Immutable transformation plan for rendering WhatsApp report."""

    template_path: Path
    save_dir: Path
    context: dict[str, Any]
    substations_count: int
    station_name: str
    report_date: str


class WhatsAppReportPreflightGuard:
    """Pre-flight validation stage for WhatsApp report workflow."""

    def validate(self, env: ProjectEnvironment, request: WhatsAppReportRequest) -> None:
        report_dir = request.report_dir
        if report_dir is None:
            raise ValueError("report_dir cannot be None. It must be provided in the request.")

        report_dir_path = Path(report_dir)
        if not report_dir_path.exists() or not report_dir_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {report_dir}")

        has_qualifying = False
        for child in report_dir_path.iterdir():
            if child.is_file() and child.suffix.lower() == ".docx":
                if QUALIFYING_DOCX_PATTERN.match(child.name):
                    has_qualifying = True
                    break
        if not has_qualifying:
            raise ValueError(f"No qualifying PE DOCX files found in {report_dir_path}")

        resources = env.get_whatsapp_report_resources()
        if not resources.template_path.exists():
            raise FileNotFoundError(f"Template file not found at {resources.template_path}")

        if not resources.total_pe_path.exists():
            raise FileNotFoundError(f"TOTAL PE workbook not found at {resources.total_pe_path}")
            
        try:
            with pd.ExcelFile(resources.total_pe_path) as xls:
                if "DataCycle1" not in xls.sheet_names:
                    raise RuntimeError("DataCycle1 sheet not found in TOTAL PE workbook")
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError("DataCycle1 sheet not found in TOTAL PE workbook") from e


class WhatsAppReportExtractor:
    """Pure Read I/O extraction stage for WhatsApp report workflow."""

    def extract(self, env: ProjectEnvironment, request: WhatsAppReportRequest) -> WhatsAppRawTuple:
        resources = env.get_whatsapp_report_resources()
        report_dir_path = Path(request.report_dir)  # type: ignore[arg-type]

        substation_docx_files = self._scan_qualifying_docx_files(report_dir_path)
        total_pe_df = self._load_total_pe_dataframe(resources.total_pe_path)

        return WhatsAppRawTuple(
            substation_docx_files=substation_docx_files,
            total_pe_df=total_pe_df,
            resources=resources,
        )

    def _scan_qualifying_docx_files(self, report_dir_path: Path) -> list[Path]:
        substation_docx_files = []
        for child in report_dir_path.iterdir():
            if child.is_file() and child.suffix.lower() == ".docx":
                if QUALIFYING_DOCX_PATTERN.match(child.name):
                    substation_docx_files.append(child)

        substation_docx_files.sort(
            key=lambda p: int(QUALIFYING_DOCX_PATTERN.match(p.name).group(1))  # type: ignore[union-attr]
        )
        return substation_docx_files

    def _load_total_pe_dataframe(self, total_pe_path: Path) -> pd.DataFrame:
        return pd.read_excel(
            total_pe_path,
            sheet_name="DataCycle1",
            parse_dates=["DATE"],
        )


class WhatsAppReportFilter:
    """Pure validation and predicate logic stage for WhatsApp report workflow."""

    def filter(self, raw: WhatsAppRawTuple) -> list[WhatsAppTargetEntity]:
        targets = []
        for docx_path in raw.substation_docx_files:
            parsed = self._parse_docx_target(docx_path)
            if not parsed:
                continue

            substation_number, stem_name, defect_val = parsed
            sub_name, wo_val, raw_date, fl_num = self._lookup_substation_row(
                raw.total_pe_df, substation_number, stem_name
            )

            targets.append(
                WhatsAppTargetEntity(
                    substation_number=substation_number,
                    substation_name=sub_name,
                    defect=defect_val,
                    msms=wo_val,
                    raw_date=raw_date,
                    fl_number=fl_num,
                )
            )

        if not any(t.raw_date is not None for t in targets):
            raise ValueError("No valid inspection dates found in PE reports")

        return targets

    def _parse_docx_target(self, docx_path: Path) -> tuple[int, str, str] | None:
        match = QUALIFYING_DOCX_PATTERN.match(docx_path.name)
        if not match:
            return None

        prefix_str, stem_name, suffix_str = match.groups()
        substation_number = int(prefix_str)
        defect_val = suffix_str.strip() if (suffix_str and suffix_str.strip()) else "-"
        return substation_number, stem_name, defect_val

    def _lookup_substation_row(
        self, total_pe_df: pd.DataFrame, substation_number: int, stem_name: str
    ) -> tuple[str, str, Any, str]:
        substation_matches = total_pe_df[
            total_pe_df["PE NO"].apply(
                lambda x: int(x) if pd.notna(x) and str(x).strip().isdigit() else -1
            ) == substation_number
        ]

        if not substation_matches.empty:
            row = substation_matches.iloc[0]
            sub_name = (
                str(row["SUBSTATION NAME"])
                if pd.notna(row["SUBSTATION NAME"]) and str(row["SUBSTATION NAME"]).strip()
                else stem_name.strip()
            )
            wo_val = normalize_for_report(row["WO"])
            raw_date = row["DATE"] if pd.notna(row["DATE"]) else None
            fl_num = str(row["FL NUMBER"]).strip() if pd.notna(row["FL NUMBER"]) else ""
        else:
            sub_name = stem_name.strip() if stem_name and stem_name.strip() else f"PE {substation_number}"
            wo_val = "-"
            raw_date = None
            fl_num = ""

        return sub_name, wo_val, raw_date, fl_num


class WhatsAppReportTransformer:
    """Pure transformation and plan construction stage for WhatsApp report workflow."""

    def transform(
        self, targets: list[WhatsAppTargetEntity], resources: WhatsAppReportResources
    ) -> WhatsAppReportPlan:
        items = []
        report_date = None
        station_name = "UNKNOWN STATION"

        for t in targets:
            items.append({
                "name": t.substation_name,
                "defect": t.defect,
                "msms": t.msms,
            })
            if report_date is None and t.raw_date is not None:
                formatted_dt = format_date_cbm(t.raw_date)
                if formatted_dt != "-":
                    report_date = formatted_dt
                    station_code = t.fl_number[:4] if len(t.fl_number) >= 4 else t.fl_number
                    station_name = resources.station_mapping.get(
                        station_code, f"UNKNOWN ({station_code})"
                    )


        if report_date is None:
            raise ValueError("No valid inspection dates found in PE reports")

        context = {
            "date": report_date,
            "station": station_name,
            "items": items,
        }

        return WhatsAppReportPlan(
            template_path=resources.template_path,
            save_dir=resources.save_dir,
            context=context,
            substations_count=len(items),
            station_name=station_name,
            report_date=report_date,
        )


class WhatsAppReportLoader:
    """Pure docx template rendering and disk write stage for WhatsApp report workflow."""

    def load(self, plan: WhatsAppReportPlan) -> Path:
        doc = DocxTemplate(plan.template_path)
        doc.render(plan.context)

        plan.save_dir.mkdir(parents=True, exist_ok=True)
        next_num = get_next_file_number(plan.save_dir)
        clean_date = plan.report_date.replace("/", "-")
        output_path = plan.save_dir / f"{next_num:02d}. {plan.station_name} {clean_date}.docx"

        doc.save(output_path)
        return output_path


class WhatsAppReportAuditor:
    """Verification and history logging stage for WhatsApp report workflow."""

    def audit(self, plan: WhatsAppReportPlan, output_path: Path) -> WhatsAppReportResult:
        if not output_path.exists():
            raise RuntimeError(f"Output file was not created at {output_path}")
        if output_path.stat().st_size == 0:
            raise RuntimeError(f"Output file at {output_path} is empty (0 bytes)")
            
        return WhatsAppReportResult(
            substations_count=plan.substations_count,
            output_path=output_path,
        )


class WhatsAppReportWorkflow:
    """Orchestrates WhatsApp summary report generation.

    Resilience Policy: atomic
    All-or-nothing execution. Any unhandled stage exception aborts the entire workflow.
    """

    def __init__(
        self,
        preflight_guard: WhatsAppReportPreflightGuard | None = None,
        extractor: WhatsAppReportExtractor | None = None,
        filter_stage: WhatsAppReportFilter | None = None,
        transformer: WhatsAppReportTransformer | None = None,
        loader: WhatsAppReportLoader | None = None,
        auditor: WhatsAppReportAuditor | None = None,
    ) -> None:
        self.preflight_guard = preflight_guard or WhatsAppReportPreflightGuard()
        self.extractor = extractor or WhatsAppReportExtractor()
        self.filter_stage = filter_stage or WhatsAppReportFilter()
        self.transformer = transformer or WhatsAppReportTransformer()
        self.loader = loader or WhatsAppReportLoader()
        self.auditor = auditor or WhatsAppReportAuditor()

    def execute(
        self, env: ProjectEnvironment, request: WhatsAppReportRequest
    ) -> WhatsAppReportResult:
        if request.progress_sink:
            request.progress_sink("Validating environment and inputs for WhatsApp report...")

        self.preflight_guard.validate(env, request)

        if request.progress_sink:
            request.progress_sink("Extracting raw PE report files and data...")

        raw_data = self.extractor.extract(env, request)

        if request.progress_sink:
            request.progress_sink("Filtering substation targets...")

        targets = self.filter_stage.filter(raw_data)

        if request.progress_sink:
            request.progress_sink("Building WhatsApp report plan...")

        plan = self.transformer.transform(targets, raw_data.resources)

        if request.progress_sink:
            request.progress_sink("Rendering and saving WhatsApp report document...")

        load_output = self.loader.load(plan)

        if request.progress_sink:
            request.progress_sink("Auditing created report file...")

        result = self.auditor.audit(plan, load_output)
        return result


def run_generate_whatsapp_report(
    env: ProjectEnvironment,
    report_dir: Path | str,
    progress_sink: ProgressSink | None = None,
) -> WhatsAppReportResult:
    """Execute WhatsApp report generation workflow for a specific date/report folder."""
    workflow = WhatsAppReportWorkflow()
    request = WhatsAppReportRequest(report_dir=Path(report_dir), progress_sink=progress_sink)
    return workflow.execute(env, request)

