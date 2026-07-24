# Task: Station ENGR Code Mapping and Path Resolution

Labels: wayfinder:task
Type: task
Status: open

## Question

Add the station-to-ENGR-code lookup table to `config.py` and extend `WorkspaceStorage` with ENGR file path resolution that accepts a station name and returns the correct per-station ENGR workbook path.

## Specification

### 1. `config.py` — Add `ENGR_STATION_CODES`

```python
ENGR_STATION_CODES: dict[str, str] = {
    "MARAN": "MRN",
    "KUANTAN": "KTN",
    "JENGKA": "JEN",
    "MUADZAM SHAH": "BMS",
    "BENTONG": "BTG",
    "GEBENG": "GBG",
    "ROMPIN": "ROM",
    "TEMERLOH": "TML",
    "PEKAN": "PEK",
    "TRIANG": "TRI",
    "KUALA LIPIS": "KLS",
    "CAMERON HIGHLAND": "CHL",
    "RAUB": "RAU",
    "JERANTUT": "JRT",
}
```

### 2. `src/project/storage.py` — Add `get_engr_cba_path(station: str, year: str) -> Path`

Resolves to: `PYTHON/ENGR FROM DRIVE/ENGR-750-36-CBA-{ENGR_STATION_CODES[station]}-{year}.xlsx`

Raises `ValueError` if station not found in mapping.
