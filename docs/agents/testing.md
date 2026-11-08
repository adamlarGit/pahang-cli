# Running tests

**Fast Run**, the default during development. It skips tests marked `word` or `live_data` and runs in parallel. Set the worker count with `-n` and keep it the same when comparing timings:

```
uv run --frozen --with pytest==9.2.0 --with pytest-xdist==3.8.0 pytest -n 4
```

Plain `pytest` selects the same tests serially and doesn't need xdist.

**Full Run**, required before merging into the Integration Branch. It runs the Fast Run tests in parallel, then every `word` or `live_data` test serially. Both phases run even if the first fails:

```
uv run --frozen --with pytest==9.2.0 --with pytest-xdist==3.8.0 python -m scripts.run_full_suite --workers 4
```

A Full Run starts real Word and reads live project folders. Close Word and Excel first, because #176 suggests these runs can close an open Word window. It needs `.cli_config.json` and `.active_project.json`; without them, some live-data tests skip. The merge gate is defined for the one machine that holds the benchmark data.

| Exit code | Result | Meaning |
| --- | --- | --- |
| 0 | Passed | Every required check ran. Diagnosed allowances are listed by name and reason. |
| 1 | Failed | A test or phase failed, pytest crashed or errored, or a protected input changed. |
| 10 | Incomplete | A required check can't be confirmed: a serial test or test module skipped, a phase collected no tests or didn't finish recording, the serial phase was blocked, or protected inputs couldn't be checked. |

The serial phase is blocked, without starting Office, if Word or Excel is open or another Full Run holds the machine-wide lock. This does not resolve #176.

Every serial test is required by default. A skip makes the run incomplete unless the test has `@pytest.mark.optional("why this check is optional")`.

The runner checks that protected inputs did not change: `tests/benchmarks` by SHA-256, and the project folders in `.cli_config.json` by path, size and modified time. Results are saved per test in the gitignored `.test-results/` folder.

## Timing history

Bare `pytest` records nothing, so partial runs can't enter the history. To record a Fast Run:

```
uv run --frozen --with pytest==9.2.0 --with pytest-xdist==3.8.0 python -m scripts.run_full_suite --fast-only --workers 4
```

Then report the newest run, or pick one with `--kind fast`, `--kind full` or `--run-id <id>`:

```
uv run --frozen --with pytest==9.2.0 --with pytest-xdist==3.8.0 python -m scripts.timing_report
```

The history is the gitignored `.test-results/` folder, one file per grouped run. Both phases of a Full Run share one file and one run ID and count as one run. The runner keeps the newest 200 runs.

Each file has `run_start` metadata, per-test records, and `run_end` with the result and wall times. Total and per-phase wall times are measured elapsed time; summed test durations are not, because xdist runs tests at once. A test's time is setup + call + teardown.

**Baseline runs** finished with result Passed, on known code and packages, with no staged or unstaged tracked changes and no untracked code or config files (such as `.py`, `.toml` or `.json`). Untracked notes are counted but don't disqualify a run. A run with tracked changes is compared and labelled but never becomes a baseline. A Failed, Incomplete or unfinished run stays visible with its outcomes and isn't compared.

**Comparable runs** are the same kind (Fast or Full) with the same machine, platform, CPU count, Python, pytest and xdist versions, `uv.lock` hash and worker count.

- **Total time** also needs the same selected tests and the same tests executed; otherwise it is labelled not compared.
- **A single test** is compared with earlier comparable runs where it had the same ID, tier and outcome. Only `passed` and `xfailed` tests are timed, so a skip or failure can't look like a speed-up. If the rest of the suite differed, the report warns that shared fixtures and worker contention may affect the timing.

A regression needs at least 3 earlier samples (the newest 10 are used), and must exceed the median by more than the observed range and by more than 0.5 s and 30% for a test, or 5 s and 10% for the total. The report shows median, range and sample count, and counts earlier runs it left out by reason.

Strict unexpected passes are recorded as `xpassed` with `strict: true`, and still fail the run. A test cut off before teardown is recorded as `interrupted` and makes the run incomplete.

## Running part of a tier

Add these after `pytest` in the Fast Run command. The Full Run runner doesn't accept test selections.

- One tier: `-m word` or `-m live_data`.
- One marked test: `--override-ini=addopts= tests/test_file.py::test_name`.

Selection has two traps:

- Any `-m` you pass replaces the default one, so `-m "not slow"` also selects `word` and `live_data` tests.
- A node ID alone keeps the default `-m`, so a marked test is deselected and nothing runs.

## Why `uv run --frozen --with`

These commands run on the locked packages and bring in pinned test tools for that run only. `uv.lock` stays unchanged and pytest stays out of `.venv`.

Keep test tools out of dependency groups. Past `start_cli.bat` update failures have been attributed to `uv.lock`: `git pull` can fail if a colleague's lock has local changes and the incoming commit changes it too. `uv sync` also installs a group named `dev` by default, which would put test tools on colleagues' machines.

## Markers

- `word`: the test starts real Word or Excel.
- `live_data`: the test reads a real project folder, directly or through `.cli_config.json` or the active project.

A test that does both gets both markers.

- `optional(reason)`: a skip of this serial-phase test doesn't make a Full Run incomplete.

A guard in `tests/tier_guard.py` fails a test without the `word` marker that reaches Word or Excel through pywin32: `Dispatch`, `DispatchEx`, `GetActiveObject`, or `GetObject` on an Office file (including CSV files, workbook item monikers, and Office CLSID monikers). CSV activation is guarded conservatively because its registered handler can be Excel. It applies to Fast and Full Runs, and a skip, an xfail or `except Exception` can't hide the failure.

The guard also blocks Word and Excel launched through `subprocess`, as list commands or quoted paths, and Office files opened through `os.startfile`.

It is a safety net for the routes this repo uses, not a sandbox:

- **Not caught:** an unquoted path containing spaces in a `subprocess` string, such as `C:\Program Files\...\WINWORD.EXE`, and some unusual moniker forms.
- **Not covered:** `shell=True`, `os.system`, `os.spawn*`, `os.exec*`, `win32api.ShellExecute`, `win32process.CreateProcess`, and child programs or scripts. A search found none of these starting Office in `src`, `tests` or `scripts` today. A test that starts Office these ways still needs the `word` marker.
- **False positives:** `os.startfile` on a folder named like Office (such as `excel` or `Winword`) is blocked, and `GetObject` treats any name starting `word.` or `excel.` as Office.

## Expected failures

`xfail_strict` is on, so an `xfail` marker on a test that passes fails the run and gets reviewed.

Don't use a plain `xfail` marker for a change in live data, because it excuses every failure in the test. After diagnosing the change, call `xfail_while_data_condition` from `tests/live_data_allowance.py` immediately before the affected assertion, with a `detected` value that inspects the data. Give the condition, evidence and removal condition.

## Client folders

Tests may read live project folders, and must write only to `tmp_path`. Live-data tests that call a workflow need a temporary output location or a temporary copy of their inputs, because workflows write under the project base path by default.
