<!-- status: closed -->
# Ticket #141: feat(postprocessing): integrate dual-mode high-fidelity PDF converter across Full Report and Utility batch workflows

## Parent
Part of #90

## What to build
Integration and end-to-end verification of the dual-mode high-fidelity Word converter across all consumers in the application:
1. `14) Post-Process Full Reports (PDF + Testsheet Merge)` (`src/workflows/full_report_postprocessing.py`) for single-part and multi-part documents, preserving testsheet PDF appending (`processed_testsheet/pdf/`) and ultrasound audio embedding (`embed_survey_ultrasound_into_pdf`).
2. `6) Convert DOCX to PDF (batch)` (`src/workflows/docx_to_pdf.py`) converting folders of DOCX files at full fidelity.
3. `11) Run Full Substation Post-Processing Pipeline` (`src/workflows/postprocessing_pipeline.py`).
4. Verification against unit and workflow tests ensuring full integration parity.

## Acceptance criteria
- [x] `src/workflows/full_report_postprocessing.py` utilizes dual-mode converter with testsheet appending and ultrasound embedding.
- [x] `src/workflows/docx_to_pdf.py` utilizes dual-mode high-fidelity conversion.
- [x] `src/workflows/postprocessing_pipeline.py` integrates dual-mode high-fidelity conversion.
- [x] Unit and workflow test suite passes with zero regressions.

## Blocked by
#140
