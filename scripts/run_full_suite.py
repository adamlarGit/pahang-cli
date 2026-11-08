"""Run and record a Full Run (parallel Fast Run tests, then word and live_data tests serially) or a Fast Run."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import msvcrt
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PASSED, FAILED, INCOMPLETE = 0, 1, 10
PYTEST_NO_TESTS_COLLECTED = 5
GROUPED_RUNS_KEPT = 200
_UNKNOWN = "unknown"
# Untracked files of these types can change what a run executes; notes and documents cannot.
_EXECUTION_INPUT_SUFFIXES = {
    ".bat", ".cfg", ".cmd", ".ini", ".json", ".lock", ".ps1", ".py", ".pyd", ".pyi", ".toml", ".yaml", ".yml",
}
_OFFICE_PROCESSES = {"winword.exe", "excel.exe"}
_DEFAULT_LOCK_FILE = Path(tempfile.gettempdir()) / "pahang-cli-full-run.lock"
_RESULT_NAMES = {PASSED: "PASSED", FAILED: "FAILED", INCOMPLETE: "INCOMPLETE"}


@dataclass
class Findings:
    """Reasons a run cannot pass. Any failure outranks any incompleteness."""

    failed: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)

    def exit_code(self) -> int:
        if self.failed:
            return FAILED
        return INCOMPLETE if self.incomplete else PASSED


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO, help="folder to run pytest in")
    parser.add_argument("--workers", default="4", help="xdist worker count for the Fast Run phase")
    parser.add_argument("--results-dir", type=Path, default=REPO / ".test-results")
    parser.add_argument("--lock-file", type=Path, default=_DEFAULT_LOCK_FILE)
    parser.add_argument("--fast-only", action="store_true", help="record a Fast Run, without the serial phase")
    return parser.parse_args(argv)


def _git(root: Path, *arguments: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", *arguments], cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _tool_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return _UNKNOWN


def _run_start(args: argparse.Namespace, run_id: str, kind: str) -> dict:
    """What identifies this run's code and environment, written before any test runs."""
    status = _git(args.root, "status", "--porcelain", "--untracked-files=no")
    untracked_output = _git(args.root, "ls-files", "--others", "--exclude-standard", "-z")
    untracked = [path for path in (untracked_output or "").split("\0") if path]
    lock = args.root / "uv.lock"
    return {
        "event": "run_start",
        "run_id": run_id,
        "phase": "",
        "started_at": time.time(),
        "kind": kind,
        "git_sha": (_git(args.root, "rev-parse", "HEAD") or _UNKNOWN).strip(),
        # None means the state is unknown, which the report treats like a dirty worktree.
        "tracked_dirty": None if status is None else bool(status.strip()),
        "untracked_count": len(untracked),
        "untracked_execution_inputs": sorted(p for p in untracked if Path(p).suffix.lower() in _EXECUTION_INPUT_SUFFIXES),
        "identity": {
            "machine": platform.node(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "pytest": _tool_version("pytest"),
            "xdist": _tool_version("pytest-xdist"),
            "uv_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else _UNKNOWN,
            "workers": args.workers,
        },
    }


def _append_event(results: Path, event: dict) -> None:
    with results.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event) + "\n")


def _prune_history(folder: Path) -> None:
    """Keep the newest grouped runs. Each run is one file, however many phases it had."""
    runs = [path for path in folder.glob("*.jsonl") if re.fullmatch(r"[0-9a-f]{32}", path.stem)]
    runs.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    for path in runs[GROUPED_RUNS_KEPT:]:
        try:
            path.unlink()
        except OSError as error:
            print(f"could not remove old test history {path}: {error}")


def _run_phase(
    args: argparse.Namespace, name: str, run_id: str, git_sha: str, results: Path, selection: list[str]
) -> int:
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(REPO), os.environ.get("PYTHONPATH")])))
    # Inherited options could silently narrow what a merge-gate run selects.
    env.pop("PYTEST_ADDOPTS", None)
    command = [
        sys.executable, "-m", "pytest",
        "-p", "tests.results_plugin",
        f"--results-file={results}",
        f"--grouped-run-id={run_id}",
        f"--run-phase={name}",
        f"--git-sha={git_sha}",
        *selection,
    ]
    return subprocess.run(command, cwd=args.root, env=env).returncode


