# Running tests

**Fast Run**, the default during development. It skips tests marked `word` or `live_data`:

```
uv run --frozen --with pytest==9.2.0 --with pytest-xdist==3.8.0 pytest
```

**Full Run**, required before merging into the Integration Branch. It runs every test:

```
uv run --frozen --with pytest==9.2.0 --with pytest-xdist==3.8.0 pytest --override-ini=addopts=
```

A Full Run starts real Word and reads live project folders. Close Word and Excel first, because #176 suggests these runs can close an open Word window. It needs `.cli_config.json` and `.active_project.json`; without them, some live-data tests skip.

## Running part of a tier

Add these after `pytest` in the commands above.

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

A guard in `tests/tier_guard.py` fails a test without the `word` marker that reaches Word or Excel through pywin32: `Dispatch`, `DispatchEx`, `GetActiveObject`, or `GetObject` on an Office file (including CSV files, workbook item monikers, and Office CLSID monikers). CSV activation is guarded conservatively because its registered handler can be Excel. It applies to Fast and Full Runs, and a skip, an xfail or `except Exception` can't hide the failure.

The guard also blocks direct Word/Excel launches through `subprocess` and Office files opened through `os.startfile`. It leaves other programs and non-Office files alone.

The guard runs inside pytest's Python process. It can't see `subprocess` calls with `shell=True`, because it doesn't parse shell strings, or what a child program or shell script later launches. Tests that start Office those ways still need the `word` marker. It is a test guard, not a process sandbox.

## Client folders

Tests may read live project folders, and must write only to `tmp_path`. Live-data tests that call a workflow need a temporary output location or a temporary copy of their inputs, because workflows write under the project base path by default.
