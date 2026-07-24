# Changelog

All notable changes to Pahang CLI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-07-24

### Added
- Interactive date folder selector (`src/cli_selectors.py`) for Pahang 3-tier inspection folders.
- Deep module for testsheet parsing (`src/testsheet/`) including models, extractor, and repository.
- Workflow `Populate TOTAL PE` (`src/populate_total_pe_workflow.py`) scanning `TESTSHEET/` and upserting `TOTAL PE.xlsx` (`DataCycle1`).
- Workflow `Raw Material Creation & Sorting` (`src/raw_material_workflow.py`) for automated folder provisioning and `IR`/`DG` photo sorting.
- Comprehensive unit and integration test suite (`tests/`).
