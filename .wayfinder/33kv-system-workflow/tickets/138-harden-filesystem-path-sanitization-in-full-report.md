<!-- status: closed -->
# Ticket #138: fix(full-report): Harden filesystem path sanitization in Full Report intermediate parts and multi-part chunks

## Parent
Part of #101

## What to build
Full report intermediate part rendering and multi-part chunk document compilation must strictly sanitize all file paths against Windows-forbidden characters and ASCII control characters ([\x00-\x1f\r\n\t]). Intermediate docx files in .temp/full_report/.../rendered/ and partitioned output chunk documents must never throw OSError: [Errno 22] Invalid argument when compiling substations with complex, long, or multiline panel names (such as SSU LYNAS 33kV).

## Acceptance criteria
- [x] Intermediate scan part filename generation in plan_builder.py:render_all sanitizes all forbidden Windows characters and control characters ([\x00-\x1f\r\n\t]).
- [x] Shared sanitize_filename utility strips/replaces ASCII control characters ([\x00-\x1f\r\n\t]) in addition to existing reserved characters ([<>:"/\\|?*]).
- [x] Multi-part partition chunk labels and output filenames are sanitized against control characters and invalid filename characters.
- [x] Regression test verifies that Full Report generation compiles all intermediate parts and multi-part chunk deliverables for SSU LYNAS 33kV without [Errno 22] Invalid argument or COM compilation failures.

## Blocked by
None (can start immediately).
