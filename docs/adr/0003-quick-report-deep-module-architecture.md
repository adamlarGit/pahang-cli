# 3. Quick Report Deep Module Architecture with Batch Word COM Session

Date: 2026-09-07
Status: Accepted

## Context

The legacy Quick Report pipeline evolved into a shallow multi-stage design (`QuickReportExtractor`, `QuickReportFilter`, `QuickReportTransformer`, `CbmDefectPlanner`, `QuickReportComposer`, and `WorkflowService.run_quick_report()`). This introduced several structural issues:

1. **Surface Complexity and Model Indirection**: Callers had to construct request dataclasses (`QuickReportRequest`), configure mode enums (`QuickReportMode.FOLDER` vs `QuickReportMode.FL`), configure filter stages, and route through indirect service shims.
2. **Word COM Lifecycle Inefficiency**: Each substation report in a batch spawned and terminated an independent Microsoft Word COM instance (`O(N)` process launches). A batch of 30 substations incurred 30 distinct `WINWORD.EXE` initializations and teardowns, slowing batch compilation and increasing the risk of orphaned background processes.
3. **Leaky Compilation Seam**: Compilation was coupled to Microsoft Word COM, making headless execution in continuous integration (CI) and on non-Windows platforms impossible without mocking internal private functions across stages.
4. **Late Template Failure**: Precondition failures (e.g. missing Front Page or Sticker Page templates) were detected mid-flight after COM initialization had already begun.

## Decision

Refactor Quick Report into a deep module (`QuickReportWorkflow`) exposing exactly two public methods, backed by an isolated batch Word COM session and a swappable compiler seam:

1. **Two-Method Public Surface**:
   - `QuickReportWorkflow.generate(target: ReportTarget, environment: ProjectEnvironment, *, station: str | Sequence[str] | None = None, condition_template: Path | None = None, progress_sink: ProgressSink | None = None) -> QuickReportResult`
   - `QuickReportWorkflow.inspect(target: ReportTarget, environment: ProjectEnvironment, *, station: str | Sequence[str] | None = None, condition_template: Path | None = None) -> QuickReportInspection`
   - `ReportTarget` polymorphically accepts a `Path`, date `str` (`DD-MM-YYYY`), single or comma-separated functional location `str` (e.g. `"CCHL/PCE/J00059, CCHL/PCE/J00060"`), or sequence of `Path` / functional location `str`.
2. **Unified Planning Pipeline (`_plan()`)**:
   - Discovery, station filtering, and defect transformation are unified in `_plan()`.
   - `inspect()` executes `_plan()` to verify targets, defect counts, stems, and required templates without launching Microsoft Word or writing to disk.
   - `generate()` executes `_plan()`, enforces preflight template validation, and iterates through station plans.
3. **Document Compiler Seam & Headless Testing**:
   - `DocumentCompiler` protocol defines `@runtime_checkable class DocumentCompiler(Protocol)` with `compile(self, parts: Sequence[Path], output_path: Path) -> Path`.
   - Production adapter `WordComDocumentCompiler` implements `compile()` and a `@contextmanager session()` context manager.
   - Test suites and CI runners use `FakeDocumentCompiler` (writing valid stub OpenXML packages) to test end-to-end report generation in sub-seconds without Word COM or Windows dependencies.
4. **Batch COM Session Context Manager**:
   - `generate()` enters `with self._compiler.session():` across the entire batch. A single `Word.Application` COM instance is initialized once (`O(1)`) and reused across all substations in the batch.
   - Standalone calls to `compiler.compile()` automatically wrap themselves in a one-off session if called outside a batch.
   - Each substation retains its own freshly isolated ActiveX container via `word_app.Documents.Add()` per ADR 0002.
   - Process ID tracking and a `finally` block watchdog guarantee that hung or lingering Word processes terminate cleanly on batch completion or unexpected error.
5. **Substation Fault Isolation (`SubstationIsolatedBatchResiliencePolicy`)**:
   - Individual substation compilation failures are captured in `QuickReportResult.errors` while subsequent substations in the batch continue compiling.
6. **Purge of Legacy Shims**:
   - `QuickReportRequest` and `QuickReportMode` are removed.
   - `QuickReportFilter` is deleted, inlining predicate checks directly into discovery and planning.
   - `QuickReportExtractor.extract()` accepts explicit arguments (`folders`, `fls`).
   - `WorkflowService.run_quick_report()` wrapper is retired.

## Consequences

### Positive
- Callers and CLI presentation actions interact exclusively with `generate()` and `inspect()`.
- Reusing a single Word COM instance reduces batch runtime across large runs (e.g. 30 substations).
- Preflight guards fail fast upfront (`FileNotFoundError`) before any Word processes spawn.
- The `DocumentCompiler` seam allows 100% headless CI test execution with zero COM dependencies.
- Legacy request models and mode enums are eliminated.

### Negative and Constraints
- Callers requiring custom pipeline steps must configure them via constructor dependency injection or use the high-level workflow interface.
- Production Word COM compilation still requires a Windows host with Microsoft Word installed.
