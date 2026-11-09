"""Report how many commits have landed since the newest passed Full Run."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from scripts.timing_report import REPO, Run, _load_history

SUGGEST_AT_COMMITS = 10


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=REPO / ".test-results")
    parser.add_argument("--repo", type=Path, default=REPO)
    return parser.parse_args(argv)


def _newest_passed_full_run(history: list[Run]) -> Run | None:
    passed = [run for run in history if run.start and run.start["kind"] == "full" and run.result == "PASSED"]
    return passed[-1] if passed else None


def _commits_since(repo: Path, sha: str) -> int | None:
    """Commits on HEAD that sha doesn't have, or None if git can't compare them."""
    completed = subprocess.run(
        ["git", "rev-list", "--count", f"{sha}..HEAD"], cwd=repo, capture_output=True, text=True, timeout=60
    )
    return int(completed.stdout) if completed.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run = _newest_passed_full_run(_load_history(args.results_dir))
    if run is None:
        print("no Full Run recorded")
        return 0
    short_sha = run.start["git_sha"][:7]
    count = _commits_since(args.repo, run.start["git_sha"])
    if count is None:
        print(f"last passed Full Run was at {short_sha}, which this checkout can't compare with HEAD")
        return 0
    noun = "commit" if count == 1 else "commits"
    print(f"{count} {noun} since the last passed Full Run ({short_sha})")
    if count >= SUGGEST_AT_COMMITS:
        print(f"{SUGGEST_AT_COMMITS} or more: consider a Full Run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
