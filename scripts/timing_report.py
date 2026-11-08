"""Report the slowest tests and timing regressions from the local test history."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MINIMUM_EARLIER_RUNS = 3
RECENT_RUNS_COMPARED = 10
# A difference counts only if it exceeds the floor, the fraction of the median and the observed range.
TEST_FLOOR_SECONDS, TEST_FRACTION = 0.5, 0.30
TOTAL_FLOOR_SECONDS, TOTAL_FRACTION = 5.0, 0.10
_TIMED_OUTCOMES = {"passed", "xfailed"}
_EXECUTED_OUTCOMES = {"passed", "failed", "xfailed", "xpassed"}
_IDENTITY_FIELDS = ("machine", "platform", "cpu_count", "python", "pytest", "xdist", "uv_lock_sha256", "workers")


@dataclass
class Run:
    path: Path
    start: dict | None = None
    end: dict | None = None
    tests: list[dict] = field(default_factory=list)

    @property
    def order(self) -> float:
        return self.start["started_at"] if self.start else self.path.stat().st_mtime

    @property
    def result(self) -> str:
        return self.end["result"] if self.end else "did not finish"

    @property
    def selected(self) -> frozenset[str]:
        return frozenset(test["test_id"] for test in self.tests)

    @property
    def timed(self) -> frozenset[str]:
        return frozenset(test["test_id"] for test in self.tests if test["outcome"] in _TIMED_OUTCOMES)

    def not_comparable_reason(self) -> str | None:
        """Why this run's timing cannot be judged at all."""
        if self.start is None:
            return "no run metadata"
        if self.end is None:
            return "did not finish"
        if self.result != "PASSED":
            return f"result {self.result}"
        return None

    def baseline_rejections(self) -> list[str]:
        """Why this run cannot serve as a baseline for later runs; empty if it can."""
        if reason := self.not_comparable_reason():
            return [reason]
        reasons = []
        if self.start["tracked_dirty"] is not False:
            reasons.append("tracked changes")
        if self.start["untracked_execution_inputs"]:
            reasons.append("untracked execution inputs")
        if self.start["git_sha"] == "unknown" or self.start["identity"]["uv_lock_sha256"] == "unknown":
            reasons.append("unknown code or package identity")
        return reasons


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=REPO / ".test-results")
    parser.add_argument("--kind", choices=("fast", "full"), help="report the newest run of this kind")
    parser.add_argument("--run-id", help="report this run instead of the newest")
    parser.add_argument("--top", type=int, default=20, help="how many of the slowest tests to list")
    return parser.parse_args(argv)


def _load_run(path: Path) -> Run:
    run = Run(path)
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue  # An interrupted run can leave a partial last line.
        if entry.get("event") == "run_start":
            run.start = entry
        elif entry.get("event") == "run_end":
            run.end = entry
        elif "test_id" in entry and not entry.get("collection"):
            run.tests.append(entry)
    return run


def _load_history(folder: Path) -> list[Run]:
    return sorted((_load_run(path) for path in folder.glob("*.jsonl")), key=lambda run: run.order) if folder.is_dir() else []


def _seconds(test: dict) -> float:
    return sum(test["durations"].values())


def _usable_earlier_runs(current: Run, history: list[Run]) -> tuple[list[Run], Counter[str]]:
    """Baseline runs equivalent to current, newest first, and why the others were left out."""
    usable, rejected = [], Counter()
    for run in reversed(history):
        if run.order >= current.order or run is current:
            continue
        if run.start is not None and run.start["kind"] != current.start["kind"]:
            continue
        reasons = run.baseline_rejections()
        if not reasons:
            reasons = [
                f"different {name}"
                for name in _IDENTITY_FIELDS
                if run.start["identity"].get(name) != current.start["identity"].get(name)
            ]
        if reasons:
            rejected["; ".join(reasons)] += 1
        else:
            usable.append(run)
    return usable, rejected


def _is_slower(value: float, samples: list[float], floor: float, fraction: float) -> bool:
    middle = statistics.median(samples)
    return value - middle > max(floor, fraction * middle, max(samples) - min(samples))


def _describe(value: float, samples: list[float], decimals: int) -> str:
    return (
        f"{value:.{decimals}f}s vs median {statistics.median(samples):.{decimals}f}s "
        f"(n={len(samples)}, range {min(samples):.{decimals}f}-{max(samples):.{decimals}f}s)"
    )


