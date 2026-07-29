# Ticket 049: Research Standalone Utility Actions Architecture & Implementations

## Parent Map

[Map 048: Standalone Utility Actions Deep Dive & Implementation](file:///.issues/048-standalone-utility-actions-map.md)

## Type

`research` (AFK)

## Status

`CLOSED`

## Question

What domain modules exist or need to be ported/restored to replace the `_make_stub_runner` entries in `src/utility_actions.py`, and how should standalone utility actions be structured to support direct user execution?

## Resolution

1. **Standalone Environment Helper**: Implement `get_or_create_utility_environment(target_dir)` in `src/project/environment.py`. If active project exists, use its environment; if `env is None`, prompt operator for directory and synthesize a transient `ProjectEnvironment`.
2. **Domain Workflow Consolidation**: Port all core workflow modules from the reference CLI (`C:\Users\ADAM\Documents\PO 42234207 - JOHOR - JBU - 400 PE IR US TEV\src\`) into `src/workflows/`:
   - `converters.py` (`ComDocumentConverter`, `DocumentConverter`, `_is_pce_testsheet_sheet`, `_is_pce_vi_sheet`, `select_and_sort_sheets`)
   - `docx_to_pdf.py`
   - `testsheet_to_pdf.py`
   - `combine_pdfs.py`
   - `diagonal_borders.py`
   - `pdf_extract.py`
   - `rename_files.py`
   - `rename_flir.py`
   - `replace_signatures.py`
3. **Registry Un-stubbing**: Un-stub all 11 action runners in `src/utility_actions.py` to lazy-load these domain workflow modules. Fix `_load_whatsapp_runner` fallback when `env is None`.
4. **Project Pipeline Consolidation**: Wire `PostProcessingPipelineAction` in `src/project_workflow_actions.py` and `WorkflowService.run_postprocessing_pipeline` to consume these exact same core workflow modules for 1-Click project execution.
