"""MSMS Domain Models."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MsmsRecord:
    functional_location: str
    substation_name_erms: str
    date: str
    wo: str


@dataclass(frozen=True)
class ConsolidateResult:
    """Telemetry result of consolidating client .xls files into DATA MSMS."""
    files_processed: int
    rows_appended: int
    duplicates_skipped: int
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnrichResult:
    """Telemetry result of enriching DATA MSMS with TOTAL PE / ENGR metadata."""
    matched_count: int
    unmatched_count: int
    unmatched_wos: tuple[str, ...] = ()
    updated_cells_count: int = 0


@dataclass(frozen=True)
class PropagateResult:
    """Telemetry result of propagating WO numbers from DATA MSMS into TOTAL PE."""
    matched_count: int
    already_populated_count: int
    unmatched_count: int
    unmatched_fls: tuple[str, ...] = ()
    updated_count: int = 0


MSMS_COLUMN_MAPPING = {

    "wo": "A",
    "location": "B",
    "substation_name_erms": "D",
    "functional_location": "E",
    "date": "F",
}

ENGR_COLUMN_MAPPING_11KV = {
    "functional_location": "I",
    "substation_name_erms": "J",
    "date": "O",
    "type": "M",
}

ENGR_COLUMN_MAPPING_33KV = {
    "functional_location": "E",
    "substation_name_erms": "H",
    "date": "Q",
    "type": "I",
}

TOTAL_PE_COLUMN_MAPPING = {
    "pe_no": "A",
    "functional_location": "B",
    "substation_name_erms": "C",
    "date": "D",
    "type": "E",
    "wo": "F",
}
