"""A live-data allowance excuses one named data condition and nothing else."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_sample(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(
        "from tests.live_data_allowance import xfail_while_data_condition\n\n" + body,
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rxX", "test_sample.py"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )


def test_detected_condition_is_an_expected_failure_naming_reason_and_removal(tmp_path: Path) -> None:
    result = _run_sample(
        tmp_path,
        """
def test_sample():
    xfail_while_data_condition(
        True,
        condition="workbook X no longer has row Y",
        evidence="row count fell from 12 to 11",
        removal="remove once row Y returns",
    )
    assert False
""",
    )

    assert "1 xfailed" in result.stdout, result.stdout
    assert "workbook X no longer has row Y" in result.stdout
    assert "row count fell from 12 to 11" in result.stdout
    assert "remove once row Y returns" in result.stdout
    assert result.returncode == 0


def test_failure_after_the_condition_clears_is_a_real_failure(tmp_path: Path) -> None:
    result = _run_sample(
        tmp_path,
        """
def test_sample():
    xfail_while_data_condition(False, condition="row Y missing", evidence="n/a", removal="when row Y returns")
    assert False, "unrelated regression"
""",
    )

    assert "1 failed" in result.stdout, result.stdout
    assert "xfailed" not in result.stdout
    assert result.returncode == 1


def test_unrelated_failure_before_the_allowance_stays_a_failure(tmp_path: Path) -> None:
    result = _run_sample(
        tmp_path,
        """
def test_sample():
    assert False, "unrelated regression"
    xfail_while_data_condition(True, condition="row Y missing", evidence="n/a", removal="when row Y returns")
""",
    )

    assert "1 failed" in result.stdout, result.stdout
    assert "xfailed" not in result.stdout


def test_project_config_makes_an_unexpected_pass_fail() -> None:
    import tomllib

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert config["tool"]["pytest"]["ini_options"]["xfail_strict"] is True
