"""1-Click Post-Processing Pipeline orchestrating Steps 1-5 (preflight, renaming, whatsapp, signatures, diagonals, and PDF merge)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from src.postprocessing.converters import (
    ComDocumentConverter,
    DocumentConverter,
    batch_com_session,
)
from src.project.environment import ProjectEnvironment
from src.testsheet.models import SubstationPackage
from src.testsheet.repository import LocalTestsheetPackageRepository
from src.workflows.diagonal_borders import process_workbook
from src.workflows.models import (
    PostProcessingFailure,
    PostProcessingMode,
    PostProcessingRequest,
    PostProcessingSummary,
)
from src.workflows.postprocessing_preflight import validate_postprocessing_preflight
from src.workflows.rename_files import rename_files_match
from src.workflows.replace_signatures import replace_pce_images
from src.workflows.whatsapp import run_generate_whatsapp_report

logger = logging.getLogger(__name__)


def discover_substation_packages(env: ProjectEnvironment) -> list[SubstationPackage]:
    """Scan TESTSHEET/ and QUICK REPORT/ to discover paired substation workbooks and Word documents."""
    repo = LocalTestsheetPackageRepository()
    return repo.find_packages(env.get_testsheet_dir(), env.get_quick_report_dir())


class PostProcessingPipelineWorkflow:
    """Lean orchestrator service executing the 6-stage post-processing lifecycle."""

    def __init__(self, converter: DocumentConverter | None = None) -> None:
        self.converter = converter

    def execute(
        self,
        env: ProjectEnvironment,
        request: PostProcessingRequest | None = None,
    ) -> PostProcessingSummary:
        """Execute the post-processing pipeline according to the provided request."""
        req = request or PostProcessingRequest()
        sink = req.progress_sink or (lambda msg: None)

        sink("Starting Post-Processing Pipeline...")

        # Stage 1: Discovery & Scoping
        if req.target_packages:
            packages = list(req.target_packages)
        else:
            packages = discover_substation_packages(env)

        if not packages:
            sink("No substation packages found in workspace.")
            return PostProcessingSummary(
                processed_packages=(),
                final_deliverables=(),
                warnings=("No matching substation packages found to process.",),
            )

        target_packages: list[SubstationPackage] = []
        if req.mode == PostProcessingMode.BY_DATE:
            if req.target_dates:
                target_dates_set = {str(d).strip().strip('"').strip("'") for d in req.target_dates}
                target_packages = [
                    p for p in packages
                    if p.date_folder in target_dates_set
                    or p.testsheet_xlsx.parent.name in target_dates_set
                    or str(p.testsheet_xlsx.parent) in target_dates_set
                ]
            else:
                target_packages = list(packages)
        elif req.mode == PostProcessingMode.BY_FL:
            if req.target_fls:
                target_fls_set = {str(fl).strip().upper() for fl in req.target_fls}
                target_packages = [
                    p
                    for p in packages
                    if p.fl_erms.strip().upper() in target_fls_set
                    or p.station_name.strip().upper() in target_fls_set
                    or str(p.substation_number) in target_fls_set
                    or p.quick_report_docx.stem.strip().upper() in target_fls_set
                ]
            else:
                target_packages = list(packages)

        if not target_packages:
            sink("No matching substation packages found for target criteria.")
            return PostProcessingSummary(
                processed_packages=(),
                final_deliverables=(),
                warnings=("No matching substation packages found for target criteria.",),
            )

        sink(f"Queued {len(target_packages)} substation package(s) for processing.")

        # Stage 2: Pre-Flight Validation & Renaming Sync
        folder_groups: dict[Path, list[SubstationPackage]] = {}
        for pkg in target_packages:
            folder_groups.setdefault(pkg.testsheet_xlsx.parent, []).append(pkg)

        for ts_dir, pkgs in sorted(folder_groups.items(), key=lambda item: str(item[0])):
            first_pkg = pkgs[0]
            df_name = first_pkg.date_folder or ts_dir.name
            qr_dir = first_pkg.quick_report_docx.parent

            # Resolve corresponding raw material directory
            try:
                rel = ts_dir.relative_to(env.get_testsheet_dir())
                raw_mat_dir = env.get_raw_material_dir() / rel
            except ValueError:
                raw_mat_dir = env.get_raw_material_dir() / ts_dir.name

            # Pre-flight integrity validation (fail-fast)
            sink(f"Validating pre-flight file integrity for date folder '{df_name}'...")
            validate_postprocessing_preflight(
                env,
                date_folder=df_name,
                ts_dir=ts_dir,
                qr_dir=qr_dir,
                raw_dir=raw_mat_dir,
            )

            # Renaming sync
            if qr_dir.exists() and ts_dir.exists():
                try:
                    summary = rename_files_match(qr_dir, ts_dir, target_type="testsheet")
                    for pair in summary.renamed:
                        sink(f"Renamed testsheet in {df_name}: {pair.old_name} -> {pair.new_name}")
                except Exception as exc:
                    logger.warning("Testsheet renaming in %s skipped: %s", df_name, exc)

            if qr_dir.exists() and raw_mat_dir.exists():
                try:
                    summary = rename_files_match(qr_dir, raw_mat_dir, target_type="raw_material")
                    for pair in summary.renamed:
                        sink(f"Renamed raw material in {df_name}: {pair.old_name} -> {pair.new_name}")
                except Exception as exc:
                    logger.warning("Raw material renaming in %s skipped: %s", df_name, exc)

        # Refresh target packages after renaming sync
        refreshed_packages = discover_substation_packages(env)
        refreshed_map = {pkg.quick_report_docx.resolve(): pkg for pkg in refreshed_packages}
        updated_target_packages: list[SubstationPackage] = []
        for pkg in target_packages:
            res_qr = pkg.quick_report_docx.resolve()
            if res_qr in refreshed_map:
                updated_target_packages.append(refreshed_map[res_qr])
            else:
                updated_target_packages.append(pkg)
        target_packages = updated_target_packages

        # Stage 3: WhatsApp Reporting (BY_DATE mode only)
        if req.mode == PostProcessingMode.BY_DATE and req.generate_whatsapp:
            qr_date_dirs = {pkg.quick_report_docx.parent for pkg in target_packages if pkg.quick_report_docx.parent.exists()}
            for qr_dir in sorted(qr_date_dirs, key=lambda p: str(p)):
                try:
                    sink(f"Generating WhatsApp daily report for date folder '{qr_dir.name}'...")
                    wa_result = run_generate_whatsapp_report(env, qr_dir)
                    if wa_result and wa_result.output_path:
                        sink(f"WhatsApp report generated -> {wa_result.output_path.name}")
                except Exception as exc:
                    logger.warning("WhatsApp generation failed for %s: %s", qr_dir, exc)
                    sink(f"WhatsApp generation skipped for {qr_dir.name}: {exc}")

        # Stage 4: Substation Document Processing Loop (Inside batch_com_session)
        converter: DocumentConverter = req.converter or self.converter or ComDocumentConverter()
        processed_packages: list[SubstationPackage] = []
        final_deliverables: list[Path] = []
        failed_packages: list[PostProcessingFailure] = []
        warnings: list[str] = []

        start_time = time.time()

        if isinstance(ComDocumentConverter, type) and isinstance(converter, ComDocumentConverter):
            session_cm = batch_com_session()
        else:
            session_cm = batch_com_session(word_app=object(), excel_app=object())

        with session_cm as session:
            for i, pkg in enumerate(target_packages, start=1):

                sink(f"[{i}/{len(target_packages)}] Processing: {pkg.station_name} [{pkg.fl_erms}] ({pkg.date_folder})")
                try:
                    # 1. Working copy setup (Testsheet Immutability)
                    processed_xlsx_dir = pkg.testsheet_xlsx.parent / "processed_testsheet"
                    processed_xlsx_dir.mkdir(parents=True, exist_ok=True)
                    processed_xlsx = processed_xlsx_dir / pkg.testsheet_xlsx.name

                    # 2. Signatures: replace placeholders if enabled, or strip placeholders cleanly if disabled
                    if req.apply_signatures and (req.vendor_signature_path or req.tnb_signature_path):
                        replace_pce_images(
                            pkg.testsheet_xlsx,
                            req.vendor_signature_path,
                            req.tnb_signature_path,
                            output_path=processed_xlsx,
                            mode="placeholder",
                        )
                    else:
                        replace_pce_images(
                            pkg.testsheet_xlsx,
                            None,
                            None,
                            output_path=processed_xlsx,
                            mode="none",
                        )

                    # 3. Diagonals: apply diagonal borders to blank cells
                    process_workbook(processed_xlsx)

                    # 4. Testsheet PDF
                    testsheet_pdf_dir = processed_xlsx_dir / "pdf"
                    testsheet_pdf_dir.mkdir(parents=True, exist_ok=True)
                    testsheet_pdf = testsheet_pdf_dir / f"{pkg.testsheet_xlsx.stem}.pdf"
                    converter.convert_testsheet_to_pdf(processed_xlsx, testsheet_pdf, session=session)

                    # 5. Quick Report DOCX to PDF
                    quick_report_pdf = pkg.quick_report_docx.with_suffix(".pdf")
                    converter.convert_docx_to_pdf(pkg.quick_report_docx, quick_report_pdf, session=session)

                    # 6. PDF Merge: combine in-place into quick_report_pdf
                    converter.merge_pdfs(quick_report_pdf, testsheet_pdf, quick_report_pdf)

                    processed_packages.append(pkg)
                    final_deliverables.append(quick_report_pdf)
                    sink(f"Completed deliverable -> {quick_report_pdf.name}")

                except Exception as exc:
                    logger.error("Failed post-processing for substation %s: %s", pkg.station_name, exc)
                    failed_packages.append(PostProcessingFailure(package=pkg, error=str(exc)))
                    sink(f"Failed post-processing for {pkg.station_name}: {exc}")

        duration = time.time() - start_time

        # Stage 5: Summary Result
        return PostProcessingSummary(
            processed_packages=tuple(processed_packages),
            final_deliverables=tuple(final_deliverables),
            failed_packages=tuple(failed_packages),
            warnings=tuple(warnings),
            errors=tuple(f"{f.package.station_name}: {f.error}" for f in failed_packages),
            duration_seconds=duration,
        )


def run_postprocessing_pipeline(
    env: ProjectEnvironment,
    request: PostProcessingRequest | None = None,
) -> PostProcessingSummary:
    """Entrypoint executing the post-processing workflow."""
    workflow = PostProcessingPipelineWorkflow()
    return workflow.execute(env, request)
