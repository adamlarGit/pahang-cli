# 4. Unconditional Transformer HV Cable Split Generation Policy

Date: 2026-09-09
Status: Accepted

## Context

In distribution substation condition-based assessments, transformers may undergo thermal inspection of their High Voltage (HV) terminations, which can include both the primary HV Cable terminations and secondary HV Cable Split configurations depending on the cable box and termination physical structure.

In field deliverables, certain substations (such as Talapia, PE 5) include a dedicated `HV CABLE SPLIT` row in Executive Summary Table 2 and a dedicated 4-quadrant scanning page (`tx-hv-sides.docx`), while other substations (such as Cenderawasih No. 1 and Telekom Tanah Putih) document only `HV CABLE` and `HV BUSHING`.

Currently, legacy and active `PCE Testsheet` Excel workbooks do not maintain an authoritative checkbox, cell coordinate, or structured metadata field explicitly designating whether an inspected transformer features an HV Cable Split. In manual report authoring, the diagnostic engineer manually retained or trimmed the HV Cable Split section from the master template based on personal site knowledge.

An automated generation pipeline requires deterministic behavior. Guessing whether a cable split exists based on informal photo count bounds or row parsing heuristics risks false negatives, which could omit required contractual inspection deliverables.

## Decision

The Full Report automated generator adopts an **unconditional generation policy** for Transformer HV Cable Split:

1. **Deterministic 7-Point Scanning Sequence**:
   For every testable distribution transformer (`TransformerSpec`), the generator will always provision a 7-point scanning layout:
   - Page 1: `OVERVIEW` (`tx-overview.docx`)
   - Page 2: `OVERVIEW TOP` (`tx-overview.docx`)
   - Page 3: `HV BUSHING` (`tx-hv-sides.docx`)
   - Page 4: `HV CABLE` (`tx-hv-sides.docx`)
   - Page 5: `HV CABLE SPLIT` (`tx-hv-sides.docx`)
   - Page 6: `LV BUSHING` (`tx-lv-sides.docx`)
   - Page 7: `LV CABLE` (`tx-lv-sides.docx`)

2. **Executive Summary Census Alignment**:
   Executive Summary Table 2 will always include both `HV CABLES` and `CABLE SPLIT` rows for each transformer under normal operation via the domain predicate stub `has_hv_cable_split(tx) -> True`.

3. **Safe Missing-Asset Fallback**:
   If an inspection run does not capture an explicit second thermal image for cable split, `RawPhotoResolver` safely resolves the placeholder to an empty string (`""`), rendering a pristine unpopulated image quadrant without crashing or corrupting Word document structure.

## Consequences

### Positive
- **Guaranteed Contractual Completeness**: Guarantees that substations requiring HV Cable Split inspection never omit this deliverable due to automation misclassification.
- **Uniform Document Structure**: Every transformer across all stations follows an identical, predictable 7-page structure.
- **Inspector Review Seam**: Stage 1 outputs an editable Word document (`.docx`), allowing diagnostic engineers during their qualitative review to either populate the split photo or delete the page before Stage 2 post-processing.

### Negative and Future Evolution
- Substations that do not have an HV Cable Split installation will include an unpopulated Cable Split page and census row by default unless manually trimmed by the engineer.
- **Future Direction**: When a future revision of `PCE Testsheet` (or TNB digital testsheet schema) introduces an authoritative cell coordinate or structured checkbox for Cable Split, `has_hv_cable_split` will be updated to read directly from that domain seam.
