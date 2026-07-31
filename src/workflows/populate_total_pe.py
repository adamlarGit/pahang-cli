"""Populate TOTAL PE workflow implementation for Pahang CLI."""

from __future__ import annotations

import openpyxl
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from src.core.normalizers import normalize_date_str
from src.master.total_pe import LocalExcelTotalPeRepository, TotalPeRepository
from src.project.environment import ProjectEnvironment
from src.testsheet.models import SubstationTestsheetPackage
from src.testsheet.repository import SubstationTestsheetRepository
from src.workflows.history import ProcessingHistoryStore
from src.workflows.models import (
    PopulateMode,
    PopulateTotalPeRequest,
    PopulateTotalPeResult,
)


class PopulateTotalPePreflightGuard:
    """Pre-flight resource guard stage for Populate Total PE workflow."""

    def validate(self, environment: ProjectEnvironment) -> None:
        """Validate environmental preconditions before reading data."""
        testsheet_dir = environment.storage.get_testsheet_dir()
        self._validate_testsheet_directory(testsheet_dir)

        total_pe_path = environment.storage.get_total_pe_path()
        self._validate_total_pe_workbook(total_pe_path)

    def _validate_testsheet_directory(self, testsheet_dir: Path) -> None:
        if not testsheet_dir.exists() or not testsheet_dir.is_dir():
            raise FileNotFoundError(f"TESTSHEET directory not found: {testsheet_dir}")

    def _validate_total_pe_workbook(self, total_pe_path: Path) -> None:
        if not total_pe_path.exists():
            raise FileNotFoundError(f"TOTAL PE.xlsx workbook not found: {total_pe_path}")

        try:
            wb = openpyxl.load_workbook(total_pe_path, read_only=True)
            if "DataCycle1" not in wb.sheetnames:
                wb.close()
                raise RuntimeError("DataCycle1 sheet not found in TOTAL PE.xlsx")
            wb.close()
        except openpyxl.utils.exceptions.InvalidFileException as e:
            raise RuntimeError(f"Failed to load TOTAL PE.xlsx: {e}")


@dataclass(frozen=True)
class PopulateTotalPePlan:
    """Transformation execution plan for upserting testsheet packages to TOTAL PE."""

    total_pe_path: Path
    packages: tuple[SubstationTestsheetPackage, ...]


class PopulateTotalPeExtractor:
    """Pure I/O reading stage for Populate Total PE workflow."""

    def __init__(
        self,
        repository: SubstationTestsheetRepository | None = None,
        total_pe_repository: TotalPeRepository | None = None,
    ) -> None:
        self.repository = repository or SubstationTestsheetRepository()
        self.total_pe_repository = total_pe_repository or LocalExcelTotalPeRepository()

    def discover_packages(self, testsheet_dir: Path) -> list[SubstationTestsheetPackage]:
        """Scan testsheet packages from repository."""
        return self.repository.discover_packages(testsheet_dir)

    def get_existing_auto_keys(self, total_pe_path: Path) -> set[tuple[str, str]]:
        """Read existing auto keys from TOTAL PE workbook."""
        return self.total_pe_repository.get_existing_auto_keys(total_pe_path)


class PopulateTotalPeFilter:
    """Pure predicate logic stage for Populate Total PE workflow."""

    def filter_packages(
        self,
        packages: Sequence[SubstationTestsheetPackage],
        mode: PopulateMode,
        target_folder_names: Sequence[str] | None = None,
        existing_auto_keys: set[tuple[str, str]] | None = None,
    ) -> list[SubstationTestsheetPackage]:
        """Filter packages according to specified PopulateMode and criteria."""
        if mode == PopulateMode.SPECIFIC_FOLDERS:
            return self._filter_specific_folders(packages, target_folder_names)
        elif mode == PopulateMode.AUTO:
            return self._filter_auto_mode(packages, existing_auto_keys)
        return list(packages)

    def _filter_specific_folders(
        self,
        packages: Sequence[SubstationTestsheetPackage],
        target_folder_names: Sequence[str] | None,
    ) -> list[SubstationTestsheetPackage]:
        """Filter packages by target folder names or date strings."""
        if not target_folder_names:
            return list(packages)
        return [
            pkg
            for pkg in packages
            if any(
                target in pkg.date_str or target in str(pkg.testsheet_path)
                for target in target_folder_names
            )
        ]

    def _filter_auto_mode(
        self,
        packages: Sequence[SubstationTestsheetPackage],
        existing_auto_keys: set[tuple[str, str]] | None,
    ) -> list[SubstationTestsheetPackage]:
        """Filter out packages already present in TOTAL PE workbook."""
        keys = existing_auto_keys or set()
        return [pkg for pkg in packages if not self._is_package_in_keys(pkg, keys)]

    def _is_package_in_keys(
        self, pkg: SubstationTestsheetPackage, keys: set[tuple[str, str]]
    ) -> bool:
        """Check if package matches any existing key in TOTAL PE."""
        raw_date = pkg.date_str
        norm_date = normalize_date_str(raw_date)
        dates_to_check = {raw_date, norm_date}

        str_sub_num = str(pkg.substation_number)
        padded_sub_num = f"{pkg.substation_number:03d}"
        erms_name = pkg.data.substation_name_erms.upper() if (pkg.data and pkg.data.substation_name_erms) else None

        for str_id, key_dt in keys:
            norm_key_dt = normalize_date_str(key_dt)
            if key_dt in dates_to_check or norm_key_dt in dates_to_check:
                if str_id in (str_sub_num, padded_sub_num):
                    return True
                if erms_name and str_id == erms_name:
                    return True

        return False


