"""Update QR02 CBA workflow orchestrator for Pahang CLI."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from src.master.qr02 import LocalExcelQr02Repository, Qr02Repository
from src.project.environment import ProjectEnvironment
from src.project.storage import WorkspaceStorage
from src.testsheet.extractor import TestsheetExtractor
from src.testsheet.models import SubstationTestsheetPackage, TestsheetData
from src.testsheet.repository import SubstationTestsheetRepository
from src.workflows.models import (
    PopulateMode,
    UpdateQr02CbaRequest,
    UpdateQr02CbaResult,
)


def get_package_key(pkg: SubstationTestsheetPackage) -> str:
    """Format package history key: <STATION>/<MONTH>/<DD-MM-YYYY>."""
    date_str = pkg.date_str or (pkg.data.date_str if pkg.data else "")
    parts = [p for p in (pkg.station, pkg.month, date_str) if p]
    return "/".join(parts)


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


class UpdateQr02CbaWorkflow:
    """Orchestrates updating QR02 CBA workbook with testsheet data."""

    def __init__(
        self,
        testsheet_repository: SubstationTestsheetRepository | None = None,
        extractor: TestsheetExtractor | None = None,
    ) -> None:
        self.testsheet_repository = testsheet_repository or SubstationTestsheetRepository()
        self.extractor = extractor or TestsheetExtractor()

    def execute(
        self,
        environment: ProjectEnvironment,
        request: UpdateQr02CbaRequest,
        repository_factory: Callable[[WorkspaceStorage, str, str], Qr02Repository] | None = None,
    ) -> UpdateQr02CbaResult:
        testsheet_dir = environment.storage.get_testsheet_dir()
        python_dir = environment.storage.get_python_dir()
        history_file = python_dir / "processed_folders.json"

        if request.progress_sink:
            request.progress_sink(f"Scanning testsheet packages in {testsheet_dir}...")

        packages = self.testsheet_repository.discover_packages(testsheet_dir)

        # Read processing history from PYTHON/processed_folders.json
        history: dict[str, Any] = {}
        if history_file.exists():
            try:
                with history_file.open("r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = {}

        # Determine processing mode
        is_all_mode = (
            request.mode == PopulateMode.ALL
            or any(str(t).strip().lower() == "all" for t in request.target_package_names)
        )
        is_specific_mode = (
            request.mode == PopulateMode.SPECIFIC_FOLDERS
            or (bool(request.target_package_names) and not is_all_mode)
        )

        # Filter packages
        filtered_packages: list[SubstationTestsheetPackage] = []
        if is_all_mode:
            filtered_packages = list(packages)
        elif is_specific_mode:
            filtered_packages = [
                pkg
                for pkg in packages
                if any(_matches_target(pkg, get_package_key(pkg), t) for t in request.target_package_names)
            ]
        else:
            # AUTO mode: skip packages whose key is in history
            filtered_packages = [
                pkg for pkg in packages if get_package_key(pkg) not in history
            ]

        if request.progress_sink:
            request.progress_sink(
                f"Discovered {len(packages)} packages. Filtered to {len(filtered_packages)} packages to process."
            )

        if not filtered_packages:
            return UpdateQr02CbaResult(
                records_updated=0,
                processed_folders=(),
                warnings=(),
                errors=(),
            )

        # Group packages by station
        station_groups: dict[str, list[SubstationTestsheetPackage]] = defaultdict(list)
        for pkg in filtered_packages:
            station_groups[pkg.station].append(pkg)

        year = getattr(environment, "year", None) or getattr(environment.metadata, "year", None) or "2026"
        total_records_updated = 0
        warnings: list[str] = []
        errors: list[str] = []
        processed_packages: list[SubstationTestsheetPackage] = []

        # Process each station group
        for station, station_pkgs in station_groups.items():
            if request.progress_sink:
                request.progress_sink(f"Processing station '{station}' ({len(station_pkgs)} packages)...")

            station_records: list[TestsheetData] = []
            station_processed_pkgs: list[SubstationTestsheetPackage] = []

            for pkg in station_pkgs:
                data = pkg.data
                if data is None:
                    try:
                        data = self.extractor.extract_testsheet_data(
                            pkg.testsheet_path,
                            station_hint=pkg.station,
                            date_hint=pkg.date_str,
                        )
                    except Exception as exc:
                        warn_msg = f"Failed to extract testsheet data from {pkg.testsheet_path}: {exc}"
                        warnings.append(warn_msg)
                        if request.progress_sink:
                            request.progress_sink(warn_msg)
                        continue

                station_records.append(data)
                station_processed_pkgs.append(pkg)

            if not station_records:
                continue

            # Resolve repository
            if repository_factory is not None:
                repo = repository_factory(environment.storage, station, year)
            else:
                repo = LocalExcelQr02Repository(environment.storage, station, year)

            # Open transaction and upsert records
            with repo.transaction() as tx:
                updated = tx.upsert_qr02_cba_records(station_records)
                total_records_updated += updated

            processed_packages.extend(station_processed_pkgs)

        # Update processed_folders.json
        newly_processed_keys: list[str] = []
        if processed_packages:
            files_per_key: dict[str, int] = defaultdict(int)
            for pkg in processed_packages:
                key = get_package_key(pkg)
                if key:
                    files_per_key[key] += 1

            now_iso = datetime.now().isoformat()
            for key, count in files_per_key.items():
                history[key] = {
                    "last_processed": now_iso,
                    "files_scanned": count,
                }
                newly_processed_keys.append(key)

            python_dir.mkdir(parents=True, exist_ok=True)
            with history_file.open("w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)

        if request.progress_sink:
            request.progress_sink(
                f"Update QR02 CBA workflow complete. {total_records_updated} records updated."
            )

        return UpdateQr02CbaResult(
            records_updated=total_records_updated,
            processed_folders=sorted(list(set(newly_processed_keys))),
            warnings=warnings,
            errors=errors,
        )


def run_update_qr02_cba(
    environment: ProjectEnvironment,
    request: UpdateQr02CbaRequest,
    repository_factory: Callable[[WorkspaceStorage, str, str], Qr02Repository] | None = None,
) -> UpdateQr02CbaResult:
    """Standalone function entrypoint for Update QR02 CBA workflow."""
    return UpdateQr02CbaWorkflow().execute(
        environment=environment,
        request=request,
        repository_factory=repository_factory,
    )
