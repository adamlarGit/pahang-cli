# Task: Create Master QR02 Repository

Labels: wayfinder:task
Type: task
Status: open
Blocked by: 014

## Question

Create `src/master/qr02.py` following Johor's repository/transaction architecture — abstract `Qr02Repository`, `LocalExcelQr02Repository` with per-station ENGR resolution, `LocalExcelQr02Transaction` with Unit of Work pattern, atomic saves, ghost cell cleanup, and FL-based row matching.

## Specification

### 1. Module structure: `src/master/qr02.py`

Create `src/master/__init__.py` and `src/master/qr02.py`.

### 2. Abstract interfaces

```python
class Qr02Transaction(ABC):
    def __enter__(self) -> Qr02Transaction
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool | None
    def upsert_qr02_cba_records(self, records: Sequence[Any]) -> int

class Qr02Repository(ABC):
    def transaction(self) -> Qr02Transaction
```

### 3. `LocalExcelQr02Repository`

- Constructor takes `WorkspaceStorage`, `station: str`, `year: str`
- `_get_cba_path()` → calls `storage.get_engr_cba_path(station, year)`
- `transaction()` → returns `LocalExcelQr02Transaction`
- `invalidate_caches()` callback for post-transaction cleanup

### 4. `LocalExcelQr02Transaction`

**Row matching** (3-tier, matching by FL in Col I):
1. `fl_to_row` — exact FL match (primary)
2. `erms_name_to_row` — exact ERMS name match in Col J (secondary)
3. `fuzzy_name_to_row` — fuzzy name match (tertiary, strip PE/PDT/P-E prefixes, NO., non-alphanum)
4. Append new row as fallback

**Columns written** (Pahang-simplified, no equipment):
- Col L (12): GPS Coordinate
- Col M (13): Type
- Col N (14): Building Type (normalized)
- Col O (15): Cycle 1 date (with `DD-MMM-YYYY` number format)
- Col P (16): Vendor = `"EET"`

**Safety patterns** (ported from Johor):
- `atomic_save()` — write to tempfile, `shutil.copy2` to destination
- `_sanitize_ghost_formatting()` — purge ghost cells/rows/columns beyond real data bounds
- `_get_real_dimensions()` — scan `ws._cells` for true max row/col

### 5. `FakeQr02Repository` / `FakeQr02Transaction`

Port Johor's test doubles for unit testing.
