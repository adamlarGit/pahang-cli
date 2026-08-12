# Architectural Research & Comparison Report: Pahang CLI vs. TNB (Source CLI)

**Date**: August 6, 2026  
**Target Codebases**:
- **Current CLI**: [`pahang-cli`](file:///C:/Users/ADAM/Desktop/pahang-cli) (Entrypoint: [`main.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/main.py))
- **Source CLI**: [`tnb`](file:///C:/Users/ADAM/Desktop/tnb) (Entrypoint: [`main.py`](file:///C:/Users/ADAM/Desktop/tnb/main.py))

---

## Executive Summary

This research report provides a high-level architectural comparison between the **Source CLI (`tnb`)** (originally created for personal use) and the **Current CLI (`pahang-cli`)** (refactored for multi-laptop deployment and colleague collaboration). 

### Key Findings
1. **Maintainability & Scalability**: **`pahang-cli` is significantly superior**. It adopts a clean layered architecture with a clear boundary between presentation (CLI adapters), domain request models, and a pure service orchestrator ([`src/workflows/service.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/service.py)). Configuration is dynamic and portable via [`.cli_config.json`](file:///C:/Users/ADAM/Desktop/pahang-cli/.cli_config.json). Conversely, `tnb` relies on procedural scripts with hardcoded local file paths in [`config.py`](file:///C:/Users/ADAM/Desktop/tnb/config.py) and tight coupling between terminal prompts and execution.
2. **Web App / Local Frontend Migration**: **`pahang-cli` is dramatically easier to migrate**. Because `pahang-cli`'s workflows accept typed dataclasses ([`src/workflows/models.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/models.py)) and report updates via an abstract `progress_sink`, a web backend (e.g. FastAPI / Flask) can execute workflows directly without modifying domain code. While `tnb` includes an experimental FastAPI prototype ([`src/app_api.py`](file:///C:/Users/ADAM/Desktop/tnb/src/app_api.py)), its actual core automation workflows (e.g., [`quick_report_workflow.py`](file:///C:/Users/ADAM/Desktop/tnb/src/quick_report_workflow.py)) embed interactive CLI prompt calls deep inside processing loops, creating high migration friction.

---

## High-Level Architectural Comparison

| Architectural Dimension | Source CLI (`tnb`) | Current CLI (`pahang-cli`) | Winner & Impact |
| :--- | :--- | :--- | :--- |
| **Layering & Separation** | Monolithic & procedural. CLI menus trigger runner functions that directly mix I/O prompts and processing. | Layered (CLI Presentation $\rightarrow$ Request/Result Models $\rightarrow$ Workflow Service $\rightarrow$ Engine Operations). | **`pahang-cli`**: High modularity and clear responsibility separation. |
| **Configuration Management** | Static & Environment-bound. Hardcoded absolute Windows paths in [`config.py`](file:///C:/Users/ADAM/Desktop/tnb/config.py). | Dynamic & Portable. Global templates use package-relative paths; user project profiles live in [`.cli_config.json`](file:///C:/Users/ADAM/Desktop/pahang-cli/.cli_config.json). | **`pahang-cli`**: Can run seamlessly across different colleague machines without code changes. |
| **Domain State & Models** | Untyped dictionary payloads and inline tuples passed through deeply nested functions. | Immutable typed dataclasses ([`PopulateTotalPeRequest`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/models.py#L32), [`QuickReportRequest`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/models.py#L88)). | **`pahang-cli`**: Strong type safety, auto-completion, and predictable contract interfaces. |
| **Terminal I/O Coupling** | High. Interactive selectors (`cli_selectors`) called directly inside workflow loops. | Low. CLI adapters ([`src/project_workflow_actions.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/project_workflow_actions.py)) gather user choices *before* invoking services. | **`pahang-cli`**: Core logic runs headlessly without requiring a terminal. |
| **Progress & Logging** | Direct `print()` and `logging.error()` calls throughout code. | Dependency-injected `progress_sink: Callable[[str], None]` parameter in requests. | **`pahang-cli`**: Progress can be streamed to terminal, WebSocket, or web SSE response. |
| **Testability** | Hard to unit-test. Tests require mocking interactive prompts or full filesystem states. | Highly testable. Workflows can be tested headlessly by passing request objects to `WorkflowService`. | **`pahang-cli`**: Enables automated CI unit/integration testing. |

---

## Question 1: Maintainability & Scalability Evaluation

### 1. Code Base Structure & Modularity
- **`tnb`**: Organized by feature files in `src/` (e.g. `quick_report_workflow.py`, `whatsapp_report_workflow.py`). However, each workflow file contains the entire stack: user prompting, data fetching, Jinja2 template rendering, Excel manipulation, and error printing.
- **`pahang-cli`**: Introduces a dedicated [`src/workflows/`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows) package directory:
  - [`models.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/models.py): Pure request and response data contracts.
  - [`service.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/service.py): Single entry facade ([`WorkflowService`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/service.py#L26)) exposing standard workflow execution methods.
  - Feature engines (`quick_report.py`, `populate_total_pe.py`, `raw_material.py`, `whatsapp.py`) handle pure domain processing.

### 2. Configuration & Multi-User Portability
- **`tnb`**: Hardcodes user-specific directory paths in [`config.py`](file:///C:/Users/ADAM/Desktop/tnb/config.py):
  ```python
  # tnb/config.py
  TEMPLATES = {
      "Pahang": {
          "11kV": {
              "whatsapp": r"C:\Users\ADAM\Desktop\tnb\template_sample\PAHANG\11kV\TEMPLATE WHATSAPP PYTHON.docx",
              ...
          }
      }
  }
  ```
  Sharing `tnb` with a colleague requires modifying source code to update paths.
- **`pahang-cli`**: Solves portability using dynamic resolution in [`config.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/config.py):
  ```python
  # pahang-cli/config.py
  GLOBAL_TEMPLATES_DIR: Path = Path(__file__).parent / "templates"
  _CONFIG_FILE = Path(__file__).parent / ".cli_config.json"
  ```
  Project-specific workspace directories are stored per-laptop in [`.cli_config.json`](file:///C:/Users/ADAM/Desktop/pahang-cli/.cli_config.json) via interactive onboarding ([`src/project/management.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/project/management.py)).

### Maintainability & Scalability Verdict
> **Winner: `pahang-cli`**  
> `pahang-cli` is engineered for growth. Adding a new workflow or supporting a new state/region requires simply adding a request model in `models.py` and a service method in `service.py`, without touching existing CLI menu infrastructure or worrying about path breaks on colleagues' machines.

---

## Question 2: Local Web App / Frontend Migration Readiness

If you decide to convert the CLI into a local web application (e.g. running a FastAPI backend on `localhost` with a React, Vue, or Next.js frontend UI), here is how the two codebases compare:

### Migration Analysis for `pahang-cli` (Recommended Path)

`pahang-cli` is already **80% prepared for a web architecture**.

#### Why `pahang-cli` is Easy to Migrate:
1. **Clean Service Boundary**: In [`src/project_workflow_actions.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/project_workflow_actions.py#L346-L351), CLI actions act merely as HTTP controller equivalents:
   ```python
   # CLI Presentation Adapter
   request = WhatsAppReportRequest(
       report_dir=report_dir,
       progress_sink=_cli_progress_sink,
   )
   service = WorkflowService()
   result = service.run_whatsapp(environment, request)
   ```
2. **Pluggable Progress Streaming**: `progress_sink` is an abstract callable `Callable[[str], None]`. For a Web App, a WebSocket or Server-Sent Events (SSE) log streamer can be passed directly as the `progress_sink` to push real-time progress bars to the web UI.
3. **Headless Execution**: `WorkflowService` methods do not call `print()` or interactive prompt functions.

#### Proposed Web Architecture for `pahang-cli`:
```
+-------------------------------------------------------------------+
|                        Local Web Frontend                         |
|                 (React / Vue / Vite / Tailwind UI)               |
+-------------------------------------------------------------------+
                                 | HTTP REST / WebSockets
                                 v
+-------------------------------------------------------------------+
|                     FastAPI / Flask Web Server                    |
|                (Translates HTTP JSON -> Request Models)           |
+-------------------------------------------------------------------+
                                 |
                                 v
+-------------------------------------------------------------------+
|                Pahang CLI Core WorkflowService                    |
|            (src/workflows/service.py - Unchanged)                 |
+-------------------------------------------------------------------+
                                 |
                                 v
+-------------------------------------------------------------------+
|               Excel / Word / Data Processing Engines              |
+-------------------------------------------------------------------+
```

---

### Migration Analysis for `tnb` (High Friction)

At first glance, `tnb` appears web-ready because it already contains a FastAPI module ([`src/app_api.py`](file:///C:/Users/ADAM/Desktop/tnb/src/app_api.py)) and SQLite database services ([`src/app_services.py`](file:///C:/Users/ADAM/Desktop/tnb/src/app_services.py)).

#### The Hidden Friction in `tnb`:
1. **Disconnected Web API**: `app_api.py` in `tnb` only provides CRUD endpoints for managing metadata (States, Purchase Orders, Substation lists). It **does not wire into or execute** the actual document generation workflows (`quick_report_workflow.py`, `whatsapp_report_workflow.py`).
2. **Embedded Terminal Prompts**: Inside [`src/quick_report_workflow.py`](file:///C:/Users/ADAM/Desktop/tnb/src/quick_report_workflow.py), functions directly invoke terminal prompt selectors:
   ```python
   # tnb/src/quick_report_workflow.py
   substation_choice = cli_selectors.select_option(...) # Freezes web server thread!
   ```
   If called from a web server, these functions would block the server thread indefinitely while waiting for keyboard input in a non-existent terminal session.

---

## Conclusion & Actionable Recommendation

1. **Architecture & Scalability**: Continue using **`pahang-cli`** as your foundation. The refactoring effort paid off—its domain service pattern and configuration system are clean, robust, and maintainable.
2. **Web Application Migration**: Use **`pahang-cli`** as the backend core for your web app.
   - Build a lightweight FastAPI wrapper around `WorkflowService`.
   - Use Pydantic models for web request validation that map directly to `pahang-cli` dataclasses ([`src/workflows/models.py`](file:///C:/Users/ADAM/Desktop/pahang-cli/src/workflows/models.py)).
   - Stream `progress_sink` messages via FastAPI `EventSourceResponse` (SSE) or WebSockets to display progress UI.
