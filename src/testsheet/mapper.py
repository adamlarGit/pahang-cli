"""Canonical Testsheet Reading Mapper for Pahang CLI.

Resolves MSMS METERNAME codes and TNBLOCATION paths to exact Excel cell
coordinates across 11kV ('PCE Testsheet') and 33kV ('33kV (Main)', '11kV (Main)',
'TX', 'Visual Inspec.') workbooks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import re
from typing import ClassVar
import openpyxl


def extract_root_substation_token(tnb_location: str) -> str:
    """Extract root substation token by trimming bay segments after /33KV/, /11KV/, or /TX/.

    Examples:
        'CGBG/PPUAPMM/33KV/3P5' -> 'CGBG/PPUAPMM'
        'CGBG/PPUAPMM/11KV/5K5' -> 'CGBG/PPUAPMM'
        'CGBG/PPUAPMM/TX/PTX2'  -> 'CGBG/PPUAPMM'
        'CKTN/SSUKIIP/33KV/6S5' -> 'CKTN/SSUKIIP'
        'CCHL/PCEJ00024/TX/DTX1'-> 'CCHL/PCEJ00024'
        'CGBG/PPUAPMM'          -> 'CGBG/PPUAPMM'
    """
    if not tnb_location:
        return ""
    norm = str(tnb_location).replace("\\", "/").strip()
    parts = re.split(r"/(?:33KV|11KV|TX|FP)(?:/.*)?$", norm, flags=re.IGNORECASE)
    if len(parts) > 1 and parts[0]:
        return parts[0]
    return norm


def parse_equipment_index(tnb_location: str) -> tuple[str, int]:
    """Parse TNBLOCATION string to extract equipment category and index.

    Examples:
        '/11KV/1' -> ('11KV', 1)
        'CGBG/PPUAPMM/11KV/5K5' -> ('11KV', 5)
        'CGBG/PPUAPMM/33KV/1' -> ('33KV', 1)
        'CGBG/PPUAPMM/33KV/3P5' -> ('33KV', 3)
        'CCHL/PCEJ00024/TX/DTX1' -> ('TX', 1)
        'CGBG/PPUAPMM/TX/PTX2' -> ('TX', 2)
        '/FP/FP2' -> ('FP', 2)

    Raises:
        ValueError: If the location string cannot be parsed into a known equipment category.
    """
    if not tnb_location:
        raise ValueError("Empty TNBLOCATION string provided")

    norm = str(tnb_location).replace("\\", "/").strip().upper()

    # 33KV Switchgear: /33KV/N or 33KV/N or /33KV/3P5
    m_33kv = re.search(r"(?:^|/)33KV/(?:[A-Z_]*(\d+)|([A-Z0-9_]+))", norm)
    if m_33kv:
        num_str = m_33kv.group(1)
        if num_str:
            return "33KV", int(num_str)
        return "33KV", 1

    # 11KV Switchgear: /11KV/N or 11KV/N or /11KV/5K5
    m_11kv = re.search(r"(?:^|/)11KV/(?:[A-Z_]*(\d+)|([A-Z0-9_]+))", norm)
    if m_11kv:
        num_str = m_11kv.group(1)
        if num_str:
            return "11KV", int(num_str)
        return "11KV", 1

    # Transformer: /TX/PTXN or /TX/DTXN or /TX/N
    m_tx = re.search(r"(?:^|/)TX/(?:P|D)?TX(\d+)", norm)
    if not m_tx:
        m_tx = re.search(r"(?:^|/)DTX(\d+)", norm)
    if not m_tx:
        m_tx = re.search(r"(?:^|/)TX/(\d+)", norm)
    if m_tx:
        return "TX", int(m_tx.group(1))

    # Local TX
    if re.search(r"(?:^|/)TX/L(?:OCAL)?TX", norm):
        return "TX", 5

    # Feeder Pillar: /FP/FPN or FP/FPN or FPN
    m_fp = re.search(r"(?:^|/)FP/FP(\d+)", norm)
    if not m_fp:
        m_fp = re.search(r"(?:^|/)FP(\d+)", norm)
    if m_fp:
        return "FP", int(m_fp.group(1))

    raise ValueError(f"Could not parse equipment category and index from TNBLOCATION: {tnb_location}")


def get_sheet_name(sheet_index: int) -> str:
    """Return sheet name corresponding to sheet index (1-based) for PCE Testsheet."""
    if sheet_index <= 1:
        return "PCE Testsheet"
    return f"PCE Testsheet ({sheet_index})"


def build_ppu_bay_map(wb: openpyxl.Workbook) -> dict[tuple[str, str], tuple[str, int]]:
    """Build a mapping of (voltage_prefix, bay_token) -> (sheet_name, base_row) from a 33kV workbook.

    Scans all 33kV and 11kV switchgear worksheets ('33kV (Main)', '33kV (Extra)*', '11kV (Main)',
    '11kV (2)', '11kV (Extra)*') and indexes panels by feeder codes, parenthesized feeder names,
    bus section/coupler/tie conventions, transition markers, and panel numbers.
    """
    bay_map: dict[tuple[str, str], tuple[str, int]] = {}
    for s_name in wb.sheetnames:
        s_clean = s_name.strip()
        s_upper = s_clean.upper()
        if "33KV" in s_upper:
            voltage = "33KV"
        elif "11KV" in s_upper:
            voltage = "11KV"
        else:
            continue

        ws = wb[s_name]
        for r in range(15, 65, 6):
            if r > ws.max_row:
                break
            p_no = ws.cell(r, 2).value
            f_code = str(ws.cell(r, 3).value or "").strip().upper()
            f_name = str(ws.cell(r, 4).value or "").strip().upper()

            if not p_no and not f_code and not f_name:
                continue

            tokens: set[str] = set()

            # Defensively check p_no (Col B) if it contains a feeder code instead of a pure number
            if p_no is not None:
                p_str = str(p_no).replace(".0", "").strip().upper()
                if p_str and p_str not in ("-", "NONE", "N/A"):
                    if not p_str.isdigit():
                        tokens.add(p_str)
                        tokens.add(p_str.replace("0", "O"))
                        tokens.add(p_str.replace("O", "0"))
                        m_lead_p = re.match(r"^(\d+)[A-Z]+[A-Z0-9]*$", p_str)
                        if m_lead_p:
                            tokens.add(m_lead_p.group(1))

            if f_code and f_code not in ("-", "NONE", "N/A"):
                tokens.add(f_code)
                tokens.add(f_code.replace("0", "O"))
                tokens.add(f_code.replace("O", "0"))
                if f_code.isdigit():
                    for sfx in ("K5", "L5", "S5", "P5", "B5", "TO", "HO", "WO", "SO"):
                        tokens.add(f"{f_code}{sfx}")
                m_lead = re.match(r"^(\d+)[A-Z]+[A-Z0-9]*$", f_code)
                if m_lead:
                    tokens.add(m_lead.group(1))

            # Feeder name parenthesized bay codes (e.g. 'PMU GBID (1L5)', 'SSU FLEXSYS (5S5)')
            for p_tok in re.findall(r"\(([^)]+)\)", f_name):
                p_clean = p_tok.strip().upper()
                tokens.add(p_clean)
                tokens.add(p_clean.replace("0", "O"))
                tokens.add(p_clean.replace("O", "0"))

            # Standard functional markers
            if "TRANSITION" in f_name or "TRANSITION" in f_code:
                tokens.add("TRANS")
            if "BUS COUPLER" in f_name or "BUS-COUPLER" in f_name:
                tokens.add("1WO")
                tokens.add("1W0")
            if "BUS SECTION" in f_name or "BUS-SECTION" in f_name or "BUS - SECTION" in f_name:
                tokens.add("1SO")
                tokens.add("1S0")
            if "BUS TIE" in f_name or "BUSTIE" in f_name:
                tokens.add("BT1")
                tokens.add("BT2")
                tokens.add("1B5")
                tokens.add("2B5")
            if "LOCAL TX" in f_name or "LOCAL TRANSFORMER" in f_name:
                tokens.add("16K5")
                tokens.add("LTX")

            for tok in tokens:
                if tok.isdigit() and (voltage, tok) in bay_map:
                    continue
                bay_map[(voltage, tok)] = (s_clean, r)

            # Fallback panel number
            if p_no is not None:
                p_clean = str(p_no).replace(".0", "").strip()
                if p_clean.isdigit() and (voltage, p_clean) not in bay_map:
                    bay_map[(voltage, p_clean)] = (s_clean, r)

    return bay_map


class ReadingMapperStrategy(ABC):
    """Abstract strategy seam for testsheet reading coordinate resolution."""

    @abstractmethod
    def get_target(
        self,
        meter_name: str,
        tnb_location: str = "",
        bay_map: dict[tuple[str, str], tuple[str, int]] | None = None,
    ) -> tuple[str, str] | None:
        """Resolve a METERNAME and optional TNBLOCATION to (sheet_name, cell_coordinate).

        Returns:
            (sheet_name, cell_coordinate) or None if unmapped / stub placeholder.
        """
        pass

    def is_stub(
        self,
        meter_name: str,
        tnb_location: str = "",
        bay_map: dict[tuple[str, str], tuple[str, int]] | None = None,
    ) -> bool:
        """Return True if meter is a stub or unmapped to testsheet cells."""
        return self.get_target(meter_name, tnb_location, bay_map=bay_map) is None


class PceReadingMapper(ReadingMapperStrategy):
    """11kV PCE coordinate resolution engine mapping METERNAME to PCE Testsheet cells."""

    # Fixed metadata / background cell mapping (always on Sheet 1)
    BACKGROUND_METADATA_MAP: ClassVar[dict[str, str]] = {
        "BG_ROOM_TV": "P6",
        "BG_ROOM_HUM": "S6",
        "BG_ROOM_TEM": "W6",
        "EXECUTION_DATE": "P4",
        "TIME_IN": "P5",
        "TIME_OUT": "S5",
        "PE_NAME": "C5",
        "FLOC": "W5",
    }

    # RMU fixed slot assignments (CBL1=1, CBL2=2, CBL3=3, FS1=4, FS2=5)
    RMU_SLOT_MAP: ClassVar[dict[str, int]] = {
        "RMUCBL1": 1,
        "CBL1": 1,
        "CBL": 1,
        "RMUCBL2": 2,
        "CBL2": 2,
        "RMUCBL3": 3,
        "CBL3": 3,
        "RMUFS1": 4,
        "FS1": 4,
        "RMUFS2": 5,
        "FS2": 5,
    }

    # Switchgear column mappings
    SWITCHGEAR_COLUMNS: ClassVar[dict[str, str]] = {
        "REF": "K",
        "MAX": "L",
        "DIF": "M",
        "AVG": "N",
        "US": "Q",
        "TV": "T",
        "TEV": "T",
        "PUL": "U",
    }

    # Transformer column mappings
    TRANSFORMER_COLUMNS: ClassVar[dict[str, str]] = {
        "REF": "F",
        "MAX": "G",
        "DIF": "H",
        "AVG": "I",
        "US": "K",
    }

    @staticmethod
    def resolve_panel_sheet_and_slot(panel_index: int) -> tuple[str, int]:
        """Resolve sheet name and 1-based local slot (1-4) for a given 1-based panel index."""
        if panel_index < 1:
            panel_index = 1
        sheet_index = (panel_index - 1) // 4 + 1
        local_slot = ((panel_index - 1) % 4) + 1
        return get_sheet_name(sheet_index), local_slot

    def get_target(
        self,
        meter_name: str,
        tnb_location: str = "",
        bay_map: dict[tuple[str, str], tuple[str, int]] | None = None,
    ) -> tuple[str, str] | None:
        """Resolve a METERNAME and optional TNBLOCATION to (sheet_name, cell_coordinate)."""
        if not meter_name:
            return None

        meter = meter_name.strip().upper()

        # 1. Background & Metadata
        if meter in self.BACKGROUND_METADATA_MAP:
            return ("PCE Testsheet", self.BACKGROUND_METADATA_MAP[meter])

        # 2. Feeder Pillar (All 64 thermal meters are stubs)
        if meter.startswith("TH_FP") or meter.startswith("TH_EARTH"):
            return None
        if tnb_location:
            try:
                cat, _ = parse_equipment_index(tnb_location)
                if cat == "FP":
                    return None
            except ValueError:
                pass

        # 3. Oil Variant Stubs (_PE13O)
        if meter.endswith("_PE13O"):
            return None

        # 4. Distribution Transformer (_PE13R or _PE13V with DTX / TX / Body)
        if (
            "_DTX_" in meter
            or meter.startswith("US_DTX")
            or meter.startswith("TH_TX_RMU")
            or meter.startswith("TH_S11_VCB")
        ):
            return self._resolve_transformer(meter, tnb_location)

        # 5. RMU SF6 / MRMU Switchgear (_PE13R)
        if meter.endswith("_PE13R"):
            return self._resolve_rmu(meter, tnb_location)

        # 6. VCB Switchgear (_PE13V / _PE13V2)
        if meter.endswith("_PE13V") or meter.endswith("_PE13V2"):
            return self._resolve_vcb(meter, tnb_location)

        return None

    def _resolve_transformer(self, meter: str, tnb_location: str) -> tuple[str, str] | None:
        """Resolve Transformer numeric readings (TX1: rows 33-37, TX2: rows 38-42)."""
        tx_idx = 1
        if tnb_location:
            try:
                cat, idx = parse_equipment_index(tnb_location)
                if cat == "TX":
                    tx_idx = idx
            except ValueError:
                pass

        if tx_idx == 1:
            base_row = 33
        elif tx_idx == 2:
            base_row = 38
        else:
            return None

        # Component row offset: HV=0 (HT Cable), LV=2 (LV Cable), Body=4 (Body)
        if "_HV_" in meter or meter.startswith("US_DTX_HV") or meter.startswith("US_DTX_PE13V"):
            row = base_row + 0
        elif "_LV_" in meter:
            row = base_row + 2
        elif meter.startswith("TH_TX_RMU") or meter.startswith("TH_S11_VCB"):
            row = base_row + 4
        else:
            return None

        col = self._extract_transformer_column(meter)
        if not col:
            return None

        return ("PCE Testsheet", f"{col}{row}")

    def _extract_transformer_column(self, meter: str) -> str | None:
        """Extract transformer reading column (F, G, H, I, K)."""
        if meter.startswith("US_"):
            return self.TRANSFORMER_COLUMNS["US"]
        if "_REF" in meter:
            return self.TRANSFORMER_COLUMNS["REF"]
        if "_MAX" in meter:
            return self.TRANSFORMER_COLUMNS["MAX"]
        if "_DIF" in meter:
            return self.TRANSFORMER_COLUMNS["DIF"]
        if "_AVG" in meter:
            return self.TRANSFORMER_COLUMNS["AVG"]
        return None

    def _resolve_rmu(self, meter: str, tnb_location: str) -> tuple[str, str] | None:
        """Resolve RMU SF6 / MRMU fixed slot mappings."""
        if (
            meter.startswith("TH_S11_RMU_")
            or meter.startswith("TV_S11_RMU_")
            or meter.startswith("US_S11_RMU_")
        ):
            if meter == "TH_S11_RMU_AVG_PE13R":
                return ("PCE Testsheet", "N26")
            if meter == "TV_S11_RMU_PE13R":
                return ("PCE Testsheet", "P6")
            return None

        slot = None
        for infix, slot_num in [
            ("RMUCBL1", 1),
            ("RMUCBL2", 2),
            ("RMUCBL3", 3),
            ("RMUFS1", 4),
            ("RMUFS2", 5),
            ("CBL2", 2),
            ("CBL3", 3),
            ("FS1", 4),
            ("FS2", 5),
            ("CBL", 1),
        ]:
            if f"_{infix}_" in meter or f"_{infix}" in meter or f"S11_{infix}" in meter:
                slot = slot_num
                break

        if slot is None:
            return None

        sheet_name, local_slot = self.resolve_panel_sheet_and_slot(slot)
        row = 10 + (local_slot - 1) * 4 + 0

        col = self._extract_switchgear_column(meter)
        if not col:
            return None

        return (sheet_name, f"{col}{row}")

    def _resolve_vcb(self, meter: str, tnb_location: str) -> tuple[str, str] | None:
        """Resolve VCB dynamic panel slot mappings."""
        if "_LV_" in meter or "_LV" in meter:
            return None

        panel_idx = 1
        if tnb_location:
            try:
                cat, idx = parse_equipment_index(tnb_location)
                if cat == "11KV":
                    panel_idx = idx
            except ValueError:
                pass

        sheet_name, local_slot = self.resolve_panel_sheet_and_slot(panel_idx)

        offset = None
        if (
            "_CBL_" in meter
            or "_CBL" in meter
            or "S11_CBL" in meter
            or "_BP_" in meter
            or "S11_BP" in meter
        ):
            offset = 0
        elif "_BR_" in meter or "_BR" in meter or "S11_BR" in meter:
            offset = 1
        elif "_BB_" in meter or "_BB" in meter or "S11_BB" in meter:
            offset = 2
        elif "_PT_" in meter or "_PT" in meter or "S11_PT" in meter:
            offset = 3

        if offset is None:
            return None

        row = 10 + (local_slot - 1) * 4 + offset

        col = self._extract_switchgear_column(meter)
        if not col:
            return None

        return (sheet_name, f"{col}{row}")

    def _extract_switchgear_column(self, meter: str) -> str | None:
        """Extract switchgear column (K, L, M, N, Q, T, U)."""
        if meter.startswith("US_"):
            return self.SWITCHGEAR_COLUMNS["US"]
        if "_PUL" in meter:
            return self.SWITCHGEAR_COLUMNS["PUL"]
        if meter.startswith("TEV_") or meter.startswith("TV_"):
            return self.SWITCHGEAR_COLUMNS.get("TEV", self.SWITCHGEAR_COLUMNS["TV"])
        if "_REF" in meter:
            return self.SWITCHGEAR_COLUMNS["REF"]
        if "_MAX" in meter:
            return self.SWITCHGEAR_COLUMNS["MAX"]
        if "_DIF" in meter:
            return self.SWITCHGEAR_COLUMNS["DIF"]
        if "_AVG" in meter:
            return self.SWITCHGEAR_COLUMNS["AVG"]
        return None


class PpuReadingMapper(ReadingMapperStrategy):
    """33kV PPU/SSU/PMU coordinate resolution engine routing meters across 4 sheets.

    Routes:
    1. 33kV switchgear meters -> '33kV (Main)' (or '33kV (Extra)')
    2. 11kV switchgear meters -> '11kV (Main)' (or '11kV (Extra)')
    3. Power Transformer meters -> 'TX'
    4. Visual inspection defect meters -> 'Visual Inspec.'
    """

    # Stride = 6 rows per panel, starting row 15
    PANELS_PER_SHEET: ClassVar[int] = 8
    PANEL_START_ROW: ClassVar[int] = 15
    PANEL_STRIDE: ClassVar[int] = 6

    # Switchgear columns on 33kV (Main) and 11kV (Main)
    SWITCHGEAR_COLUMNS: ClassVar[dict[str, str]] = {
        "REF": "L",
        "MAX": "M",
        "DIF": "N",
        "DEL": "N",
        "AVG": "O",
        "TAVG": "O",
        "TEV": "R",
        "PUL": "S",
        "US": "T",
        "LOADING": "I",
        "HEATER": "J",
        "PRES_CB": "V",
        "PRES_MBB": "V",
        "PRES_RBB": "V",
    }

    # Transformer slot rows on TX sheet: slot_idx -> (part1_row, part2_row)
    TX_SLOT_ROWS: ClassVar[dict[int, tuple[int, int]]] = {
        1: (14, 33),
        2: (17, 36),
        3: (20, 39),
        4: (23, 42),
        5: (26, 45),  # Local TX
    }

    # Distribution VCB meter suffixes handled by PceReadingMapper
    PCE_DISTRIBUTION_SUFFIXES: ClassVar[tuple[str, ...]] = (
        "_PE13R",
        "_PE13V",
        "_PE13V2",
        "_PE13O",
    )

    def __init__(
        self,
        panel_map: dict[str, int] | None = None,
        bay_map: dict[tuple[str, str], tuple[str, int]] | None = None,
    ) -> None:
        """Initialize PpuReadingMapper with optional bay token to panel index mapping and workbook bay map."""
        self.panel_map = panel_map or {}
        self.bay_map = bay_map or {}

    def get_target(
        self,
        meter_name: str,
        tnb_location: str = "",
        bay_map: dict[tuple[str, str], tuple[str, int]] | None = None,
    ) -> tuple[str, str] | None:
        """Resolve a 33kV METERNAME and optional TNBLOCATION to (sheet_name, cell_coordinate)."""
        if not meter_name:
            return None

        meter = meter_name.strip().upper()
        norm_loc = str(tnb_location).replace("\\", "/").strip().upper() if tnb_location else ""

        # Exclude PCE 11kV distribution VCB meters so TestsheetReadingMapper fallback delegates to PceReadingMapper
        if any(meter.endswith(sfx) for sfx in self.PCE_DISTRIBUTION_SUFFIXES):
            return None

        # 1. Background Environment Meters
        if meter.startswith("BG_"):
            return self._resolve_background(meter, norm_loc)

        # 2. Visual Inspection Checklist Defect Meters & Status Checklist Meters
        # Return None so they are handled semantically via visual findings, matching PceReadingMapper
        if (
            meter.startswith("VI_")
            or meter == "HEATER_33KV_STATUS"
            or meter == "HEATER_11KV_STATUS"
        ):
            return None

        # 3. Power Transformer Meters -> TX
        if (
            meter.startswith("TH_PTX")
            or meter.startswith("US_PTX")
            or meter.startswith("US_LTX")
            or "_PTX" in meter
            or "/TX/" in norm_loc
        ):
            return self._resolve_transformer(meter, norm_loc)

        # 4. 33kV Switchgear Meters -> 33kV (Main) / 33kV (Extra)
        if (
            meter.startswith("SG_33_")
            or meter.startswith("TH_S33_")
            or meter.startswith("US_S33_")
            or meter.startswith("TEV_S33_")
            or meter.startswith("HEATER_33KV_")
            or "/33KV/" in norm_loc
        ):
            return self._resolve_switchgear(meter, norm_loc, voltage_prefix="33kV", bay_map=bay_map)

        # 5. 11kV Switchgear Meters -> 11kV (Main) / 11kV (Extra)
        if (
            meter == "SG_11_LOADING"
            or meter.startswith("TH_S11_")
            or meter.startswith("US_S11_")
            or meter.startswith("TEV_S11_")
            or meter.startswith("HEATER_11KV_")
            or "/11KV/" in norm_loc
        ):
            return self._resolve_switchgear(meter, norm_loc, voltage_prefix="11kV", bay_map=bay_map)

        return None

    def _resolve_background(self, meter: str, norm_loc: str) -> tuple[str, str] | None:
        """Resolve ambient and background measurement meters."""
        if "TX" in meter or "/TX/" in norm_loc:
            # Transformer Bay Background Temperature
            return ("TX", "U6")

        # 11kV / Substation room environment
        if "TEM" in meter:
            return ("11kV (Main)", "U6")
        if "HUM" in meter:
            return ("11kV (Main)", "U7")
        if "TEV" in meter or "TV" in meter:
            return ("11kV (Main)", "U8")

        return ("11kV (Main)", "U6")

    def _resolve_transformer(self, meter: str, norm_loc: str) -> tuple[str, str] | None:
        """Resolve Power Transformer measurements on TX sheet."""
        tx_slot = 1
        if norm_loc:
            try:
                cat, idx = parse_equipment_index(norm_loc)
                if cat == "TX":
                    tx_slot = idx
            except ValueError:
                pass

        p1_row, p2_row = self.TX_SLOT_ROWS.get(tx_slot, (14, 33))

        # Part 1: Ultrasound
        if meter.startswith("US_PTX_HV") or meter.startswith("US_LTX_HV"):
            return ("TX", f"J{p1_row}")
        if meter.startswith("US_PTX_LV") or meter.startswith("US_LTX_LV"):
            return ("TX", f"N{p1_row}")

        # Part 1: HV Cable Thermal
        if "PTXHV" in meter or "LTXHV" in meter:
            col = self._extract_column_from_suffix(meter, ("R", "S", "T", "U"))
            return ("TX", f"{col}{p1_row}") if col else None

        # Part 1: LV Cable Thermal
        if "PTXLV" in meter or "LTXLV" in meter:
            col = self._extract_column_from_suffix(meter, ("W", "X", "Y", "Z"))
            return ("TX", f"{col}{p1_row}") if col else None

        # Part 2: Main Tank / Body
        if "PTXMT" in meter or "PTX_BODY" in meter or "TX_BODY" in meter:
            col = self._extract_column_from_suffix(meter, ("R", "S", "T", "U"))
            return ("TX", f"{col}{p2_row}") if col else None

        # Part 2: Cooling Fins
        if "PTXFIN" in meter:
            col = self._extract_column_from_suffix(meter, ("X", "Y", "Z", "AA"))
            return ("TX", f"{col}{p2_row}") if col else None

        # Part 2: Marshalling Kiosk
        if "PTXMK" in meter:
            col = self._extract_column_from_suffix(meter, ("F", "G", "H", "I"))
            return ("TX", f"{col}{p2_row}") if col else None

        # Part 2: Conservator Tank
        if "PTXCT" in meter:
            col = self._extract_column_from_suffix(meter, ("L", "M", "N", "O"))
            return ("TX", f"{col}{p2_row}") if col else None

        return None

    @staticmethod
    def _extract_column_from_suffix(meter: str, cols: tuple[str, str, str, str]) -> str | None:
        """Extract ref (cols[0]), max (cols[1]), del/dif (cols[2]), or avg (cols[3])."""
        ref_col, max_col, del_col, avg_col = cols
        if "_REF" in meter:
            return ref_col
        if "_MAX" in meter:
            return max_col
        if "_DEL" in meter or "_DIF" in meter:
            return del_col
        if "_AVG" in meter or "_TAVG" in meter:
            return avg_col
        return None

    def _resolve_switchgear(
        self,
        meter: str,
        norm_loc: str,
        voltage_prefix: str,
        bay_map: dict[tuple[str, str], tuple[str, int]] | None = None,
    ) -> tuple[str, str] | None:
        """Resolve 33kV or 11kV switchgear meter to exact cell coordinate."""
        active_bay_map = bay_map if bay_map is not None else self.bay_map
        bay_token = norm_loc.split("/")[-1].strip().upper() if norm_loc else ""
        voltage_key = voltage_prefix.upper()

        if active_bay_map and (voltage_key, bay_token) in active_bay_map:
            sheet_name, base_row = active_bay_map[(voltage_key, bay_token)]
        else:
            panel_idx = self._resolve_panel_index(norm_loc, voltage_prefix)
            sheet_name, local_slot = self._resolve_switchgear_sheet_and_slot(panel_idx, voltage_prefix)
            base_row = self.PANEL_START_ROW + (local_slot - 1) * self.PANEL_STRIDE

        # Loading & Heater
        if meter in ("SG_33_LOADING", "SG_11_LOADING"):
            return (sheet_name, f"I{base_row}")
        if meter.startswith("HEATER_") and ("AMP" in meter or "STATUS" in meter):
            return (sheet_name, f"J{base_row}")

        # Gas Pressure
        if "GIS_PRES_CB" in meter:
            return (sheet_name, f"V{base_row + 1}")
        if "GIS_PRES_MBB" in meter or "GIS_PRES_RBB" in meter:
            return (sheet_name, f"V{base_row + 2}")

        # Compartment sub-row offset
        offset = self._resolve_compartment_offset(meter)
        if offset is None:
            return None

        row = base_row + offset

        # Column mapping
        col = self._extract_swg_column(meter)
        if not col:
            return None

        return (sheet_name, f"{col}{row}")

    def _resolve_panel_index(self, norm_loc: str, voltage_prefix: str) -> int:
        """Resolve 1-based panel index from TNBLOCATION and panel_map."""
        if not norm_loc:
            return 1

        # Check explicit panel_map first (e.g. '3P5' -> 1)
        bay_token = norm_loc.split("/")[-1].strip()
        if bay_token in self.panel_map:
            return self.panel_map[bay_token]

        try:
            cat, idx = parse_equipment_index(norm_loc)
            if cat in (voltage_prefix.upper(), "33KV", "11KV"):
                return idx
        except ValueError:
            pass

        return 1

    def _resolve_switchgear_sheet_and_slot(
        self, panel_index: int, voltage_prefix: str
    ) -> tuple[str, int]:
        """Resolve sheet title and 1-based local slot (1..8) on that sheet."""
        if panel_index < 1:
            panel_index = 1

        if panel_index <= self.PANELS_PER_SHEET:
            return f"{voltage_prefix} (Main)", panel_index

        extra_num = ((panel_index - 1) // self.PANELS_PER_SHEET)
        local_slot = ((panel_index - 1) % self.PANELS_PER_SHEET) + 1

        if extra_num == 1:
            return f"{voltage_prefix} (Extra)", local_slot
        return f"{voltage_prefix} (Extra) ({extra_num})", local_slot

    @staticmethod
    def _resolve_compartment_offset(meter: str) -> int | None:
        """Map meter compartment infix to 0-5 row offset."""
        # Offset 0: Breaker / Front Panel
        if "_BR_" in meter or "_FP_" in meter or "S33_FP" in meter or "S11_BR" in meter:
            return 0
        # Offset 1: Cable Compartment / Back Panel
        if (
            "_CBL_" in meter
            or "S33_CBL" in meter
            or "S11_CBL" in meter
            or "_BP_" in meter
            or "S33_BP" in meter
            or "S11_BP" in meter
        ):
            return 1
        # Offset 2: Busbar Top
        if (
            "_BB_" in meter
            or "_TBB_" in meter
            or "_TOP_" in meter
            or "S33_TOP" in meter
            or "S11_TOP" in meter
        ):
            return 2
        # Offset 3: PT Compartment
        if "_PT_" in meter or meter.endswith("_PT"):
            return 3
        # Offset 4: Cable Entry
        if "_CE_" in meter or "_CBLENT_" in meter:
            return 4
        # Offset 5: Link Box
        if "_LB_" in meter:
            return 5
        # Transition Panel: row offset 0
        if "_TP_" in meter or meter.endswith("_TP"):
            return 0

        return None

    def _extract_swg_column(self, meter: str) -> str | None:
        """Extract column letter for switchgear measurements."""
        if meter.startswith("US_"):
            return self.SWITCHGEAR_COLUMNS["US"]
        if "_PUL" in meter:
            return self.SWITCHGEAR_COLUMNS["PUL"]
        if meter.startswith("TEV_") or meter.startswith("TV_"):
            return self.SWITCHGEAR_COLUMNS["TEV"]
        if "_REF" in meter or "_TREF" in meter:
            return self.SWITCHGEAR_COLUMNS["REF"]
        if "_MAX" in meter or "_TMAX" in meter:
            return self.SWITCHGEAR_COLUMNS["MAX"]
        if "_DEL" in meter or "_TDEL" in meter or "_DIF" in meter:
            return self.SWITCHGEAR_COLUMNS["DEL"]
        if "_AVG" in meter or "_TAVG" in meter:
            return self.SWITCHGEAR_COLUMNS["AVG"]
        return None


class TestsheetReadingMapper(ReadingMapperStrategy):
    """Facade for testsheet coordinate resolution supporting both 11kV and 33kV."""

    __test__ = False

    # Backward compatibility re-exports of 11kV class attributes
    BACKGROUND_METADATA_MAP: ClassVar[dict[str, str]] = PceReadingMapper.BACKGROUND_METADATA_MAP
    RMU_SLOT_MAP: ClassVar[dict[str, int]] = PceReadingMapper.RMU_SLOT_MAP
    SWITCHGEAR_COLUMNS: ClassVar[dict[str, str]] = PceReadingMapper.SWITCHGEAR_COLUMNS
    TRANSFORMER_COLUMNS: ClassVar[dict[str, str]] = PceReadingMapper.TRANSFORMER_COLUMNS

    @staticmethod
    def resolve_panel_sheet_and_slot(panel_index: int) -> tuple[str, int]:
        return PceReadingMapper.resolve_panel_sheet_and_slot(panel_index)

    def __init__(
        self,
        strategy: ReadingMapperStrategy | None = None,
        voltage_type: str = "11kV",
    ) -> None:
        """Initialize TestsheetReadingMapper with concrete strategy or voltage type."""
        if strategy is not None:
            self.strategy = strategy
        elif str(voltage_type).strip().lower() == "33kv":
            self.strategy = PpuReadingMapper()
        else:
            self.strategy = PceReadingMapper()

    def get_target(
        self,
        meter_name: str,
        tnb_location: str = "",
        bay_map: dict[tuple[str, str], tuple[str, int]] | None = None,
    ) -> tuple[str, str] | None:
        """Resolve meter to cell coordinate, delegating to active strategy with cross-voltage fallback."""
        target = self.strategy.get_target(meter_name, tnb_location, bay_map=bay_map)
        if target is not None:
            return target

        # Cross-voltage fallback
        if isinstance(self.strategy, PceReadingMapper) and self._is_33kv_meter(meter_name):
            return PpuReadingMapper(bay_map=bay_map).get_target(meter_name, tnb_location, bay_map=bay_map)
        if isinstance(self.strategy, PpuReadingMapper) and self._is_11kv_pce_meter(meter_name):
            return PceReadingMapper().get_target(meter_name, tnb_location, bay_map=bay_map)

        return None

    @staticmethod
    def _is_33kv_meter(meter_name: str) -> bool:
        m = str(meter_name).strip().upper()
        return (
            m.startswith("SG_33_")
            or m.startswith("TH_S33_")
            or m.startswith("US_S33_")
            or m.startswith("TEV_S33_")
            or m.startswith("HEATER_33KV_")
            or m.startswith("TH_PTX")
            or m.startswith("US_PTX")
            or m.startswith("US_LTX")
            or m.startswith("BG_TEM_TX")
            or m.startswith("VI_NER_")
            or m.startswith("VI_FCBL_")
            or m.startswith("VI_BLDG_")
            or m.startswith("VI_SGERT_")
            or m.startswith("VI_PTX_")
            or m.startswith("VI_SGEX_")
            or m.startswith("VI_SGIN_")
            or m == "SG_11_LOADING"
            or m.startswith("HEATER_11KV_")
            or "_P31VV" in m
        )

    @staticmethod
    def _is_11kv_pce_meter(meter_name: str) -> bool:
        m = str(meter_name).strip().upper()
        return m.endswith("_PE13R") or m.endswith("_PE13V") or m.endswith("_PE13V2") or m.endswith("_PE13O")
