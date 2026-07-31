"""Defect extraction and normalization module for Quick Report composer."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import pandas as pd

from src.quick_report.utils import normalize_functional_location_input



@dataclass(frozen=True)
class CbmDefectRecord:
    """Normalized CBM (IR/US/TEV) defect record."""

    equipment: str = ""
    technology: str = ""
    brand: str = ""
    model: str = ""
    rating: str = ""
    defect_area: str = ""
    remarks: str = ""
    ir_reading: str = ""
    us_reading: str = ""
    tev_reading: str = ""
    source_order: int = 0

    def to_dict(self) -> dict:
        return {
            "equipment": self.equipment,
            "technology": self.technology,
            "brand": self.brand,
            "model": self.model,
            "rating": self.rating,
            "defect_area": self.defect_area,
            "remarks": self.remarks,
            "ir_reading": self.ir_reading,
            "us_reading": self.us_reading,
            "tev_reading": self.tev_reading,
            "source_order": self.source_order,
        }


@dataclass(frozen=True)
class ViDefectRecord:
    """Normalized Visual Inspection (VI) defect record."""

    equipment: str = ""
    defect_area: str = ""
    remarks: str = ""

    def to_dict(self) -> dict:
        return {
            "equipment": self.equipment,
            "defect_area": self.defect_area,
            "remarks": self.remarks,
        }


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment
    from src.project.storage import WorkspaceStorage

class MasterQr03DefectRepository:
    """Repository for fetching CBM & VI defects strictly from master QR03 Excel workbooks in PYTHON/ENGR FROM DRIVE."""

    def __init__(
        self,
        engr_dir: Path | str | None = None,
        storage: 'WorkspaceStorage | None' = None,
        environment: 'ProjectEnvironment | None' = None,
    ) -> None:
        if engr_dir:
            self.engr_dir = Path(engr_dir)
        elif storage:
            self.engr_dir = storage.get_engr_folder()
        elif environment:
            self.engr_dir = environment.storage.get_engr_folder()
        else:
            raise ValueError("Must provide either engr_dir, storage, or environment to resolve ENGR folder.")

    def _get_engr_files(self) -> list[Path]:
        if not self.engr_dir or not self.engr_dir.exists():
            raise FileNotFoundError(f"Required ENGR directory does not exist: {self.engr_dir}")

        files = [
            f for f in sorted(self.engr_dir.iterdir())
            if f.is_file() and f.suffix.lower() in {".xlsx", ".xls"} and not f.name.startswith("~$")
        ]
        if not files:
            raise FileNotFoundError(f"No ENGR Excel workbooks found in directory: {self.engr_dir}")

        return files

    def fetch_cbm_defects(self, fl_erms: str) -> list[dict]:
        """Fetch CBM defects for a functional location strictly from sheet 'QR03 CBA'."""
        if not fl_erms:
            return []

        files = self._get_engr_files()
        normalized_target = normalize_functional_location_input(fl_erms)

        for filepath in files:
            try:
                xl = pd.ExcelFile(filepath, engine="openpyxl")
                target_sheet = next((s for s in xl.sheet_names if s.strip().upper() == "QR03 CBA"), None)
                if not target_sheet:
                    raise RuntimeError(f"Missing required sheet 'QR03 CBA' in ENGR master Excel file: {filepath}")

                df = None
                fl_col = None
                for header_idx in (0, 1):
                    temp_df = pd.read_excel(xl, sheet_name=target_sheet, header=header_idx, engine="openpyxl")
                    candidate_col = next((c for c in temp_df.columns if "FUNCTIONAL" in str(c).upper() or "FL" in str(c).upper()), None)
                    if candidate_col:
                        df = temp_df
                        fl_col = candidate_col
                        break

                if df is None or not fl_col:
                    continue

                mask = df[fl_col].astype(str).apply(normalize_functional_location_input) == normalized_target
                matched_df = df[mask]
                if matched_df.empty:
                    continue

                defects = []
                for idx, (_, row) in enumerate(matched_df.iterrows(), start=1):
                    tech = str(row.get("TECHNOLOGY") or row.get("TECH") or row.get("DEFECT FROM") or "").strip().upper()
                    equipment = str(row.get("EQUIPMENT") or "").strip()
                    brand = str(row.get("BRAND") or "").strip()
                    model = str(row.get("MODEL") or "").strip()
                    rating = str(row.get("RATING") or "").strip()
                    defect_area = str(row.get("DEFECT AREA") or row.get("DEFECT_AREA") or "").strip()
                    remarks = str(row.get("ADDITIONAL REMARKS") or row.get("REMARKS") or "").strip()
                    reading = str(row.get("READING") or "").strip()

                    ir_reading = reading if tech == "IR" else str(row.get("IR READING") or "").strip()
                    us_reading = reading if tech == "US" else str(row.get("US READING") or "").strip()
                    tev_reading = reading if tech == "TEV" else str(row.get("TEV READING") or "").strip()

                    rec = CbmDefectRecord(
                        equipment=equipment,
                        technology=tech,
                        brand=brand,
                        model=model,
                        rating=rating,
                        defect_area=defect_area,
                        remarks=remarks,
                        ir_reading=ir_reading,
                        us_reading=us_reading,
                        tev_reading=tev_reading,
                        source_order=idx,
                    )
                    d_dict = rec.to_dict()
                    d_dict["reading"] = reading
                    defects.append(d_dict)

                if defects:
                    return defects
            except FileNotFoundError:
                raise
            except Exception as exc:
                logging.exception("Error processing CBM defects from workbook %s: %s", filepath.name, exc)
                continue

        return []

    def fetch_vi_defects(self, fl_erms: str) -> list[dict]:
        """Fetch VI defects for a functional location strictly from sheet 'QR03 VI'."""
        if not fl_erms:
            return []

        files = self._get_engr_files()
        normalized_target = normalize_functional_location_input(fl_erms)

        for filepath in files:
            try:
                xl = pd.ExcelFile(filepath, engine="openpyxl")
                target_sheet = next((s for s in xl.sheet_names if s.strip().upper() == "QR03 VI"), None)
                if not target_sheet:
                    raise RuntimeError(f"Missing required sheet 'QR03 VI' in ENGR master Excel file: {filepath}")

                df = None
                fl_col = None
                for header_idx in (0, 1):
                    temp_df = pd.read_excel(xl, sheet_name=target_sheet, header=header_idx, engine="openpyxl")
                    candidate_col = next((c for c in temp_df.columns if "FUNCTIONAL" in str(c).upper() or "FL" in str(c).upper()), None)
                    if candidate_col:
                        df = temp_df
                        fl_col = candidate_col
                        break

                if df is None or not fl_col:
                    continue

                mask = df[fl_col].astype(str).apply(normalize_functional_location_input) == normalized_target
                matched_df = df[mask]
                if matched_df.empty:
                    continue

                defects = []
                for _, row in matched_df.iterrows():
                    rec = ViDefectRecord(
                        equipment=str(row.get("EQUIPMENT") or "").strip(),
                        defect_area=str(row.get("DEFECT AREA") or row.get("DEFECT_AREA") or "").strip(),
                        remarks=str(row.get("ADDITIONAL REMARKS") or row.get("REMARKS") or "").strip(),
                    )
                    defects.append(rec.to_dict())

                if defects:
                    return defects
            except FileNotFoundError:
                raise
            except Exception as exc:
                logging.exception("Error processing VI defects from workbook %s: %s", filepath.name, exc)
                continue

        return []






