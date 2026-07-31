# Ticket 069: Research Quick Report Workflow Service Call Architecture

Labels: wayfinder:research
Status: Closed
Parent: [Map 068: Quick Report Workflow Service Call Alignment Map](file:///.issues/068-quick-report-workflow-service-alignment-map.md)

## Question

Should `WorkflowService.run_quick_report` instantiate a `QuickReportWorkflow` in `src/workflows/quick_report.py` conforming to `docs/etl_pipeline_refactoring_methodology.md` and delegating to `src/quick_report/` domain modules, or directly invoke `src/quick_report/composer.py`? What architectural pattern best preserves 1:1 behavior while maintaining high codebase leverage and developer experience?

## Resolution

Adopt **Option A: Create a standardized `QuickReportWorkflow` orchestrator in `src/workflows/quick_report.py`**.

### Findings:
1. **Architectural Consistency**: All other major workflows (`PopulateTotalPeWorkflow`, `RawMaterialWorkflow`, `WhatsAppReportWorkflow`, `UpdateQr02CbaWorkflow`) live in `src/workflows/` and implement the 6-stage ETL pipeline seam (`Workflow.execute(environment, request)`).
2. **Decoupling Orchestration from Rendering Engine**:
   - `src/workflows/quick_report.py` will serve as the top-level 6-stage orchestrator (`PreflightGuard`, `Extractor`, `Filter`, `Transformer`, `Loader`, `Auditor`).
   - `src/quick_report/` will serve strictly as a specialized document rendering domain engine, receiving pure `QuickReportPlan` objects from the workflow's `Transformer` stage and executing DOCX compilation in its `Loader` stage.
3. **High Locality & Testability**:
   - Pure logic (FL normalization, suffix calculation `(IR+US+VI)`, `pe_info` preparation, template path resolution) moves to `QuickReportTransformer`, enabling fast in-memory unit tests without Word/Excel I/O.
   - Standardized `Auditor` handles file integrity verification and telemetry collection.
