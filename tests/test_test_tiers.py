"""Fast Run and Full Run behaviour, checked by running pytest on small sample tests.

Every sample run replaces pywin32's low-level start functions with a stub before the
guard wraps them, so these tests cannot start real Word or Excel even if the guard breaks.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

pytest.importorskip("pythoncom")

REPO = Path(__file__).resolve().parent.parent
FULL_RUN_OPTION = "--override-ini=addopts="

SAMPLE_CONFTEST = """
import pythoncom


class RealStartReached(Exception):
    pass


def _stub(*args, **kwargs):
    raise RealStartReached(f"real COM start reached: {args[0]}")


for _name in ("connect", "CoCreateInstance", "CoCreateInstanceEx", "GetActiveObject", "MkParseDisplayName"):
    setattr(pythoncom, _name, _stub)

from tests.conftest import *  # noqa: E402,F403
"""


def _write_repo_options(folder: Path) -> None:
    """Copy the repo's real default options into folder, so pytest's root stays inside it."""
    options = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    markers = "\n    ".join(options["markers"])
    (folder / "pytest.ini").write_text(
        f"[pytest]\npythonpath = {REPO.as_posix()}\naddopts = {options['addopts']}\nmarkers =\n    {markers}\n",
        encoding="utf-8",
    )


def run_pytest(tmp_path: Path, sample: str, *options: str) -> str:
    """Run pytest with the repo's real options on a sample test file and return its output."""
    _write_repo_options(tmp_path)
    (tmp_path / "conftest.py").write_text(SAMPLE_CONFTEST, encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(textwrap.dedent(sample), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "-p", "no:cacheprovider",
            "-rA",
            *options,
            "test_sample.py",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout + result.stderr


TIERED_SAMPLE = """
    import pytest

    def test_plain():
        pass

    @pytest.mark.word
    def test_needs_word():
        pass

    @pytest.mark.live_data
    def test_needs_live_data():
        pass
"""


def test_plain_pytest_excludes_word_and_live_data_tests(tmp_path: Path) -> None:
    output = run_pytest(tmp_path, TIERED_SAMPLE)

    assert "PASSED test_sample.py::test_plain" in output
    assert "test_needs_word" not in output
    assert "test_needs_live_data" not in output
    assert "1 passed, 2 deselected" in output


def test_full_run_option_selects_every_test(tmp_path: Path) -> None:
    output = run_pytest(tmp_path, TIERED_SAMPLE, FULL_RUN_OPTION)

    assert "3 passed" in output
    assert "deselected" not in output


@pytest.mark.parametrize(
    "start",
    [
        'win32com.client.Dispatch("Word.Application")',
        'win32com.client.DispatchEx("Word.Application")',
        'win32com.client.GetActiveObject("Word.Application")',
        'win32com.client.Dispatch("Excel.Application")',
        'win32com.client.DispatchEx("Excel.Application")',
        'win32com.client.GetObject("C:/fake/REPORT.DOCX")',
        'win32com.client.GetObject("C:/fake/testsheet.xlsx")',
    ],
)
def test_unmarked_test_starting_office_fails_naming_the_marker(tmp_path: Path, start: str) -> None:
    output = run_pytest(
        tmp_path,
        f"""
        import win32com.client

        def test_unmarked():
            {start}
        """,
    )

    assert "1 failed" in output
    assert "@pytest.mark.word" in output
    assert "real COM start reached" not in output


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            """
            import win32com.client

            def test_hides_start():
                try:
                    win32com.client.Dispatch("Word.Application")
                except Exception:
                    pass
            """,
            id="swallowed",
        ),
        pytest.param(
            """
            import pytest
            import win32com.client

            def test_hides_start():
                try:
                    win32com.client.Dispatch("Word.Application")
                except Exception as exc:
                    pytest.skip(f"Word is unavailable: {exc}")
            """,
            id="com-error-skip",
        ),
        pytest.param(
            """
            import pytest
            import win32com.client

            @pytest.mark.xfail(reason="sample")
            def test_hides_start():
                win32com.client.Dispatch("Word.Application")
            """,
            id="xfail",
        ),
        pytest.param(
            """
            import pytest
            import win32com.client

            @pytest.mark.xfail(reason="sample")
            def test_hides_start():
                try:
                    win32com.client.Dispatch("Word.Application")
                except Exception as exc:
                    pytest.skip(f"Word is unavailable: {exc}")
            """,
            id="xfail-with-com-error-skip",
        ),
    ],
)
def test_guard_failure_cannot_be_hidden(tmp_path: Path, body: str) -> None:
    output = run_pytest(tmp_path, body)

    assert "1 failed" in output
    assert "@pytest.mark.word" in output
    assert "skipped" not in output
    assert "xfailed" not in output


def test_guard_catches_a_start_in_a_fixture(tmp_path: Path) -> None:
    output = run_pytest(
        tmp_path,
        """
        import pytest
        import win32com.client

        @pytest.fixture
        def word():
            return win32com.client.Dispatch("Word.Application")

        def test_uses_fixture(word):
            pass
        """,
    )

    assert "1 error" in output
    assert "@pytest.mark.word" in output


def test_live_data_marker_alone_does_not_permit_office(tmp_path: Path) -> None:
    output = run_pytest(
        tmp_path,
        """
        import pytest
        import win32com.client

        @pytest.mark.live_data
        def test_live_only():
            win32com.client.Dispatch("Word.Application")
        """,
        FULL_RUN_OPTION,
    )

    assert "1 failed" in output
    assert "@pytest.mark.word" in output


def test_word_marked_test_may_start_office(tmp_path: Path) -> None:
    output = run_pytest(
        tmp_path,
        """
        import pytest
        import win32com.client
        from conftest import RealStartReached

        @pytest.mark.word
        def test_marked():
            with pytest.raises(RealStartReached):
                win32com.client.Dispatch("Word.Application")
            with pytest.raises(RealStartReached):
                win32com.client.DispatchEx("Excel.Application")
        """,
        FULL_RUN_OPTION,
    )

    assert "1 passed" in output


def test_guard_ignores_other_com_servers(tmp_path: Path) -> None:
    output = run_pytest(
        tmp_path,
        """
        import pytest
        import win32com.client
        from conftest import RealStartReached

        def test_other_server():
            with pytest.raises(RealStartReached):
                win32com.client.Dispatch("Shell.Application")
            with pytest.raises(RealStartReached):
                win32com.client.GetObject("winmgmts:")
        """,
    )

    assert "1 passed" in output


def test_mocked_dispatch_is_not_blocked(tmp_path: Path) -> None:
    output = run_pytest(
        tmp_path,
        """
        from unittest.mock import patch
        import win32com.client

        def test_mocked():
            with patch("win32com.client.DispatchEx") as dispatch:
                assert win32com.client.DispatchEx("Word.Application") is dispatch.return_value
        """,
    )

    assert "1 passed" in output


def _fingerprint(folder: Path) -> dict[str, str]:
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def test_pe157_fixture_test_leaves_benchmark_files_unchanged(tmp_path: Path) -> None:
    benchmark = REPO / "tests" / "benchmarks" / "pe157_perpustakaan_awam"
    before = _fingerprint(benchmark)

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "-p", "no:cacheprovider",
            "--basetemp", str(tmp_path / "basetemp"),
            "tests/test_full_report_multipart_e2e.py::TestSyntheticVcbBenchmarkFixture",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert _fingerprint(benchmark) == before
