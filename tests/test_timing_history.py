"""Test timing history and its report, checked on temporary sample tests and history files."""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts import run_full_suite, timing_report
from tests.test_test_tiers import _test_records, _write_repo_options

REPO = Path(__file__).resolve().parent.parent
SHA = "a" * 40
OUTCOME_SAMPLE = """
    import pytest

    def test_passes():
        pass

    @pytest.mark.xfail(reason="known", strict=True)
    def test_known_failure():
        assert False

    @pytest.mark.xfail(reason="stale strict", strict=True)
    def test_strict_unexpected_pass():
        pass

    @pytest.mark.xfail(reason="stale loose", strict=False)
    def test_loose_unexpected_pass():
        pass

    @pytest.fixture
    def broken_setup():
        raise RuntimeError("setup")

    def test_setup_failure(broken_setup):
        pass

    @pytest.fixture
    def broken_teardown():
        yield
        raise RuntimeError("teardown")

    def test_teardown_failure(broken_teardown):
        pass

    @pytest.mark.word
    def test_word_tier():
        pass
"""


@pytest.mark.parametrize("options", [(), ("-n", "2")], ids=["serial", "xdist"])
def test_plugin_keeps_every_outcome_visible_with_git_sha_and_tier(tmp_path: Path, options: tuple[str, ...]) -> None:
    if options:
        pytest.importorskip("xdist")
    results = _results_for(tmp_path, OUTCOME_SAMPLE, f"--git-sha={SHA}", *options)

    assert {name: record["outcome"] for name, record in results.items()} == {
        "test_passes": "passed",
        "test_known_failure": "xfailed",
        "test_strict_unexpected_pass": "xpassed",
        "test_loose_unexpected_pass": "xpassed",
        "test_setup_failure": "failed",
        "test_teardown_failure": "failed",
        "test_word_tier": "passed",
    }
    assert results["test_strict_unexpected_pass"]["strict"] is True
    assert "stale strict" in results["test_strict_unexpected_pass"]["reason"]
    assert "strict" not in results["test_loose_unexpected_pass"]
    assert results["test_loose_unexpected_pass"]["reason"] == "stale loose"
    assert results["test_setup_failure"]["durations"]["setup"] > 0
    assert results["test_teardown_failure"]["durations"]["teardown"] > 0
    assert results["test_word_tier"]["tier"] == "word"
    assert {record["git_sha"] for record in results.values()} == {SHA}


def _results_for(tmp_path: Path, sample: str, *options: str) -> dict[str, dict]:
    results_file = tmp_path / "results.jsonl"
    _write_repo_options(tmp_path)
    (tmp_path / "test_sample.py").write_text(textwrap.dedent(sample), encoding="utf-8")
    subprocess.run(
        [
            sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "tests.results_plugin",
            f"--results-file={results_file}", "--grouped-run-id=run-1", "--run-phase=sample",
            "--override-ini=addopts=", *options, "test_sample.py",
        ],
        cwd=tmp_path, env=dict(os.environ, PYTHONPATH=str(REPO)), capture_output=True, text=True, timeout=120,
    )
    records = _test_records(results_file)
    by_test = {record["test_id"].split("::")[1]: record for record in records}
    assert len(by_test) == len(records), "a test was recorded twice"
    return by_test


def test_plugin_records_an_interrupted_test_as_interrupted_not_passed(tmp_path: Path) -> None:
    results = _results_for(
        tmp_path,
        """
        def test_interrupted():
            raise KeyboardInterrupt
        """,
    )

    assert results["test_interrupted"]["outcome"] == "interrupted"


