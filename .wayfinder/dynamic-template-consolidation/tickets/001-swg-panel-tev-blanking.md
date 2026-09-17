---
id: "001"
title: "Switchgear Panel TEV Dynamic Blanking & PRPD Optimization"
github_issue: 41
status: closed
---

# Ticket 001: Switchgear Panel TEV Dynamic Blanking & PRPD Optimization

<!-- status: closed -->

## Objective

Implement Method 1 (truly dynamic templates via OpenXML blanking) for Switchgear Panel templates (`swg-panel.docx`) across Full Report and Quick Report.

## Two-Tier Eligibility Model

1. **Tier 1 (Contract Awarded Technologies)**:
   - Check if `TEV` is in project awarded technologies (e.g. `ProjectMetadata.technologies` / `pe_info.technologies`).
   - Default: `("IR", "US", "TEV")` if unspecified.

2. **Tier 2 (Switchgear Compartment Eligibility)**:
   - **TEV-Eligible**: `BREAKER COMPARTMENT`, `CABLE COMPARTMENT`, `PT COMPARTMENT`, and `FUSE COMPARTMENT` (e.g. INDKOM RMUs).
   - **Non-TEV / Blanked**: `CABLE ENTRY`, `BUSBAR COMPARTMENT`, and any other compartment not in the eligible set.

## Blanking Requirements

When TEV is inactive (either contract lacks TEV, or panel compartment is not TEV-eligible):
- [x] Clear text, remove cell background shading, and set borders to `<w:val="nil"/>` for the TEV cells (rows 21–32, columns 11–22 of the 37x24 table in `swg-panel.docx`).
- [x] Inject empty strings for TEV placeholders in docxtpl render context (`bg`, `reading`, `ppc`, `char`, `severity`, `prpd`).
- [x] Skip generating TEV PRPD graph images in `src/quick_report/prpd.py` for non-TEV compartments to eliminate unnecessary disk I/O and computation.
- [x] Applied to both Full Report (`src/full_report/scan_adapters.py`, `src/full_report/scan_render.py`) and Quick Report (`src/quick_report/cbm_render.py`).
- [x] Automated tests verifying OpenXML borders and PRPD skipping.
