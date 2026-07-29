"""MSMS Domain Models."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MsmsRecord:
    functional_location: str
    substation_name: str
    date: str
    wo: str


@dataclass
class MsmsUpdateSummary:
    data_msms_path: Path
    total_pe_path: Path
    engr_pattern: str


@dataclass(frozen=True)
class WorkbookUpdateMappings:
    """Resolved column mappings for workbook update workflows."""
    data_msms: dict[str, str]
    engr_excel: dict[str, str]
    total_pe: dict[str, str]


MSMS_COLUMN_MAPPING = {
    "wo": "A",
    "location": "B",
    "substation_name": "D",
    "functional_location": "E",
    "date": "F",
}

ENGR_COLUMN_MAPPING_11KV = {
    "functional_location": "I",
    "substation_name": "J",
    "date": "O",
    "type": "M",
}

ENGR_COLUMN_MAPPING_33KV = {
    "functional_location": "E",
    "substation_name": "H",
    "date": "Q",
    "type": "I",
}

TOTAL_PE_COLUMN_MAPPING = {
    "pe_no": "A",
    "functional_location": "B",
    "substation_name": "C",
    "date": "D",
    "type": "E",
    "wo": "F",
}