def _print_outcomes(run: Run) -> None:
    counts = Counter(test["outcome"] for test in run.tests)
    executed = sum(counts[outcome] for outcome in _EXECUTED_OUTCOMES)
    print(
        f"executed={executed} passed={counts['passed']} failed={counts['failed']} skipped={counts['skipped']} "
        f"xfailed={counts['xfailed']} xpassed={counts['xpassed']} interrupted={counts['interrupted']}"
    )
    labels = {"failed": "failed", "skipped": "skipped", "xfailed": "expected failure", "xpassed": "unexpected pass"}
    for test in run.tests:
        if test["outcome"] == "interrupted":
            print(f"interrupted: {test['test_id']}")
        elif test["outcome"] in labels:
            print(f"{labels[test['outcome']]}: {test['test_id']}: {test['reason']}")
    if run.end:
        for reason in run.end["failed"]:
            print(f"failed: {reason}")
        for reason in run.end["incomplete"]:
            print(f"incomplete: {reason}")


def _print_header(run: Run) -> None:
    print(f"Run {run.path.stem}")
    if run.start:
        identity = run.start["identity"]
        state = "tracked changes" if run.start["tracked_dirty"] is not False else "clean"
        print(f"{run.start['kind']} run at {run.start['git_sha']} ({state}); {identity['workers']} workers")
        print(f"Untracked files: {run.start['untracked_count']}")
        for path in run.start["untracked_execution_inputs"]:
            print(f"untracked execution input: {path}")
    print(f"Result: {run.result}")


def _print_total(current: Run, earlier: list[Run]) -> None:
    wall = current.end["wall_seconds"]
    phases = ", ".join(f"{name} {seconds:.1f}s" for name, seconds in current.end["phase_wall_seconds"].items())
    print(f"Phase wall time: {phases}")
    same_tests = [run for run in earlier if run.selected == current.selected and run.timed == current.timed]
    if earlier and not same_tests:
        print(f"Total wall: {wall:.1f}s; not compared, the test set differs from all {len(earlier)} comparable earlier runs")
        return
    samples = [run.end["wall_seconds"] for run in same_tests[:RECENT_RUNS_COMPARED]]
    if len(samples) < MINIMUM_EARLIER_RUNS:
        print(f"Total wall: {wall:.1f}s; only {len(samples)} comparable earlier runs, need {MINIMUM_EARLIER_RUNS}")
        return
    verdict = "REGRESSION" if _is_slower(wall, samples, TOTAL_FLOOR_SECONDS, TOTAL_FRACTION) else "within variation"
    print(f"Total wall: {_describe(wall, samples, 1)}: {verdict}")


def _print_regressions(current: Run, earlier: list[Run]) -> None:
    print("\nTest regressions")
    found = 0
    suite_changed = False
    for test in current.tests:
        if test["outcome"] not in _TIMED_OUTCOMES:
            continue
        samples, used = [], []
        for run in earlier:
            match = next(
                (old for old in run.tests
                 if old["test_id"] == test["test_id"] and old["tier"] == test["tier"] and old["outcome"] == test["outcome"]),
                None,
            )
            if match is not None:
                samples.append(_seconds(match))
                used.append(run)
            if len(samples) == RECENT_RUNS_COMPARED:
                break
        if len(samples) < MINIMUM_EARLIER_RUNS or not _is_slower(_seconds(test), samples, TEST_FLOOR_SECONDS, TEST_FRACTION):
            continue
        found += 1
        suite_changed = suite_changed or any(run.selected != current.selected for run in used)
        print(f"REGRESSION {test['test_id']}: {_describe(_seconds(test), samples, 2)}")
    if not found:
        print("none found")
    if suite_changed:
        print("Warning: the surrounding suite changed, so shared fixtures and worker contention may affect these timings.")


def _print_slowest(run: Run, top: int) -> None:
    print("\nSlowest tests")
    ran = [test for test in run.tests if test["outcome"] in _EXECUTED_OUTCOMES]
    for test in sorted(ran, key=_seconds, reverse=True)[:top]:
        print(f"{_seconds(test):8.2f}s  {test['outcome']:<8} {test['test_id']}")


def _choose(history: list[Run], args: argparse.Namespace) -> Run | None:
    if args.run_id:
        return next((run for run in history if run.path.stem == args.run_id), None)
    if args.kind:
        return next((run for run in reversed(history) if run.start and run.start["kind"] == args.kind), None)
    return history[-1] if history else None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    history = _load_history(args.results_dir)
    if not history:
        print(f"No test history in {args.results_dir}")
        return 0
    current = _choose(history, args)
    if current is None:
        print("No matching run in the test history")
        return 2

    _print_header(current)
    _print_outcomes(current)
    rejections = current.baseline_rejections()
    print("Baseline eligible: " + (f"no ({'; '.join(rejections)})" if rejections else "yes"))
    if reason := current.not_comparable_reason():
        print(f"Not compared: {reason}")
    else:
        earlier, rejected = _usable_earlier_runs(current, history)
        for reason, count in rejected.items():
            print(f"Earlier runs not used ({count}): {reason}")
        _print_total(current, earlier)
        _print_regressions(current, earlier)
    _print_slowest(current, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
