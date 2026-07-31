"""Repository for discovering testsheet packages in Pahang nested input tree."""

from __future__ import annotations

import re
from pathlib import Path

from src.core.normalizers import format_month_folder
from src.testsheet.extractor import TestsheetExtractor
from src.testsheet.models import SubstationTestsheetPackage


class SubstationTestsheetRepository:
    """Discovers testsheet packages across Pahang's TESTSHEET directory hierarchy."""

    def __init__(self, extractor: TestsheetExtractor | None = None) -> None:
        self.extractor = extractor or TestsheetExtractor()

    def discover_packages(self, root_path: Path | str) -> list[SubstationTestsheetPackage]:
        """Discover all testsheet packages under root_path."""
        root = Path(root_path)
        if not root.exists():
            return []

        date_folders: list[Path] = []
        if re.match(r"^\d{2}-\d{2}-\d{4}$", root.name) and root.is_dir():
            date_folders.append(root)
        else:
            date_folders = self._find_date_folders(root)

        packages: list[SubstationTestsheetPackage] = []
        for df in date_folders:
            station = ""
            raw_month = ""
            date_str = df.name

            # Infer station and month from relative parent directory structure
            for idx, part in enumerate(df.parts):
                if part.upper() in ("TESTSHEET", "RAW MATERIAL") and idx + 2 < len(df.parts):
                    station = df.parts[idx + 1]
                    raw_month = df.parts[idx + 2]
                    break

            if not raw_month:
                if df.parent and not df.parent.name.upper().startswith("TESTSHEET"):
                    raw_month = df.parent.name
            if not station:
                if df.parent and df.parent.parent and not df.parent.parent.name.upper().startswith("TESTSHEET"):
                    station = df.parent.parent.name

            month = format_month_folder(raw_month) or format_month_folder(date_str)
            unsorted_dir = df / "UNSORTED RAW DATA"

            xlsx_files = [
                f for f in sorted(df.glob("*.xlsx"))
                if not f.name.startswith("~$")
            ]

            for xlsx_path in xlsx_files:
                substation_number = 1
                match = re.match(r"^(\d+)", xlsx_path.name)
                if match:
                    substation_number = int(match.group(1))

                data = None
                try:
                    data = self.extractor.extract_testsheet_data(
                        xlsx_path, station_hint=station, date_hint=date_str
                    )
                except Exception:
                    pass

                pkg = SubstationTestsheetPackage(
                    testsheet_path=xlsx_path,
                    unsorted_raw_data_dir=unsorted_dir,
                    station=station,
                    month=month,
                    date_str=date_str,
                    substation_number=substation_number,
                    data=data,
                )
                packages.append(pkg)

        return packages

    def _find_date_folders(self, directory: Path) -> list[Path]:
        """Find all date-formatted directories (DD-MM-YYYY) recursively under directory."""
        date_folders: list[Path] = []
        for p in directory.rglob("*"):
            if p.is_dir() and re.match(r"^\d{2}-\d{2}-\d{4}$", p.name):
                date_folders.append(p)
        date_folders.sort(key=lambda d: d.name, reverse=True)
        return date_folders
