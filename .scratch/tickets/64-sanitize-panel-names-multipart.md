<!-- status: closed -->
# 64: fix(full-report): sanitize panel names in MultiPartPartitionPolicy chunk destination paths

**What to build:**
Sanitize switchgear panel names when constructing chunk filenames and destination paths in `MultiPartPartitionPolicy` (`src/full_report/plan_builder.py`).

In VCB switchgear lineups, panels can have names containing slashes or path-unsafe characters, such as `B/S` (Bus Section). Because `panel_name` was not sanitized before formatting `output_filename = f"{stem} - {label}.docx"`, Python `Path` interpreted `/` as a path separator, creating an unintended nested directory `... Panel 6 (B` containing `S).docx`.

Sanitize `panel_name` using `sanitize_filename()` (or replacing invalid path characters `/` and `\` with `-`) so that chunk files are always created as flat files in the target directory.

**Blocked by:** None (can start immediately)

**Status:** closed

- [x] In `src/full_report/plan_builder.py` (`MultiPartPartitionPolicy._partition_vcb_gis`), `panel_name` is sanitized using `sanitize_filename` or replacing path separators before constructing `label`, `output_filename`, and `destination_path`.
- [x] For panel names with slashes like `B/S`, the resulting chunk filename is flat (e.g. `... - Part 07 - Panel 6 (B-S).docx`) and `destination_path.parent` resolves strictly to `dest_dir`.
- [x] Unit tests in `tests/unit/test_multipart_partition_policy.py` assert that panels with `/`, `\`, and other path characters produce flat filenames without creating subdirectories.
- [x] Full test suite passes.
