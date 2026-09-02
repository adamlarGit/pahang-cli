"""Repository for discovering testsheet packages in Pahang nested input tree."""

from __future__ import annotations

import re
from pathlib import Path

from src.core.normalizers import format_month_folder
from src.project.storage import extract_numerical_prefix
from src.testsheet.extractor import TestsheetExtractor
from src.testsheet.models import SubstationPackage, SubstationTestsheetPackage


class SubstationTestsheetRepository:
    """Discovers testsheet packages across Pahang's TESTSHEET directory hierarchy."""

    def __init__(self, extractor: TestsheetExtractor | None = None) -> None:
        self.extractor = extractor or TestsheetExtractor()

    def discover_packages(
        self,
        root_path: Path | str,
        eager_extract: bool = True,
    ) -> list[SubstationTestsheetPackage]:
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
                if eager_extract:
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


class LocalTestsheetPackageRepository:
    """Repository for discovering and pairing testsheet (.xlsx) and quick report (.docx) packages."""

    def __init__(self, extractor: TestsheetExtractor | None = None) -> None:
        self.extractor = extractor or TestsheetExtractor()

    def find_packages(
        self,
        testsheet_dir: Path | str,
        quick_report_dir: Path | str,
    ) -> list[SubstationPackage]:
        """Scan TESTSHEET and QUICK REPORT directories to discover paired substation packages."""
        ts_root = Path(testsheet_dir).expanduser().resolve()
        qr_root = Path(quick_report_dir).expanduser().resolve()

        if not ts_root.exists() or not qr_root.exists():
            return []

        from src.workflows.postprocessing_preflight import (
            filter_valid_quick_reports,
            filter_valid_testsheets,
        )

        # Find candidate directory pairs (date_folder_name, ts_dir, qr_dir)
        date_folder_pairs: list[tuple[str, Path, Path]] = []

        # 1. Flat root directory check
        ts_root_files = filter_valid_testsheets(ts_root)
        qr_root_files = filter_valid_quick_reports(qr_root)
        if ts_root_files and qr_root_files:
            date_folder_pairs.append((ts_root.name, ts_root, qr_root))

        # 2. Recursive subdirectories check under ts_root
        for ts_sub in sorted(ts_root.rglob("*")):
            if ts_sub.is_dir() and not ts_sub.name.startswith((".", "~$", "processed_")):
                ts_files = filter_valid_testsheets(ts_sub)
                if ts_files:
                    try:
                        rel = ts_sub.relative_to(ts_root)
                        qr_candidate = qr_root / rel
                    except ValueError:
                        qr_candidate = qr_root / ts_sub.name

                    if not (qr_candidate.exists() and qr_candidate.is_dir()):
                        qr_candidate = qr_root / ts_sub.name

                    if qr_candidate.exists() and qr_candidate.is_dir():
                        date_folder_pairs.append((ts_sub.name, ts_sub, qr_candidate))

        packages: list[SubstationPackage] = []
        seen_pairs: set[tuple[Path, Path]] = set()

        for df_name, ts_folder, qr_folder in date_folder_pairs:
            ts_files = filter_valid_testsheets(ts_folder)
            qr_files = filter_valid_quick_reports(qr_folder)

            # Match files by numerical prefix
            prefix_to_qr: dict[int, Path] = {}
            for qf in qr_files:
                try:
                    pfx = extract_numerical_prefix(qf.name)
                    prefix_to_qr[pfx] = qf
                except ValueError:
                    try:
                        pfx = extract_numerical_prefix(qf.name, split_char="_")
                        prefix_to_qr[pfx] = qf
                    except ValueError:
                        pass

            pairs: list[tuple[Path, Path]] = []
            for tf in ts_files:
                pfx = None
                try:
                    pfx = extract_numerical_prefix(tf.name)
                except ValueError:
                    try:
                        pfx = extract_numerical_prefix(tf.name, split_char="_")
                    except ValueError:
                        pass

                if pfx is not None and pfx in prefix_to_qr:
                    pairs.append((tf, prefix_to_qr[pfx]))

            if len(pairs) != len(ts_files) and len(ts_files) == len(qr_files):
                pairs = list(zip(ts_files, qr_files))
            elif len(pairs) != len(ts_files) and len(pairs) == 0:
                pairs = list(zip(ts_files, qr_files))

            for tf, qf in pairs:
                pair_key = (tf.resolve(), qf.resolve())
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                sub_num = 0
                try:
                    sub_num = extract_numerical_prefix(qf.name)
                except ValueError:
                    try:
                        sub_num = extract_numerical_prefix(tf.name)
                    except ValueError:
                        pass

                station_name = qf.stem
                fl_erms = ""

                m = re.match(r"^(\d+)[\.\-_]\s*(.*?)(?:\((.*?)\))?$", qf.stem)
                if m:
                    station_name = m.group(2).strip()

                try:
                    ts_data = self.extractor.extract_testsheet_data(tf)
                    if ts_data.fl_erms:
                        fl_erms = ts_data.fl_erms
                    if ts_data.substation_name_erms:
                        station_name = ts_data.substation_name_erms
                    if ts_data.substation_number:
                        sub_num = ts_data.substation_number
                except Exception:
                    pass

                pkg = SubstationPackage(
                    testsheet_xlsx=tf,
                    quick_report_docx=qf,
                    date_folder=df_name,
                    station_name=station_name or qf.stem,
                    fl_erms=fl_erms,
                    substation_number=sub_num,
                )
                packages.append(pkg)

        return packages

