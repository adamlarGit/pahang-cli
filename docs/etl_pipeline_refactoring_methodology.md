# ETL Pipeline Refactoring & Deep Module Methodology

## Overview & Purpose

This document defines the standard architecture methodology for refactoring data processing workflows in `pahang-cli`.

When asked to refactor any workflow (e.g. `PopulateTotalPeWorkflow`, `UpdateQr02CbaWorkflow`, `UpdateDataMsmsWorkflow`, `WhatsAppReportWorkflow`, or new future workflows), **AI agents and developers MUST follow this exact methodology**.

The goal is to transform monolithic workflow functions into **deep, modular 6-stage ETL pipelines** (Preflight Guard, Extract, Filter, Transform, Load, Audit) with pure testable seams, 1:1 behavioral preservation, and zero silent fallbacks.

---

## Core Philosophy & Design Principles

### 1. Deep Modules
A module is **deep** when it exposes a small, simple interface hiding significant internal behavior behind a clean seam.
- **High Leverage:** Callers call one clean entry point (`Workflow.execute(...)`).
- **High Locality:** Bug fixes, path logic, and data calculations are concentrated in explicit, single-purpose stages rather than spread across loops.

### 2. The Rule of Class Extraction (Preventing Shallow Classes)
To prevent creating **shallow modules** (forcing empty 2-line class boilerplate wrappers that increase context switching without hiding complexity), developers must apply the **Rule of Class Extraction**:

- **External Deep Module Seam**: Regardless of internal complexity, callers and CLI commands see **one deep entry point**: `Workflow.execute(env, request)`.
- **Internal 6-Phase Logical Pipeline**: All workflows strictly follow the 6 logical phases (`Preflight Guard` ➔ `Extractor` ➔ `Filter` ➔ `Transformer` ➔ `Loader` ➔ `Auditor`).
- **Class Extraction Criteria**:
  - **Extract a Dedicated Stage Class** (`[WorkflowName]Filter`, `[WorkflowName]Transformer`, etc.) when:
    - The stage contains non-trivial domain logic (e.g. complex regex matching, FL row lookup, multi-file path math).
    - The stage is pure logic (`Filter` / `Transformer`) and needs fast **in-memory unit testing** without disk/Excel I/O.
    - The stage maintains its own state or external dependencies (e.g. an Excel repository or Docx template binder).
  - **Keep as an Internal Workflow Method** (`_validate_preconditions()`, `_audit_and_format_result()`) when:
    - The stage is simple and straightforward (e.g. a 3-line path assertion check or simple history logging call).
    - Extracting a class would create a pass-through wrapper that adds zero leverage.
- **Internal Stage Delegation (Single Responsibility Principle)**:
  - Even when a stage is extracted into a dedicated class (e.g. `WhatsAppReportExtractor` or `WhatsAppReportFilter`), its main entry method (`extract()`, `filter()`) **must not be a monolithic function**.
  - The main stage method acts as a high-level summary that delegates specific sub-tasks to:
    1. **Single-purpose private helper methods** (`_scan_qualifying_docx_files()`, `_match_substation_row()`).
    2. **Zero-dependency domain normalizers** (`src/core/normalizers.py`).
    3. **Reusable domain repositories** (`TotalPeRepository`, `WorkflowHistoryRepository`).

### 3. Explicit & Verbose Stage Names
Do **NOT** create generic, fuzzy abstractions like `GenericExtractor` or `PipelineStage[T]` shared across different workflows. Each workflow has unique domain rules and I/O needs.
- Every extracted stage MUST be named explicitly after its workflow domain:
  - `[WorkflowName]PreflightGuard` (Pre-flight validation stage)
  - `[WorkflowName]Extractor` (Read stage)
  - `[WorkflowName]Filter` (Filter & Row Validation stage)
  - `[WorkflowName]Transformer` (Transformation & Plan construction stage)
  - `[WorkflowName]Loader` (Write stage)
  - `[WorkflowName]Auditor` (Verification & History logging stage)
  - `[WorkflowName]Workflow` (Orchestrator)

### 4. 1:1 Behavioral Fidelity
- **Zero Breaking Changes:** Preserve all public function signatures, return types (`WorkflowResult`), error message strings, warning formats, and progress callbacks (`progress_sink`).
- **Escalate Conflicts:** If legacy logic contains ambiguous edge cases, escalate to the user before assuming behavior.

### 5. No Silent Fallbacks (Fail Fast)
- **Eliminate Silent Sheet Fallbacks:** Never fallback to `wb.active` if a specific sheet (e.g. `DataCycle1`) is expected. Raise an explicit `RuntimeError` immediately.
- **Eliminate Silent Directory Fallbacks:** If a requested directory path does not exist or has 0 packages, raise an explicit `FileNotFoundError` immediately instead of silently scanning alternative folders.

### 6. Error Handling Contract
Every workflow must define two things: what exceptions **mean** (taxonomy) and how the orchestrator **responds** to them (resilience policy).

