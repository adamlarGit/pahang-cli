<!-- status: closed -->
# Ticket #128: fix(filesystem): Windows MAX_PATH hardening for deep raw data extraction in RawMaterialLoader

## Parent
Part of #90

## What to build
Immunize raw material extraction and deep survey file operations against Windows MAX_PATH (260 character) limits in `RawMaterialLoader` and centralize Win32 extended-length path handling:

- **Centralize `safe_path()` (`src/core/path_utils.py`)**:
  - Create `src/core/path_utils.py` defining canonical `safe_path(p: Path | str) -> str` prepending `\\?\` (or `\\?\UNC\` for network shares) on Windows, ensuring forward slashes are normalized to backslashes.
  - Refactor `src/quick_report/prpd.py` to import `safe_path` directly from `src.core.path_utils`.
- **Integrate `safe_path()` into `RawMaterialLoader` (`src/workflows/raw_material.py`)**:
  - Use `safe_path()` across directory provisioning, existence checks, cleanup (`shutil.rmtree`), photo copying (`shutil.copy2`), and archive extraction (`zipfile.ZipFile.extractall`) for `RAW MATERIAL` operations.
- **Behavioral Unit Tests**:
  - Real filesystem integration tests (`tmp_path`) verifying file copying, directory cleanup, and archive extraction on paths exceeding 260 characters succeed without `WinError 206` or `FileNotFoundError`.

## Acceptance criteria
- [x] `safe_path()` is centralized in `src/core/path_utils.py` with slash normalization and imported by `src/quick_report/prpd.py`.
- [x] `RawMaterialLoader` in `src/workflows/raw_material.py` uses `safe_path()` for directory provisioning, existence checks, cleanup (`rmtree`), photo copying (`copy2`), and zip extraction (`extractall`).
- [x] COM workflows in `src/postprocessing/converters.py` remain untouched and excluded from `safe_path` wrapping.
- [x] Real-filesystem unit tests (`tests/test_raw_material_max_path.py`) verify copy, rmtree, and zip extraction succeed on paths exceeding 260 characters without `WinError 206`.

## Blocked by
- #126 (Closed)
