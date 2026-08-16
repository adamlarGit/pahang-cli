# Audit Results: Deprecated `update_data_msms` Code Paths & Dependencies

- **Date:** 2026-08-13
- **Ticket:** [Audit deprecated update_data_msms code paths](file:///C:/Users/ADAM/Desktop/pahang-cli/.wayfinder/msms-total-pe-refactoring/001-audit-deprecated-code.md)
- **Status:** Resolved

## Legacy vs. New Architecture

| Feature / Action | Legacy Path | New Replacement |
|---|---|---|
| `.xls` WO Consolidation | Manual by user | **Consolidate MSMS** workflow |
| ENGR → DATA MSMS Enrichment | `LocalExcelMsmsRepository.update_msms()` | **Enrich MSMS** workflow |
| ENGR → TOTAL PE (Name, Date, Type) | `LocalExcelTotalPeRepository.update_from_engr_and_msms()` | **DEPRECATED** — owned by Populate Total PE |
| DATA MSMS → TOTAL PE (WO only) | `LocalExcelTotalPeRepository.update_from_engr_and_msms()` | **Propagate WO** workflow |

---

## 🔴 REMOVE (Fully Deprecated)

### `src/workflows/update_data_msms.py` (entire file)
- `update_data_msms(env)` — monolithic workflow function
- `run_update_data_msms(env)` — interactive entrypoint
- `UpdateDataMsmsResources` — monolithic resource dataclass
- `get_update_data_msms_resources(env)` — resource resolution helper

### `src/msms/models.py`
- `MsmsUpdateSummary` — monolithic summary dataclass
- `WorkbookUpdateMappings` — combined mapping container coupling MSMS + ENGR + Total PE

### `src/msms/repository.py`
- `MsmsRepository.update_msms()` — abstract method for monolithic ENGR → DATA MSMS update
- `LocalExcelMsmsRepository.update_msms()` — concrete in-place Excel update (slash insertion + ENGR field copy)

### `src/master/total_pe.py`
- `TotalPeRepository.update_from_engr_and_msms()` — abstract method coupling ENGR + MSMS updates
- `LocalExcelTotalPeRepository.update_from_engr_and_msms()` — concrete method writing name/date/type from ENGR + WO from MSMS

---

## 🟡 REFACTOR (Partially Survives)

| Component | Current Location | Action |
|---|---|---|
| `load_engr_files()` | `src/workflows/update_data_msms.py` | Relocate to `EnrichMsmsExtractor` or shared `src/engr/` helper |
| `col_to_index()` | Duplicated in `repository.py` & `total_pe.py` | Centralize in `src/core/normalizers.py` |
| `_resolve_named_column()` | Duplicated in `repository.py` & `total_pe.py` | Extract to `src/core/normalizers.py` or shared helper |
| `write_cell()` | Duplicated in `repository.py` & `total_pe.py` | Centralize in shared excel utility |
| `MSMS_COLUMN_MAPPING` | `src/msms/models.py` | Update to support consolidated master WO schema |
| `TOTAL_PE_COLUMN_MAPPING` | `src/msms/models.py` | Scope down for Propagate WO (only FL match + WO write) |
| CLI callers | `service.py`, `project_workflow_actions.py`, `utility_actions.py` | Replace `run_update_data_msms()` with 3 independent commands |
| Tests | `tests/test_msms_workflow.py` | Replace with modular per-pipeline tests |

---

## 🟢 KEEP (Reusable As-Is)

| Component | Location | Used By |
|---|---|---|
| `MsmsRecord` | `src/msms/models.py` | Domain entity, all workflows |
| `ENGR_COLUMN_MAPPING_11KV` | `src/msms/models.py` | Enrich MSMS |
| `ENGR_COLUMN_MAPPING_33KV` | `src/msms/models.py` | Enrich MSMS |
| `read_col()` | `src/msms/repository.py` | Excel column reader, all workflows |
| `get_work_order_by_fl()` | `src/msms/repository.py` | Point lookups |
| All non-update methods on `LocalExcelTotalPeRepository` | `src/master/total_pe.py` | Populate Total PE |