#### Exception Taxonomy (Universal)
All stages must use these exception types consistently:
- **`ValueError`** — Invalid request input or user-provided parameters (e.g. `report_dir` is `None`, no qualifying files found).
- **`FileNotFoundError`** — Missing precondition resource (e.g. template file, input directory, required workbook).
- **`RuntimeError`** — Corrupted or unexpected data state (e.g. missing expected Excel sheet, output file is 0 bytes after write).

#### Resilience Policy (Per-Workflow)
Each workflow must declare its resilience policy in its class docstring or as a class-level comment:
- **`atomic`** — All-or-nothing. Any unhandled stage exception aborts the entire workflow. The orchestrator has no `try/except` around the pipeline. Use for single-output workflows (e.g. `WhatsAppReportWorkflow`).
- **`best-effort`** — Collect errors per-item and continue processing remaining items. The orchestrator wraps per-item processing in `try/except`, accumulates errors into the result object (e.g. `warnings`, `errors` tuple fields), and the `Auditor` reports partial success. Use for batch workflows (e.g. `RawMaterialWorkflow`).

### 7. Progress Reporting
Progress callbacks (`progress_sink`) are the **orchestrator's responsibility**. Individual stages must remain pure and must NOT accept or call progress callbacks.

The orchestrator's `execute()` method may contain a loop with progress calls wrapping stage invocations:
```python
for i, target in enumerate(targets):
    progress_sink(f"Processing {i+1} of {len(targets)}...")
    plan = self.transformer.transform(target)
    self.loader.load(plan)
```

---

## The 6 Pipeline Stages (ETL Pattern)

```
┌─────────────────────────────────────────────────┐
│ 1. PreflightGuard (Pre-flight Resource Guard)   │  ← Pure I/O Check (assert paths, templates & schemas exist)
└────────────────────────┬────────────────────────┘
                         │ Pre-flight Validated Inputs
                         ▼
┌─────────────────────────────────────────────────┐
│ 2. Extractor (Read Stage)                       │  ← Pure Read I/O (load Excel, scan disk, query DB)
└────────────────────────┬────────────────────────┘
                         │ Raw Domain Entities
                         ▼
┌─────────────────────────────────────────────────┐
│ 3. Filter (Filter & Row Validation Stage)       │  ← Pure Logic (row validations, alignment checks, predicates)
└────────────────────────┬────────────────────────┘
                         │ Verified Targets
                         ▼
┌─────────────────────────────────────────────────┐
│ 4. Transformer (Transform Stage)                │  ← Pure Math & Path Math (build Execution Plan / Copy Plan)
└────────────────────────┬────────────────────────┘
                         │ Transformation Plan / Instructions
                         ▼
┌─────────────────────────────────────────────────┐
│ 5. Loader (Write Stage)                         │  ← Pure Write I/O (provision folders, write Excel, copy files)
└────────────────────────┬────────────────────────┘
                         │ Write Output Handles
                         ▼
┌─────────────────────────────────────────────────┐
│ 6. Auditor (Verification & History Logging)    │  ← Output Verification & Audit (verify size, log history, build telemetry)
└─────────────────────────────────────────────────┘
```

### Stage 1: PreflightGuard (Pre-flight Validation Phase)
- **Responsibility:** Validate environmental preconditions before reading data. Verify input directory paths exist, required template files exist on disk, and Excel sheet schemas are present.
- **Rules:** Fails fast immediately with `FileNotFoundError` or `RuntimeError`. Does not parse business row data.

### Stage 2: Extractor (Read Phase)
- **Responsibility:** Read raw data from external sources (Excel workbooks, disk filesystem, SQLite, APIs).
- **Rules:** Pure Read I/O. Does not perform business calculations or filtering. Assumes preconditions are valid. Returns raw domain entities or tuples.

### Stage 3: Filter (Filter & Row Validation Phase)
- **Responsibility:** Validate record alignment, execute mode predicates (`ALL`, `AUTO`, `SPECIFIC`), and filter target entities.
- **Rules:** Pure in-memory predicates. Zero side-effects. Zero file creation or modification.

### Stage 4: Transformer (Transformation Phase)
- **Responsibility:** Perform path calculations, value normalizations, defect suffix calculations (`IR+US+VI`), and construct immutable execution plans (`TransformationPlan`, `CopyInstruction`, `WhatsAppReportPlan`).
- **Rules:** Pure logic. Must NOT execute disk I/O, file copies, or Excel saves.

### Stage 5: Loader (Write Phase)
- **Responsibility:** Execute the execution plan created by the Transformer.
- **Rules:** Pure persistence / write I/O. Creates directories, writes Excel workbooks, renders Docx templates, saves files.

### Stage 6: Auditor (Verification & History Audit Phase)
- **Responsibility:** Verify written output file integrity (check file existence and non-zero byte size), log execution history to `WorkflowHistoryRepository`, and construct the standardized `WorkflowResult` telemetry object.
- **Rules:** Ensures zero unverified or corrupt file writes and standardizes execution telemetry.

