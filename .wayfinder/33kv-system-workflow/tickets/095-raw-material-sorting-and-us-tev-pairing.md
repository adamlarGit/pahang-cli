<!-- status: open -->
Part of #90
Specification: [spec.md](../spec.md)

# 095: feat(33kv-raw): Raw material directory discovery and US+TEV multi-board archive extraction

**What to build:** Adapt raw material sorting and UltraTEV survey archive discovery to handle 33kV substation directory conventions (`01. PPU APMM 33-11kV (VI)`, `08. PMU GBID 275-132-33-11kV (VI)`, `05. SSU KPC GEBENG 33kV (VI)`), copying IR/DG photos according to 33kV `RAW DATA` sheet ranges, and extracting multi-board US+TEV surveys into canonical substation raw folders.

**Blocked by:** #92

**Status:** ready-for-agent

## Detailed Design & Architecture

1. **Substation Stem Parsing & Numeric Resolution (`src/project/storage.py`)**:
   - Define `SubstationStemInfo` dataclass:
     - `substation_number: int`
     - `station_type: str | None` (e.g. `"PPU"`, `"PMU"`, `"SSU"`, `"PE"`)
     - `name: str` (e.g. `"APMM"`, `"GBID"`, `"KIIP (SSU CAMEL POWER)"`)
     - `voltage_token: str | None` (e.g. `"33-11kV"`, `"275-132-33-11kV"`, `"33kV"`)
     - `defect_suffix: str | None` (e.g. `"(VI)"`, `"(US+VI)"`, `"(IR+US+TEV+VI)"`)
   - Implement `parse_substation_stem(name: str) -> SubstationStemInfo`:
     - Robust regex supporting leading digits (`1`, `01`, `001`), electrical station prefixes, multi-voltage tokens, and nested/multiple parentheses.
   - Update `WorkspaceStorage.get_substation_raw_data_dir()`:
     - Match date directory children using `extract_numerical_prefix(child.name) == substation_number` rather than fixed 3-digit prefix string matching.
     - Support child directories named `RAW DATA`, and child directories containing `US+TEV`, `US`, `IR`, or `DG`.

2. **Destination Folder Resolution (`src/workflows/raw_material.py`)**:
   - In `RawMaterialTransformer._resolve_substation_dest_dir()`:
     - When `environment.metadata.voltage_type == "33kV"` (or testsheet stem has descriptive tokens):
       - If a directory matching `substation_number` already exists under `RAW MATERIAL/<STATION>/<MONTH>/<DATE>/`, resolve to it directly.
       - Otherwise, default destination folder name to `package.testsheet_path.stem` (e.g. `01. PPU APMM 33-11kV (VI)`).
     - When `voltage_type == "11kV"`:
       - Retain strict 3-digit numeric folder convention `f"{package.substation_number:03d}"`.

3. **US & US+TEV Discovery & Extraction Ingestion**:
   - In `RawMaterialExtractor._scan_us_tev_archives()`:
     - Scan for `.zip` files in `unsorted_dir / "US+TEV"`, `unsorted_dir / "US"`, and root `unsorted_dir`.
   - In `RawMaterialTransformer.build_plan()`:
     - Check if destination already has `substation_dest_dir / "US"`; if so, maintain `US` as destination, otherwise default to canonical `substation_dest_dir / "US+TEV"`.

4. **Multi-Board US+TEV Cardinality Policy (`UsTevCardinalityPolicy`)**:
   - In `RawMaterialFilter.filter_us_tev_archive()` (or `filter_us_tev_archives()`):
     - For 33kV: Allow 1-to-many archive matching (e.g. `01_PPU_APMM_33KV.zip` and `01_PPU_APMM_11KV.zip`), returning all matched archives.
     - For 11kV: Enforce strict 1-to-1 archive cardinality; raise `RuntimeError` if multiple archives match.
   - For each matched archive in 33kV:
     - Generate an `ExtractInstruction` targeting `<US_DEST_DIR>/<ZIP_STEM>/`.
     - `RawMaterialLoader` extracts each archive idempotently with clean overwrite.

5. **2-Digit & Station Token Archive Matching (`UsTevArchiveMatching`)**:
   - Update matching patterns to include 2-digit zero-padded number tokens:
     - `rf"(?:^|[\W_]){substation_number:02d}(?:[\W_]|$)"`
     - `rf"(?:^|[\W_]){substation_number:03d}(?:[\W_]|$)"`
     - `rf"(?:^|[\W_]){substation_number}(?:[\W_]|$)"`
   - Use `normalize_substation_tokens()` to verify substation name tokens when multiple candidate archives exist across different stations.

6. **Photo Range Bounds Policy**:
   - Ingest `ir` and `dg` `PhotoRange` objects extracted by `PpuTestsheetParser` from the testsheet `RAW DATA` sheet.
   - No automatic heuristic scanning of panel photo columns when `RAW DATA` sheet bounds are unpopulated; emit standard non-blocking warning and skip photo copy.

## Acceptance Criteria Checklist

- [ ] Define `SubstationStemInfo` and implement `parse_substation_stem()` in `src/project/storage.py`.
- [ ] Update `WorkspaceStorage.get_substation_raw_data_dir()` to match directories using `extract_numerical_prefix()` and recognize `US` alongside `US+TEV`.
- [ ] Adapt `RawMaterialTransformer._resolve_substation_dest_dir()` to target existing matching directories or testsheet stems for 33kV while preserving `f"{num:03d}"` for 11kV.
- [ ] Update `RawMaterialExtractor._scan_us_tev_archives()` to scan `US+TEV` and `US` directories.
- [ ] Update `RawMaterialFilter` and `UsTevCardinalityPolicy` to support multi-board archives for 33kV (extracting into separate `<ZIP_STEM>` folders) while retaining 1-to-1 check for 11kV.
- [ ] Extend `UsTevArchiveMatching` to support 2-digit tokens (`f"{num:02d}"`) and station name token disambiguation.
- [ ] Add unit tests in `tests/test_raw_material_33kv.py` covering:
  - [ ] 33kV substation stem parsing (PPU, PMU, SSU, multi-voltage tokens, nested parentheses).
  - [ ] Raw data directory resolution with 2-digit stems.
  - [ ] Multi-board US+TEV archive matching and extraction.
  - [ ] Dual `US` / `US+TEV` source folder discovery.
  - [ ] Blank `RAW DATA` bounds resilience.
- [ ] Verify full test suite passes with 0 regressions.
