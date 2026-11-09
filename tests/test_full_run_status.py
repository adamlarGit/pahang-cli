"""The commit count an agent reports after each ticket, read from real git history."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import full_run_status


def _git(repo: Path, *arguments: str) -> str:
    command = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *arguments]
    return subprocess.run(command, cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, count: int = 1) -> str:
    for _ in range(count):
        _git(repo, "commit", "--allow-empty", "-m", "change")
    return _git(repo, "rev-parse", "HEAD")


def _record(folder: Path, run_id: str, sha: str, started_at: float, kind: str = "full", result: str | None = "PASSED") -> None:
    folder.mkdir(exist_ok=True)
    events = [{"event": "run_start", "run_id": run_id, "kind": kind, "git_sha": sha, "started_at": started_at}]
    if result is not None:
        events.append({"event": "run_end", "run_id": run_id, "result": result})
    (folder / f"{run_id}.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init")
    return path


def _report(repo: Path, capsys: pytest.CaptureFixture[str]) -> str:
    assert full_run_status.main(["--results-dir", str(repo / "results"), "--repo", str(repo)]) == 0
    return capsys.readouterr().out


def test_counts_commits_since_the_newest_passed_full_run(repo, capsys):
    older = _commit(repo)
    newer = _commit(repo, 2)
    _commit(repo, 3)
    _record(repo / "results", "older", older, 1.0)
    _record(repo / "results", "newer", newer, 2.0)

    output = _report(repo, capsys)

    assert f"3 commits since the last passed Full Run ({newer[:7]})" in output
    assert "consider" not in output


@pytest.mark.parametrize(
    "ignored",
    [
        {"kind": "fast"},
        {"result": "FAILED"},
        {"result": "INCOMPLETE"},
        {"result": None},
    ],
    ids=["fast-run", "failed", "incomplete", "unfinished"],
)
def test_only_a_passed_full_run_resets_the_count(repo, capsys, ignored):
    passed = _commit(repo)
    other = _commit(repo)
    _record(repo / "results", "passed", passed, 1.0)
    _record(repo / "results", "other", other, 2.0, **ignored)

    assert "1 commit since the last passed Full Run" in _report(repo, capsys)


def test_ten_commits_are_flagged(repo, capsys):
    _record(repo / "results", "passed", _commit(repo), 1.0)
    _commit(repo, 10)

    assert "10 commits since the last passed Full Run" in (output := _report(repo, capsys))
    assert "consider a Full Run" in output


def test_nine_commits_are_not_flagged(repo, capsys):
    _record(repo / "results", "passed", _commit(repo), 1.0)
    _commit(repo, 9)

    assert "consider" not in _report(repo, capsys)


def test_no_passed_full_run_shows_no_count(repo, capsys):
    sha = _commit(repo)
    _record(repo / "results", "failed", sha, 1.0, result="FAILED")

    assert _report(repo, capsys).strip() == "no Full Run recorded"


def test_missing_results_folder_shows_no_count(repo, capsys):
    _commit(repo)

    assert _report(repo, capsys).strip() == "no Full Run recorded"


def test_a_commit_git_cannot_find_shows_no_count(repo, capsys):
    _commit(repo)
    _record(repo / "results", "passed", "0" * 40, 1.0)

    output = _report(repo, capsys)

    assert "commits since" not in output
    assert "0000000" in output
