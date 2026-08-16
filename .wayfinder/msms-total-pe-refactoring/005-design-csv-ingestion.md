<!-- label: wayfinder:grilling -->
<!-- status: closed -->
<!-- claimed-by: assistant -->
<!-- blocked-by: none -->
# Design CSV Ingestion pipeline

## Question

How should the Ingest MSMS CSVs workflow handle the date extraction and file normalization from RAW DATA/ to TO BE FILLED/?

## Context

Client CSVs arrive with **unpredictable naming conventions** that vary by person:
- `TNBWOCREATEWOMETER_02062026` (DDMMYYYY suffix)
- `CBMS_05-08-2026` (DD-MM-YYYY suffix)
- `04.08.2026` (DD.MM.YYYY, date-only filename)

The canonical output format is: `DD-MM-YYYY_NNN.csv` where NNN is a zero-padded index for duplicate dates.

A single CSV can contain data for **multiple PahangStations** (row-level attribute via TNBLOCATION), so station is NOT part of the filename.

**Folder structure:**
```
PYTHON/MSMS/
├── RAW DATA/        ← client drops raw CSVs here
├── TO BE FILLED/    ← normalized CSVs ready for processing
└── COMPLETED/       ← manually moved by user after review
```

## Design Decisions Needed

- **Date extraction parser**: What regex/parsing strategy handles all known client naming variants? What about future unknown variants?
- **Validation**: Should the script validate CSV structure (check for expected columns like WONUM, TNBLOCATION, METERNAME) before moving?
- **Duplicate handling**: When a file with the same date already exists in TO BE FILLED/, auto-increment index. But what if the same file is dropped twice in RAW DATA/?
- **Error UX**: What happens when the script can't extract a date from a filename? Fail fast? Prompt user?
- **Move vs copy**: Move files from RAW DATA to TO BE FILLED, or copy (keeping RAW DATA as backup)?

## Standards

Must follow [etl_pipeline_refactoring_methodology.md](file:///C:/Users/ADAM/Desktop/pahang-cli/docs/etl_pipeline_refactoring_methodology.md).

## Resolution

- **PreflightGuard**: Requires `PYTHON/MSMS/RAW DATA/` directory to exist and contain at least 1 `.csv` file. Requires `PYTHON/MSMS/TO BE FILLED/` directory to exist.
- **Extractor**: Reads `.csv` files from `RAW DATA/` and performs pre-ingestion schema validation, checking for required header columns (`WONUM`, `TNBLOCATION`, `METERNAME`). Invalid files raise a schema error.
- **Filter**: Computes file content hash (SHA-256) to detect identical files. Skips exact duplicates already present in `TO BE FILLED/`.
- **Transformer**: Multi-pattern regex parser attempts matching sequential patterns (`DD-MM-YYYY`, `DD.MM.YYYY`, `DDMMYYYY`) to extract dates. Formats target canonical filename as `DD-MM-YYYY_NNN.csv` with zero-padded index for multiple files on the same date.
- **Loader**: Moves normalized `.csv` files from `RAW DATA/` into `TO BE FILLED/`.
- **Auditor & Resilience Policy**: Strict **fail-fast** resilience policy — halts batch execution immediately if any filename date cannot be parsed or schema validation fails, preventing invalid data entry.

