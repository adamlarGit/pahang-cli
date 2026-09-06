"""Defect extraction and normalization module for Quick Report composer."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any, TYPE_CHECKING
import pandas as pd

from config import ENGR_STATION_CODES
from src.core.normalizers import normalize_us_characteristic, resolve_station_code
from src.quick_report.utils import normalize_functional_location_input

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment
    from src.project.storage import WorkspaceStorage


def _clean_val(val: Any) -> str:
    """Normalize a pandas cell value to a clean string, converting NaN/None to empty string."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


@dataclass(frozen=True)
class CbmDefectRecord:
    """Normalized CBM (IR/US/TEV) defect record.

    Fields map to QR03 CBA Excel columns:
    - raw_measurement: The raw value from the READING column, before technology-specific splitting.
    - ir_reading: IR temperature reading (from READING if tech==IR, else IR READING column).
    - us_reading: US dB reading (from READING if tech==US, else US READING column).
    - us_char: US waveform characteristic.
    - tev_reading: TEV dB reading (from READING if tech==TEV, else TEV READING column).
    - tev_char: TEV waveform characteristic.
    - additional_remarks: From ADDITIONAL REMARKS or REMARKS Excel column.
    - equipment_id: Equipment identifier / panel / feeder / tx identifier.
    """

    equipment: str = ""
    technology: str = ""
    brand: str = ""
    model: str = ""
    rating: str = ""
    defect_area: str = ""
    additional_remarks: str = ""
    ir_reading: str = ""
    us_reading: str = ""
    us_char: str = ""
    tev_reading: str = ""
    tev_char: str = ""
    raw_measurement: str = ""
    equipment_id: str = ""
    source_order: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "technology", _clean_val(self.technology).upper())
        object.__setattr__(self, "equipment", _clean_val(self.equipment))
        object.__setattr__(self, "brand", _clean_val(self.brand))
        object.__setattr__(self, "model", _clean_val(self.model))
        object.__setattr__(self, "rating", _clean_val(self.rating))
        object.__setattr__(self, "defect_area", _clean_val(self.defect_area))
        object.__setattr__(self, "additional_remarks", _clean_val(self.additional_remarks))
        object.__setattr__(self, "ir_reading", _clean_val(self.ir_reading))
        object.__setattr__(self, "us_reading", _clean_val(self.us_reading))
        object.__setattr__(self, "us_char", _clean_val(self.us_char))
        object.__setattr__(self, "tev_reading", _clean_val(self.tev_reading))
        object.__setattr__(self, "tev_char", _clean_val(self.tev_char))
        object.__setattr__(self, "raw_measurement", _clean_val(self.raw_measurement))
        object.__setattr__(self, "equipment_id", _clean_val(self.equipment_id))

        tech = self.technology
        raw = self.raw_measurement
        if tech == "IR":
            if raw and not self.ir_reading:
                object.__setattr__(self, "ir_reading", raw)
            elif self.ir_reading and not raw:
                object.__setattr__(self, "raw_measurement", self.ir_reading)
        elif tech == "US":
            if raw and not self.us_reading:
                object.__setattr__(self, "us_reading", raw)
            elif self.us_reading and not raw:
                object.__setattr__(self, "raw_measurement", self.us_reading)
        elif tech == "TEV":
            if raw and not self.tev_reading:
                object.__setattr__(self, "tev_reading", raw)
            elif self.tev_reading and not raw:
                object.__setattr__(self, "raw_measurement", self.tev_reading)

    def to_dict(self) -> dict:
        """Convert record to dictionary."""
        return {
            "equipment": self.equipment,
            "technology": self.technology,
            "brand": self.brand,
            "model": self.model,
            "rating": self.rating,
            "defect_area": self.defect_area,
            "additional_remarks": self.additional_remarks,
            "ir_reading": self.ir_reading,
            "us_reading": self.us_reading,
            "us_char": self.us_char,
            "tev_reading": self.tev_reading,
            "tev_char": self.tev_char,
            "raw_measurement": self.raw_measurement,
            "equipment_id": self.equipment_id,
            "source_order": self.source_order,
        }


@dataclass(frozen=True)
class ViDefectRecord:
    """Normalized Visual Inspection (VI) defect record."""

    equipment: str = ""
    defect_area: str = ""
    additional_remarks: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "equipment", _clean_val(self.equipment))
        object.__setattr__(self, "defect_area", _clean_val(self.defect_area))
        object.__setattr__(self, "additional_remarks", _clean_val(self.additional_remarks))

    def to_dict(self) -> dict:
        return {
            "equipment": self.equipment,
            "defect_area": self.defect_area,
            "remarks": self.additional_remarks,
        }


