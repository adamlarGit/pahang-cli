# Ticket #183 verification

Branch: `ticket/183-run-records`. Specification: https://github.com/adamlarGit/pahang-cli/issues/183.

## Interactive console check - 2026-11-07

Passed by manually interacting through an allocated Windows ConPTY console (`stdin.isatty()` and `stdout.isatty()` both true), using real questionary prompts and the production `_run_recorded_action` wrapper. No mocked input or prompt output.

1. Opened a selection prompt before the Run, matching the real CLI's initial menu.
2. During the Run, entered `07-11-2026` into a text prompt.
3. Used the checkbox toggle-all key to select `PE ONE` and `PE TWO`, then accepted.
4. Entered `checked` through plain `input()`.
5. Observed normal prompt rendering and the expected progress and warning lines.
6. Raised an expected `ValueError`; the console showed the normal failure message followed by the Run Record path.
7. Read the temporary JSONL record: status `failed`, progress and full traceback present, and no ANSI prompt drawing codes.

Console result: `CONSOLE CHECK PASSED`. All records were written beneath a temporary `pahang-183-console-*` directory; no Office application or real project data was used.

## Automated validation

- Run Record behavior: 194 tests passed after resolving review findings.
- Recorder and affected workflow/CLI regression files: 358 passed; additional Full Report, multipart, and COM-session regression files: 40 passed.
- Recorder, action wrapper, and project selection module: pyright reports zero errors.
- Compared all edited source modules with pre-ticket commit `dc10cd3` using pyright: 48 existing errors before, 43 after, and zero new diagnostics. Recorder, action wrapper, and project selection module pass independently.
- Reproduced all three non-live baseline failures against `dc10cd3`: whitespace normalization, `TX1` versus `TX 1`, and stale chamber-keyword tuple expectations.
- Full-suite result: 2,257 passed, 10 failed, 6 skipped, 3 XPASS in 12m31s. Nine failures are existing live-data or stale assertion expectations; the tenth is an unchanged Git-state helper decoding a dirty UTF-8 diff with Windows cp1252. The Git-state test passes with PYTHONUTF8=1. No ticket-related failure remains.

## Review

Standards: no documented-standard or ADR violations. One low-priority maintainability observation remains: Raw Material derives its all-unreadable status from a shared warning prefix.

Spec: resolved missing production Step timing, missing input metadata, and unwanted Settings activation-failure records. Added action-layer regressions for these behaviors.
