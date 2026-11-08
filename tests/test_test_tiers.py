"""Fast Run and Full Run behaviour, checked by running pytest on small sample tests.

Sample runs that exercise the Office guard replace COM and OS launch functions with
stubs before the guard wraps them, so they cannot start real Word or Excel even if the
guard breaks. Results-plugin and runner samples never touch Office.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

from scripts import run_full_suite
from tests import tier_guard

pytest.importorskip("pythoncom")

REPO = Path(__file__).resolve().parent.parent
FULL_RUN_OPTION = "--override-ini=addopts="

SAMPLE_CONFTEST = """
import os
import subprocess
import sys

import pythoncom


class RealStartReached(Exception):
    pass


def _stub(*args, **kwargs):
    raise RealStartReached(f"real launch reached: {args[0]}")


for _name in ("connect", "CoCreateInstance", "CoCreateInstanceEx", "GetActiveObject", "MkParseDisplayName"):
    setattr(pythoncom, _name, _stub)

class _FakePopen(subprocess.Popen):
    def __init__(self, args, *positional, **kwargs):
        sys.audit("subprocess.Popen", kwargs.get("executable"), args, None, None)
        _stub(args)


def _fake_startfile(path, *args, **kwargs):
    sys.audit("os.startfile", path, kwargs.get("operation", "open"))
    return _stub(path)


subprocess.Popen = _FakePopen
os.startfile = _fake_startfile

from tests.tier_guard import install_guard, pytest_runtest_makereport, pytest_runtest_protocol  # noqa: E402,F401

install_guard()
"""


def _write_repo_options(folder: Path) -> None:
    """Copy the repo's real default options into folder, so pytest's root stays inside it."""
    options = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    scalars = "".join(f"{key} = {value}\n" for key, value in options.items() if not isinstance(value, list))
    markers = "\n    ".join(options["markers"])
    (folder / "pytest.ini").write_text(
        f"[pytest]\npythonpath = {REPO.as_posix()}\n{scalars}markers =\n    {markers}\n",
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


def test_suite_conftest_wires_the_guard(request: pytest.FixtureRequest) -> None:
    hooks = request.config.hook
    assert tier_guard.is_installed()
    assert tier_guard.pytest_runtest_protocol in [i.function for i in hooks.pytest_runtest_protocol.get_hookimpls()]
    assert tier_guard.pytest_runtest_makereport in [i.function for i in hooks.pytest_runtest_makereport.get_hookimpls()]


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
        'win32com.client.GetObject("C:/fake/data.csv")',
        'win32com.client.GetObject("C:/fake/book.xlsx!Sheet1")',
        'win32com.client.GetObject("new:{000209FF-0000-0000-C000-000000000046}")',
        'win32com.client.GetObject("clsid:00024500-0000-0000-C000-000000000046:")',
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
    assert "real launch reached" not in output


@pytest.mark.parametrize(
    "start",
    [
        'subprocess.Popen(["WINWORD.EXE"])',
        'subprocess.run(["EXCEL.EXE"])',
        'subprocess.Popen(["alias"], executable="EXCEL.EXE")',
        'subprocess.Popen(["C:/Program Files/Microsoft Office/WINWORD.EXE"])',
        'subprocess.Popen(\'"C:/Program Files/Microsoft Office/WINWORD.EXE" /q\')',
        'os.startfile("C:/fake/WINWORD.EXE")',
        'os.startfile("C:/fake/report.docx")',
        'os.startfile("C:/fake/workbook.xlsx")',
        'os.startfile("C:/fake/data.csv")',
        'os.startfile(b"C:/fake/report.docx")',
    ],
)
def test_unmarked_office_process_or_file_launch_fails(tmp_path: Path, start: str) -> None:
    output = run_pytest(
        tmp_path,
        f"""
        import os
        import subprocess

        def test_unmarked():
            {start}
        """,
    )

    assert "1 failed" in output
    assert "@pytest.mark.word" in output
    assert "real launch reached" not in output


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
        import os
        import subprocess
        import win32com.client
        from conftest import RealStartReached

        @pytest.mark.word
        def test_marked():
            with pytest.raises(RealStartReached):
                win32com.client.Dispatch("Word.Application")
            with pytest.raises(RealStartReached):
                win32com.client.DispatchEx("Excel.Application")
            with pytest.raises(RealStartReached):
                subprocess.Popen(["WINWORD.EXE"])
            with pytest.raises(RealStartReached):
                os.startfile("C:/fake/workbook.xlsx")
        """,
        FULL_RUN_OPTION,
    )

    assert "1 passed" in output


