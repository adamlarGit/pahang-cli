"""Workspace storage abstractions and implementations for Pahang CLI."""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from pathlib import Path

import config
from src.project.models import HealthCheckItem, WorkspaceHealth


def sanitize_filename(name: str) -> str:
    """Remove invalid characters from Windows filename."""
    return re.sub(r'[<>:"/\\|?*]', '', name)


def get_next_file_number(directory: str | Path, pattern: str = r'^(\d+)\.') -> int:
    """Find next sequential file number in directory."""
    if not os.path.exists(directory):
        return 1

    existing_numbers = []
    for f in os.listdir(directory):
        match = re.match(pattern, f)
        if match:
            try:
                existing_numbers.append(int(match.group(1)))
            except ValueError:
                continue

    return max(existing_numbers) + 1 if existing_numbers else 1


def extract_numerical_prefix(filename: str, split_char: str | None = None) -> int:
    """Extract leading numerical prefix from filename."""
    if split_char:
        filename = filename.split(split_char, 1)[0]

    match = re.match(r'^(\d+)', filename)
    if not match:
        raise ValueError(f"No numerical prefix found in {filename}")
    return int(match.group(1))


def is_canonical_msms_csv_name(filename: str) -> bool:
    """Check if filename matches canonical DD-MM-YYYY(_NNN).csv format."""
    return bool(re.match(r"^(\d{2}-\d{2}-\d{4})(_\d{3})?\.csv$", filename, re.IGNORECASE))



class WorkspaceStorage(ABC):
    """Abstract base class for project folder and file resolution."""

    @property
    @abstractmethod
    def root_path(self) -> Path:
        """Return the root path of the project workspace."""

    @abstractmethod
    def get_python_dir(self) -> Path:
        """Return the PYTHON directory path."""

    @abstractmethod
    def get_testsheet_dir(self) -> Path:
        """Return the TESTSHEET directory path."""

    @abstractmethod
    def get_raw_material_dir(self) -> Path:
        """Return the RAW MATERIAL directory path."""

    @abstractmethod
    def get_quick_report_dir(self) -> Path:
        """Return the QUICK REPORT directory path."""

    @abstractmethod
    def get_engr_folder(self) -> Path:
        """Return the engineering files folder path."""

    @abstractmethod
    def list_engr_files(self) -> list[Path]:
        """Return matching ENGR Excel files in the engineering folder."""

    @abstractmethod
    def get_total_pe_path(self) -> Path:
        """Return the TOTAL PE.xlsx file path."""

    @abstractmethod
    def get_data_msms_path(self) -> Path:
        """Return the DATA MSMS.xlsx file path."""

    @abstractmethod
    def get_msms_dir(self) -> Path:
        """Return the PYTHON/MSMS directory path."""

    @abstractmethod
    def get_msms_raw_data_dir(self) -> Path:
        """Return the PYTHON/MSMS/RAW DATA directory path."""

    @abstractmethod
    def get_msms_to_be_filled_dir(self) -> Path:
        """Return the PYTHON/MSMS/TO BE FILLED directory path."""

    @abstractmethod
    def get_msms_completed_dir(self) -> Path:
        """Return the PYTHON/MSMS/COMPLETED directory path."""

    @abstractmethod
    def get_python_msms_dir(self) -> Path:
        """Return the PYTHON/MSMS directory path."""

    @abstractmethod
    def get_python_msms_completed_dir(self) -> Path:
        """Return the PYTHON/MSMS/COMPLETED directory path."""

    @abstractmethod
    def list_msms_xls_files(self) -> list[Path]:
        """Return matching scattered .xls files in PYTHON/MSMS."""

    @abstractmethod
    def list_msms_raw_csv_files(self) -> list[Path]:
        """Return matching raw CSV files in PYTHON/MSMS/RAW DATA (or TO BE FILLED fallback)."""

    @abstractmethod
    def list_msms_to_be_filled_csv_files(self) -> list[Path]:
        """Return matching CSV files in PYTHON/MSMS/TO BE FILLED."""

    @abstractmethod
    def get_whatsapp_dir(self) -> Path:
        """Return the WHATSAPP directory path."""

    @abstractmethod
    def get_sign_dir(self) -> Path:
        """Return the OTHERS/SIGN directory path for signatures."""

    @abstractmethod
    def get_template(self, key: str) -> Path:
        """Return the resolved path for a template key."""


    @abstractmethod
    def validate_existence(self) -> None:
        """Validate required workspace directories exist."""

    @abstractmethod
    def list_testsheet_folders(self) -> list[Path]:
        """Returns ordered list of testsheet folder paths (descending)."""

    @abstractmethod
    def list_quick_report_folders(self) -> list[Path]:
        """Returns ordered list of quick report folder paths (descending)."""

    @abstractmethod
    def ensure_directory(self, path: Path | str) -> Path:
        """Ensure a directory and its parents exist and return as Path."""

    @abstractmethod
    def get_engr_cba_path(self, station: str, year: str) -> Path:
        """Return the ENGR CBA workbook path for a specific station and year."""

    @abstractmethod
    def resolve_template_path(self, key: str) -> Path:
        """Resolve and validate existence of a template path by key."""

    @abstractmethod
    def check_workspace_health(self) -> WorkspaceHealth:
        """Inspect and report existence status for core workspace folders and seed files."""