PHASE_SAMPLE = """
    import pytest

    def test_fast():
        pass

    @pytest.mark.word
    def test_word():
        pass
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _sample_repo(root: Path, sample: str = PHASE_SAMPLE) -> str:
    _write_repo_options(root)
    (root / "test_sample.py").write_text(textwrap.dedent(sample), encoding="utf-8")
    (root / "uv.lock").write_text("locked\n", encoding="utf-8")
    (root / ".gitignore").write_text("results/\nfull-run.lock\n__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "sample")
    return _git(root, "rev-parse", "HEAD")


def _runner(root: Path, *options: str, clock=None) -> int:
    pytest.importorskip("xdist")
    return run_full_suite.main(
        [
            "--root", str(root),
            "--workers", "2",
            "--results-dir", str(root / "results"),
            "--lock-file", str(root / "full-run.lock"),
            *options,
        ],
        list_processes=lambda: [],
        clock=clock,
    )


def _events(root: Path) -> list[dict]:
    files = list((root / "results").glob("*.jsonl"))
    assert len(files) == 1, "every phase belongs to one grouped run"
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def _event(events: list[dict], name: str) -> dict:
    matches = [event for event in events if event.get("event") == name]
    assert len(matches) == 1
    return matches[0]


def test_full_run_records_metadata_for_one_grouped_run(tmp_path: Path) -> None:
    head = _sample_repo(tmp_path)

    assert _runner(tmp_path) == 0

    events = _events(tmp_path)
    start, end = _event(events, "run_start"), _event(events, "run_end")
    assert start["kind"] == "full"
    assert start["git_sha"] == head
    assert start["tracked_dirty"] is False
    assert start["untracked_execution_inputs"] == []
    identity = start["identity"]
    assert identity["workers"] == "2"
    assert identity["python"] and identity["pytest"] and identity["xdist"] and identity["machine"]
    assert len(identity["uv_lock_sha256"]) == 64
    assert end["result"] == "PASSED"
    assert end["selected_count"] == 2
    assert len(end["selected_tests_sha256"]) == 64
    records = [event for event in events if "test_id" in event]
    assert {record["phase"] for record in records} == {"fast", "serial"}
    assert {record["git_sha"] for record in records} == {head}


def test_wall_time_is_elapsed_time_not_summed_test_durations(tmp_path: Path) -> None:
    _sample_repo(tmp_path)
    ticks = itertools.count(0, 100)

    _runner(tmp_path, clock=lambda: float(next(ticks)))

    end = _event(_events(tmp_path), "run_end")
    assert end["phase_wall_seconds"] == {"fast": 100.0, "serial": 100.0}
    assert end["wall_seconds"] == 500.0


def test_fast_only_records_a_fast_run_without_the_serial_phase(tmp_path: Path) -> None:
    _sample_repo(tmp_path)

    assert _runner(tmp_path, "--fast-only") == 0

    events = _events(tmp_path)
    assert _event(events, "run_start")["kind"] == "fast"
    assert list(_event(events, "run_end")["phase_wall_seconds"]) == ["fast"]
    assert [record["phase"] for record in events if "test_id" in record] == ["fast"]


def test_tracked_changes_are_dirty_and_untracked_notes_are_not(tmp_path: Path) -> None:
    _sample_repo(tmp_path)
    (tmp_path / "issues to solve.txt").write_text("note", encoding="utf-8")
    (tmp_path / "notes.md").write_text("note", encoding="utf-8")

    _runner(tmp_path, "--fast-only")

    start = _event(_events(tmp_path), "run_start")
    assert start["tracked_dirty"] is False
    assert start["untracked_count"] == 2
    assert start["untracked_execution_inputs"] == []


@pytest.mark.parametrize("name", ["helper.py", "extra.toml"])
def test_untracked_code_or_config_is_listed(tmp_path: Path, name: str) -> None:
    _sample_repo(tmp_path)
    (tmp_path / name).write_text("", encoding="utf-8")

    _runner(tmp_path, "--fast-only")

    assert _event(_events(tmp_path), "run_start")["untracked_execution_inputs"] == [name]


def test_staged_and_unstaged_tracked_changes_are_dirty(tmp_path: Path) -> None:
    _sample_repo(tmp_path)
    with (tmp_path / "uv.lock").open("a", encoding="utf-8") as stream:
        stream.write("changed\n")

    _runner(tmp_path, "--fast-only")
    assert _event(_events(tmp_path), "run_start")["tracked_dirty"] is True

    for file in (tmp_path / "results").glob("*.jsonl"):
        file.unlink()
    _git(tmp_path, "add", "uv.lock")
    _runner(tmp_path, "--fast-only")
    assert _event(_events(tmp_path), "run_start")["tracked_dirty"] is True


def test_retention_keeps_the_newest_200_grouped_runs(tmp_path: Path) -> None:
    _sample_repo(tmp_path)
    results = tmp_path / "results"
    results.mkdir()
    old = []
    for index in range(203):
        path = results / f"{index:032x}.jsonl"
        path.write_text("", encoding="utf-8")
        os.utime(path, (1_000_000 + index, 1_000_000 + index))
        old.append(path)
    unrelated = results / "notes.jsonl"
    unrelated.write_text("", encoding="utf-8")
    os.utime(unrelated, (1, 1))

    assert _runner(tmp_path) == 0

    remaining = [path for path in results.glob("*.jsonl") if path != unrelated]
    assert len(remaining) == 200
    assert not any(path.exists() for path in old[:4])
    assert all(path.exists() for path in old[4:])
    assert unrelated.exists()
    newest = max(remaining, key=lambda path: path.stat().st_mtime)
    phases = {r["phase"] for r in _test_records(newest)}
    assert phases == {"fast", "serial"}, "both phases count as one run"


# ---- report, on hand-written history ----

IDENTITY = {
    "machine": "reference", "platform": "win", "cpu_count": 8, "python": "3.12", "pytest": "9.2.0",
    "xdist": "3.8.0", "uv_lock_sha256": "b" * 64, "workers": "4",
}
PASSING = {"t.py::slow": 1.0, "t.py::steady": 2.0}


def write_run(
    folder: Path,
    number: int,
    tests: dict[str, float | tuple[float, str]] | None = None,
    *,
    wall: float = 100.0,
    kind: str = "full",
    result: str = "PASSED",
    tracked_dirty: bool = False,
    untracked: tuple[str, ...] = (),
    identity: dict | None = None,
    finished: bool = True,
    incomplete: tuple[str, ...] = (),
    tier: str = "fast",
) -> str:
    folder.mkdir(exist_ok=True)
    run_id = f"{number:032x}"
    lines: list[dict] = [{
        "event": "run_start", "run_id": run_id, "phase": "", "started_at": 1000.0 + number, "kind": kind,
        "git_sha": SHA, "tracked_dirty": tracked_dirty, "untracked_count": len(untracked),
        "untracked_execution_inputs": list(untracked), "identity": {**IDENTITY, **(identity or {})},
    }]
    for test_id, value in (PASSING if tests is None else tests).items():
        seconds, outcome = value if isinstance(value, tuple) else (value, "passed")
        lines.append({
            "run_id": run_id, "phase": "fast", "git_sha": SHA, "test_id": test_id, "tier": tier, "outcome": outcome,
            "reason": "why" if outcome != "passed" else "",
            "durations": {"setup": 0.0, "call": seconds, "teardown": 0.0},
        })
    if finished:
        lines.append({
            "event": "run_end", "run_id": run_id, "phase": "", "result": result, "failed": [],
            "incomplete": list(incomplete), "wall_seconds": wall, "phase_wall_seconds": {"fast": wall},
        })
    (folder / f"{run_id}.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return run_id


def report(folder: Path, capsys: pytest.CaptureFixture[str], *options: str) -> str:
    assert timing_report.main(["--results-dir", str(folder), *options]) == 0
    return capsys.readouterr().out


def three_baselines(folder: Path, **kwargs) -> None:
    for number, slow in enumerate((0.9, 1.0, 1.1), start=1):
        write_run(folder, number, {"t.py::slow": slow, "t.py::steady": 2.0}, wall=100.0 + number, **kwargs)


def test_report_flags_a_regression_with_its_baseline_and_variability(tmp_path, capsys) -> None:
    three_baselines(tmp_path)
    write_run(tmp_path, 4, {"t.py::slow": 5.0, "t.py::steady": 2.0}, wall=130.0)

    out = report(tmp_path, capsys)

    assert "REGRESSION t.py::slow: 5.00s vs median 1.00s (n=3, range 0.90-1.10s)" in out
    assert "t.py::steady" not in out.split("Slowest tests")[0].split("Test regressions")[1]
    assert "Total wall: 130.0s vs median 102.0s (n=3, range 101.0-103.0s): REGRESSION" in out


def test_report_lists_slowest_tests_slowest_first(tmp_path, capsys) -> None:
    write_run(tmp_path, 1, {"t.py::a": 1.0, "t.py::b": 9.0, "t.py::c": 4.0})

    out = report(tmp_path, capsys, "--top", "2")

    slowest = out.split("Slowest tests")[1]
    assert slowest.index("t.py::b") < slowest.index("t.py::c")
    assert "t.py::a" not in slowest


def test_report_keeps_differences_within_variation_quiet(tmp_path, capsys) -> None:
    for number, slow in enumerate((1.0, 4.0, 2.0), start=1):
        write_run(tmp_path, number, {"t.py::slow": slow})
    write_run(tmp_path, 4, {"t.py::slow": 4.5})

    assert "REGRESSION t.py::slow" not in report(tmp_path, capsys)


def test_report_needs_three_earlier_runs_before_calling_a_regression(tmp_path, capsys) -> None:
    write_run(tmp_path, 1, wall=100.0)
    write_run(tmp_path, 2, wall=100.0)
    write_run(tmp_path, 3, {"t.py::slow": 50.0, "t.py::steady": 2.0}, wall=300.0)

    out = report(tmp_path, capsys)

    assert "REGRESSION" not in out
    assert "Total wall: 300.0s; only 2 comparable earlier runs, need 3" in out


@pytest.mark.parametrize("outcome", ["skipped", "failed", "xpassed", "interrupted"])
def test_report_never_compares_a_test_whose_outcome_is_not_a_timing(tmp_path, capsys, outcome: str) -> None:
    three_baselines(tmp_path)
    write_run(tmp_path, 4, {"t.py::slow": (50.0 if outcome != "skipped" else 0.0, outcome), "t.py::steady": 2.0})

    out = report(tmp_path, capsys)

    assert "REGRESSION t.py::slow" not in out
    assert "IMPROVED" not in out


def test_report_ignores_earlier_runs_where_the_test_had_another_outcome(tmp_path, capsys) -> None:
    for number in (1, 2, 3):
        write_run(tmp_path, number, {"t.py::slow": (0.01, "skipped"), "t.py::steady": 2.0})
    write_run(tmp_path, 4, {"t.py::slow": 5.0, "t.py::steady": 2.0})

    assert "REGRESSION t.py::slow" not in report(tmp_path, capsys)


def test_report_ignores_earlier_runs_where_the_test_had_another_tier(tmp_path, capsys) -> None:
    three_baselines(tmp_path, tier="word")
    write_run(tmp_path, 4, {"t.py::slow": 5.0, "t.py::steady": 2.0})

    assert "REGRESSION t.py::slow" not in report(tmp_path, capsys)


def test_report_total_time_needs_an_identical_executed_test_set(tmp_path, capsys) -> None:
    three_baselines(tmp_path)
    write_run(tmp_path, 4, {"t.py::slow": (0.0, "skipped"), "t.py::steady": 2.0}, wall=50.0)

    out = report(tmp_path, capsys)

    assert "Total wall: 50.0s; not compared, the test set differs from all 3 comparable earlier runs" in out


def test_report_compares_individual_tests_across_a_changed_suite_with_a_warning(tmp_path, capsys) -> None:
    three_baselines(tmp_path)
    write_run(tmp_path, 4, {"t.py::slow": 5.0, "t.py::steady": 2.0, "t.py::new": 0.1}, wall=500.0)

    out = report(tmp_path, capsys)

    assert "REGRESSION t.py::slow" in out
    assert "not compared, the test set differs" in out
    assert "Warning: the surrounding suite changed" in out


@pytest.mark.parametrize(
    ("write", "reason"),
    [
        ({"result": "INCOMPLETE"}, "result INCOMPLETE"),
        ({"result": "FAILED"}, "result FAILED"),
        ({"tracked_dirty": True}, "tracked changes"),
        ({"untracked": ("helper.py",)}, "untracked execution inputs"),
        ({"finished": False}, "did not finish"),
    ],
)
def test_report_excludes_ineligible_runs_from_the_baseline(tmp_path, capsys, write: dict, reason: str) -> None:
    for number in (1, 2, 3):
        write_run(tmp_path, number, {"t.py::slow": 0.1}, wall=1.0, **write)
    write_run(tmp_path, 4, {"t.py::slow": 5.0}, wall=500.0)

    out = report(tmp_path, capsys)

    assert "REGRESSION" not in out
    assert "only 0 comparable earlier runs" in out
    assert f"Earlier runs not used (3): {reason}" in out


@pytest.mark.parametrize(
    "field", ["machine", "python", "pytest", "xdist", "uv_lock_sha256", "workers"]
)
def test_report_labels_runs_from_another_environment_as_incomparable(tmp_path, capsys, field: str) -> None:
    for number in (1, 2, 3):
        write_run(tmp_path, number, {"t.py::slow": 0.1}, wall=1.0, identity={field: "other"})
    write_run(tmp_path, 4, {"t.py::slow": 5.0}, wall=500.0)

    out = report(tmp_path, capsys)

    assert "REGRESSION" not in out
    assert f"Earlier runs not used (3): different {field}" in out


@pytest.mark.parametrize("result", ["INCOMPLETE", "FAILED"])
def test_report_shows_an_unsuccessful_run_without_comparing_it(tmp_path, capsys, result: str) -> None:
    three_baselines(tmp_path)
    write_run(
        tmp_path, 4, {"t.py::slow": 50.0, "t.py::gone": (0.0, "skipped")}, wall=900.0, result=result,
        incomplete=("required check skipped: t.py::gone: no data",),
    )

    out = report(tmp_path, capsys)

    assert f"Result: {result}" in out
    assert "incomplete: required check skipped: t.py::gone: no data" in out
    assert f"Baseline eligible: no (result {result})" in out
    assert f"Not compared: result {result}" in out
    assert "REGRESSION" not in out


def test_report_labels_a_dirty_run_and_still_compares_it(tmp_path, capsys) -> None:
    three_baselines(tmp_path)
    write_run(tmp_path, 4, {"t.py::slow": 5.0, "t.py::steady": 2.0}, tracked_dirty=True)

    out = report(tmp_path, capsys)

    assert "Baseline eligible: no (tracked changes)" in out
    assert "REGRESSION t.py::slow" in out


def test_report_keeps_every_outcome_visible(tmp_path, capsys) -> None:
    write_run(tmp_path, 1, {
        "t.py::ok": 1.0, "t.py::bad": (1.0, "failed"), "t.py::skip": (0.0, "skipped"),
        "t.py::known": (1.0, "xfailed"), "t.py::stale": (1.0, "xpassed"), "t.py::cut": (1.0, "interrupted"),
    })

    out = report(tmp_path, capsys)

    assert "executed=4 passed=1 failed=1 skipped=1 xfailed=1 xpassed=1 interrupted=1" in out
    for line in ("skipped: t.py::skip: why", "expected failure: t.py::known: why",
                 "unexpected pass: t.py::stale: why", "interrupted: t.py::cut", "failed: t.py::bad: why"):
        assert line in out


def test_report_compares_only_the_same_kind_of_run(tmp_path, capsys) -> None:
    three_baselines(tmp_path, kind="fast")
    write_run(tmp_path, 4, {"t.py::slow": 5.0, "t.py::steady": 2.0}, kind="full", wall=500.0)

    out = report(tmp_path, capsys, "--kind", "full")

    assert "REGRESSION" not in out
    assert "only 0 comparable earlier runs" in out


def test_report_labels_older_files_without_metadata(tmp_path, capsys) -> None:
    (tmp_path / f"{1:032x}.jsonl").write_text(
        json.dumps({"run_id": "x", "phase": "fast", "test_id": "t.py::slow", "tier": "fast", "outcome": "passed",
                    "reason": "", "durations": {"setup": 0, "call": 0.1, "teardown": 0}}) + "\n",
        encoding="utf-8",
    )
    os.utime(tmp_path / f"{1:032x}.jsonl", (500, 500))
    write_run(tmp_path, 2)

    assert "Earlier runs not used (1): no run metadata" in report(tmp_path, capsys)


def test_report_tolerates_a_truncated_last_line(tmp_path, capsys) -> None:
    run_id = write_run(tmp_path, 1, finished=False)
    with (tmp_path / f"{run_id}.jsonl").open("a", encoding="utf-8") as stream:
        stream.write('{"event": "run_e')

    assert "Baseline eligible: no (did not finish)" in report(tmp_path, capsys)


def test_report_with_no_history_says_so(tmp_path, capsys) -> None:
    assert "No test history" in report(tmp_path, capsys)
