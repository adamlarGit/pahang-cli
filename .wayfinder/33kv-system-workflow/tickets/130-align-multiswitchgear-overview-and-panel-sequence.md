<!-- status: open -->
# Ticket #130: feat(full-report): align multi-switchgear overview and panel sequence across summary census and document chunks

## Parent
Part of #90

## What to build
Implement strict multi-switchgear generation sequence prioritizing 33kV before 11kV, with separate overview documents per switchgear lineup (Option A):

- **Sequential Generation Flow**:
  - Enforce order: 33kV Switchgear Overview -> 33kV Panels -> 11kV Switchgear Overview -> 11kV Panels -> Transformers & Substation Condition.
- **Dedicated Lineup Overview Document Chunks (`src/full_report/plan_builder.py`)**:
  - Update `MultiPartPartitionPolicy._partition_multipart()` to split overview pages into dedicated per-lineup chunks rather than bundling all overviews into Chunk 1:
    - `Part 01 - Summary.docx`: Front Page, Executive Summary Census, Visual Defect Summary (without switchgear overviews).
    - `Part 02 - Switchgear 33kV Overview.docx` (e.g. `Part 02 - Switchgear 1 (33kV - <TYPE>) Overview.docx`).
    - `Part 03..10 - Switchgear 33kV Panels.docx`.
    - `Part 11 - Switchgear 11kV Overview.docx` (e.g. `Part 11 - Switchgear 2 (11kV - <TYPE>) Overview.docx`).
    - `Part 12..40 - Switchgear 11kV Panels.docx`.
    - Final Part: Transformers, LVDB, Battery, Condition, Defects, Sticker.
- **Census Summary Table Alignment (`src/full_report/census.py`)**:
  - Ensure `ExecutiveSummaryCensusBuilder` consistently orders equipment rows with 33kV switchgear and panels first, followed by 11kV switchgear and panels, followed by balance-of-plant assets.
- **Unit and End-to-End Tests**:
  - Verify document chunk partitioning, naming, and page contents on dual-switchgear substations (e.g. `CJEN/PMU/J00001`).

## Acceptance criteria
- [ ] Multi-part partitioning produces dedicated overview chunks per switchgear lineup: Part 01 Summary, 33kV Overview, 33kV Panels, 11kV Overview, 11kV Panels, and TX/Condition.
- [ ] Census summary tables order 33kV lineup before 11kV lineup.
- [ ] Document chunk indices and labels reflect Option A structure cleanly.
- [ ] All unit and plan builder tests in `tests/test_full_report_workflow.py` pass.

## Blocked by
#129