class LocalWorkspaceStorage(WorkspaceStorage):
    """Workspace storage resolved on the local filesystem."""

    def __init__(self, root_path: Path | str, templates_dir: Path | None = None) -> None:
        self._root_path = Path(root_path)
        if templates_dir is None:
            self._templates_dir = self._root_path / "templates"
        else:
            self._templates_dir = Path(templates_dir)

    @property
    def root_path(self) -> Path:
        return self._root_path

    def get_python_dir(self) -> Path:
        return self.root_path / "PYTHON"

    def get_testsheet_dir(self) -> Path:
        return self.root_path / "TESTSHEET"

    def get_raw_material_dir(self) -> Path:
        return self.root_path / "RAW MATERIAL"

    def get_quick_report_dir(self) -> Path:
        return self.root_path / "QUICK REPORT"

    def get_engr_folder(self) -> Path:
        return self.get_python_dir() / "ENGR FROM DRIVE"

    def list_engr_files(self) -> list[Path]:
        engr_dir = self.get_engr_folder()
        if not engr_dir.exists():
            return []
        return sorted(list(engr_dir.glob("ENGR-*.xlsx")))

    def get_total_pe_path(self) -> Path:
        return self.get_python_dir() / "TOTAL PE.xlsx"

    def get_data_msms_path(self) -> Path:
        return self.get_python_dir() / "DATA MSMS.xlsx"

    def get_msms_dir(self) -> Path:
        return self.get_python_dir() / "MSMS"

    def get_msms_raw_data_dir(self) -> Path:
        return self.get_msms_dir() / "RAW DATA"

    def get_msms_to_be_filled_dir(self) -> Path:
        return self.get_msms_dir() / "TO BE FILLED"

    def get_msms_completed_dir(self) -> Path:
        return self.get_msms_dir() / "COMPLETED"

    def get_python_msms_dir(self) -> Path:
        return self.get_msms_dir()

    def get_python_msms_completed_dir(self) -> Path:
        return self.get_msms_completed_dir()

    def list_msms_xls_files(self) -> list[Path]:
        msms_dir = self.get_msms_dir()
        if not msms_dir.exists() or not msms_dir.is_dir():
            return []
        return sorted([p for p in msms_dir.glob("*.xls") if p.is_file()])

    def list_msms_raw_csv_files(self) -> list[Path]:
        raw_dir = self.get_msms_raw_data_dir()
        if raw_dir.exists() and raw_dir.is_dir():
            raw_files = sorted([p for p in raw_dir.glob("*.csv") if p.is_file()])
            if raw_files:
                return raw_files

        to_be_filled_dir = self.get_msms_to_be_filled_dir()
        if to_be_filled_dir.exists() and to_be_filled_dir.is_dir():
            return sorted([
                p for p in to_be_filled_dir.glob("*.csv")
                if p.is_file() and not is_canonical_msms_csv_name(p.name)
            ])

        return []

    def list_msms_to_be_filled_csv_files(self) -> list[Path]:
        to_be_filled_dir = self.get_msms_to_be_filled_dir()
        if not to_be_filled_dir.exists() or not to_be_filled_dir.is_dir():
            return []
        return sorted([p for p in to_be_filled_dir.glob("*.csv") if p.is_file()])


    def get_whatsapp_dir(self) -> Path:
        return self.get_python_dir() / "WHATSAPP"

    def get_sign_dir(self) -> Path:
        return self.root_path / "OTHERS" / "SIGN"

    def get_template(self, key: str) -> Path:

        if key not in config.TEMPLATES:
            raise KeyError(f"Unknown template key: {key}")

        relative_path = config.TEMPLATES[key]
        local_path = self._templates_dir / relative_path

        if not local_path.exists():
            raise FileNotFoundError(
                f"Required project template '{key}' ({relative_path}) is missing at '{local_path}'. "
                f"Every project must contain its own templates in its project root directory ('{self.root_path}')."
            )
        return local_path

    def validate_existence(self) -> None:
        required = [self.root_path, self.get_python_dir()]
        missing = [p for p in required if not p.exists()]
        if missing:
            raise FileNotFoundError(f"Required path missing: {missing[0]}")

    def list_testsheet_folders(self) -> list[Path]:
        testsheet_dir = self.get_testsheet_dir()
        if not testsheet_dir.exists() or not testsheet_dir.is_dir():
            return []

        num_folders: list[tuple[int, Path]] = []
        other_folders: list[Path] = []
        for p in testsheet_dir.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            try:
                num = extract_numerical_prefix(p.name)
                num_folders.append((num, p))
            except ValueError:
                other_folders.append(p)

        if num_folders:
            num_folders.sort(key=lambda item: (item[0], item[1].name), reverse=True)
            return [p for _, p in num_folders] + sorted(other_folders, key=lambda p: p.name, reverse=True)
        return sorted(other_folders, key=lambda p: p.name, reverse=True)

    def list_quick_report_folders(self) -> list[Path]:
        qr_dir = self.get_quick_report_dir()
        if not qr_dir.exists() or not qr_dir.is_dir():
            return []

        num_folders: list[tuple[int, Path]] = []
        other_folders: list[Path] = []
        for p in qr_dir.iterdir():
            if not p.is_dir() or p.name.startswith("."):
                continue
            try:
                num = extract_numerical_prefix(p.name)
                num_folders.append((num, p))
            except ValueError:
                other_folders.append(p)

        if num_folders:
            num_folders.sort(key=lambda item: (item[0], item[1].name), reverse=True)
            return [p for _, p in num_folders] + sorted(other_folders, key=lambda p: p.name, reverse=True)
        return sorted(other_folders, key=lambda p: p.name, reverse=True)

    def ensure_directory(self, path: Path | str) -> Path:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_engr_cba_path(self, station: str, year: str) -> Path:
        """Resolve per-station ENGR CBA workbook path.

        Pattern: PYTHON/ENGR FROM DRIVE/ENGR-750-36-CBA-{STATION_CODE}-{YEAR}.xlsx
        """
        station_upper = station.strip().upper()
        if station_upper not in config.ENGR_STATION_CODES:
            raise ValueError(
                f"Unknown station '{station}'. "
                f"Valid stations: {', '.join(sorted(config.ENGR_STATION_CODES.keys()))}"
            )
        code = config.ENGR_STATION_CODES[station_upper]
        return self.get_engr_folder() / f"ENGR-750-36-CBA-{code}-{year}.xlsx"

    def resolve_template_path(self, key: str) -> Path:
        # get_template now strictly verifies existence and raises if missing
        return self.get_template(key)
    def _initialize_project_workspace(self) -> None:
        """Copy missing master seed templates and seed files to the project workspace."""
        import shutil
        import logging

        logger = logging.getLogger(__name__)

        # Create core workspace subdirectories
        for dir_fn in (
            self.get_python_dir,
            self.get_testsheet_dir,
            self.get_raw_material_dir,
            self.get_quick_report_dir,
            self.get_engr_folder,
            self.get_whatsapp_dir,
            self.get_msms_dir,
            self.get_msms_raw_data_dir,
            self.get_msms_to_be_filled_dir,
            self.get_msms_completed_dir,
        ):
            dir_fn().mkdir(parents=True, exist_ok=True)

        def _safe_copy(src: Path, dst: Path) -> None:

            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_file():
                    shutil.copy2(src, dst)
                elif src.is_dir():
                    shutil.copytree(src, dst)
            except (PermissionError, OSError, FileNotFoundError) as e:
                logger.warning(f"Failed to copy template from {src} to {dst}: {e}")

        # Copy TEMPLATES
        for key, relative_path in config.TEMPLATES.items():
            global_path = config.GLOBAL_TEMPLATES_DIR / relative_path
            local_path = self._templates_dir / relative_path

            if global_path.exists() and not local_path.exists():
                _safe_copy(global_path, local_path)

        # Copy SEED_FILES
        if hasattr(config, "SEED_FILES"):
            for source_rel, target_rel in config.SEED_FILES.items():
                global_path = config.GLOBAL_TEMPLATES_DIR / source_rel
                local_path = self._root_path / target_rel

                if global_path.exists() and not local_path.exists():
                    _safe_copy(global_path, local_path)

    def check_workspace_health(self) -> WorkspaceHealth:
        """Inspect and report existence status for core workspace folders and seed files."""
        targets = [
            ("Workspace Root Directory", self.root_path, True),
            ("PYTHON Directory", self.get_python_dir(), True),
            ("TESTSHEET Directory", self.get_testsheet_dir(), True),
            ("RAW MATERIAL Directory", self.get_raw_material_dir(), True),
            ("QUICK REPORT Directory", self.get_quick_report_dir(), True),
            ("ENGR FROM DRIVE Directory", self.get_engr_folder(), True),
            ("MSMS Directory", self.get_msms_dir(), False),
            ("MSMS RAW DATA Directory", self.get_msms_raw_data_dir(), False),
            ("MSMS TO BE FILLED Directory", self.get_msms_to_be_filled_dir(), False),
            ("MSMS COMPLETED Directory", self.get_msms_completed_dir(), False),
            ("Seed Data: TOTAL PE.xlsx", self.get_total_pe_path(), True),
            ("Seed Data: DATA MSMS.xlsx", self.get_data_msms_path(), True),
        ]
        items = tuple(
            HealthCheckItem(
                label=label,
                path=str(path),
                exists=path.exists(),
                is_critical=is_critical,
            )
            for label, path, is_critical in targets
        )
        is_healthy = all(item.exists for item in items if item.is_critical)
        return WorkspaceHealth(is_healthy=is_healthy, items=items)

