"""Update QR02 CBA workflow orchestrator for Pahang CLI."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.master.qr02 import LocalExcelQr02Repository, Qr02Repository
from src.project.environment import ProjectEnvironment
from src.project.storage import WorkspaceStorage
from src.testsheet.extractor import TestsheetExtractor
from src.testsheet.models import SubstationTestsheetPackage, TestsheetData
from src.testsheet.repository import SubstationTestsheetRepository
from src.workflows.history import ProcessingHistoryStore, format_package_history_key
from src.workflows.models import (
    PopulateMode,
    UpdateQr02CbaRequest,
    UpdateQr02CbaResult,
)


def get_package_key(pkg: SubstationTestsheetPackage) -> str:
    """Format package history key: <STATION>/<MONTH>/<DD-MM-YYYY>."""
    return format_package_history_key(pkg)


def _matches_target(pkg: SubstationTestsheetPackage, key: str, target: str) -> bool:
    """Return True if package matches target_package_name string."""
    t = target.strip()
    if not t:
        return False
    t_lower = t.lower()

    if t_lower in (
        key.lower(),
        pkg.date_str.lower(),
        pkg.station.lower(),
        pkg.month.lower(),
        pkg.testsheet_path.parent.name.lower(),
        pkg.testsheet_path.name.lower(),
        pkg.testsheet_path.stem.lower(),
    ):
        return True

    if t_lower in key.lower() or t_lower in str(pkg.testsheet_path).lower():
        return True

    return False


@dataclass
class UpdateQr02StationPlan:
    station: str
    records: list[TestsheetData]
    packages: list[SubstationTestsheetPackage]


@dataclass
class UpdateQr02CbaPlan:
    station_plans: list[UpdateQr02StationPlan]
    warnings: list[str]


@dataclass
class UpdateQr02CbaLoadResult:
    records_updated: int
    processed_packages: list[SubstationTestsheetPackage]


class UpdateQr02CbaPreflightGuard:
    """Stage 1: PreflightGuard (Pre-flight Resource Guard)

    Validates environmental preconditions and workbook availability before processing.
    """

    def validate(
        self,
        environment: ProjectEnvironment,
        station: str,
        year: str,
        repository_factory: Callable[[WorkspaceStorage, str, str], Qr02Repository] | None = None,
    ) -> None:
        """Validate target QR02 CBA workbook exists for the specified station."""
        if repository_factory is None:
            cba_path = environment.storage.get_engr_cba_path(station, year)
            if not cba_path.exists():
                raise FileNotFoundError(
                    f"Target QR02 CBA workbook not found for station '{station}' at '{cba_path}'"
                )


class UpdateQr02CbaExtractor:
    """Stage 2: Extractor (Read Stage)

    Pure read I/O stage responsible for discovering testsheet packages and reading testsheet records.
    """

    def __init__(
        self,
        testsheet_repository: SubstationTestsheetRepository | None = None,
        data_extractor: TestsheetExtractor | None = None,
    ) -> None:
        self.testsheet_repository = testsheet_repository or SubstationTestsheetRepository()
        self.data_extractor = data_extractor or TestsheetExtractor()

    def extract_packages(
        self, environment: ProjectEnvironment
    ) -> list[SubstationTestsheetPackage]:
        """Discover all testsheet packages under the testsheet directory."""
        testsheet_dir = environment.storage.get_testsheet_dir()
        return list(self.testsheet_repository.discover_packages(testsheet_dir))

    def extract_records(
        self, packages: list[SubstationTestsheetPackage]
    ) -> tuple[dict[str, list[TestsheetData]], list[str]]:
        """Read testsheet data records for all target packages."""
        records_map: dict[str, list[TestsheetData]] = defaultdict(list)
        warnings: list[str] = []
        for pkg in packages:
            data = self._extract_single_package_data(pkg, warnings)
            if data is not None:
                records_map[get_package_key(pkg)].append(data)
        return records_map, warnings

    def _extract_single_package_data(
        self, pkg: SubstationTestsheetPackage, warnings: list[str]
    ) -> TestsheetData | None:
        """Extract data from a single package, collecting warnings on extraction failures."""
        if pkg.data is not None:
            return pkg.data

        try:
            return self.data_extractor.extract_testsheet_data(
                pkg.testsheet_path,
                station_hint=pkg.station,
                date_hint=pkg.date_str,
            )
        except Exception as exc:
            warn_msg = f"Failed to extract testsheet data from {pkg.testsheet_path}: {exc}"
            warnings.append(warn_msg)
            return None


class UpdateQr02CbaFilter:
    """Stage 3: Filter (Filter & Row Validation Stage)

    Pure logic stage responsible for filtering testsheet packages based on populate mode and processing history.
    """

    def filter(
        self,
        packages: list[SubstationTestsheetPackage],
        request: UpdateQr02CbaRequest,
        history: dict[str, Any],
    ) -> list[SubstationTestsheetPackage]:
        """Filter target packages according to populate mode (ALL, SPECIFIC_FOLDERS, AUTO)."""
        is_all = self._is_all_mode(request)
        is_specific = self._is_specific_mode(request, is_all)

        if is_all:
            return self._filter_all_mode(packages)
        if is_specific:
            return self._filter_specific_mode(packages, request.target_package_names)
        return self._filter_auto_mode(packages, history)

    def _is_all_mode(self, request: UpdateQr02CbaRequest) -> bool:
        """Check if request specifies ALL populate mode."""
        return request.mode == PopulateMode.ALL or any(
            str(t).strip().lower() == "all" for t in request.target_package_names
        )

    def _is_specific_mode(self, request: UpdateQr02CbaRequest, is_all_mode: bool) -> bool:
        """Check if request specifies SPECIFIC_FOLDERS populate mode."""
        return request.mode == PopulateMode.SPECIFIC_FOLDERS or (
            bool(request.target_package_names) and not is_all_mode
        )

    def _filter_all_mode(
        self, packages: list[SubstationTestsheetPackage]
    ) -> list[SubstationTestsheetPackage]:
        """Return all packages without filtering."""
        return list(packages)

    def _filter_specific_mode(
        self,
        packages: list[SubstationTestsheetPackage],
        target_package_names: tuple[str, ...],
    ) -> list[SubstationTestsheetPackage]:
        """Filter packages matching target package names."""
        return [
            pkg
            for pkg in packages
            if any(_matches_target(pkg, get_package_key(pkg), t) for t in target_package_names)
        ]

    def _filter_auto_mode(
        self,
        packages: list[SubstationTestsheetPackage],
        history: dict[str, Any],
    ) -> list[SubstationTestsheetPackage]:
        """Filter out packages that have already been recorded in processing history."""
        return [pkg for pkg in packages if get_package_key(pkg) not in history]


class UpdateQr02CbaTransformer:
    """Stage 4: Transformer (Transform Stage)

    Pure transformation stage grouping records by station into UpdateQr02CbaPlan execution instructions.
    """

    def transform(
        self,
        filtered_packages: list[SubstationTestsheetPackage],
        records_map: dict[str, list[TestsheetData]],
        extraction_warnings: list[str],
    ) -> UpdateQr02CbaPlan:
        """Build execution plan by grouping filtered packages into station plans."""
        station_groups = self._group_packages_by_station(filtered_packages)
        station_plans: list[UpdateQr02StationPlan] = []

        for station, pkgs in station_groups.items():
            station_plan = self._build_station_plan(station, pkgs, records_map)
            if station_plan is not None:
                station_plans.append(station_plan)

        return UpdateQr02CbaPlan(station_plans=station_plans, warnings=extraction_warnings)

    def _group_packages_by_station(
        self, packages: list[SubstationTestsheetPackage]
    ) -> dict[str, list[SubstationTestsheetPackage]]:
        """Group packages by station string."""
        station_groups: dict[str, list[SubstationTestsheetPackage]] = defaultdict(list)
        for pkg in packages:
            station_groups[pkg.station].append(pkg)
        return station_groups

    def _build_station_plan(
        self,
        station: str,
        packages: list[SubstationTestsheetPackage],
        records_map: dict[str, list[TestsheetData]],
    ) -> UpdateQr02StationPlan | None:
        """Construct station plan containing records and associated packages."""
        station_records: list[TestsheetData] = []
        station_pkgs: list[SubstationTestsheetPackage] = []
        for pkg in packages:
            key = get_package_key(pkg)
            records = records_map.get(key, [])
            if records:
                station_records.extend(records)
                station_pkgs.append(pkg)

        if not station_records:
            return None

        return UpdateQr02StationPlan(
            station=station, records=station_records, packages=station_pkgs
        )


class UpdateQr02CbaLoader:
    """Stage 5: Loader (Write Stage)

    Pure write I/O stage responsible for upserting records into station repositories.
    """

    def load(
        self,
        environment: ProjectEnvironment,
        plan: UpdateQr02CbaPlan,
        year: str,
        repository_factory: Callable[[WorkspaceStorage, str, str], Qr02Repository] | None = None,
    ) -> UpdateQr02CbaLoadResult:
        """Execute the load plan by writing records to target station repositories."""
        total_records_updated = 0
        processed_packages: list[SubstationTestsheetPackage] = []

        for station_plan in plan.station_plans:
            records_updated = self._load_station_plan(
                environment, station_plan, year, repository_factory
            )
            total_records_updated += records_updated
            processed_packages.extend(station_plan.packages)

        return UpdateQr02CbaLoadResult(
            records_updated=total_records_updated,
            processed_packages=processed_packages,
        )

    def _load_station_plan(
        self,
        environment: ProjectEnvironment,
        station_plan: UpdateQr02StationPlan,
        year: str,
        repository_factory: Callable[[WorkspaceStorage, str, str], Qr02Repository] | None,
    ) -> int:
        """Load records for a single station plan using repository transaction."""
        repo = self._create_repository(environment, station_plan.station, year, repository_factory)
        with repo.transaction() as tx:
            return tx.upsert_qr02_cba_records(station_plan.records)

    def _create_repository(
        self,
        environment: ProjectEnvironment,
        station: str,
        year: str,
        repository_factory: Callable[[WorkspaceStorage, str, str], Qr02Repository] | None,
    ) -> Qr02Repository:
        """Instantiate Qr02Repository via factory or default LocalExcelQr02Repository."""
        if repository_factory is not None:
            return repository_factory(environment.storage, station, year)
        return LocalExcelQr02Repository(environment.storage, station, year)


class UpdateQr02CbaAuditor:
    """Stage 6: Auditor (Verification & History Logging Stage)

    Audits output processing, records history entries, and constructs UpdateQr02CbaResult telemetry.
    """

    def audit(
        self,
        environment: ProjectEnvironment,
        plan: UpdateQr02CbaPlan,
        load_result: UpdateQr02CbaLoadResult,
    ) -> UpdateQr02CbaResult:
        """Record processed packages to history and format workflow execution result."""
        python_dir = environment.storage.get_python_dir()
        history_file = python_dir / "qr02_processed_folders.json"
        history_store = ProcessingHistoryStore(history_file)

        newly_processed_keys = history_store.record_processed_packages(
            load_result.processed_packages
        )

        return UpdateQr02CbaResult(
            records_updated=load_result.records_updated,
            processed_folders=tuple(newly_processed_keys),
            warnings=tuple(plan.warnings),
            errors=(),
        )


class UpdateQr02CbaWorkflow:
    """Orchestrates updating QR02 CBA workbook with testsheet data.

    Resilience Policy: best-effort (accumulates warnings for unextractable package data
    and continues processing valid items).
    """

    def __init__(
        self,
        testsheet_repository: SubstationTestsheetRepository | None = None,
        extractor: TestsheetExtractor | None = None,
    ) -> None:
        self.preflight_guard = UpdateQr02CbaPreflightGuard()
        self.extractor = UpdateQr02CbaExtractor(
            testsheet_repository=testsheet_repository, data_extractor=extractor
        )
        self.filter_stage = UpdateQr02CbaFilter()
        self.transformer = UpdateQr02CbaTransformer()
        self.loader = UpdateQr02CbaLoader()
        self.auditor = UpdateQr02CbaAuditor()

    def execute(
        self,
        environment: ProjectEnvironment,
        request: UpdateQr02CbaRequest,
        repository_factory: Callable[[WorkspaceStorage, str, str], Qr02Repository] | None = None,
    ) -> UpdateQr02CbaResult:
        """Execute the Update QR02 CBA workflow across all 6 stages."""
        if request.progress_sink:
            testsheet_dir = environment.storage.get_testsheet_dir()
            request.progress_sink(f"Scanning testsheet packages in {testsheet_dir}...")

        # 2. Extractor (Read package metadata)
        all_packages = self.extractor.extract_packages(environment)

        history_file = environment.storage.get_python_dir() / "qr02_processed_folders.json"
        history = ProcessingHistoryStore(history_file).load()

        # 3. Filter (Filter targets)
        filtered_packages = self.filter_stage.filter(all_packages, request, history)

        if request.progress_sink:
            request.progress_sink(
                f"Discovered {len(all_packages)} packages. Filtered to {len(filtered_packages)} packages to process."
            )

        if not filtered_packages:
            return UpdateQr02CbaResult(
                records_updated=0,
                processed_folders=(),
                warnings=(),
                errors=(),
            )

        year = (
            getattr(environment, "year", None)
            or getattr(environment.metadata, "year", None)
            or "2026"
        )

        # 1. PreflightGuard (Assert target QR02 CBA workbooks exist)
        stations_to_process = {pkg.station for pkg in filtered_packages}
        for station in stations_to_process:
            self.preflight_guard.validate(
                environment=environment,
                station=station,
                year=year,
                repository_factory=repository_factory,
            )

        # 2. Extractor (Read data records)
        records_map, extraction_warnings = self.extractor.extract_records(filtered_packages)
        if request.progress_sink:
            for warn_msg in extraction_warnings:
                request.progress_sink(warn_msg)

        # 4. Transformer (Transform into load plan)
        plan = self.transformer.transform(filtered_packages, records_map, extraction_warnings)

        # 5. Loader (Write to target)
        if request.progress_sink:
            for station_plan in plan.station_plans:
                request.progress_sink(
                    f"Processing station '{station_plan.station}' ({len(station_plan.packages)} packages)..."
                )

        load_result = self.loader.load(
            environment=environment,
            plan=plan,
            year=year,
            repository_factory=repository_factory,
        )

        # 6. Auditor (Verify and return result)
        result = self.auditor.audit(environment, plan, load_result)

        if request.progress_sink:
            request.progress_sink(
                f"Update QR02 CBA workflow complete. {result.records_updated} records updated."
            )

        return result
