# Ticket #183 console verification

## Operator hand check

The operator ran the 8 checks by hand in a real PowerShell console, through the real `pahang-cli` menus, using a throwaway project. All 8 passed at commit `93bf5df`. See the [result on #183](https://github.com/adamlarGit/pahang-cli/issues/183#issuecomment-6708337908).

`93bf5df` was later rebased, so it isn't in this branch's history. Its rebased form is `89afbf0`.

The commits after `89afbf0` weren't hand-checked. They change what's recorded, how a Run's status is decided, and how folders are listed for the record. They don't change prompts, `input()`, or how `sys.stdout` and logging are captured: `src/workflow_cli.py`, `src/cli_selectors.py`, `src/cli_menu.py` and the capture classes in `src/run_records.py` are the same as at `89afbf0`.

## Scripted console check

Before that, a script drove real `questionary` prompts and `input()` through a Windows pseudo-console (ConPTY), using the production `_run_recorded_action` wrapper. This was automated, not a hand check, and doesn't replace one. It saw normal prompt rendering, the failure message followed by the Run Record path, and a record with a full traceback and no prompt drawing codes.

## Automated tests

Run Record behaviour is covered by `tests/test_run_records.py`. See `docs/agents/testing.md` for how to run tests.
