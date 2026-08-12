"""1-Click Post-Processing Pipeline automating Steps 1-5 (signatures, diagonals, PDF conversions, renaming, and merging)."""

from __future__ import annotations

import logging
import os
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import openpyxl

from src import cli_selectors
from src.workflows.diagonal_borders import (
    TESTSHEET_RANGES_TO_PROCESS,
    VI_SHEET_RANGES_TO_PROCESS,
    process_range,
)
from src.postprocessing.converters import (
    ComDocumentConverter,
    DocumentConverter,
    _is_pce_testsheet_sheet,
    _is_pce_vi_sheet,
)
from src.project.environment import ProjectEnvironment
# Core functions imported from replace_signatures (reused per architecture design)
from src.workflows.replace_signatures import (
    _select_signature_path,
    replace_pce_images,
)


from src.workflows.whatsapp import run_generate_whatsapp_report


from src.testsheet.models import SubstationPackage
from src.testsheet.repository import LocalTestsheetPackageRepository


@dataclass(frozen=True)
class PostProcessingSummary:
    """Summary of completed post-processing executions."""
    processed_packages: tuple[SubstationPackage, ...]
    final_deliverables: tuple[Path, ...]


def discover_substation_packages(env: ProjectEnvironment) -> list[SubstationPackage]:
    """Scan TESTSHEET/ and QUICK REPORT/ to discover paired substation workbooks and Word documents."""
    repo = LocalTestsheetPackageRepository()
    return repo.find_packages(env.get_testsheet_dir(), env.get_quick_report_dir())


def _apply_diagonals_to_workbook(input_xlsx: Path, output_xlsx: Path) -> Path:
    """Load workbook, apply diagonal borders across standard testsheet ranges, and save."""
    from src.workflows.diagonal_borders import process_workbook
    res = Path(process_workbook(input_xlsx))
    if res.resolve() != output_xlsx.resolve():
        shutil.copy2(res, output_xlsx)
    return output_xlsx



