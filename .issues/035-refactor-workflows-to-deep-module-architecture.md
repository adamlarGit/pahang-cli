# Refactor Legacy Workflows to Deep Module + Orchestrator Architecture

Labels: wayfinder:task
Status: Closed
Parent: [Map: WhatsApp Report Generation Workflow (Pahang CLI)](file:///.issues/030-whatsapp-report-generation-map.md)

## Question

How should existing flat workflows `src/update_qr02_cba_workflow.py` and `src/populate_total_pe_workflow.py` be refactored to follow the deep module + orchestrator architecture (separating domain logic/data access into `src/master/` or `src/pe_total/` deep modules, leaving top-level files strictly as lean workflow orchestrators)?

## Resolution

1. **Orchestrator Package Consolidation (`src/workflows/`)**:
   - All workflow orchestrators moved into `src/workflows/`:
     - `src/workflows/update_qr02_cba.py`
     - `src/workflows/populate_total_pe.py`
     - `src/workflows/whatsapp.py`
     - `src/workflows/raw_material.py`
   - Re-exports provided in `src/workflows/__init__.py` and top-level root modules maintained for backwards-compatibility.

2. **History Persistence Decoupling (`src/workflows/history.py`)**:
   - Extracted `ProcessingHistoryStore` to encapsulate reading and writing persistent JSON processing history.
   - Standardized on explicit, workflow-specific history filename `PYTHON/qr02_processed_folders.json`.

3. **Deep Module & Orchestrator Seams**:
   - Excel repositories (`src/master/qr02.py`, `src/master/total_pe.py`) and docx renderers (`src/whatsapp/`) handle data persistence and UoW transactions.
   - Orchestrators in `src/workflows/` coordinate discovery, mode filtering (`AUTO`, `ALL`, `SPECIFIC_FOLDERS`), history tracking, and progress reporting.
