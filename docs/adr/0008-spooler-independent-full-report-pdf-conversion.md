# Spooler-Independent Full Report PDF Conversion

Status: Superseded by [ADR 0009: Native Word Export with Source Image Restoration](./0009-native-export-with-source-image-restoration.md)

> **Superseded on 2026-11-01. Do not implement from this ADR.** Its investigation sequence has been run. Its first candidate (native Word export with converter-owned quality settings) was disproved, because Word has no setting that stops PDF export resampling, and the second (`PrintToFile → FileToPDF`) is no longer needed. ADR 0009 is the current decision and contains a table mapping every element below to its new status. The original text follows, unchanged, as history.

---

Full Report PDF conversion must not use Adobe PDF virtual-printer printing in production batches. Although user-interactive Adobe printing established the required thermogram fidelity, its Session 0 spooler dependency cannot meet the `PdfConversionDeliveryContract`; native Word export is the first candidate and any future Distiller approach must first prove an isolated, spooler-independent end-to-end batch path with source-pixel preservation for every thermogram in reports `101`, `102`, and one normal report. The converter owns and restores any Word or Office quality settings it requires, so its result is reproducible without changing the operator's normal Word profile. Native Word export is evaluated first through a one-off read-only fidelity probe; direct Session 1 `PrintToFile → FileToPDF` is evaluated only if it fails. Until that path is validated, the existing native fallback remains for operational continuity and is explicitly not a high-fidelity claim; the CLI notifies the operator when it is used, without persisting a separate deliverable classification.