class MasterQr03DefectRepository:
    """Repository for fetching CBM & VI defects strictly from master QR03 Excel workbooks in PYTHON/ENGR FROM DRIVE.

    Loads and validates QR03 CBA and QR03 VI sheets once on first access,
    then serves per-FL lookups from cached DataFrames.
    """

    def __init__(
        self,
        engr_dir: Path | str | None = None,
        storage: WorkspaceStorage | None = None,
        environment: ProjectEnvironment | None = None,
    ) -> None:
        if engr_dir:
            self.engr_dir = Path(engr_dir)
        elif storage:
            self.engr_dir = storage.get_engr_folder()
        elif environment:
            self.engr_dir = environment.storage.get_engr_folder()
        else:
            raise ValueError(
                "Must provide either engr_dir, storage, or environment to resolve ENGR folder."
            )

        self._file_cache: dict[
            Path,
            tuple[list[tuple[pd.DataFrame, str]], list[tuple[pd.DataFrame, str]]],
        ] = {}
        self._loaded: bool = False

    def _get_engr_files(self) -> list[Path]:
        if not self.engr_dir or not self.engr_dir.exists():
            raise FileNotFoundError(
                f"Required ENGR directory does not exist: {self.engr_dir}"
            )

        files = [
            f
            for f in sorted(self.engr_dir.iterdir())
            if f.is_file()
            and f.suffix.lower() in {".xlsx", ".xls"}
            and not f.name.startswith("~$")
        ]
        if not files:
            raise FileNotFoundError(
                f"No ENGR Excel workbooks found in directory: {self.engr_dir}"
            )

        return files

    def _extract_df_and_fl_col(
        self, xl: pd.ExcelFile, sheet_name: str
    ) -> tuple[pd.DataFrame | None, str | None]:
        for header_idx in (0, 1):
            temp_df = pd.read_excel(
                xl, sheet_name=sheet_name, header=header_idx, engine="openpyxl"
            )
            candidate_col = next(
                (
                    c
                    for c in temp_df.columns
                    if "FUNCTIONAL" in str(c).upper() or "FL" in str(c).upper()
                ),
                None,
            )
            if candidate_col:
                temp_df["__norm_fl"] = (
                    temp_df[candidate_col]
                    .astype(str)
                    .apply(normalize_functional_location_input)
                )
                return temp_df, candidate_col
        return None, None

    def _load_single_file(
        self, filepath: Path
    ) -> tuple[list[tuple[pd.DataFrame, str]], list[tuple[pd.DataFrame, str]]]:
        """Load and cache QR03 CBA and QR03 VI sheets from a single ENGR master Excel file."""
        resolved = filepath.resolve()
        if resolved in self._file_cache:
            return self._file_cache[resolved]

        try:
            xl = pd.ExcelFile(filepath, engine="openpyxl")

            # Validate and load QR03 CBA
            cba_sheet = next(
                (s for s in xl.sheet_names if s.strip().upper() == "QR03 CBA"),
                None,
            )
            if not cba_sheet:
                raise RuntimeError(
                    f"Missing required sheet 'QR03 CBA' in ENGR master Excel file: {filepath}"
                )

            cbm_dfs: list[tuple[pd.DataFrame, str]] = []
            cbm_df, cbm_fl_col = self._extract_df_and_fl_col(xl, cba_sheet)
            if cbm_df is not None and cbm_fl_col:
                cbm_dfs.append((cbm_df, cbm_fl_col))

            # Validate and load QR03 VI
            vi_sheet = next(
                (s for s in xl.sheet_names if s.strip().upper() == "QR03 VI"),
                None,
            )
            if not vi_sheet:
                raise RuntimeError(
                    f"Missing required sheet 'QR03 VI' in ENGR master Excel file: {filepath}"
                )

            vi_dfs: list[tuple[pd.DataFrame, str]] = []
            vi_df, vi_fl_col = self._extract_df_and_fl_col(xl, vi_sheet)
            if vi_df is not None and vi_fl_col:
                vi_dfs.append((vi_df, vi_fl_col))

            self._file_cache[resolved] = (cbm_dfs, vi_dfs)
            return cbm_dfs, vi_dfs

        except (FileNotFoundError, RuntimeError):
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read CBM defects from workbook {filepath.name}: {exc}"
            ) from exc

    def _load_sheets(self) -> None:
        """Load and validate all ENGR workbooks (bulk load / legacy fallback)."""
        if self._loaded:
            return

        files = self._get_engr_files()
        for filepath in files:
            self._load_single_file(filepath)
        self._loaded = True

    @property
    def _cbm_sheets(self) -> list[tuple[pd.DataFrame, str]]:
        if not self._file_cache:
            self._load_sheets()
        res: list[tuple[pd.DataFrame, str]] = []
        for cbm_dfs, _ in self._file_cache.values():
            res.extend(cbm_dfs)
        return res

    @property
    def _vi_sheets(self) -> list[tuple[pd.DataFrame, str]]:
        if not self._file_cache:
            self._load_sheets()
        res: list[tuple[pd.DataFrame, str]] = []
        for _, vi_dfs in self._file_cache.values():
            res.extend(vi_dfs)
        return res

    def _match_files_for_station(self, code: str, files: list[Path]) -> list[Path]:
        """Find ENGR files matching the given station code."""
        code_upper = code.upper()
        target_codes = {code_upper}
        if code_upper in ("TMH", "TML"):
            target_codes.update({"TMH", "TML"})
        elif code_upper in ("PKN", "PEK"):
            target_codes.update({"PKN", "PEK"})
        elif code_upper in ("BTG", "BTO"):
            target_codes.update({"BTG", "BTO"})

        matches: list[Path] = []
        for f in files:
            name_upper = f.stem.upper()
            parts = re.split(r"[-_\s\.]+", name_upper)
            for c in target_codes:
                if (
                    c in parts
                    or f"-{c}-" in name_upper
                    or f"-{c}." in name_upper
                    or f"_{c}_" in name_upper
                ):
                    matches.append(f)
                    break
        return matches

    def _get_station_files(self, station: str | None) -> tuple[list[Path], bool]:
        """Resolve target ENGR files for station.

        Returns:
            tuple[list[Path], bool]: (files_to_search, is_strictly_matched).
            If station is provided and matches target station workbook(s), returns
            ([matched_files], True).
            Otherwise, returns (all_engr_files, False).
        """
        all_files = self._get_engr_files()
        if station:
            station_code = resolve_station_code(station)
            if station_code:
                target_files = self._match_files_for_station(station_code, all_files)
                if target_files:
                    return target_files, True
        return all_files, False

    def _parse_cbm_defects_from_df(
        self, df: pd.DataFrame, matched_df: pd.DataFrame
    ) -> list[CbmDefectRecord]:
        """Parse matched rows from QR03 CBA sheet into CbmDefectRecord instances."""
        col_map: dict[str, Any] = {}
        for c in df.columns:
            c_str = str(c).strip().upper()
            col_map[c_str] = c
            col_map[c_str.replace(" ", "_")] = c
            col_map[c_str.replace("_", " ")] = c

        us_char_col = next(
            (
                c
                for c in df.columns
                if "US CHAR" in str(c).upper() or "US CHARACTER" in str(c).upper()
            ),
            None,
        )
        tev_char_col = next(
            (
                c
                for c in df.columns
                if "TEV CHAR" in str(c).upper() or "TEV CHARACTER" in str(c).upper()
            ),
            None,
        )
        defect_type_col = next(
            (
                c
                for c in df.columns
                if "DEFECT TYPE" in str(c).upper() or "DEFECT_TYPE" in str(c).upper()
            ),
            None,
        )

        defects: list[CbmDefectRecord] = []
        for idx, (_, row) in enumerate(matched_df.iterrows(), start=1):
            def _get_val(*candidate_keys: str) -> str:
                for key in candidate_keys:
                    k_norm = key.strip().upper()
                    if k_norm in col_map:
                        val = _clean_val(row.get(col_map[k_norm]))
                        if val:
                            return val
                return ""

            tech = _get_val("DEFECT FROM", "TECHNOLOGY", "TECH").upper()
            equipment = _get_val("EQUIPMENT", "EQUIPMENT NAME", "EQUIPMENT_NAME")
            equipment_id = _get_val("EQUIPMENT ID", "EQUIPMENT_ID", "ID")
            brand = _get_val("BRAND")
            model = _get_val("MODEL")
            rating = _get_val("RATING")
            defect_area = _get_val("DEFECT AREA", "DEFECT_AREA", "AREA")
            additional_remarks = _get_val(
                "ADDITIONAL REMARKS", "REMARKS", "ADDITIONAL_REMARKS", "REMARK"
            )
            reading = _get_val(
                "READING",
                "RAW READING",
                "RAW_READING",
                "RAW MEASUREMENT",
                "RAW_MEASUREMENT",
            )

            ir_reading = _get_val("IR READING", "IR_READING")
            us_reading = _get_val("US READING", "US_READING")
            tev_reading = _get_val("TEV READING", "TEV_READING")

            us_char_raw = (
                _clean_val(row.get(us_char_col))
                if us_char_col
                else _get_val("US CHAR", "US CHARACTER", "US_CHAR", "US_CHARACTER")
            )
            if not us_char_raw and tech == "US":
                us_char_raw = (
                    _clean_val(row.get(defect_type_col))
                    if defect_type_col
                    else _get_val("DEFECT TYPE", "DEFECT_TYPE", "DEFECT")
                )
            norm_us = normalize_us_characteristic(us_char_raw)
            us_char = "" if norm_us == "-" else norm_us

            tev_char = (
                _clean_val(row.get(tev_char_col))
                if tev_char_col
                else _get_val("TEV CHAR", "TEV CHARACTER", "TEV_CHAR", "TEV_CHARACTER")
            )
            if not tev_char and tech == "TEV":
                tev_char = (
                    _clean_val(row.get(defect_type_col))
                    if defect_type_col
                    else _get_val("DEFECT TYPE", "DEFECT_TYPE", "DEFECT")
                )

            rec = CbmDefectRecord(
                equipment=equipment,
                technology=tech,
                brand=brand,
                model=model,
                rating=rating,
                defect_area=defect_area,
                additional_remarks=additional_remarks,
                ir_reading=ir_reading,
                us_reading=us_reading,
                us_char=us_char,
                tev_reading=tev_reading,
                tev_char=tev_char,
                raw_measurement=reading,
                equipment_id=equipment_id,
                source_order=idx,
            )
            defects.append(rec)

        return defects

    def _parse_vi_defects_from_df(
        self, df: pd.DataFrame, matched_df: pd.DataFrame
    ) -> list[ViDefectRecord]:
        """Parse matched rows from QR03 VI sheet into ViDefectRecord instances."""
        report_by_col = next(
            (c for c in df.columns if "REPORT" in str(c).upper()),
            None,
        )

        defects: list[ViDefectRecord] = []
        for _, row in matched_df.iterrows():
            if report_by_col is not None:
                report_by_val = _clean_val(row.get(report_by_col)).upper()
                if report_by_val != "EET":
                    continue

            rec = ViDefectRecord(
                equipment=_clean_val(row.get("EQUIPMENT")),
                defect_area=_clean_val(
                    row.get("DEFECT AREA") or row.get("DEFECT_AREA")
                ),
                additional_remarks=_clean_val(
                    row.get("ADDITIONAL REMARKS") or row.get("REMARKS")
                ),
            )
            defects.append(rec)

        return defects

    def fetch_cbm_defects(
        self, fl_erms: str, station: str | None = None
    ) -> list[CbmDefectRecord]:
        """Fetch CBM defects for a functional location strictly from sheet 'QR03 CBA'.

        If station is provided and matches a station workbook, queries ONLY that station
        workbook without touching other station files. Falls back to searching all workbooks
        only if station is None or unmatched.
        """
        if not fl_erms:
            return []

        search_files, _ = self._get_station_files(station)
        normalized_target = normalize_functional_location_input(fl_erms)

        for filepath in search_files:
            cbm_dfs, _ = self._load_single_file(filepath)
            for df, _ in cbm_dfs:
                mask = df["__norm_fl"] == normalized_target
                matched_df = df[mask]
                if matched_df.empty:
                    continue

                defects = self._parse_cbm_defects_from_df(df, matched_df)
                if defects:
                    return defects

        return []

    def fetch_vi_defects(
        self, fl_erms: str, station: str | None = None
    ) -> list[ViDefectRecord]:
        """Fetch VI defects for a functional location strictly from sheet 'QR03 VI', filtered by REPORT BY == 'EET'.

        If station is provided and matches a station workbook, queries ONLY that station
        workbook without touching other station files. Falls back to searching all workbooks
        only if station is None or unmatched.
        """
        if not fl_erms:
            return []

        search_files, _ = self._get_station_files(station)
        normalized_target = normalize_functional_location_input(fl_erms)

        for filepath in search_files:
            _, vi_dfs = self._load_single_file(filepath)
            for df, _ in vi_dfs:
                mask = df["__norm_fl"] == normalized_target
                matched_df = df[mask]
                if matched_df.empty:
                    continue

                defects = self._parse_vi_defects_from_df(df, matched_df)
                if defects:
                    return defects

        return []

