"""QR02 CBA repository and unit of work implementations for Pahang CLI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import pythoncom
import win32com.client as win32

from src.project.storage import WorkspaceStorage
from src.testsheet.extractor import clean_val, normalize_building_type, normalize_fl_erms, to_excel_date


def _get_field(rec: Any, *names: str, default: Any = None) -> Any:
    """Helper to extract value from object attribute or dictionary key."""
    for name in names:
        if isinstance(rec, dict):
            if name in rec and rec[name] is not None and rec[name] != "":
                return rec[name]
        else:
            val = getattr(rec, name, None)
            if val is not None and val != "":
                return val
    return default


def _fuzzy_normalize_name(name: str | None) -> str:
    """Fuzzy normalize substation name by removing prefixes, NO., and non-alphanumeric chars."""
    if not name:
        return ""
    s = str(name).strip().upper()
    raw_alphanum = re.sub(r"[^A-Z0-9]", "", s)

    # Remove numerical prefixes like "001." or "1-"
    s = re.sub(r"^\d+[\.\s_-]*", "", s)

    # Strip prefixes PE/PDT/P-E/SSU
    prev = None
    while s != prev:
        prev = s
        s = re.sub(r"^(?:P-E|PE|PDT|SSU)\b\s*", "", s)

    # Strip NO. or NO
    s = re.sub(r"\bNO\.?\b", "", s)

    # Remove non-alphanumeric characters
    cleaned = re.sub(r"[^A-Z0-9]", "", s)
    return cleaned if cleaned else raw_alphanum


class Qr02Transaction(ABC):
    """Abstract unit of work for QR02 CBA operations."""

    @abstractmethod
    def __enter__(self) -> Qr02Transaction:
        ...

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> bool | None:
        ...

    @abstractmethod
    def upsert_qr02_cba_records(self, records: Sequence[Any]) -> int:
        ...


class Qr02Repository(ABC):
    """Abstract repository for QR02 CBA workbook management."""

    @abstractmethod
    def transaction(self) -> Qr02Transaction:
        ...


class LocalExcelQr02Transaction(Qr02Transaction):
    """Excel COM-backed transaction for QR02 CBA workbook updates."""

    def __init__(
        self,
        cba_path: Path | str,
        on_commit: Callable[[], None] | None = None,
    ) -> None:
        self.cba_path = Path(cba_path)
        self.on_commit = on_commit
        self.excel_app: Any = None
        self.wb: Any = None
        self.ws: Any = None
        self.fl_to_row: dict[str, int] = {}
        self._last_data_row = 1

    def __enter__(self) -> LocalExcelQr02Transaction:
        if not self.cba_path.exists():
            raise FileNotFoundError(f"ENGR CBA workbook file not found at '{self.cba_path}'")

        pythoncom.CoInitialize()
        self.excel_app = win32.Dispatch("Excel.Application")
        self.excel_app.Visible = False
        self.excel_app.DisplayAlerts = False
        self.excel_app.ScreenUpdating = False

        try:
            self.wb = self.excel_app.Workbooks.Open(str(self.cba_path.resolve()))

            # Locate or create "QR02 CBA" worksheet
            self.ws = None
            for sheet in self.wb.Worksheets:
                if sheet.Name == "QR02 CBA":
                    self.ws = sheet
                    break

            if self.ws is None:
                if self.wb.Worksheets.Count == 1 and self.wb.Worksheets(1).Name == "Sheet":
                    self.ws = self.wb.Worksheets(1)
                    self.ws.Name = "QR02 CBA"
                else:
                    self.ws = self.wb.Worksheets.Add()
                    self.ws.Name = "QR02 CBA"

            self._build_index()
            return self
        except Exception:
            if self.wb is not None:
                try:
                    self.wb.Close(SaveChanges=False)
                except Exception:
                    pass
                self.wb = None
            if self.excel_app is not None:
                try:
                    self.excel_app.Quit()
                except Exception:
                    pass
                self.excel_app = None
            pythoncom.CoUninitialize()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> bool | None:
        try:
            if exc_type is None and self.wb is not None:
                self.wb.Save()
                if self.on_commit is not None:
                    self.on_commit()
        finally:
            if self.wb is not None:
                try:
                    self.wb.Close(SaveChanges=False)
                except Exception:
                    pass
                finally:
                    self.wb = None
                    self.ws = None
            if self.excel_app is not None:
                try:
                    self.excel_app.Quit()
                except Exception:
                    pass
                finally:
                    self.excel_app = None
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
        return None

    def _is_header_row(self, val_i: Any, val_j: Any) -> bool:
        headers = {
            "FL",
            "FL ERMS",
            "FUNCTION LOCATION",
            "NAME",
            "SUBSTATION NAME",
            "ERMS NAME",
            "STATION NAME",
            "NO.",
            "PE NAME",
        }
        s_i = str(val_i).strip().upper() if val_i is not None else ""
        s_j = str(val_j).strip().upper() if val_j is not None else ""
        return s_i in headers or s_j in headers

    def _build_index(self) -> None:
        self.fl_to_row.clear()
        if self.ws is None:
            return

        used_range = self.ws.UsedRange
        self._last_data_row = 1

        vals = used_range.Value
        if vals is None:
            return

        if not isinstance(vals, tuple):
            vals = ((vals,),)
        elif vals and not isinstance(vals[0], tuple):
            vals = (vals,)

        start_r = used_range.Row
        start_c = used_range.Column

        col_i_offset = 9 - start_c
        col_j_offset = 10 - start_c

        for i, row_vals in enumerate(vals):
            r = start_r + i
            val_i = row_vals[col_i_offset] if 0 <= col_i_offset < len(row_vals) else None
            val_j = row_vals[col_j_offset] if 0 <= col_j_offset < len(row_vals) else None

            if r <= 5 and self._is_header_row(val_i, val_j):
                continue

            if (val_i is not None and str(val_i).strip()) or (val_j is not None and str(val_j).strip()):
                if r > self._last_data_row:
                    self._last_data_row = r

            fl_norm = normalize_fl_erms(val_i)
            if fl_norm and fl_norm.lower() != "n/a" and fl_norm not in self.fl_to_row:
                self.fl_to_row[fl_norm] = r

    def upsert_qr02_cba_records(self, records: Sequence[Any]) -> int:
        if self.ws is None:
            raise RuntimeError("Transaction is not active. Must be used as context manager.")

        table = None
        if self.ws.ListObjects.Count > 0:
            table = self.ws.ListObjects(1)

        updated_count = 0
        for rec in records:
            rec_fl = normalize_fl_erms(_get_field(rec, "fl_erms", "fl", default=""))
            rec_name = str(
                _get_field(
                    rec,
                    "substation_name_erms",
                    "name",
                    default="",
                )
            ).strip()
            raw_site = _get_field(rec, "substation_name_site", default="")
            if raw_site is not None and str(raw_site).strip().upper() in ("-", "N/A", "NONE", "NULL", "#REF!", "NAN"):
                rec_name_site = ""
            elif raw_site is not None:
                rec_name_site = str(raw_site).strip()
            else:
                rec_name_site = ""

            target_row: int | None = None
            is_new_row = False

            if rec_fl and rec_fl in self.fl_to_row:
                target_row = self.fl_to_row[rec_fl]
            else:
                is_new_row = True
                if table is not None:
                    new_list_row = table.ListRows.Add()
                    target_row = new_list_row.Range.Row
                else:
                    target_row = self._last_data_row + 1

                self._last_data_row = target_row

            # If NEW row, populate Columns I (9) and J (10)
            if is_new_row:
                if rec_fl:
                    self.ws.Cells(target_row, 9).Value = rec_fl
                if rec_name:
                    self.ws.Cells(target_row, 10).Value = rec_name

            # Col K (11): Site Substation Name (written for all rows, empty string if N/A, -, empty/None)
            self.ws.Cells(target_row, 11).Value = rec_name_site

            # Populate Columns L through P for both existing and new rows
            # Col L (12): GPS Coordinate
            rec_gps = _get_field(rec, "gps_coordinate", "gps", default=None)
            if rec_gps is not None and str(rec_gps).strip():
                self.ws.Cells(target_row, 12).Value = str(rec_gps).strip()

            # Col M (13): Type (pulled as-is from testsheet, empty if missing/N/A)
            rec_type = _get_field(rec, "substation_type", "type", default=None)
            cleaned_type = clean_val(rec_type) if rec_type is not None else None
            self.ws.Cells(target_row, 13).Value = cleaned_type if cleaned_type is not None else ""

            # Col N (14): Building Type (strictly normalized to INDOOR, OUTDOOR, ATTACH)
            rec_bldg = _get_field(rec, "building_type", "bldg_type", default=None)
            if rec_bldg is not None:
                norm_bldg = normalize_building_type(rec_bldg)
                if norm_bldg in ("INDOOR", "OUTDOOR", "ATTACH"):
                    self.ws.Cells(target_row, 14).Value = norm_bldg

            # Col O (15): Cycle 1 date formatted as YYYY-MM-DD string with NumberFormat = "d-mmm-yy"
            rec_cycle = _get_field(rec, "cycle_1", "cycle1", "date", default=None)
            if rec_cycle is not None:
                dt_cycle = to_excel_date(rec_cycle)
                if dt_cycle is not None:
                    cell_o = self.ws.Cells(target_row, 15)
                    cell_o.Value = dt_cycle.strftime("%Y-%m-%d")
                    cell_o.NumberFormat = "d-mmm-yy"

            # Col P (16): Vendor = "EET"
            self.ws.Cells(target_row, 16).Value = "EET"

            # Update index for subsequent records in the transaction
            if rec_fl:
                self.fl_to_row[rec_fl] = target_row

            updated_count += 1

        return updated_count


class LocalExcelQr02Repository(Qr02Repository):
    """Excel-backed repository resolving per-station ENGR CBA workbooks."""

    def __init__(self, storage: WorkspaceStorage, station: str, year: str) -> None:
        self.storage = storage
        self.station = station
        self.year = year

    def _get_cba_path(self) -> Path:
        return self.storage.get_engr_cba_path(self.station, self.year)

    def invalidate_caches(self) -> None:
        """Callback for post-transaction cleanup."""
        pass

    def transaction(self) -> Qr02Transaction:
        return LocalExcelQr02Transaction(
            cba_path=self._get_cba_path(),
            on_commit=self.invalidate_caches,
        )


class FakeQr02Transaction(Qr02Transaction):
    """Test double for Qr02Transaction storing records in-memory."""

    def __init__(self, repo: FakeQr02Repository) -> None:
        self.repo = repo
        self.is_active = False

    def __enter__(self) -> FakeQr02Transaction:
        self.is_active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> bool | None:
        self.is_active = False
        return None

    def upsert_qr02_cba_records(self, records: Sequence[Any]) -> int:
        if not self.is_active:
            raise RuntimeError("Transaction is not active")
        count = 0
        for rec in records:
            self.repo.records.append(rec)
            count += 1
        return count


class FakeQr02Repository(Qr02Repository):
    """Test double for Qr02Repository."""

    def __init__(self) -> None:
        self.records: list[Any] = []

    def transaction(self) -> FakeQr02Transaction:
        return FakeQr02Transaction(self)
