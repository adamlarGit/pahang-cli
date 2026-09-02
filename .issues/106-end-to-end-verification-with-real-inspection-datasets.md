# Ticket 106: End-to-End Verification with Real Inspection Datasets

Labels: wayfinder:task, afk, state:closed

Blocked by: [Ticket 105: Part 4 CBM Defect Detail Pages Context Builder & Composer Integration](file:///.issues/105-part4-cbm-defect-detail-pages-context-builder-and-composer-integration.md)

## Question

How should comprehensive unit and integration tests be constructed to verify end-to-end Quick Report compilation against real substation packages (`TAMAN BUKIT BEIRUT PERMAI`, `BUKIT UBI NO.2`, `PASARAYA OCEAN`, `TRAS`), confirming that severity cells are colored correctly, testsheet measurements are populated accurately, and PRPD images are cleanly embedded without regressions?

## Resolution

- **Integration Test Execution**:
  - Implemented `tests/test_e2e_real_substations.py` and `tests/test_cbm_defect_pages_integration.py`.
  - Ingests actual testsheet workbooks (`020 IR.xlsx`), extracts TEV background (cell `P6` = `2`), extracts SWG panel measurements (Cols Q/S/T/U/V) and TX measurements (Cols K/L).
  - Automatically discovers raw UltraTEV survey files (`20260805T121020_020-TRAS`), decodes FlatBuffers `eventData.js` and JSON `ultrasonic_phase_plot.js`, generates PRPD scatter plots using 4-tier repetition density bins, and binds `InlineImage` into the rendered detail DOCX.
  - Verifies OpenXML table cell severity fills (`#EE0000` for defect technology, `#00B050` for non-defective technology, text cleanly cleared) and checks that all inline shapes are properly populated.
- **Verification**: 114 passing unit and integration tests across the test suite.