def test_guard_ignores_other_com_servers(tmp_path: Path) -> None:
    output = run_pytest(
        tmp_path,
        """
        import os
        import subprocess
        import pytest
        import win32com.client
        from conftest import RealStartReached

        def test_other_server():
            with pytest.raises(RealStartReached):
                win32com.client.Dispatch("Shell.Application")
            with pytest.raises(RealStartReached):
                win32com.client.GetObject("winmgmts:")
            with pytest.raises(RealStartReached):
                subprocess.Popen(["python", "-c", "pass"])
            with pytest.raises(RealStartReached):
                os.startfile("C:/fake/image.png")
        """,
    )

    assert "1 passed" in output


@pytest.mark.parametrize("name", ["word.txt", "Word.pdf", "excel.png", "word.notes.pdf"])
def test_startfile_ignores_non_office_files_named_like_a_progid(tmp_path: Path, name: str) -> None:
    output = run_pytest(
        tmp_path,
        f"""
        import os
        import pytest
        from conftest import RealStartReached

        def test_named_like_progid():
            with pytest.raises(RealStartReached):
                os.startfile("{name}")
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


@pytest.mark.parametrize("options", [(), (FULL_RUN_OPTION,)], ids=["fast-run", "full-run"])
def test_misspelled_marker_is_a_collection_error(tmp_path: Path, options: tuple[str, ...]) -> None:
    output = run_pytest(
        tmp_path,
        """
        import pytest

        @pytest.mark.live_dta
        def test_misspelled():
            pass
        """,
        *options,
    )

    assert "1 error" in output
    assert "'live_dta' not found in `markers`" in output


RESULTS_SAMPLE = """
    import pytest

    def test_passes():
        pass

    def test_fails():
        assert False

    def test_skips():
        pytest.skip("no data here")

    @pytest.mark.xfail(reason="diagnosed sample", strict=True)
    def test_allowed_failure():
        assert False

    @pytest.fixture
    def broken():
        raise RuntimeError("setup broke")

    def test_setup_error(broken):
        pass

    @pytest.mark.word
    @pytest.mark.live_data
    def test_both_markers():
        pass
"""


def _test_records(results_file: Path) -> list[dict]:
    records = [json.loads(line) for line in results_file.read_text(encoding="utf-8").splitlines()]
    return [record for record in records if "test_id" in record]


def _results(tmp_path: Path, *options: str) -> dict[str, dict]:
    results_file = tmp_path / "results.jsonl"
    env = dict(os.environ, PYTHONPATH=str(REPO))
    _write_repo_options(tmp_path)
    (tmp_path / "test_sample.py").write_text(textwrap.dedent(RESULTS_SAMPLE), encoding="utf-8")
    subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "-p", "no:cacheprovider",
            "-p", "tests.results_plugin",
            f"--results-file={results_file}",
            "--grouped-run-id=run-1",
            "--run-phase=sample",
            FULL_RUN_OPTION,
            *options,
            "test_sample.py",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    records = _test_records(results_file)
    by_test = {record["test_id"].split("::")[1]: record for record in records}
    assert len(by_test) == len(records), "a test was recorded twice"
    return by_test


@pytest.mark.parametrize(
    "options",
    [(), ("-n", "2")],
    ids=["serial", "xdist"],
)
def test_results_plugin_records_each_test_once(tmp_path: Path, options: tuple[str, ...]) -> None:
    if options:
        pytest.importorskip("xdist")

    results = _results(tmp_path, *options)

    assert {name: record["outcome"] for name, record in results.items()} == {
        "test_passes": "passed",
        "test_fails": "failed",
        "test_skips": "skipped",
        "test_allowed_failure": "xfailed",
        "test_setup_error": "failed",
        "test_both_markers": "passed",
    }
    assert results["test_skips"]["reason"].endswith("no data here")
    assert results["test_allowed_failure"]["reason"] == "diagnosed sample"
    assert results["test_both_markers"]["tier"] == "word+live_data"
    assert results["test_passes"]["tier"] == "fast"
    assert results["test_passes"]["run_id"] == "run-1"
    assert results["test_passes"]["phase"] == "sample"
    assert set(results["test_passes"]["durations"]) == {"setup", "call", "teardown"}


def full_run(tmp_path: Path, sample: str, *options: str, processes: tuple[str, ...] = ()) -> int:
    """Run the Full Run runner on a sample suite; only the Office process list is faked."""
    pytest.importorskip("xdist")
    _write_repo_options(tmp_path)
    (tmp_path / "test_sample.py").write_text(textwrap.dedent(sample), encoding="utf-8")
    return run_full_suite.main(
        [
            "--root", str(tmp_path),
            "--workers", "2",
            "--results-dir", str(tmp_path / "results"),
            "--lock-file", str(tmp_path / "full-run.lock"),
            *options,
        ],
        list_processes=lambda: list(processes),
    )


def full_run_records(tmp_path: Path) -> list[dict]:
    files = list((tmp_path / "results").glob("*.jsonl"))
    assert len(files) == 1, "both phases belong to one grouped run"
    return _test_records(files[0])


PHASE_SAMPLE = """
    import pytest

    def test_fast_a():
        pass

    def test_fast_b():
        pass

    @pytest.mark.word
    def test_word():
        pass

    @pytest.mark.live_data
    def test_live():
        pass

    @pytest.mark.word
    @pytest.mark.live_data
    def test_both():
        pass
"""


def test_full_run_runs_fast_tests_then_marked_tests_once_each(tmp_path: Path) -> None:
    assert full_run(tmp_path, PHASE_SAMPLE) == 0

    records = full_run_records(tmp_path)
    phases = [record["phase"] for record in records]
    assert phases == ["fast"] * 2 + ["serial"] * 3
    names = sorted(record["test_id"].split("::")[1] for record in records)
    assert names == ["test_both", "test_fast_a", "test_fast_b", "test_live", "test_word"]
    assert {record["run_id"] for record in records} == {records[0]["run_id"]}


@pytest.mark.parametrize(
    "sample",
    [
        pytest.param(
            """
            import pytest

            def test_fast():
                assert False

            @pytest.mark.word
            def test_word():
                pass
            """,
            id="fast-phase-fails",
        ),
        pytest.param(
            """
            import pytest

            def test_fast():
                pass

            @pytest.mark.word
            def test_word():
                assert False
            """,
            id="serial-phase-fails",
        ),
    ],
)
def test_full_run_runs_both_phases_and_reports_a_failure_in_either(tmp_path: Path, sample: str) -> None:
    assert full_run(tmp_path, sample) == 1

    assert {record["phase"] for record in full_run_records(tmp_path)} == {"fast", "serial"}


@pytest.mark.parametrize(
    ("sample", "expected_code", "expected_text"),
    [
        pytest.param(
            """
            import pytest

            def test_fast():
                pass

            @pytest.mark.live_data
            def test_live():
                pytest.skip("project folder missing")
            """,
            10,
            "project folder missing",
            id="required-serial-skip-is-incomplete",
        ),
        pytest.param(
            """
            import pytest

            def test_fast():
                pass

            @pytest.mark.live_data
            @pytest.mark.optional("only some machines have this archive")
            def test_live():
                pytest.skip("archive missing")
            """,
            0,
            "only some machines have this archive",
            id="optional-serial-skip-is-allowed",
        ),
        pytest.param(
            """
            import pytest

            def test_fast():
                pytest.skip("not on this platform")

            @pytest.mark.word
            def test_word():
                pass
            """,
            0,
            "RESULT: PASSED",
            id="fast-phase-skip-is-not-required-coverage",
        ),
        pytest.param(
            """
            def test_fast():
                pass
            """,
            10,
            "collected no tests",
            id="phase-with-no-tests-is-incomplete",
        ),
        pytest.param(
            """
            import does_not_exist

            def test_fast():
                pass
            """,
            1,
            "RESULT: FAILED",
            id="collection-error-is-failed",
        ),
        pytest.param(
            """
            import pytest

            def test_fast():
                assert False

            @pytest.mark.word
            def test_word():
                pytest.skip("Word missing")
            """,
            1,
            "Word missing",
            id="failure-outranks-incomplete",
        ),
        pytest.param(
            """
            import pytest

            def test_fast():
                pass

            @pytest.mark.live_data
            def test_live():
                pytest.xfail("diagnosed data drift")
            """,
            0,
            "test_live: diagnosed data drift",
            id="allowance-passes-and-is-listed",
        ),
    ],
)
def test_full_run_verdict(
    tmp_path: Path, capfd: pytest.CaptureFixture[str], sample: str, expected_code: int, expected_text: str
) -> None:
    assert full_run(tmp_path, sample) == expected_code
    assert expected_text in capfd.readouterr().out


def test_full_run_summary_counts_each_outcome_separately(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    full_run(
        tmp_path,
        """
        import pytest

        def test_passes():
            pass

        def test_fails():
            assert False

        def test_skips():
            pytest.skip("sample")

        @pytest.mark.xfail(reason="sample")
        def test_xfails():
            assert False

        @pytest.mark.xfail(reason="sample", strict=False)
        def test_xpasses():
            pass

        @pytest.mark.word
        def test_word():
            pass
        """,
    )

    assert "executed=5 passed=2 failed=1 skipped=1 xfailed=1 xpassed=1" in capfd.readouterr().out


@pytest.mark.parametrize("process", ["WINWORD.EXE", "excel.exe"])
def test_full_run_with_office_open_is_incomplete_and_skips_serial_phase(
    tmp_path: Path, capfd: pytest.CaptureFixture[str], process: str
) -> None:
    assert full_run(tmp_path, PHASE_SAMPLE, processes=("explorer.exe", process)) == 10

    assert process in capfd.readouterr().out
    assert {record["phase"] for record in full_run_records(tmp_path)} == {"fast"}


def test_full_run_while_another_holds_the_lock_is_incomplete(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    with run_full_suite.full_run_lock(tmp_path / "full-run.lock") as acquired:
        assert acquired
        assert full_run(tmp_path, PHASE_SAMPLE) == 10

    assert "another Full Run" in capfd.readouterr().out
    assert {record["phase"] for record in full_run_records(tmp_path)} == {"fast"}


def _write_protected_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """Create a repo benchmark file and a live project file the runner should protect."""
    benchmark = tmp_path / "tests" / "benchmarks" / "report.docx"
    benchmark.parent.mkdir(parents=True)
    benchmark.write_text("original", encoding="utf-8")
    live = tmp_path / "live_project" / "testsheet.xlsx"
    live.parent.mkdir()
    live.write_text("original", encoding="utf-8")
    config = {"projects": {"sample": {"base_path": str(live.parent)}}}
    (tmp_path / ".cli_config.json").write_text(json.dumps(config), encoding="utf-8")
    return benchmark, live


def _sample_running(statement: str) -> str:
    return f"""
    from pathlib import Path
    import pytest

    def test_fast():
        pass

    @pytest.mark.word
    def test_word():
        {statement}
    """


def test_full_run_passes_when_protected_inputs_are_untouched(tmp_path: Path) -> None:
    _write_protected_inputs(tmp_path)

    assert full_run(tmp_path, PHASE_SAMPLE) == 0


def test_full_run_fails_when_benchmark_content_changes_at_same_size(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    benchmark, _ = _write_protected_inputs(tmp_path)
    stat = benchmark.stat()
    restore_time = f"import os; os.utime({str(benchmark)!r}, ns=({stat.st_atime_ns}, {stat.st_mtime_ns}))"

    code = full_run(
        tmp_path,
        _sample_running(f"Path({str(benchmark)!r}).write_text('modified', encoding='utf-8'); {restore_time}"),
    )

    assert code == 1
    assert "report.docx" in capfd.readouterr().out


@pytest.mark.parametrize(
    "statement",
    [
        "Path({live!r}).write_text('changed size', encoding='utf-8')",
        "Path({live!r}).with_name('added.xlsx').write_text('new', encoding='utf-8')",
        "Path({live!r}).unlink()",
    ],
    ids=["modified", "added", "deleted"],
)
def test_full_run_fails_when_a_live_project_file_changes(tmp_path: Path, statement: str) -> None:
    _, live = _write_protected_inputs(tmp_path)

    assert full_run(tmp_path, _sample_running(statement.format(live=str(live)))) == 1


def test_full_run_ignores_word_owner_lock_files_in_live_projects(tmp_path: Path) -> None:
    _, live = _write_protected_inputs(tmp_path)

    code = full_run(tmp_path, _sample_running(f"Path({str(live)!r}).with_name('~$report.docx').write_text('x')"))

    assert code == 0


@pytest.mark.parametrize("application", ["Word.Application", "Excel.Application"])
def test_guard_failure_survives_a_fixture_converting_the_error_to_a_skip(tmp_path: Path, application: str) -> None:
    output = run_pytest(
        tmp_path,
        f"""
        import pytest
        import win32com.client

        @pytest.fixture
        def office():
            try:
                return win32com.client.Dispatch("{application}")
            except Exception as exc:
                pytest.skip(f"Office is unavailable: {{exc}}")

        def test_uses_office(office):
            pass
        """,
    )

    assert "1 error" in output
    assert "@pytest.mark.word" in output
    assert "skipped" not in output


def test_full_run_phase_ending_abruptly_is_not_a_pass(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    code = full_run(tmp_path, _sample_running("import os; os._exit(0)"))

    assert code == 10
    assert "serial phase did not finish recording" in capfd.readouterr().out


def test_full_run_with_a_lost_xdist_worker_fails(tmp_path: Path) -> None:
    code = full_run(
        tmp_path,
        """
        import os
        import pytest

        def test_fast():
            os._exit(1)

        @pytest.mark.word
        def test_word():
            pass
        """,
    )

    assert code == 1


def test_full_run_counts_a_module_level_skip_as_missing_coverage(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "test_unavailable.py").write_text(
        'import pytest\npytestmark = pytest.mark.word\npytest.importorskip("no_such_module")\n',
        encoding="utf-8",
    )

    assert full_run(tmp_path, PHASE_SAMPLE) == 10
    assert "no_such_module" in capfd.readouterr().out


def test_full_run_ignores_inherited_pytest_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k test_fast_a")

    assert full_run(tmp_path, PHASE_SAMPLE) == 0
    assert len(full_run_records(tmp_path)) == 5


def test_full_run_lists_unexpected_passes_by_name(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    full_run(
        tmp_path,
        """
        import pytest

        @pytest.mark.xfail(reason="sample", strict=False)
        def test_now_works():
            pass

        @pytest.mark.word
        def test_word():
            pass
        """,
    )

    assert "unexpected pass: test_now_works" in capfd.readouterr().out


def test_full_run_with_unreadable_project_config_runs_both_phases_and_is_incomplete(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".cli_config.json").write_text("{not json", encoding="utf-8")

    assert full_run(tmp_path, PHASE_SAMPLE) == 10
    assert ".cli_config.json" in capfd.readouterr().out
    assert {record["phase"] for record in full_run_records(tmp_path)} == {"fast", "serial"}


def test_full_run_with_a_missing_project_folder_is_incomplete(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    config = {"projects": {"sample": {"base_path": str(tmp_path / "gone")}}}
    (tmp_path / ".cli_config.json").write_text(json.dumps(config), encoding="utf-8")

    assert full_run(tmp_path, PHASE_SAMPLE) == 10
    assert "gone" in capfd.readouterr().out


def test_full_run_protects_the_external_benchmark_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    external = tmp_path / "vault" / "report.docx"
    external.parent.mkdir()
    external.write_text("original", encoding="utf-8")
    monkeypatch.setenv("PAHANG_BENCHMARK_ROOT", str(external.parent))

    assert full_run(tmp_path, _sample_running(f"Path({str(external)!r}).write_text('changed size')")) == 1


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
