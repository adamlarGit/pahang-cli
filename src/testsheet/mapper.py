"""Canonical Testsheet Reading Mapper for Pahang CLI.

Resolves MSMS METERNAME codes and TNBLOCATION paths to exact Excel cell
coordinates on 'PCE Testsheet' and its rollover sheets.
"""

from __future__ import annotations

import re
from typing import ClassVar


def parse_equipment_index(tnb_location: str) -> tuple[str, int]:
    """Parse TNBLOCATION string to extract equipment category and index.

    Examples:
        '/11KV/1' -> ('11KV', 1)
        'CCHL/PCEJ00024/TX/DTX1' -> ('TX', 1)
        '/FP/FP2' -> ('FP', 2)

    Raises:
        ValueError: If the location string cannot be parsed into a known equipment category.
    """
    if not tnb_location:
        raise ValueError("Empty TNBLOCATION string provided")

    norm = str(tnb_location).replace("\\", "/").strip().upper()

    # 11KV Switchgear: /11KV/N or 11KV/N
    m_11kv = re.search(r"(?:^|/)11KV/(\d+)", norm)
    if m_11kv:
        return "11KV", int(m_11kv.group(1))

    # Transformer: /TX/DTXN or TX/DTXN or DTXN
    m_tx = re.search(r"(?:^|/)TX/DTX(\d+)", norm)
    if not m_tx:
        m_tx = re.search(r"(?:^|/)DTX(\d+)", norm)
    if m_tx:
        return "TX", int(m_tx.group(1))

    # Feeder Pillar: /FP/FPN or FP/FPN or FPN
    m_fp = re.search(r"(?:^|/)FP/FP(\d+)", norm)
    if not m_fp:
        m_fp = re.search(r"(?:^|/)FP(\d+)", norm)
    if m_fp:
        return "FP", int(m_fp.group(1))

    raise ValueError(f"Could not parse equipment category and index from TNBLOCATION: {tnb_location}")


def get_sheet_name(sheet_index: int) -> str:
    """Return sheet name corresponding to sheet index (1-based)."""
    if sheet_index <= 1:
        return "PCE Testsheet"
    return f"PCE Testsheet ({sheet_index})"


class TestsheetReadingMapper:
    """Zero-side-effect coordinate resolution engine mapping METERNAME to PCE Testsheet cells."""

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

    def get_target(self, meter_name: str, tnb_location: str = "") -> tuple[str, str] | None:
        """Resolve a METERNAME and optional TNBLOCATION to (sheet_name, cell_coordinate).

        Returns:
            (sheet_name, cell_coordinate) or None if unmapped / stub placeholder.
        """
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

    def is_stub(self, meter_name: str, tnb_location: str = "") -> bool:
        """Return True if meter is a stub or unmapped to testsheet cells."""
        return self.get_target(meter_name, tnb_location) is None

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
            # TX3/TX4 deferred
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

        # Column mapping
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
        # Body Readings (Overview row 26 & background)
        if (
            meter.startswith("TH_S11_RMU_")
            or meter.startswith("TV_S11_RMU_")
            or meter.startswith("US_S11_RMU_")
        ):
            if meter == "TH_S11_RMU_AVG_PE13R":
                return ("PCE Testsheet", "N26")
            if meter == "TV_S11_RMU_PE13R":
                return ("PCE Testsheet", "P6")
            # All other RMU body metrics (MAX, REF, DIF, PUL, US) are stubs
            return None

        # Determine compartment slot from METERNAME infix
        slot = None
        # Check specific multi-char infixes first
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
        # RMU only uses CABLE sub-row (+0)
        row = 10 + (local_slot - 1) * 4 + 0

        col = self._extract_switchgear_column(meter)
        if not col:
            return None

        return (sheet_name, f"{col}{row}")

    def _resolve_vcb(self, meter: str, tnb_location: str) -> tuple[str, str] | None:
        """Resolve VCB dynamic panel slot mappings."""
        # LV compartment is not on testsheet (stub)
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

        # Compartment sub-row offset: CBL=0, BR=1, BB=2, PT=3
        offset = None
        if "_CBL_" in meter or "_CBL" in meter or "S11_CBL" in meter:
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
        if meter.startswith("TV_"):
            return self.SWITCHGEAR_COLUMNS["TV"]
        if "_REF" in meter:
            return self.SWITCHGEAR_COLUMNS["REF"]
        if "_MAX" in meter:
            return self.SWITCHGEAR_COLUMNS["MAX"]
        if "_DIF" in meter:
            return self.SWITCHGEAR_COLUMNS["DIF"]
        if "_AVG" in meter:
            return self.SWITCHGEAR_COLUMNS["AVG"]
        return None