### Workflow Orchestrator
- **Responsibility:** Instantiate the stage components/methods and execute them sequentially. Stages may receive context from earlier non-adjacent stages — the data flow is not strictly linear:
  ```python
  self.preflight_guard.validate(env, request)
  raw_data = self.extractor.extract(env, request)
  targets = self.filter_stage.filter(raw_data)
  plan = self.transformer.transform(targets, raw_data.resources)  # may reference earlier stage outputs
  load_output = self.loader.load(plan)
  result = self.auditor.audit(plan, load_output)
  return result
  ```

---

## Centralized Domain Primitives & Normalizers

Any pure string, date, or column normalization utility MUST be extracted to zero-dependency core modules (e.g. `src/core/normalizers.py`):
- `normalize_date_str(date_input)`
- `format_month_folder(month_input)`
- `clean_substation_name(name)`
- `col_to_index(col_letter)`

**Rule:** Domain normalizers MUST NOT import openpyxl, storage facades, or CLI modules. They are pure standard-library functions.

---

## Step-by-Step Execution Guide for AI Agents

When instructed to refactor a workflow using this methodology, execute the following steps in order:

### Step 1: Baseline Verification
1. Check if existing pytest tests exist for the target workflow (`tests/test_[workflow_name].py`).
2. **If tests exist:** Run them to verify a green baseline:
   `python -m pytest tests/test_[workflow_name].py`
3. **If no tests exist:** Write a **characterization test** first — a coarse integration test that captures the current input→output behavior of the legacy workflow *before* touching any code. This becomes your regression safety net and enforces the 1:1 Behavioral Fidelity guarantee.

### Step 2: Centralize Shared Normalizers
1. Inspect the target workflow for duplicate date formatting, column calculations, or string cleaning.
2. Move pure functions into `src/core/normalizers.py`.
3. Update all existing call sites to import from `src.core.normalizers`.

### Step 3: Decouple Workflow into 6 Stages
1. Apply the **Rule of Class Extraction**: determine which of the 6 stages require dedicated classes versus internal workflow methods.
2. Separate pre-flight path/schema validation into `PreflightGuard`.
3. Move I/O read operations into `Extractor`.
4. Move validation and filtering logic into `Filter`.
5. Move path math, entity mapping, and plan creation into `Transformer`.
6. Move write operations into `Loader`.
7. Add output verification and audit history logging to `Auditor`.
8. Update `[Name]Workflow.execute()` to orchestrate the 6 stages.

### Step 4: Eliminate Silent Fallbacks
1. Audit the extractor for `ws = wb["Sheet"] if "Sheet" in wb.sheetnames else wb.active` -> replace with strict requirement for `"Sheet"`.
2. Audit directory resolution for silent path fallbacks -> replace with fast `FileNotFoundError`.

### Step 5: Add Granular Unit Tests
1. Create `tests/test_[workflow_name]_components.py`.
2. Write fast unit tests for `Filter` and `Transformer` stages directly in memory (zero disk/Excel I/O).
3. Test edge cases (e.g. diverse filename patterns, missing ranges, date formats).

### Step 6: Verify Integration & Run Suite
1. Run `tests/test_[workflow_name].py` to verify 1:1 integration behavior.
2. Run full test suite: `python -m pytest`.

### Step 7: Code Review & Cleanup
1. Remove mid-file imports, unused imports, and dead helper methods.
2. Ensure docstrings and type hints are complete.

### Step 8: Update Domain Model
1. Update `CONTEXT.md` glossary entries for the refactored workflow to reflect the deep module seam and high-level domain responsibilities (keep entries domain-focused; avoid listing internal stage class names to keep the glossary clean).
2. If any domain terms were clarified or renamed during refactoring, update the corresponding `CONTEXT.md` entries immediately.

---

## Reference Implementation Example: `RawMaterialWorkflow` & `WhatsAppReportWorkflow`

For working reference implementations, inspect:
- **Pipeline Implementation:** [src/workflows/raw_material.py](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/raw_material.py), [src/workflows/whatsapp.py](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/whatsapp.py)
- **Domain Normalizers:** [src/core/normalizers.py](file:///C:/Users/ADAM/Desktop/pahang-cli/src/core/normalizers.py)
- **Component Unit Tests:** [tests/test_raw_material_components.py](file:///C:/Users/ADAM/Desktop/pahang-cli/tests/test_raw_material_components.py), [tests/test_whatsapp_report_components.py](file:///C:/Users/ADAM/Desktop/pahang-cli/tests/test_whatsapp_report_components.py)
- **Integration Tests:** [tests/test_raw_material_workflow.py](file:///C:/Users/ADAM/Desktop/pahang-cli/tests/test_raw_material_workflow.py), [tests/test_whatsapp_report.py](file:///C:/Users/ADAM/Desktop/pahang-cli/tests/test_whatsapp_report.py)
