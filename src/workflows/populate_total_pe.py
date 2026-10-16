"""Populate TOTAL PE workflow implementation for Pahang CLI."""

from __future__ import annotations

import logging
import openpyxl
import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from src.core.normalizers import normalize_date_str
from src.master.total_pe import LocalExcelTotalPeRepository, TotalPeRepository
from src.project.environment import ProjectEnvironment
from src.testsheet.models import SubstationTestsheetPackage
from src.testsheet.parsers.common import normalize_fl_erms
from src.testsheet.repository import SubstationTestsheetRepository
from src.workflows.history import ProcessingHistoryStore
from src.workflows.models import (
    PopulateMode,
    PopulateTotalPeRequest,
    PopulateTotalPeResult,
)

logger = logging.getLogger(__name__)


def load_qr02_cba_33kv_metadata(cba_path: Path) -> dict[str, dict[str, str]]:
    """Index QR02 CBA sheet by Column G (FUNCTIONAL LOCATION).

    Reads Column G (FUNCTIONAL LOCATION), Column H (SUBSTATION NAME), and Column I (TYPE).
    Returns mapping of normalized FL -> {"substation_name": str, "substation_type": str}.
    """
    if not cba_path.exists():
        return {}

    mapping: dict[str, dict[str, str]] = {}
    try:
        wb = openpyxl.load_workbook(cba_path, read_only=True, data_only=True)
        try:
            if "QR02 CBA" not in wb.sheetnames:
                logger.warning(f"'QR02 CBA' sheet not found in {cba_path}")
                return {}
            ws = wb["QR02 CBA"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if len(row) < 7:
                    continue
                fl_val = row[6]
                if not fl_val:
                    continue
                fl_str = str(fl_val).strip()
                norm_fl = normalize_fl_erms(fl_str)
                if not norm_fl or norm_fl.lower() in (
                    "n/a",
                    "none",
                    "functional location",
                    "function location",
                    "fl",
                ):
                    continue

                name_val = str(row[7]).strip() if len(row) > 7 and row[7] is not None else ""
                type_val = str(row[8]).strip() if len(row) > 8 and row[8] is not None else ""

                entry = {"substation_name": name_val, "substation_type": type_val}
                mapping[norm_fl] = entry
                mapping[fl_str.upper()] = entry
                clean_no_slash = fl_str.upper().replace("/", "")
                if clean_no_slash:
                    mapping[clean_no_slash] = entry
        finally:
            wb.close()
    except Exception as e:
        logger.warning(f"Failed to read QR02 CBA from {cba_path}: {e}")
        return {}
    return mapping


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


def resolve_target_folders(
    testsheet_dir: Path, target_folder_names: Sequence[str]
) -> list[Path]:
    """Resolve target folder names / paths to existing directory paths."""
    matched_dirs: list[Path] = []
    seen: set[Path] = set()

    for target in target_folder_names:
        cand = Path(target)
        if cand.is_absolute() and cand.is_dir():
            resolved = cand.resolve()
            if resolved not in seen:
                seen.add(resolved)
                matched_dirs.append(resolved)
            continue

        rel_cand = (testsheet_dir / target).resolve()
        if rel_cand.is_dir():
            if rel_cand not in seen:
                seen.add(rel_cand)
                matched_dirs.append(rel_cand)
            continue

        if testsheet_dir.exists():
            for p in testsheet_dir.rglob("*"):
                if p.is_dir() and (p.name == target or target in str(p)):
                    resolved = p.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        matched_dirs.append(resolved)

    return matched_dirs


class PopulateTotalPeExtractor:
    """Pure I/O reading stage for Populate Total PE workflow."""

    def __init__(
        self,
        repository: SubstationTestsheetRepository | None = None,
        total_pe_repository: TotalPeRepository | None = None,
    ) -> None:
        self.repository = repository or SubstationTestsheetRepository()
        self.total_pe_repository = total_pe_repository or LocalExcelTotalPeRepository()

    def discover_packages(
        self,
        testsheet_dir: Path,
        target_folder_names: Sequence[str] | None = None,
        mode: PopulateMode | None = None,
        eager_extract: bool = False,
    ) -> list[SubstationTestsheetPackage]:
        """Scan testsheet packages from repository with optional scoped discovery."""
        if mode == PopulateMode.SPECIFIC_FOLDERS and target_folder_names:
            target_dirs = resolve_target_folders(testsheet_dir, target_folder_names)
            if not target_dirs:
                return []
            packages: list[SubstationTestsheetPackage] = []
            seen_paths: set[Path] = set()
            for td in target_dirs:
                try:
                    discovered = self.repository.discover_packages(
                        td, eager_extract=eager_extract
                    )
                except TypeError:
                    discovered = self.repository.discover_packages(td)
                for pkg in discovered:
                    resolved_p = pkg.testsheet_path.resolve()
                    if resolved_p not in seen_paths:
                        seen_paths.add(resolved_p)
                        packages.append(pkg)
            return packages

        try:
            return self.repository.discover_packages(
                testsheet_dir, eager_extract=eager_extract
            )
        except TypeError:
            return self.repository.discover_packages(testsheet_dir)

    def enrich_packages_with_cba(
        self,
        packages: Sequence[SubstationTestsheetPackage],
        cba_path: Path | None = None,
        environment: ProjectEnvironment | None = None,
    ) -> list[SubstationTestsheetPackage]:
        """Enrich 33kV packages with official master metadata from QR02 CBA.

        Resolves Column H (SUBSTATION NAME) and Column I (TYPE) indexed by Column G (FL).
        Falls back gracefully to cell D6 (name) and stem/sheet token (type) if FL not in CBA.
        """
        resolved_cba_path = cba_path
        if resolved_cba_path is None and environment is not None:
            if getattr(environment, "voltage_type", None) == "33kV":
                year = getattr(environment, "year", None) or "2026"
                try:
                    resolved_cba_path = environment.storage.get_engr_33kv_cba_path(year)
                except Exception as e:
                    logger.warning(f"Could not resolve 33kV CBA path: {e}")
                    resolved_cba_path = None

        if resolved_cba_path is None:
            return list(packages)

        if not resolved_cba_path.exists():
            logger.warning(
                f"33kV ENGR CBA workbook not found at '{resolved_cba_path}'. "
                "Falling back to testsheet cell D6 and stem type."
            )
            return list(packages)

        cba_index = load_qr02_cba_33kv_metadata(resolved_cba_path)
        if not cba_index:
            logger.warning(
                f"No records indexed from QR02 CBA in '{resolved_cba_path}'. "
                "Falling back to testsheet cell D6 and stem type."
            )
            return list(packages)

        enriched: list[SubstationTestsheetPackage] = []
        for pkg in packages:
            data = pkg.data
            if data is None:
                enriched.append(pkg)
                continue

            fl_candidate = (data.fl_erms or data.fl_site or "").strip()
            norm_fl = normalize_fl_erms(fl_candidate)

            cba_entry = (
                cba_index.get(norm_fl)
                or cba_index.get(fl_candidate.upper())
                or cba_index.get(fl_candidate.upper().replace("/", ""))
            )

            if cba_entry:
                cba_name = cba_entry.get("substation_name", "")
                cba_type = cba_entry.get("substation_type", "")

                new_name = cba_name if cba_name else data.substation_name_erms
                new_type = cba_type if cba_type else data.substation_type

                updated_data = dataclasses.replace(
                    data,
                    substation_name_erms=new_name,
                    substation_type=new_type,
                )
                enriched.append(dataclasses.replace(pkg, data=updated_data))
            else:
                logger.warning(
                    f"Functional location '{fl_candidate}' not found in QR02 CBA "
                    f"('{resolved_cba_path.name}'). Falling back to testsheet cell D6 "
                    f"('{data.substation_name_erms}') and type '{data.substation_type}'."
                )
                enriched.append(pkg)

        return enriched

    def hydrate_packages_metadata(
        self,
        packages: Sequence[SubstationTestsheetPackage],
        environment: ProjectEnvironment | None = None,
        cba_path: Path | None = None,
    ) -> list[SubstationTestsheetPackage]:
        """Hydrate package TestsheetData using fast read-only metadata extractor and optional CBA enrichment."""
        hydrated: list[SubstationTestsheetPackage] = []
        extractor = getattr(self.repository, "extractor", None)

        for pkg in packages:
            if pkg.data is not None:
                hydrated.append(pkg)
                continue

            if extractor is not None:
                try:
                    if hasattr(extractor, "extract_testsheet_metadata"):
                        data = extractor.extract_testsheet_metadata(
                            pkg.testsheet_path,
                            station_hint=pkg.station,
                            date_hint=pkg.date_str,
                        )
                    else:
                        data = extractor.extract_testsheet_data(
                            pkg.testsheet_path,
                            station_hint=pkg.station,
                            date_hint=pkg.date_str,
                        )
                    hydrated.append(dataclasses.replace(pkg, data=data))
                    continue
                except Exception:
                    pass

            hydrated.append(pkg)

        if cba_path is not None or (environment is not None and getattr(environment, "voltage_type", None) == "33kV"):
            hydrated = self.enrich_packages_with_cba(hydrated, cba_path=cba_path, environment=environment)

        return hydrated

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
        padded_2d_num = f"{pkg.substation_number:02d}"
        padded_sub_num = f"{pkg.substation_number:03d}"
        fl_erms = (
            pkg.data.fl_erms.upper()
            if (pkg.data and pkg.data.fl_erms)
            else ""
        )
        norm_fl = normalize_fl_erms(fl_erms) if fl_erms else ""
        clean_fl = fl_erms.replace("/", "") if fl_erms else ""
        erms_name = (
            pkg.data.substation_name_erms.upper()
            if (pkg.data and pkg.data.substation_name_erms)
            else None
        )

        for str_id, key_dt in keys:
            norm_key_dt = normalize_date_str(key_dt)
            if key_dt in dates_to_check or norm_key_dt in dates_to_check:
                if str_id in (str_sub_num, padded_2d_num, padded_sub_num):
                    return True
                if fl_erms and str_id in (fl_erms, norm_fl, clean_fl):
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

        packages = self.extractor.discover_packages(
            testsheet_dir=testsheet_dir,
            target_folder_names=request.target_folder_names,
            mode=request.mode,
            eager_extract=False,
        )

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

        if hasattr(environment, "voltage_type") and environment.voltage_type:
            if getattr(self.repository, "voltage_type", None) is None:
                self.repository.voltage_type = environment.voltage_type
            if hasattr(self.repository, "extractor") and getattr(self.repository.extractor, "voltage_type", None) is None:
                self.repository.extractor.voltage_type = environment.voltage_type

        hydrated_packages = self.extractor.hydrate_packages_metadata(
            filtered_packages, environment=environment
        )

        if request.mode == PopulateMode.AUTO and existing_auto_keys:
            hydrated_packages = self.filter_stage.filter_packages(
                packages=hydrated_packages,
                mode=request.mode,
                target_folder_names=request.target_folder_names,
                existing_auto_keys=existing_auto_keys,
            )

        if not hydrated_packages:
            if request.progress_sink:
                request.progress_sink("No testsheet packages found to process.")
            return PopulateTotalPeResult(new_rows_added=0)

        plan = self.transformer.build_plan(total_pe_path, hydrated_packages)
        load_output = self.loader.upsert_packages(plan)

        result = self.auditor.audit(environment, plan, load_output)

        if request.progress_sink:
            request.progress_sink(
                f"TOTAL PE populated successfully: {load_output[0]} new rows, {load_output[1]} updated."
            )

        return result
