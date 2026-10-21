"""Propagate Work Orders workflow implementation for Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Sequence
import openpyxl

from src.core.normalizers import normalize_date_str, normalize_fl_erms
from src.master.total_pe import LocalExcelTotalPeRepository, TotalPeRepository
from src.project.environment import ProjectEnvironment
from src.workflows.models import (
    PropagateWoRequest,
    PropagateWoResult,
)

ELECTRICAL_PREFIXES = frozenset({"PE", "SSU", "PPU", "PMU", "MPPU", "MPU", "SS"})


def clean_substation_name(name: str | None) -> str:
    """Normalize substation name for matching: strips voltage ratings, parentheticals, punctuation."""
    if not name:
        return ""
    s = str(name).upper().replace("\xa0", " ")
    # Normalize prefixes: MINI PPU -> MPPU, P/E -> PE, S/S -> SS
    s = re.sub(r"\bMINI\s+PPU\b", "MPPU", s)
    s = re.sub(r"\bP/E\b", "PE", s)
    s = re.sub(r"\bS/S\b", "SS", s)
    # Strip voltage ratings: e.g. 275/132/33/11kV, 132/33kV, 33/11kV, 132/11/33kV, 132/11kV, 33kV, 11kV, etc.
    # Anchored to \d+ with optional slash/hyphen chained digits before KV, preserving trailing station numbers (e.g. '2 33kV' -> '2')
    s = re.sub(r"\b\d+(?:\s*[/\\-]\s*\d+)*\s*KV\b", " ", s, flags=re.IGNORECASE)
    # Strip parenthesized suffixes: (VI), (SSU CAMEL POWER), (ZENITH), (T), etc.
    s = re.sub(r"\([^)]*\)", " ", s)
    # Strip leftover standalone KV, &, or punctuation
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return " ".join(s.split())


def canonical_substation_key(name: str | None) -> str:
    """Return collapsed alphanumeric key with whitespace removed."""
    return clean_substation_name(name).replace(" ", "")


def extract_station_acronym(location: str | None) -> str:
    """Extract mnemonic station acronym from Location string (e.g. CGBG/PPUAPMM -> APMM)."""
    if not location:
        return ""
    loc = str(location).strip().upper()
    station_part = loc.split("/")[-1] if "/" in loc else loc
    return re.sub(r"^(?:PMU|PPU|SSU|MPPU|MPU|PE|SS)", "", station_part)


def assert_file_unlocked(path: Path) -> None:
    """Check if file is currently open in Excel or locked by another process."""
    lock_file = path.parent / f"~${path.name}"
    if lock_file.exists():
        raise PermissionError(
            f"Workbook is locked or currently open in Microsoft Excel: '{path}'. "
            "Please close Microsoft Excel and retry."
        )

    try:
        with open(path, "r+b"):
            pass
    except PermissionError:
        raise PermissionError(
            f"Workbook is locked or in use by another process: '{path}'. "
            "Please close any application using this file and retry."
        )
    except OSError:
        pass


@dataclass(frozen=True)
class PropagateWoMsmsRow:
    """Representation of a row in DATA MSMS workbook."""

    row_index: int
    wo: str
    location: str | None = None
    description: str | None = None
    substation_name_erms: str | None = None
    fl_erms: str | None = None
    date_str: str | None = None
    substation_number: Any = None


@dataclass(frozen=True)
class PropagateWoPeRow:
    """Representation of a row in TOTAL PE DataCycle1 sheet."""

    row_index: int
    pe_no: Any
    fl_num: str | None
    substation_name: str | None
    date_str: str | None
    type_c: str | None
    wo: str | None


@dataclass(frozen=True)
class PropagateWoRowUpdate:
    """Instruction to update a single row in Column F."""

    row_index: int
    wo: str
    fl: str


@dataclass(frozen=True)
class PropagateWoRawData:
    """Raw extracted data from DATA MSMS.xlsx and TOTAL PE.xlsx."""

    fl_to_wo: dict[str, str]
    pe_rows: tuple[PropagateWoPeRow, ...]
    total_pe_path: Path
    data_msms_path: Path
    msms_rows: tuple[PropagateWoMsmsRow, ...] = ()


@dataclass(frozen=True)
class PropagateWoFilteredResults:
    """Intermediate results of filtering and matching."""

    updates: tuple[PropagateWoRowUpdate, ...]
    matched_count: int
    already_populated_count: int
    unmatched_count: int
    unmatched_fls: tuple[str, ...]


@dataclass(frozen=True)
class PropagateWoPlan:
    """Execution plan for propagating work orders into TOTAL PE."""

    total_pe_path: Path
    updates: tuple[PropagateWoRowUpdate, ...]
    matched_count: int
    already_populated_count: int
    unmatched_count: int
    unmatched_fls: tuple[str, ...]
    target_date: str | None = None


class PropagateWoPreflightGuard:
    """Pre-flight resource guard stage for Propagate Work Orders workflow."""

    def validate(
        self, environment: ProjectEnvironment, request: PropagateWoRequest | None = None
    ) -> None:
        """Validate environmental preconditions before reading data."""
        data_msms_path = environment.storage.get_data_msms_path()
        self._validate_data_msms(data_msms_path)

        total_pe_path = environment.storage.get_total_pe_path()
        self._validate_total_pe(total_pe_path)

    def _validate_data_msms(self, data_msms_path: Path) -> None:
        if not data_msms_path.exists():
            raise FileNotFoundError(f"DATA MSMS.xlsx workbook not found: {data_msms_path}")

        try:
            wb = openpyxl.load_workbook(data_msms_path, read_only=True)
            ws = wb.active
            if ws is None:
                wb.close()
                raise RuntimeError("DATA MSMS.xlsx contains no active sheet")

            # Check if there are data rows (header + at least 1 record)
            has_records = False
            for row in ws.iter_rows(min_row=2, values_only=True):
                if any(cell is not None and str(cell).strip() != "" for cell in row):
                    has_records = True
                    break

            wb.close()
            if not has_records:
                raise RuntimeError("DATA MSMS.xlsx contains no records")
        except openpyxl.utils.exceptions.InvalidFileException as e:
            raise RuntimeError(f"Failed to load DATA MSMS.xlsx: {e}")

    def _validate_total_pe(self, total_pe_path: Path) -> None:
        if not total_pe_path.exists():
            raise FileNotFoundError(f"TOTAL PE.xlsx workbook not found: {total_pe_path}")

        assert_file_unlocked(total_pe_path)

        try:
            wb = openpyxl.load_workbook(total_pe_path, read_only=True)
            if "DataCycle1" not in wb.sheetnames:
                wb.close()
                raise RuntimeError("DataCycle1 sheet not found in TOTAL PE.xlsx")
            wb.close()
        except openpyxl.utils.exceptions.InvalidFileException as e:
            raise RuntimeError(f"Failed to load TOTAL PE.xlsx: {e}")


class PropagateWoExtractor:
    """Pure I/O reading stage for Propagate Work Orders workflow."""

    def extract(self, total_pe_path: Path, data_msms_path: Path) -> PropagateWoRawData:
        """Extract fl_to_wo mapping and records from DATA MSMS, and rows from TOTAL PE DataCycle1."""
        fl_to_wo, msms_rows = self._extract_msms_data(data_msms_path)
        pe_rows = self._extract_pe_rows(total_pe_path)

        return PropagateWoRawData(
            fl_to_wo=fl_to_wo,
            pe_rows=tuple(pe_rows),
            total_pe_path=total_pe_path,
            data_msms_path=data_msms_path,
            msms_rows=tuple(msms_rows),
        )

    def _extract_fl_to_wo(self, data_msms_path: Path) -> dict[str, str]:
        """Backwards-compatible helper returning fl_to_wo dict."""
        fl_to_wo, _ = self._extract_msms_data(data_msms_path)
        return fl_to_wo

    def _extract_msms_data(
        self, data_msms_path: Path
    ) -> tuple[dict[str, str], list[PropagateWoMsmsRow]]:
        wb_msms = openpyxl.load_workbook(data_msms_path, data_only=True)
        ws_msms = wb_msms.active
        if ws_msms is None:
            wb_msms.close()
            return {}, []

        fl_to_wo: dict[str, str] = {}
        msms_rows: list[PropagateWoMsmsRow] = []

        for r_idx in range(2, (ws_msms.max_row or 1) + 1):
            wo_val = ws_msms.cell(r_idx, 1).value   # Col A: Work Order
            loc_val = ws_msms.cell(r_idx, 2).value  # Col B: Location
            desc_val = ws_msms.cell(r_idx, 3).value # Col C: Description
            erms_val = ws_msms.cell(r_idx, 4).value # Col D: Substation Name ERMS / ERMS
            fl_val = ws_msms.cell(r_idx, 5).value   # Col E: FL ERMS / FUNCTIONAL LOCATION
            date_val = ws_msms.cell(r_idx, 6).value # Col F: Cycle Date / DATE
            num_val = ws_msms.cell(r_idx, 7).value  # Col G: Substation Number / NUMBER

            wo_str = str(wo_val).strip() if wo_val is not None else ""
            if not wo_str or wo_str.lower() in ("none", "nan"):
                continue

            loc_str = str(loc_val).replace("\xa0", " ").strip() if loc_val is not None else None
            desc_str = str(desc_val).replace("\xa0", " ").strip() if desc_val is not None else None
            erms_str = str(erms_val).replace("\xa0", " ").strip() if erms_val is not None else None
            fl_str = str(fl_val).replace("\xa0", " ").strip() if fl_val is not None else None
            date_str = normalize_date_str(date_val) if date_val is not None else None
            if date_str == "":
                date_str = None

            msms_rows.append(
                PropagateWoMsmsRow(
                    row_index=r_idx,
                    wo=wo_str,
                    location=loc_str,
                    description=desc_str,
                    substation_name_erms=erms_str,
                    fl_erms=fl_str,
                    date_str=date_str,
                    substation_number=num_val,
                )
            )

            for fl_candidate in (fl_str, loc_str):
                if fl_candidate is not None:
                    c_str = str(fl_candidate).strip().upper()
                    if c_str and c_str.lower() not in ("none", "nan"):
                        fl_to_wo[c_str] = wo_str
                        c_norm = c_str.replace("/", "")
                        if c_norm:
                            fl_to_wo[c_norm] = wo_str
                        c_normalized = normalize_fl_erms(c_str).upper()
                        if c_normalized:
                            fl_to_wo[c_normalized] = wo_str
                            c_norm_noslash = c_normalized.replace("/", "")
                            if c_norm_noslash:
                                fl_to_wo[c_norm_noslash] = wo_str

        wb_msms.close()
        return fl_to_wo, msms_rows

    def _extract_pe_rows(self, total_pe_path: Path) -> list[PropagateWoPeRow]:
        wb_pe = openpyxl.load_workbook(total_pe_path, data_only=False)
        if "DataCycle1" not in wb_pe.sheetnames:
            wb_pe.close()
            raise RuntimeError(f"'DataCycle1' sheet missing in {total_pe_path}")

        ws_pe = wb_pe["DataCycle1"]
        pe_rows: list[PropagateWoPeRow] = []

        for r_idx in range(2, (ws_pe.max_row or 1) + 1):
            pe_no = ws_pe.cell(r_idx, 1).value
            fl_val = ws_pe.cell(r_idx, 2).value
            sub_name = ws_pe.cell(r_idx, 3).value
            date_val = ws_pe.cell(r_idx, 4).value
            type_val = ws_pe.cell(r_idx, 5).value
            wo_val = ws_pe.cell(r_idx, 6).value

            fl_num = str(fl_val).strip() if fl_val is not None else None
            substation_name = str(sub_name).replace("\xa0", " ").strip() if sub_name is not None else None
            date_str = str(date_val).strip() if date_val is not None else None
            type_c = str(type_val).strip() if type_val is not None else None
            wo = str(wo_val).strip() if wo_val is not None else None

            pe_rows.append(
                PropagateWoPeRow(
                    row_index=r_idx,
                    pe_no=pe_no,
                    fl_num=fl_num,
                    substation_name=substation_name,
                    date_str=date_str,
                    type_c=type_c,
                    wo=wo,
                )
            )

        wb_pe.close()
        return pe_rows


class PropagateWoFilter:
    """Pure predicate logic stage for Propagate Work Orders workflow.

    Performs multi-tier matching:
      - Tier 1: Exact / normalized FL matching (100% 11kV parity).
      - Tier 2: Normalized Substation Name matching (stripping voltage ratings, punctuation, whitespace).
      - Tier 3: Station acronym / alias token matching with date correlation.
    """

    def filter(
        self,
        raw_data: PropagateWoRawData,
        target_date: str | None = None,
        overwrite: bool = False,
    ) -> PropagateWoFilteredResults:
        """Filter rows by target_date, identify empty WO cells, match FL/Substation to WO."""
        matched_count = 0
        already_populated_count = 0
        unmatched_count = 0
        unmatched_fls: list[str] = []
        updates: list[PropagateWoRowUpdate] = []

        norm_target_date = normalize_date_str(target_date) if target_date else None

        active_pe_rows: list[PropagateWoPeRow] = []
        for row in raw_data.pe_rows:
            if target_date is not None:
                if row.date_str is None:
                    continue
                row_date_str = row.date_str
                norm_row_date = normalize_date_str(row_date_str)
                if norm_row_date != norm_target_date and row_date_str != target_date:
                    continue

            fl_str = str(row.fl_num).strip().upper() if row.fl_num else ""
            sub_name = str(row.substation_name).strip() if row.substation_name else ""
            if not fl_str and not sub_name:
                continue

            # Check if already populated
            if row.wo is not None and not overwrite:
                cur_wo = row.wo.strip()
                if cur_wo and cur_wo.lower() not in ("none", "nan"):
                    already_populated_count += 1
                    continue

            active_pe_rows.append(row)

        matches: dict[int, str] = {}  # row_index -> wo
        used_wos: set[str] = set()

        # Pass 1: Tier 1 - Exact / normalized FL matching
        for row in active_pe_rows:
            if not row.fl_num:
                continue
            fl_str = row.fl_num.strip().upper()
            if not fl_str or fl_str.lower() in ("none", "nan"):
                continue

            candidates = [
                fl_str,
                fl_str.replace("/", ""),
                normalize_fl_erms(fl_str).upper(),
                normalize_fl_erms(fl_str).upper().replace("/", ""),
            ]
            wo_match = None
            for cand in candidates:
                if cand in raw_data.fl_to_wo:
                    wo_match = raw_data.fl_to_wo[cand]
                    break

            if wo_match and wo_match not in used_wos:
                matches[row.row_index] = wo_match
                used_wos.add(wo_match)

        # Pass 2 & 3: Multi-tier resolution using msms_rows
        if raw_data.msms_rows:
            # Pass 2: Tier 2 - Normalized Substation Name matching
            for row in active_pe_rows:
                if row.row_index in matches:
                    continue
                sub_name = row.substation_name
                if not sub_name:
                    continue

                p_clean = clean_substation_name(sub_name)
                p_canon = canonical_substation_key(sub_name)
                p_tokens = set(re.findall(r"[A-Z0-9]+", sub_name.upper()))

                # 2a: Domain aliases for Cabin vs GIS (Gebeng) - strictly scoped to Gebeng/GBID
                if "GBID" in p_tokens or "GEBENG" in p_tokens:
                    if "CABIN" in p_tokens:
                        for m in raw_data.msms_rows:
                            if m.wo in used_wos:
                                continue
                            m_loc = (m.location or "").upper()
                            if "GBID" in m_loc:
                                matches[row.row_index] = m.wo
                                used_wos.add(m.wo)
                                break
                        if row.row_index in matches:
                            continue

                    if "275" in p_tokens or "GBIG" in p_tokens or "GIS" in p_tokens:
                        for m in raw_data.msms_rows:
                            if m.wo in used_wos:
                                continue
                            m_loc = (m.location or "").upper()
                            m_desc = (m.description or "").upper()
                            if "GBIG" in m_loc or "GIS" in m_desc:
                                matches[row.row_index] = m.wo
                                used_wos.add(m.wo)
                                break
                        if row.row_index in matches:
                            continue

                # 2b: Exact clean or canonical whitespace match
                matched_wo = None
                for m in raw_data.msms_rows:
                    if m.wo in used_wos:
                        continue
                    m_names = [m.description, m.substation_name_erms]
                    m_cleans = [clean_substation_name(n) for n in m_names if n]
                    m_canons = [canonical_substation_key(n) for n in m_names if n]
                    if p_clean and p_clean in m_cleans:
                        matched_wo = m.wo
                        break
                    if p_canon and p_canon in m_canons:
                        matched_wo = m.wo
                        break

                if matched_wo:
                    matches[row.row_index] = matched_wo
                    used_wos.add(matched_wo)
                    continue

                # 2c: Token subset (e.g. SSU KPC GEBENG contains SSU KPC)
                for m in raw_data.msms_rows:
                    if m.wo in used_wos:
                        continue
                    m_clean = clean_substation_name(m.description)
                    m_tokens = set(m_clean.split())
                    distinctive_m = m_tokens - ELECTRICAL_PREFIXES
                    p_clean_tokens = set(p_clean.split())
                    if distinctive_m and distinctive_m.issubset(p_clean_tokens):
                        matched_wo = m.wo
                        break

                if matched_wo:
                    matches[row.row_index] = matched_wo
                    used_wos.add(matched_wo)
                    continue

            # Pass 3: Tier 3 - Station acronym / alias token matching with date correlation
            for row in active_pe_rows:
                if row.row_index in matches:
                    continue
                sub_name = row.substation_name
                if not sub_name:
                    continue
                p_tokens = set(re.findall(r"[A-Z0-9]+", sub_name.upper()))
                row_norm_date = normalize_date_str(row.date_str) if row.date_str else None

                for m in raw_data.msms_rows:
                    if m.wo in used_wos:
                        continue
                    acronym = extract_station_acronym(m.location)
                    if not acronym:
                        continue

                    # Check acronym token match
                    acronym_matched = False
                    if acronym in p_tokens:
                        acronym_matched = True
                    elif any(
                        tok.startswith(acronym) or acronym.startswith(tok)
                        for tok in p_tokens
                        if len(tok) >= 3 and len(acronym) >= 3
                    ):
                        acronym_matched = True

                    if acronym_matched:
                        # Date correlation check if both have dates
                        if row_norm_date and m.date_str:
                            m_norm_date = normalize_date_str(m.date_str)
                            if m_norm_date and m_norm_date != row_norm_date:
                                continue  # Date mismatch, skip

                        matches[row.row_index] = m.wo
                        used_wos.add(m.wo)
                        break

        # Assemble row updates
        for row in active_pe_rows:
            fl_ident = row.fl_num or row.substation_name or f"Row {row.row_index}"
            if row.row_index in matches:
                wo = matches[row.row_index]
                updates.append(
                    PropagateWoRowUpdate(
                        row_index=row.row_index,
                        wo=wo,
                        fl=fl_ident,
                    )
                )
                matched_count += 1
            else:
                unmatched_count += 1
                unmatched_fls.append(fl_ident)

        return PropagateWoFilteredResults(
            updates=tuple(updates),
            matched_count=matched_count,
            already_populated_count=already_populated_count,
            unmatched_count=unmatched_count,
            unmatched_fls=tuple(unmatched_fls),
        )


class PropagateWoTransformer:
    """Pure transformation plan construction stage for Propagate Work Orders workflow."""

    def build_plan(
        self,
        total_pe_path: Path,
        updates: Sequence[PropagateWoRowUpdate],
        matched_count: int,
        already_populated_count: int,
        unmatched_count: int,
        unmatched_fls: Sequence[str],
        target_date: str | None = None,
    ) -> PropagateWoPlan:
        """Construct transformation execution plan."""
        return PropagateWoPlan(
            total_pe_path=total_pe_path,
            updates=tuple(updates),
            matched_count=matched_count,
            already_populated_count=already_populated_count,
            unmatched_count=unmatched_count,
            unmatched_fls=tuple(unmatched_fls),
            target_date=target_date,
        )


class PropagateWoLoader:
    """Pure write I/O stage for Propagate Work Orders workflow."""

    def __init__(self, total_pe_repository: TotalPeRepository | None = None) -> None:
        self.total_pe_repository = total_pe_repository or LocalExcelTotalPeRepository()

    def load(self, plan: PropagateWoPlan) -> int:
        """Write Column F in TOTAL PE DataCycle1 sheet using openpyxl, preserving formulas."""
        if not plan.updates:
            return 0

        assert_file_unlocked(plan.total_pe_path)

        try:
            wb = openpyxl.load_workbook(plan.total_pe_path, data_only=False)
        except PermissionError as e:
            raise PermissionError(
                f"TOTAL PE workbook is locked or in use by another process: '{plan.total_pe_path}'. "
                "Please close any application using this file and retry."
            ) from e

        if "DataCycle1" not in wb.sheetnames:
            wb.close()
            raise RuntimeError(f"'DataCycle1' sheet missing in {plan.total_pe_path}")

        ws = wb["DataCycle1"]
        for upd in plan.updates:
            ws.cell(row=upd.row_index, column=6, value=upd.wo)

        try:
            wb.save(plan.total_pe_path)
        except PermissionError as e:
            raise PermissionError(
                f"TOTAL PE workbook is locked or currently open in Microsoft Excel: '{plan.total_pe_path}'. "
                "Please close Microsoft Excel and retry."
            ) from e
        finally:
            wb.close()

        return len(plan.updates)


class PropagateWoAuditor:
    """Verification & History Audit stage for Propagate Work Orders workflow."""

    def audit(
        self,
        plan: PropagateWoPlan,
        updated_count: int,
    ) -> PropagateWoResult:
        """Verify output integrity and return workflow telemetry result."""
        self._verify_output(plan.total_pe_path)

        return PropagateWoResult(
            matched_count=plan.matched_count,
            already_populated_count=plan.already_populated_count,
            unmatched_count=plan.unmatched_count,
            unmatched_fls=plan.unmatched_fls,
            updated_count=updated_count,
        )

    def _verify_output(self, total_pe_path: Path) -> None:
        if not total_pe_path.exists():
            raise RuntimeError(f"TOTAL PE.xlsx does not exist after load at {total_pe_path}")
        if total_pe_path.stat().st_size == 0:
            raise RuntimeError(f"TOTAL PE.xlsx is empty (0 bytes) after load at {total_pe_path}")


class PropagateWoWorkflow:
    """Orchestrates WO number propagation from DATA MSMS.xlsx to TOTAL PE.xlsx.

    Resilience Policy: best-effort
        Per-row matching and population. Skips rows that are missing or already populated.
    """

    def __init__(
        self,
        preflight_guard: PropagateWoPreflightGuard | None = None,
        extractor: PropagateWoExtractor | None = None,
        filter_stage: PropagateWoFilter | None = None,
        transformer: PropagateWoTransformer | None = None,
        loader: PropagateWoLoader | None = None,
        auditor: PropagateWoAuditor | None = None,
    ) -> None:
        self.preflight_guard = preflight_guard or PropagateWoPreflightGuard()
        self.extractor = extractor or PropagateWoExtractor()
        self.filter_stage = filter_stage or PropagateWoFilter()
        self.transformer = transformer or PropagateWoTransformer()
        self.loader = loader or PropagateWoLoader()
        self.auditor = auditor or PropagateWoAuditor()

    def execute(
        self,
        environment: ProjectEnvironment,
        request: PropagateWoRequest | None = None,
    ) -> PropagateWoResult:
        """Execute Propagate Work Orders workflow."""
        req = request or PropagateWoRequest()

        if req.progress_sink:
            req.progress_sink("Validating preflight conditions for Propagate WO...")

        self.preflight_guard.validate(environment, req)

        total_pe_path = environment.storage.get_total_pe_path()
        data_msms_path = environment.storage.get_data_msms_path()

        if req.progress_sink:
            req.progress_sink("Extracting work orders and TOTAL PE records...")

        raw_data = self.extractor.extract(total_pe_path, data_msms_path)

        if req.progress_sink:
            req.progress_sink("Filtering and matching work orders across multi-tier criteria...")

        filtered = self.filter_stage.filter(
            raw_data=raw_data,
            target_date=req.target_date,
            overwrite=req.overwrite,
        )

        plan = self.transformer.build_plan(
            total_pe_path=total_pe_path,
            updates=filtered.updates,
            matched_count=filtered.matched_count,
            already_populated_count=filtered.already_populated_count,
            unmatched_count=filtered.unmatched_count,
            unmatched_fls=filtered.unmatched_fls,
            target_date=req.target_date,
        )

        if req.progress_sink:
            req.progress_sink(
                f"Writing {len(plan.updates)} work orders to TOTAL PE Column F..."
            )

        updated_count = self.loader.load(plan)

        if req.progress_sink:
            req.progress_sink("Auditing TOTAL PE workbook integrity...")

        result = self.auditor.audit(plan, updated_count)

        if req.progress_sink:
            req.progress_sink(
                f"Propagate WO completed: {result.matched_count} matched, "
                f"{result.already_populated_count} already populated, "
                f"{result.unmatched_count} unmatched."
            )

        return result
