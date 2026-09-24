<!-- status: closed -->
# 63: fix(compiler): resilient copy-paste handshake with re-copy on COM error 4605 across compiler and slicer

**What to build:**
Eliminate Word COM Error 4605 (`wdErrClipboardEmptyOrInvalid` / 'This method or property is not available because the Clipboard is empty or not valid') caused by transient OS clipboard contention or delayed rendering in both Quick Report and Full Report compilation and slicing.

Currently, if `part_doc.Content.Copy()` or `Range.Copy()` fails to acquire the Windows clipboard due to a momentary clipboard lock by an external process or user action, the clipboard remains empty from the preceding `_clear_clipboard()`. `_paste_with_retry` then retries `PasteAndFormat(16)` 5 times without re-copying, and raises an unhandled COM exception. Because the outer retry loop lacks exception handling around `_paste_with_retry`, it immediately aborts without re-copying.

Wrap paste in a robust retry handshake that catches COM exceptions, applies backoff, zeroes the clipboard, and explicitly re-copies from the source document before re-attempting paste across `src/quick_report/compiler.py` and `src/full_report/slicer.py`.

**Blocked by:** None (can start immediately)

**Status:** closed

- [x] In `src/quick_report/compiler.py` (`WordComDocumentCompiler.compile`), paste is wrapped in exception handling such that if `_paste_with_retry` raises COM error 4605 or a paste exception, the outer loop catches it, logs a warning, applies a backoff sleep (e.g. 0.25s), zeroes clipboard, and re-executes `part_doc.Content.Copy()`.
- [x] In `src/full_report/slicer.py` (`_slice_range_to_doc`), paste is wrapped in similar exception handling so that any COM paste failure catches, backs off, zeroes clipboard, and re-executes `rng.Copy()`.
- [x] Comprehensive unit tests in `tests/unit/test_compiler_clipboard_resilience.py` simulate transient COM error 4605 on first paste attempts and assert that re-copy and paste succeed cleanly.
- [x] Full existing test suite continues to pass.