@contextmanager
def full_run_lock(path: Path) -> Iterator[bool]:
    """Hold the machine-wide Full Run lock, yielding whether it was acquired.

    Windows releases the byte lock if the process dies, so a crash cannot leave it stuck.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _list_windows_processes() -> list[str]:
    output = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=True, timeout=60
    ).stdout
    return [row[0] for row in csv.reader(output.splitlines()) if row]


def _serial_blockers(lock_acquired: bool, list_processes: Callable[[], list[str]]) -> list[str]:
    """Reasons the serial phase must not start. Checking this never starts Office."""
    blockers = [] if lock_acquired else ["another Full Run holds the machine-wide lock"]
    try:
        open_office = [name for name in list_processes() if name.lower() in _OFFICE_PROCESSES]
    except (OSError, subprocess.SubprocessError) as error:
        return [*blockers, f"could not check for open Word or Excel: {error}"]
    return [*blockers, *(f"{name} is already open; close it first" for name in open_office)]


class ProtectedInputs:
    """Inputs tests must not change: repo benchmarks by hash, external folders by size and time."""

    def __init__(self, root: Path, findings: Findings) -> None:
        self._benchmarks = root / "tests" / "benchmarks"
        self._external_folders = self._configured_folders(root / ".cli_config.json", findings)

    @staticmethod
    def _configured_folders(config: Path, findings: Findings) -> list[Path]:
        folders = []
        if override := os.environ.get("PAHANG_BENCHMARK_ROOT"):
            folders.append(Path(override))
        # Without a config, live-data tests skip, which already makes the run incomplete.
        if config.exists():
            try:
                projects = json.loads(config.read_text(encoding="utf-8"))["projects"]
                folders += [Path(project["base_path"]) for project in projects.values() if project.get("base_path")]
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                findings.incomplete.append(f"could not read protected folders from {config}: {error!r}")
        for folder in folders:
            if not folder.is_dir():
                findings.incomplete.append(f"protected folder is missing: {folder}")
        return [folder for folder in folders if folder.is_dir()]

    def fingerprint(self, findings: Findings) -> dict[str, object]:
        result: dict[str, object] = {}
        try:
            if self._benchmarks.is_dir():
                for path in _files_under(self._benchmarks):
                    result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in self._external_folders:
                for path in _files_under(folder):
                    info = path.stat()
                    result[str(path)] = (info.st_size, info.st_mtime_ns)
        except OSError as error:
            findings.incomplete.append(f"could not check protected inputs: {error}")
        return result


def _raise(error: OSError) -> None:
    raise error


def _files_under(folder: Path) -> Iterator[Path]:
    # Word creates ~$ owner files beside any document it opens and removes them itself.
    for directory, _, names in os.walk(folder, onerror=_raise):
        for name in names:
            if not name.startswith("~$"):
                yield Path(directory) / name


def _judge_protected(before: dict[str, object], after: dict[str, object], findings: Findings) -> None:
    for path in sorted(before.keys() | after.keys()):
        if before.get(path) != after.get(path):
            findings.failed.append(f"protected input changed: {path}")


def _read_results(results: Path, findings: Findings) -> tuple[list[dict], list[dict]]:
    """Return per-test records and phase-end records, tolerating an incomplete last line."""
    records: list[dict] = []
    phase_ends: list[dict] = []
    if not results.exists():
        return records, phase_ends
    for line in results.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            findings.incomplete.append("results file has an unreadable line")
            continue
        if "test_id" in entry:
            records.append(entry)
        elif entry.get("event") == "phase_end":
            phase_ends.append(entry)
    return records, phase_ends


def _judge_reconciliation(phases: list[str], records: list[dict], phase_ends: list[dict], findings: Findings) -> None:
    """A phase counts only if it finished recording and recorded every test it collected."""
    collected = {end["phase"]: end["collected"] for end in phase_ends}
    for phase in phases:
        if phase not in collected:
            findings.incomplete.append(f"{phase} phase did not finish recording its results")
            continue
        recorded = sum(1 for r in records if r["phase"] == phase and not r.get("collection"))
        if recorded != collected[phase]:
            findings.incomplete.append(f"{phase} phase collected {collected[phase]} tests but recorded {recorded}")


def _judge_phase(name: str, code: int, findings: Findings) -> None:
    if code == PYTEST_NO_TESTS_COLLECTED:
        findings.incomplete.append(f"{name} phase collected no tests")
    elif code != 0:
        findings.failed.append(f"{name} phase exited with code {code}")


def _judge_records(records: list[dict], findings: Findings) -> None:
    seen = Counter(record["test_id"] for record in records)
    for test_id, times in seen.items():
        if times > 1:
            findings.incomplete.append(f"{test_id} ran {times} times")
    for record in records:
        if record["outcome"] == "interrupted":
            findings.incomplete.append(f"test did not finish: {record['test_id']}")
        if record["phase"] == "serial" and record["outcome"] == "skipped" and "optional_reason" not in record:
            findings.incomplete.append(f"required check skipped: {record['test_id']}: {record['reason']}")


def _print_summary(title: str, run_id: str, records: list[dict], findings: Findings, code: int) -> None:
    counts = Counter(record["outcome"] for record in records)
    executed = sum(counts[outcome] for outcome in ("passed", "failed", "xfailed", "xpassed"))
    print(f"\n=== {title} {run_id} ===")
    print(
        f"executed={executed} passed={counts['passed']} failed={counts['failed']} "
        f"skipped={counts['skipped']} xfailed={counts['xfailed']} xpassed={counts['xpassed']}"
    )
    for record in records:
        name = record["test_id"].split("::", 1)[-1]
        if record["outcome"] == "xfailed":
            print(f"allowance: {name}: {record['reason']}")
        elif record["outcome"] == "xpassed":
            print(f"unexpected pass: {name}: review its xfail marker")
        elif record["outcome"] == "skipped" and "optional_reason" in record:
            print(f"optional skip: {name}: {record['optional_reason']}")
    for reason in findings.failed:
        print(f"failed: {reason}")
    for reason in findings.incomplete:
        print(f"incomplete: {reason}")
    print(f"RESULT: {_RESULT_NAMES[code]}", flush=True)


def main(
    argv: list[str] | None = None,
    *,
    list_processes: Callable[[], list[str]] | None = None,
    clock: Callable[[], float] | None = None,
) -> int:
    clock = clock or time.perf_counter
    run_began = clock()
    args = _parse_args(argv)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    results = args.results_dir / f"{run_id}.jsonl"
    findings = Findings()
    start = _run_start(args, run_id, "fast" if args.fast_only else "full")
    _append_event(results, start)
    phase_wall_seconds: dict[str, float] = {}

    def run_phase(name: str, selection: list[str]) -> None:
        began = clock()
        code = _run_phase(args, name, run_id, start["git_sha"], results, selection)
        # Measured directly: summed test durations are not elapsed time under xdist.
        phase_wall_seconds[name] = clock() - began
        _judge_phase(name, code, findings)

    protected = ProtectedInputs(args.root, findings)
    before = protected.fingerprint(findings)

    run_phase("fast", ["-n", args.workers])
    if not args.fast_only:
        with full_run_lock(args.lock_file) as acquired:
            blockers = _serial_blockers(acquired, list_processes or _list_windows_processes)
            if blockers:
                findings.incomplete.extend(f"serial phase not run: {blocker}" for blocker in blockers)
            else:
                run_phase("serial", ["-m", "word or live_data"])

    _judge_protected(before, protected.fingerprint(findings), findings)
    records, phase_ends = _read_results(results, findings)
    _judge_reconciliation(list(phase_wall_seconds), records, phase_ends, findings)
    _judge_records(records, findings)
    code = findings.exit_code()
    _print_summary("Fast Run" if args.fast_only else "Full Run", run_id, records, findings, code)
    selected = sorted(record["test_id"] for record in records if not record.get("collection"))
    _append_event(results, {
        "event": "run_end",
        "run_id": run_id,
        "phase": "",
        "result": _RESULT_NAMES[code],
        "failed": findings.failed,
        "incomplete": findings.incomplete,
        "wall_seconds": clock() - run_began,
        "phase_wall_seconds": phase_wall_seconds,
        "selected_count": len(selected),
        "selected_tests_sha256": hashlib.sha256("\n".join(selected).encode("utf-8")).hexdigest(),
    })
    _prune_history(args.results_dir)
    return code


if __name__ == "__main__":
    sys.exit(main())
