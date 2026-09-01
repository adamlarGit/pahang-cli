# Ticket 095: Equipment Taxonomy Aliasing & Multi-Tech Defect Planner

Parent: [Map 092: CBM Defect and Summary Redesign Map](file:///.issues/092-cbm-defect-and-summary-redesign-map.md)
Labels: wayfinder:task
Status: closed
Blocks: [Ticket 096](file:///.issues/096-part2-cbm-technical-summary-redesign.md)
Blocked-by: [Ticket 094](file:///.issues/094-cbm-defect-record-ingestion-alignment.md)

## Question

How should `QUICK_REPORT_FAMILY_SPECS` in `src/quick_report/cbm_family.py` and `CbmDefectPlanner` in `src/quick_report/cbm_defect_planner.py` group CBM defects, alias the 25+ real equipment values into the 5 core families, route TX defects to HV/LV roles based on area, and merge multi-technology readings for the same defect area into unified cards?

## Scope

- Implement canonical aliasing taxonomy in `cbm_family.py`.
- Smart routing for TX HV side vs LV side based on `DEFECT AREA` / `EQUIPMENT ID`.
- Unit grouping by `(item_key, defect_area)` with multi-technology merging.
- Comprehensive unit tests for planner.

## Resolution

- Expanded `QUICK_REPORT_FAMILY_SPECS` in `cbm_family.py` with canonical aliased equipment values for all 5 core families with multi-tech support.
- Updated `CbmDefectPlanner` to group by `item_key`, merge multi-tech readings on `(item_key, defect_area)`, and execute TX smart routing based on area/ID/equipment.
- Added comprehensive unit tests in `tests/test_quick_report_components.py`.
