"""Defect extraction and normalization module for Quick Report composer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING
import pandas as pd

from src.quick_report.utils import normalize_functional_location_input

if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment
    from src.project.storage import WorkspaceStorage


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
    source_order: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "technology", (self.technology or "").strip().upper())
        object.__setattr__(self, "equipment", (self.equipment or "").strip())
        object.__setattr__(self, "brand", (self.brand or "").strip())
        object.__setattr__(self, "model", (self.model or "").strip())
        object.__setattr__(self, "rating", (self.rating or "").strip())
        object.__setattr__(self, "defect_area", (self.defect_area or "").strip())
        object.__setattr__(self, "additional_remarks", (self.additional_remarks or "").strip())
        object.__setattr__(self, "ir_reading", (self.ir_reading or "").strip())
        object.__setattr__(self, "us_reading", (self.us_reading or "").strip())
        object.__setattr__(self, "us_char", (self.us_char or "").strip())
        object.__setattr__(self, "tev_reading", (self.tev_reading or "").strip())
        object.__setattr__(self, "tev_char", (self.tev_char or "").strip())
        object.__setattr__(self, "raw_measurement", (self.raw_measurement or "").strip())

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
            "source_order": self.source_order,
        }


@dataclass(frozen=True)
class ViDefectRecord:
    """Normalized Visual Inspection (VI) defect record."""

    equipment: str = ""
    defect_area: str = ""
    additional_remarks: str = ""

    def to_dict(self) -> dict:
        return {
            "equipment": self.equipment,
            "defect_area": self.defect_area,
            "additional_remarks": self.additional_remarks,
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

        self._cbm_sheets: list[tuple[pd.DataFrame, str]] = []
        self._vi_sheets: list[tuple[pd.DataFrame, str]] = []
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

    def _load_sheets(self) -> None:
        """Load and validate QR03 CBA and QR03 VI sheets once."""
        if self._loaded:
            return

        files = self._get_engr_files()
        cbm_dfs: list[tuple[pd.DataFrame, str]] = []
        vi_dfs: list[tuple[pd.DataFrame, str]] = []

        for filepath in files:
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

                vi_df, vi_fl_col = self._extract_df_and_fl_col(xl, vi_sheet)
                if vi_df is not None and vi_fl_col:
                    vi_dfs.append((vi_df, vi_fl_col))

            except (FileNotFoundError, RuntimeError):
                raise
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to read CBM defects from workbook {filepath.name}: {exc}"
                ) from exc

        self._cbm_sheets = cbm_dfs
        self._vi_sheets = vi_dfs
        self._loaded = True

    def fetch_cbm_defects(self, fl_erms: str) -> list[CbmDefectRecord]:
        """Fetch CBM defects for a functional location strictly from sheet 'QR03 CBA'."""
        if not fl_erms:
            return []

        self._load_sheets()
        normalized_target = normalize_functional_location_input(fl_erms)

        for df, _ in self._cbm_sheets:
            mask = df["__norm_fl"] == normalized_target
            matched_df = df[mask]
            if matched_df.empty:
                continue

            # Fuzzy column finders
            us_char_col = next((c for c in df.columns if "US CHAR" in str(c).upper() or "US CHARACTER" in str(c).upper()), None)
            tev_char_col = next((c for c in df.columns if "TEV CHAR" in str(c).upper() or "TEV CHARACTER" in str(c).upper()), None)

            def _clean_val(val: Any) -> str:
                if val is None or pd.isna(val):
                    return ""
                s = str(val).strip()
                return "" if s.lower() == "nan" else s

            defects: list[CbmDefectRecord] = []
            for idx, (_, row) in enumerate(matched_df.iterrows(), start=1):
                tech = _clean_val(
                    row.get("TECHNOLOGY")
                    or row.get("TECH")
                    or row.get("DEFECT FROM")
                ).upper()
                equipment = _clean_val(row.get("EQUIPMENT"))
                brand = _clean_val(row.get("BRAND"))
                model = _clean_val(row.get("MODEL"))
                rating = _clean_val(row.get("RATING"))
                defect_area = _clean_val(
                    row.get("DEFECT AREA") or row.get("DEFECT_AREA")
                )
                additional_remarks = _clean_val(
                    row.get("ADDITIONAL REMARKS") or row.get("REMARKS")
                )
                reading = _clean_val(row.get("READING"))

                ir_reading = _clean_val(row.get("IR READING"))
                us_reading = _clean_val(row.get("US READING"))
                us_char = _clean_val(row.get(us_char_col)) if us_char_col else ""
                tev_reading = _clean_val(row.get("TEV READING"))
                tev_char = _clean_val(row.get(tev_char_col)) if tev_char_col else ""

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
                    source_order=idx,
                )
                defects.append(rec)

            if defects:
                return defects

        return []

    def fetch_vi_defects(self, fl_erms: str) -> list[ViDefectRecord]:
        """Fetch VI defects for a functional location strictly from sheet 'QR03 VI'."""
        if not fl_erms:
            return []

        self._load_sheets()
        normalized_target = normalize_functional_location_input(fl_erms)

        for df, _ in self._vi_sheets:
            mask = df["__norm_fl"] == normalized_target
            matched_df = df[mask]
            if matched_df.empty:
                continue

            defects: list[ViDefectRecord] = []
            for _, row in matched_df.iterrows():
                rec = ViDefectRecord(
                    equipment=str(row.get("EQUIPMENT") or "").strip(),
                    defect_area=str(
                        row.get("DEFECT AREA") or row.get("DEFECT_AREA") or ""
                    ).strip(),
                    additional_remarks=str(
                        row.get("ADDITIONAL REMARKS") or row.get("REMARKS") or ""
                    ).strip(),
                )
                defects.append(rec)

            if defects:
                return defects

        return []