def run_postprocessing_pipeline(env: ProjectEnvironment) -> PostProcessingSummary:
    """Interactive entrypoint for the 1-Click Post-Processing Pipeline."""
    print("\n" + "=" * 65)
    print(" 🚀 1-CLICK SUBSTATION POST-PROCESSING PIPELINE")
    print("=" * 65)

    packages = discover_substation_packages(env)
    if not packages:
        print("\n[!] No matching Testsheet (.xlsx) and Quick Report (.docx) pairs found in TESTSHEET/ and QUICK REPORT/.")
        print("    Ensure both files exist and share matching numerical prefixes/names before running post-processing.")
        return PostProcessingSummary(processed_packages=(), final_deliverables=())

    print(f"\nDiscovered {len(packages)} complete substation package(s) across workspace.")

    mode_options = [
        cli_selectors.SelectOption("Process by DATE Folder (Select all substations in a date folder)", "by_date"),
        cli_selectors.SelectOption("Process by FL NUMBER (Select single or multiple specific substations)", "by_fl"),
        cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"),
    ]
    mode = cli_selectors.select_one("Select Target Selection Mode:", mode_options)
    if mode in (None, "__cancel__"):
        return PostProcessingSummary(processed_packages=(), final_deliverables=())

    target_packages: list[SubstationPackage] = []

    if mode == "by_date":
        date_groups: dict[str, list[SubstationPackage]] = {}
        for pkg in packages:
            date_groups.setdefault(pkg.date_folder, []).append(pkg)

        from src.project.storage import sort_folders_descending
        
        sorted_dates = sort_folders_descending(list(date_groups.keys()))
        date_options = [
            cli_selectors.SelectOption(
                f"{df} ({len(date_groups[df])} substation{'s' if len(date_groups[df]) > 1 else ''})",
                df,
            )
            for df in sorted_dates
        ]
        date_options.append(cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"))

        selected_date = cli_selectors.select_one("Select Date Folder to Process:", date_options)
        if selected_date in (None, "__cancel__"):
            return PostProcessingSummary(processed_packages=(), final_deliverables=())

        target_packages = date_groups[selected_date]
        print(f"\nSelected Date Folder '{selected_date}' -> Queued {len(target_packages)} substation(s) for processing.")

    elif mode == "by_fl":
        fl_options = [
            cli_selectors.SelectOption(
                f"[{pkg.fl_erms}] {pkg.station_name} (Date: {pkg.date_folder})",
                pkg,
            )
            for pkg in packages
        ]
        selected_pkgs = cli_selectors.select_multiple("Select Substation(s) to Process:", fl_options)
        if not selected_pkgs:
            print("No substations selected. Operation cancelled.")
            return PostProcessingSummary(processed_packages=(), final_deliverables=())

        target_packages = list(selected_pkgs)
        print(f"\nQueued {len(target_packages)} specific substation(s) for processing.")

    processed: list[SubstationPackage] = []
    deliverables: list[Path] = []

    # Signature step prompt right after date/FL selection (Decision 1 & 3)
    apply_signatures = False
    vendor_sign_path = None
    tnb_sign_path = None

    sign_options = [
        cli_selectors.SelectOption("Yes - Apply signature stamps to testsheets", True),
        cli_selectors.SelectOption("No - Skip signature replacement (diagonals & PDF conversion only)", False),
    ]
    sign_choice = cli_selectors.select_one("Apply signature stamps?", sign_options, default_value=True)
    if sign_choice in (None, "__cancel__"):
        return PostProcessingSummary(processed_packages=(), final_deliverables=())

    if sign_choice is True:
        sign_dir = env.get_sign_dir()
        vendor_sign_path, folder1 = _select_signature_path(
            "Select vendor signature person (from OTHERS/SIGN/):",
            sign_dir,
        )
        if folder1 in (None, "__cancel__"):
            print("Cancelled signature selection for vendor. Operation cancelled.")
            return PostProcessingSummary(processed_packages=(), final_deliverables=())

        tnb_sign_path, folder2 = _select_signature_path(
            "Select TNB signature person (from OTHERS/SIGN/):",
            sign_dir,
            default_folder=folder1 if folder1 != "__none__" else None,
        )
        if folder2 in (None, "__cancel__"):
            print("Cancelled signature selection for TNB. Operation cancelled.")
            return PostProcessingSummary(processed_packages=(), final_deliverables=())

        apply_signatures = True

    # WhatsApp generation prompt (only for by_date mode)
    generate_whatsapp = False
    if selection_mode == "by_date":
        wa_options = [
            cli_selectors.SelectOption("Yes - Generate WhatsApp report (.docx)", True),
            cli_selectors.SelectOption("No - Skip WhatsApp report generation", False),
        ]
        wa_choice = cli_selectors.select_one("Generate WhatsApp report?", wa_options, default_value=True)
        if wa_choice in (None, "__cancel__"):
            return PostProcessingSummary(processed_packages=(), final_deliverables=())
        generate_whatsapp = bool(wa_choice)

    total_steps = 4 if apply_signatures else 3

    # Step 1: Generate WhatsApp daily report right at the start if requested
    if generate_whatsapp and target_packages:
        print(f"\n-----------------------------------------------------------------")
        print(f" 📨 [Initial Step] Generating WhatsApp daily report...")
        print(f"-----------------------------------------------------------------")
        try:
            report_dir = target_packages[0].quick_report_docx.parent
            whatsapp_summary = run_generate_whatsapp_report(env, report_dir)
            if whatsapp_summary:
                print(f"            ✓ WhatsApp report saved -> {whatsapp_summary.output_path.name}")
        except Exception as exc:
            logging.error("WhatsApp generation failed: %s", exc)
            print(f"            [X] WhatsApp generation failed: {exc}")
            traceback.print_exc()

    # Step 2: Rename testsheets according to quick report names using rename_files_workflow
    print(f"\n-----------------------------------------------------------------")
    print(f" 🏷️ [Initial Step] Renaming testsheets according to Quick Report names...")
    print(f"-----------------------------------------------------------------")
    date_folders = sorted({pkg.date_folder for pkg in target_packages if pkg.date_folder != "Top Level"})
    from src.workflows.rename_files import rename_files_match
    for df in date_folders:
        qr_dir = env.get_quick_report_dir() / df
        ts_dir = env.get_testsheet_dir() / df
        if qr_dir.exists() and ts_dir.exists():
            try:
                summary = rename_files_match(qr_dir, ts_dir)
                for pair in summary.renamed:
                    print(f"            ✓ Renamed testsheet in {df}: {pair.old_name} -> {pair.new_name}")
            except ValueError as val_err:
                print(f"\n [X] HARD STOP in {df} (Testsheet): {val_err}\n")
                logging.error("Hard stop due to quantity mismatch in testsheet %s: %s", df, val_err)
                raise
            except Exception as exc:
                logging.warning("Could not batch rename testsheets in %s: %s", df, exc)
                print(f"            [!] Note: Batch rename testsheet in {df} skipped ({exc})")

        raw_mat_dir = env.get_raw_material_dir() / df
        if qr_dir.exists() and raw_mat_dir.exists():
            try:
                summary = rename_files_match(qr_dir, raw_mat_dir)
                for pair in summary.renamed:
                    print(f"            ✓ Renamed raw material in {df}: {pair.old_name} -> {pair.new_name}")
            except ValueError as val_err:
                print(f"\n [X] HARD STOP in {df} (Raw Material): {val_err}\n")
                logging.error("Hard stop due to quantity mismatch in raw material %s: %s", df, val_err)
                raise
            except Exception as exc:
                logging.warning("Could not batch rename raw materials in %s: %s", df, exc)
                print(f"            [!] Note: Batch rename raw material in {df} skipped ({exc})")

    # Step 3: Refresh target_packages after renaming so all testsheet_xlsx paths point to the updated filenames
    refreshed_packages = discover_substation_packages(env)
    refreshed_map = {pkg.quick_report_docx.resolve(): pkg for pkg in refreshed_packages}
    updated_target_packages: list[SubstationPackage] = []
    for pkg in target_packages:
        resolved_qr = pkg.quick_report_docx.resolve()
        if resolved_qr in refreshed_map:
            updated_target_packages.append(refreshed_map[resolved_qr])
        else:
            updated_target_packages.append(pkg)
    target_packages = updated_target_packages

    converter: DocumentConverter = ComDocumentConverter()
    for i, pkg in enumerate(target_packages, start=1):
        print(f"\n-----------------------------------------------------------------")
        print(f"[{i}/{len(target_packages)}] Processing: {pkg.station_name} [{pkg.fl_erms}]")
        print(f"       Date Folder: {pkg.date_folder}")
        print(f"       Testsheet:   {pkg.testsheet_xlsx.name}")
        print(f"       Quick Report: {pkg.quick_report_docx.name}")
        print(f"-----------------------------------------------------------------")

        try:
            step_idx = 1
            processed_xlsx_dir = pkg.testsheet_xlsx.parent / "processed_testsheet"
            processed_xlsx_dir.mkdir(parents=True, exist_ok=True)
            processed_xlsx = processed_xlsx_dir / pkg.testsheet_xlsx.name

            if apply_signatures and vendor_sign_path and tnb_sign_path:
                print(f" [Step {step_idx}/{total_steps}] Applying signature replacements...")
                replace_pce_images(
                    pkg.testsheet_xlsx,
                    vendor_sign_path,
                    tnb_sign_path,
                    output_path=processed_xlsx,
                    mode="placeholder",
                )
                print(f"            ✓ Saved copy with signatures -> {processed_xlsx.name}")
                step_idx += 1

            print(f" [Step {step_idx}/{total_steps}] Applying diagonal borders to blank cells...")
            if apply_signatures:
                # Apply in-place on the already-copied processed_xlsx
                _apply_diagonals_to_workbook(processed_xlsx, processed_xlsx)
            else:
                # Copy from original testsheet to processed_xlsx while applying diagonals
                _apply_diagonals_to_workbook(pkg.testsheet_xlsx, processed_xlsx)
            print(f"            ✓ Saved diagonalized workbook -> {processed_xlsx.name}")
            step_idx += 1

            # Convert testsheet to PDF
            testsheet_pdf_dir = processed_xlsx_dir / "pdf"
            testsheet_pdf_dir.mkdir(parents=True, exist_ok=True)
            testsheet_pdf = testsheet_pdf_dir / f"{pkg.testsheet_xlsx.stem}.pdf"
            print(f" [Step {step_idx}/{total_steps}] Converting testsheet to PDF via COM...")
            converter.convert_testsheet_to_pdf(processed_xlsx, testsheet_pdf)
            print(f"            ✓ Created Testsheet PDF -> {testsheet_pdf.name}")
            step_idx += 1

            # Convert Quick Report DOCX to PDF (alongside source .docx)
            quick_report_pdf = pkg.quick_report_docx.with_suffix(".pdf")
            print(f" [Step {step_idx}/{total_steps}] Converting Quick Report DOCX to PDF via COM...")
            converter.convert_docx_to_pdf(pkg.quick_report_docx, quick_report_pdf)
            print(f"            ✓ Created Quick Report PDF -> {quick_report_pdf.name}")
            step_idx += 1

            # Combine Quick Report PDF and Testsheet PDF directly into Quick Report PDF (in place)
            print(f" [Step {step_idx}/{total_steps}] Merging Quick Report and Testsheet into combined PDF...")
            converter.merge_pdfs(quick_report_pdf, testsheet_pdf, quick_report_pdf)
            print(f"            ✓ GENERATED COMBINED DELIVERABLE IN PLACE -> {quick_report_pdf.name}")

            processed.append(pkg)
            deliverables.append(quick_report_pdf)
        except Exception as exc:
            logging.error("Pipeline failure for %s: %s", pkg.station_name, exc)
            print(f"            [X] Pipeline failed for {pkg.station_name}: {exc}")
            traceback.print_exc()

    print("\n" + "=" * 65)
    print(f" 🎉 PIPELINE COMPLETE! Successfully processed {len(processed)} / {len(target_packages)} substation(s).")
    print("=" * 65)
    return PostProcessingSummary(processed_packages=tuple(processed), final_deliverables=tuple(deliverables))