class PopulateTotalPeTransformer:
    """Pure transformation plan construction stage for Populate Total PE workflow."""

    def build_plan(
        self, total_pe_path: Path, packages: Sequence[SubstationTestsheetPackage]
    ) -> PopulateTotalPePlan:
        """Construct transformation execution plan."""
        return PopulateTotalPePlan(total_pe_path=total_pe_path, packages=tuple(packages))


class PopulateTotalPeLoader:
    """Pure write I/O stage for Populate Total PE workflow."""

    def __init__(
        self, total_pe_repository: TotalPeRepository | None = None
    ) -> None:
        self.total_pe_repository = total_pe_repository or LocalExcelTotalPeRepository()

    def upsert_packages(self, plan: PopulateTotalPePlan) -> tuple[int, int]:
        """Upsert packages to TOTAL PE workbook."""
        return self.total_pe_repository.upsert_packages(plan.total_pe_path, plan.packages)


class PopulateTotalPeAuditor:
    """Verification & History Audit Phase."""

    def audit(
        self,
        environment: ProjectEnvironment,
        plan: PopulateTotalPePlan,
        load_output: tuple[int, int],
    ) -> PopulateTotalPeResult:
        """Verify output integrity, update processing history, and return workflow result."""
        self._verify_output(plan.total_pe_path)
        self._record_history(environment, plan.packages)

        new_count, _ = load_output
        return PopulateTotalPeResult(new_rows_added=new_count)

    def _verify_output(self, total_pe_path: Path) -> None:
        if not total_pe_path.exists():
            raise RuntimeError("TOTAL PE.xlsx does not exist after load.")
        if total_pe_path.stat().st_size == 0:
            raise RuntimeError("TOTAL PE.xlsx is empty (0 bytes) after load.")

    def _record_history(
        self, environment: ProjectEnvironment, packages: Sequence[SubstationTestsheetPackage]
    ) -> None:
        history_file = environment.storage.root_path / "history.json"
        store = ProcessingHistoryStore(history_file)
        store.record_processed_packages(packages)


class PopulateTotalPeWorkflow:
    """Scans testsheet packages and upserts PE information into TOTAL PE.xlsx.

    Resilience Policy: atomic - All-or-nothing execution. Any unhandled stage exception aborts the workflow.
    """

    def __init__(
        self,
        repository: SubstationTestsheetRepository | None = None,
        total_pe_repository: TotalPeRepository | None = None,
        preflight_guard: PopulateTotalPePreflightGuard | None = None,
        extractor: PopulateTotalPeExtractor | None = None,
        filter_stage: PopulateTotalPeFilter | None = None,
        transformer: PopulateTotalPeTransformer | None = None,
        loader: PopulateTotalPeLoader | None = None,
        auditor: PopulateTotalPeAuditor | None = None,
    ) -> None:
        self.repository = repository or SubstationTestsheetRepository()
        self.total_pe_repository = total_pe_repository or LocalExcelTotalPeRepository()
        self.preflight_guard = preflight_guard or PopulateTotalPePreflightGuard()
        self.extractor = extractor or PopulateTotalPeExtractor(self.repository, self.total_pe_repository)
        self.filter_stage = filter_stage or PopulateTotalPeFilter()
        self.transformer = transformer or PopulateTotalPeTransformer()
        self.loader = loader or PopulateTotalPeLoader(self.total_pe_repository)
        self.auditor = auditor or PopulateTotalPeAuditor()

    def execute(
        self, environment: ProjectEnvironment, request: PopulateTotalPeRequest
    ) -> PopulateTotalPeResult:
        """Execute Populate TOTAL PE workflow."""
        self.preflight_guard.validate(environment)

        testsheet_dir = environment.storage.get_testsheet_dir()
        total_pe_path = environment.storage.get_total_pe_path()

        if request.progress_sink:
            request.progress_sink(f"Scanning testsheet packages in {testsheet_dir}...")

        packages = self.extractor.discover_packages(testsheet_dir)

        existing_auto_keys: set[tuple[str, str]] | None = None
        if request.mode == PopulateMode.AUTO:
            existing_auto_keys = self.extractor.get_existing_auto_keys(total_pe_path)

        filtered_packages = self.filter_stage.filter_packages(
            packages=packages,
            mode=request.mode,
            target_folder_names=request.target_folder_names,
            existing_auto_keys=existing_auto_keys,
        )

        if not filtered_packages:
            if request.progress_sink:
                request.progress_sink("No testsheet packages found to process.")
            return PopulateTotalPeResult(new_rows_added=0)

        plan = self.transformer.build_plan(total_pe_path, filtered_packages)
        load_output = self.loader.upsert_packages(plan)

        result = self.auditor.audit(environment, plan, load_output)

        if request.progress_sink:
            request.progress_sink(
                f"TOTAL PE populated successfully: {load_output[0]} new rows, {load_output[1]} updated."
            )

        return result


