# Refactor Legacy Workflows to Deep Module + Orchestrator Architecture

Labels: wayfinder:task
Parent: [Map: WhatsApp Report Generation Workflow (Pahang CLI)](file:///.issues/030-whatsapp-report-generation-map.md)

## Question

How should existing flat workflows `src/update_qr02_cba_workflow.py` and `src/populate_total_pe_workflow.py` be refactored to follow the deep module + orchestrator architecture (separating domain logic/data access into `src/master/` or `src/pe_total/` deep modules, leaving top-level files strictly as lean workflow orchestrators)?

## Proposed Architecture Seams

1. **Update QR02 CBA Workflow**:
   - Deep Module: `src/master/qr02.py` (`Qr02Repository`, `LocalExcelQr02Transaction`, atomic update mechanics).
   - Orchestrator: `src/update_qr02_cba_workflow.py` (lean coordination between `ProjectEnvironment`, `Qr02Repository`, and `TestsheetExtractor`).

2. **Populate Total PE Workflow**:
   - Deep Module: `src/master/total_pe.py` (or `src/total_pe/repository.py` for `TOTAL PE.xlsx` upsert operations and cell formatting).
   - Orchestrator: `src/populate_total_pe_workflow.py` (lean coordination between daily `TESTSHEET/` scanner and `TotalPeRepository`).

3. **WhatsApp Workflow**:
   - Deep Module: `src/whatsapp/` (`src/whatsapp/generator.py`, `src/whatsapp/models.py` for docxtpl rendering and PDF regex matching).
   - Orchestrator: `src/whatsapp_report_workflow.py` (lean interface bridge for `WorkflowService`).
