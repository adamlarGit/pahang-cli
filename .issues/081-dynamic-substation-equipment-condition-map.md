# Map 081: Dynamic Substation Equipment Configuration & Condition Pages Map

Labels: wayfinder:map

## Destination

Design and build a canonical, reusable substation equipment package model (`src/testsheet/models.py`), a 6-stage ETL compliant OpenPyXL extractor (`src/testsheet/extractor.py`), and a dynamic condition pairs transformer (`src/quick_report/transformer.py`) that generates 2-column condition pages tailored to any substation equipment configuration (1 TX, 2 TX, SSU switching station with 0 TX, CS compact substation, Outdoor/Indoor fire extinguisher rules, etc.) without hardcoded pair lists.

## Notes

- **Target Domain**: `src/testsheet/` (Reusable Extractor & Models), `src/quick_report/` (Condition Transformer & Loader)
- **Methodology**: `docs/etl_pipeline_refactoring_methodology.md` (6-stage ETL pipeline: PreflightGuard, Extractor, Filter, Transformer, Loader, Auditor)
- **Sample Testsheets**: `C:\Users\ADAM\Documents\PO 42360565 - PAHANG - 11kV CYCLE3 - AZZAD\TESTSHEET\KUANTAN\01. AUGUST\12-08-2026`
- **Discussion Framework**:
  - Category 1: Substation Environment & Metadata (`building_type`, `substation_type`)
  - Category 2: Switchgear Equipment Package (`switchgear_type`, specs, panel_count)
  - Category 3: Transformer Equipment Package (`transformer_count`, Tx 1..4 specs, 0 TX SSU rules)
  - Category 4: LV Distribution Board / Feeder Pillar Package (`fuse_type`, LVDB1/LVDB2 specs)
  - Category 5: Auxiliary Equipment, Indicators & Fire Safety (Battery Charger, RTU, SF6, EFI, Fire Extinguisher)
- **Skills**: `/wayfinder`, `/codebase-design`, `/domain-modeling`, `/grilling`, `/tdd`

## Decisions so far

<!-- none yet -->

## Open Tickets (Frontier)

- [Ticket 082: Reusable Substation Equipment Package Domain Models](file:///.issues/082-testsheet-equipment-package-domain-models.md) — Open (Unblocked)
- [Ticket 083: Testsheet Equipment Package OpenPyXL Extractor](file:///.issues/083-testsheet-equipment-package-extractor.md) — Open (Blocked by Ticket 082)
- [Ticket 084: Dynamic Substation Condition Pairs Transformer](file:///.issues/084-dynamic-substation-condition-pairs-transformer.md) — Open (Blocked by Ticket 082, Ticket 083)
- [Ticket 085: Substation Equipment Condition E2E Verification & Test Suite](file:///.issues/085-substation-equipment-condition-e2e-verification.md) — Open (Blocked by Ticket 084)

## Not yet specified

- **Multi-Switchgear Unit Extraction**: Detailed extraction rules for substations containing 2 or more separate switchgear brand/model installations in a single PE.
- **Cross-Workflow Model Sharing**: Reusing `SubstationEquipmentPackage` in `WhatsAppReportWorkflow` and `UpdateDataMsmsWorkflow`.
- **DOCX Layout Visual Regression**: Verification of 3-pair page chunking and cell border removal for arbitrary N-pair outputs.

## Out of scope

- Direct modification of `MASTER_SUBSTATION_CONDITION.docx` Word template.
