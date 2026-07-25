"""Populate TOTAL PE workflow implementation for Pahang CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src.master.total_pe import LocalExcelTotalPeRepository, TotalPeRepository, normalize_date_str
from src.project.environment import ProjectEnvironment
from src.testsheet.repository import SubstationTestsheetRepository
from src.workflows.models import (
    PopulateMode,
    PopulateTotalPeRequest,
    PopulateTotalPeResult,
)


class PopulateTotalPeWorkflow:
    """Scans testsheet packages and upserts PE information into TOTAL PE.xlsx."""

    def __init__(
        self,
        repository: SubstationTestsheetRepository | None = None,
        total_pe_repository: TotalPeRepository | None = None,
    ) -> None:
        self.repository = repository or SubstationTestsheetRepository()
        self.total_pe_repository = total_pe_repository or LocalExcelTotalPeRepository()

    def execute(
        self, environment: ProjectEnvironment, request: PopulateTotalPeRequest
    ) -> PopulateTotalPeResult:
        testsheet_dir = environment.storage.get_testsheet_dir()
        total_pe_path = environment.storage.get_total_pe_path()

        if request.progress_sink:
            request.progress_sink(f"Scanning testsheet packages in {testsheet_dir}...")

        packages = self.repository.discover_packages(testsheet_dir)

        if request.mode == PopulateMode.SPECIFIC_FOLDERS and request.target_folder_names:
            packages = [
                pkg for pkg in packages
                if any(target in pkg.date_str or target in str(pkg.testsheet_path) for target in request.target_folder_names)
            ]
        elif request.mode == PopulateMode.AUTO and total_pe_path.exists():
            existing_auto_keys = self.total_pe_repository.get_existing_auto_keys(total_pe_path)
            packages = [
                pkg for pkg in packages
                if (str(pkg.pe_num), pkg.date_str) not in existing_auto_keys
                and (str(pkg.pe_num), normalize_date_str(pkg.date_str)) not in existing_auto_keys
                and (f"{pkg.pe_num:03d}", pkg.date_str) not in existing_auto_keys
                and (f"{pkg.pe_num:03d}", normalize_date_str(pkg.date_str)) not in existing_auto_keys
                and (pkg.data is None or (pkg.data.substation_name.upper(), pkg.date_str) not in existing_auto_keys)
            ]

        if not packages:
            if request.progress_sink:
                request.progress_sink("No testsheet packages found to process.")
            return PopulateTotalPeResult(new_rows_added=0)

        new_count, updated_count = self.total_pe_repository.upsert_packages(total_pe_path, packages)

        if request.progress_sink:
            request.progress_sink(
                f"TOTAL PE populated successfully: {new_count} new rows, {updated_count} updated."
            )

        return PopulateTotalPeResult(new_rows_added=new_count)
