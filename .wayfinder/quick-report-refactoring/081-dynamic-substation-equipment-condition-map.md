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

- [Ticket 082: Reusable Substation Equipment Package Domain Models](082-testsheet-equipment-package-domain-models.md) — Defined immutable `SubstationEquipmentPackage`, `SwitchgearSpec` with `SwitchgearPanelSpec` (SCADA `panel_feeder_no`, `status`, `load_amp`, `heater_amp`), `TransformerSpec` (`type`), `LVDBSpec` (`label`, `source`), `BatteryBankSpec`, and `FireExtinguisherSpec`.
- [Ticket 083: Testsheet Equipment Package OpenPyXL Extractor](083-testsheet-equipment-package-extractor.md) — Specified 6 single-responsibility extractor methods in `TestsheetExtractor`: switchgear & panels across rollovers, authoritative `C17` Tx extraction, LVDB active detection via `S49`/`S53` IR photo cells, multi-battery scan (rows 59–65), fire extinguisher building guard & expiry date, and missing value representation policy (`""` in models, `"-"` in documents).
- [Ticket 084: Dynamic Substation Condition Pairs Transformer](084-dynamic-substation-condition-pairs-transformer.md) — Specified dynamic stream-packing 2-column condition pair builder algorithm: singular naming for single equipment (`SWITCHGEAR`, `TRANSFORMER`), multi-equipment indexing (`1..N`), stream-zipping of indicators (`EFI`, `SF6 INDICATOR`, `OIL LEVEL INDICATOR`), fire extinguisher inclusion for `INDOOR`/`ATTACH` and omission for `OUTDOOR`/`COMPACT`, and half-pair border stripping.

## Open Tickets (Frontier)

- [Ticket 085: Substation Equipment Condition E2E Verification & Test Suite](085-substation-equipment-condition-e2e-verification.md) — Open (Unblocked)


## Not yet specified

- **Multi-Switchgear Unit Extraction**: Detailed extraction rules for substations containing 2 or more separate switchgear brand/model installations in a single PE.
- **Cross-Workflow Model Sharing**: Reusing `SubstationEquipmentPackage` in `WhatsAppReportWorkflow` and `UpdateDataMsmsWorkflow`.
- **DOCX Layout Visual Regression**: Verification of 3-pair page chunking and cell border removal for arbitrary N-pair outputs.

## Out of scope

- Direct modification of `MASTER_SUBSTATION_CONDITION.docx` Word template.
