# Map: Quick Report Generation for Pahang

Labels: wayfinder:map

## Destination

Implement and verify the end-to-end Quick Report Generation engine in `pahang-cli` (`src/quick_report/`), including testsheet data extraction, docx template binding (`docxtpl` & `docxcompose`), IR/DG photo range matching, defect suffix calculation, and CLI integration (`QuickReportAction`) operating across Pahang's workstation directory structure (`TESTSHEET/`, `RAW MATERIAL/`, `QUICK REPORT/`).

## Notes

- **Baseline Codebase**: Johor implementation in `PO 42234207 - JOHOR - JBU - 400 PE IR US TEV/src/report_composer/`
- **Pahang Trial References**: `C:\Users\ADAM\Desktop\tnb\src\` (`quick_report_workflow.py`, `quick_report_render.py`, `quick_report_specs.py`, `quick_report_utils.py`)
- **Core Module Location**: `src/quick_report/composer.py` (`QuickReportComposer`), `src/quick_report/render.py`, `src/quick_report/specs.py`, `src/quick_report/utils.py`
- **Front Page Selection**: Determined strictly by substation technology rating (`IR` vs `IR+US` vs `IR+US+TEV`), not defect findings.
- **Output Filename**: Omits date string (`{pe_number:03d}. {name_erms} {suffix}.docx`).
- **Defect Suffix**: Canonical order `(IR+US+TEV+VI)`.
- **Undefined Handling**: Uses `PreservingUndefined` to preserve unpopulated Jinja tags (`{{ placeholder }}`) and convert empty values to `"-"`.
- **Skills**: `/codebase-design`, `/domain-modeling`, `/research`, `/grilling`

## Decisions so far

- [Quick Report Composer Architecture and Template Engine](file:///.issues/025-quick-report-composer-architecture.md) — Specified 6-module structure (`__init__.py`, `composer.py`, `cbm_family.py`, `cbm_render.py`, `visual_render.py`, `utils.py`), 7-part docx assembly sequence with mandatory Sticker Page, canonical suffix `(IR+US+TEV+VI)`, and date-omitting output filename `{pe_number:03d}. {name_erms}{suffix}.docx`.
- [Digital Testsheet Data Extraction and Context Mapping Schema](file:///.issues/026-digital-testsheet-data-extraction-schema.md) — Digital Testsheet set as single source of truth without QR02 fallback; front page date `DD MMM YYYY` vs CBM page date `DD/MM/YYYY`; time `HH:MM AM/PM`; 1-to-1 IR/US/TEV pairing with integer `dB` formatting without space; decoupled detail provider strategy.
- [Substation Condition Template Auto-Detection Rules](file:///.issues/027-substation-condition-template-auto-detection.md) — Specified Single-Page 3-Pair Template Chunking Engine (`MASTER_SUBSTATION_CONDITION_PAGE.docx` + `docxtpl` + `docxcompose`); no shaded fills; solid borders for active slots & nil borders for unused slot 3 on final chunk; full equipment names (`SWITCHGEAR`, `TRANSFORMER`); `_resolve_switchgear_label` seam with TODO stub; canonical 2-column pair sequence `(Overview, Signboard)`, `(SWITCHGEAR, Nameplate)`, `(TRANSFORMER, Nameplate)`, `(FEEDER PILLAR, Nameplate)`, `(BATTERY CHARGER, Nameplate)`, `(RTU, Nameplate)`, `(EFI, SF6)`, `(Fire Ext, Expiry)`, `(TX Oil Level)`.
- [Photo Retrieval, Aspect Ratio Resizing, and Fallback Placeholders](file:///.issues/028-photo-retrieval-resizing-and-placeholders.md) — Specified Option A stem-matching interface stubs for DG, IR, US, and TEV with explicit TODO markers for future map implementation; DG photo fallback set to `""` (empty string).
- [Quick Report CLI Action and Service Wiring](file:///.issues/029-quick-report-cli-service-wiring.md) — Specified 2-option CLI menu (`Select Date Folder`, `Manual FL Input`); auto-selected `MASTER_SUBSTATION_CONDITION.docx`; per-station `try...except` exception isolation for resilient batch processing mirroring Johor reference (`quick_report_workflow.py`).



## Not yet specified


- Batch generation error recovery and partial failure reporting across multi-station runs.
- PDF export or conversion options (if required in future scope).

## Out of scope

- Direct modification of master ENGR files (handled by Update QR02 CBA workflow).
- Hardcoded 8-digit date strings in Quick Report output file stems (`<DDMMYYYY>`).
