"""What a Full Report generation Run Record shows (#185), through the fake Word seams."""

from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.full_report.slicer import FakeDocumentSlicer
from src.quick_report.compiler import FakeDocumentCompiler
from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE, OperationCancelled, current_run
from src.workflow_cli import _run_recorded_action
from src.workflows.full_report import FullReportWorkflow
from tests.test_full_report_workflow import (
    _create_mock_qr_docx,
    _make_mock_env,
    _make_sample_pkg,
)

DATE = "04-08-2026"
STAGES = [
    "Preflight Quick Report",
    "Slice Quick Report",
    "Build Full Report plan",
    "Render Full Report parts",
    "Compile Full Report",
    "Full Report substation",
]


class _Compiler(FakeDocumentCompiler):
    """Raises the error set for any output whose name contains the key."""

    def __init__(self, raises: dict[str, Exception] | None = None) -> None:
        super().__init__()
        self._raises = raises or {}

    def compile(self, parts, output_path):
        for name, error in self._raises.items():
            if name in Path(output_path).name:
                raise error
        return super().compile(parts, output_path)


@pytest.fixture
def records(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "records"
    monkeypatch.setenv(RECORD_DIR_OVERRIDE_VARIABLE, str(folder))
    return folder


@pytest.fixture
def env(tmp_path):
    return _make_mock_env(tmp_path)


def _packages(env, names: list[str], undersized: tuple[str, ...] = ()):
    folder = env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / DATE
    packages = []
    for number, name in enumerate(names, start=1):
        size = 100 if name in undersized else 1_200_000
        _create_mock_qr_docx(folder / f"{number:03d}. {name} (IR).docx", target_size_bytes=size)
        packages.append(_make_sample_pkg(pe_number=number, station_name=name, station="RAUB"))
    return packages


def _generate(env, packages, compiler=None) -> None:
    workflow = FullReportWorkflow(compiler=compiler or _Compiler(), slicer=FakeDocumentSlicer())
    _run_recorded_action("Generate Full Reports", lambda: workflow.generate(packages, env), env)


def _entries(records: Path) -> list[dict]:
    files = list(records.glob("*.jsonl"))
    assert len(files) == 1, f"expected one Run Record, found {files}"
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def _finishes(entries: list[dict]) -> dict[tuple, dict]:
    """Step finishes for one substation, keyed by (step name, substation)."""
    return {
        (entry["name"], entry["item"][1]): entry
        for entry in entries
        if entry["type"] == "step_finish" and "item" in entry
    }


def _entries_of_type(entries: list[dict], entry_type: str) -> list[dict]:
    return [entry for entry in entries if entry["type"] == entry_type]


def test_batch_keeps_one_record_with_timed_stages_for_each_substation(records, env) -> None:
    _generate(env, _packages(env, ["PE ONE", "PE TWO"]))

    entries = _entries(records)
    finishes = _finishes(entries)
    for substation in ("PE ONE", "PE TWO"):
        for stage in STAGES:
            finish = finishes[(stage, substation)]
            assert finish["status"] == "completed"
            assert finish["item"] == [DATE, substation]
            assert isinstance(finish["duration_seconds"], float)
    assert entries[-1]["status"] == "completed"
    assert entries[-1]["counts"] == {"completed": 2, "failed": 0, "skipped": 0}


def test_discovery_has_its_own_timed_step(records, env) -> None:
    _generate(env, _packages(env, ["PE ONE"]))

    steps = [e for e in _entries_of_type(_entries(records), "step_finish") if e["name"] == "Discover Full Report packages"]
    assert [step["status"] for step in steps] == ["completed"]
    assert "item" not in steps[0]


def test_preflight_rejection_is_identifiable_and_later_substations_continue(records, env) -> None:
    _generate(env, _packages(env, ["PE BAD", "PE GOOD"], undersized=("PE BAD",)))

    entries = _entries(records)
    finishes = _finishes(entries)
    assert finishes[("Preflight Quick Report", "PE BAD")]["status"] == "failed"
    assert finishes[("Full Report substation", "PE BAD")]["status"] == "failed"
    assert ("Slice Quick Report", "PE BAD") not in finishes
    assert finishes[("Full Report substation", "PE GOOD")]["status"] == "completed"
    assert len([e for e in _entries_of_type(entries, "error") if "PE BAD" in e["message"]]) == 1
    assert entries[-1]["status"] == "partial_failure"
    assert entries[-1]["counts"] == {"completed": 1, "failed": 1, "skipped": 0}


def test_generation_failure_is_identifiable_with_a_traceback(records, env, capsys) -> None:
    compiler = _Compiler({"PE BAD": RuntimeError("Word lost the document")})

    _generate(env, _packages(env, ["PE BAD", "PE GOOD"]), compiler)

    entries = _entries(records)
    finishes = _finishes(entries)
    assert finishes[("Compile Full Report", "PE BAD")]["status"] == "failed"
    assert "Word lost the document" in finishes[("Compile Full Report", "PE BAD")]["error"]
    assert finishes[("Full Report substation", "PE BAD")]["status"] == "failed"
    assert finishes[("Full Report substation", "PE GOOD")]["status"] == "completed"
    errors = [e for e in _entries_of_type(entries, "error") if "PE BAD" in e["message"]]
    assert len(errors) == 1
    assert "Word lost the document" in errors[0]["traceback"]
    assert f"Run Record: {next(records.glob('*.jsonl'))}" in capsys.readouterr().out


def test_nine_successes_and_one_failure_is_a_partial_failure(records, env) -> None:
    names = [f"PE {number}" for number in range(10)]
    compiler = _Compiler({"PE 7": RuntimeError("broken")})

    _generate(env, _packages(env, names), compiler)

    finish = _entries(records)[-1]
    assert finish["status"] == "partial_failure"
    assert finish["counts"] == {"completed": 9, "failed": 1, "skipped": 0}


def test_every_substation_failing_is_a_failed_run(records, env) -> None:
    _generate(env, _packages(env, ["PE ONE", "PE TWO"], undersized=("PE ONE", "PE TWO")))

    finish = _entries(records)[-1]
    assert finish["status"] == "failed"
    assert finish["counts"] == {"completed": 0, "failed": 2, "skipped": 0}


def test_deliverable_rejected_after_compile_is_not_recorded_as_success(records, env) -> None:
    with patch("src.workflows.full_report.inspect_deliverable_attribution", return_value=(False, "wrong substation")):
        _generate(env, _packages(env, ["PE ONE"]))

    entries = _entries(records)
    assert _finishes(entries)[("Full Report substation", "PE ONE")]["status"] == "failed"
    assert len([e for e in _entries_of_type(entries, "error") if "attribution" in e["message"]]) == 1
    assert entries[-1]["counts"]["failed"] == 1
    assert not _entries_of_type(entries, "output")


def test_cancel_after_completed_substations_keeps_outputs_and_is_not_an_error(records, env) -> None:
    compiler = _Compiler({"PE TWO": OperationCancelled("Operator stopped")})

    _generate(env, _packages(env, ["PE ONE", "PE TWO", "PE THREE"]), compiler)

    entries = _entries(records)
    assert entries[-1]["status"] == "cancelled"
    assert entries[-1]["counts"] == {"completed": 1, "failed": 0, "skipped": 0}
    assert not _entries_of_type(entries, "error")
    outputs = [Path(entry["path"]).name for entry in _entries_of_type(entries, "output")]
    assert len(outputs) == 1 and "PE ONE" in outputs[0]
    assert _finishes(entries)[("Full Report substation", "PE TWO")]["status"] == "cancelled"
    assert ("Full Report substation", "PE THREE") not in _finishes(entries)


def test_discovery_error_returned_by_the_workflow_is_not_a_completed_step(records, env) -> None:
    workflow = FullReportWorkflow(compiler=_Compiler(), slicer=FakeDocumentSlicer())

    def discover(*args, **kwargs):
        current_run().record_error("Package discovery failed: boom", item="discovery")
        return [], [], ["Package discovery failed: boom"]

    with patch.object(FullReportWorkflow, "_discover_packages", side_effect=discover):
        _run_recorded_action("Generate Full Reports", lambda: workflow.generate(["FL1"], env), env)

    entries = _entries(records)
    step = next(e for e in _entries_of_type(entries, "step_finish") if e["name"] == "Discover Full Report packages")
    assert step["status"] == "failed"
    assert len(_entries_of_type(entries, "error")) == 1
    assert entries[-1]["status"] == "failed"


def test_request_and_actual_inputs_are_recorded_without_copies(records, env) -> None:
    packages = _packages(env, ["PE ONE"])
    census = env.get_full_report_census_template()
    census.parent.mkdir(parents=True, exist_ok=True)
    census.write_bytes(b"census")
    quick_report = next((env.get_quick_report_dir() / "RAUB" / "08. AUGUST" / DATE).glob("*.docx")).resolve()

    _generate(env, packages)

    entries = _entries(records)
    assert _entries_of_type(entries, "request")[0]["request"]["workflow"] == "Full Report"
    inputs = {entry["path"]: entry for entry in _entries_of_type(entries, "input")}
    for path, size in ((quick_report, quick_report.stat().st_size), (census, 6)):
        assert inputs[str(path)]["size"] == size
        assert inputs[str(path)]["modified"]


def test_rejection_found_while_inspecting_is_in_the_record_without_failing_it(records, env) -> None:
    packages = _packages(env, ["PE BAD", "PE GOOD"], undersized=("PE BAD",))
    workflow = FullReportWorkflow(compiler=_Compiler(), slicer=FakeDocumentSlicer())

    _run_recorded_action("Generate Full Reports", lambda: workflow.inspect(packages, env), env)

    entries = _entries(records)
    assert len([e for e in _entries_of_type(entries, "warning") if "PE BAD" in e["message"]]) == 1
    assert not [e for e in _entries_of_type(entries, "warning") if "PE GOOD" in e["message"] and "floor" in e["message"]]
    assert entries[-1]["status"] == "completed"


def test_word_failing_to_start_is_counted_against_its_substation(records, env) -> None:
    class _FailsToStart:
        def __enter__(self):
            raise RuntimeError("Word would not start")

        def __exit__(self, *details):
            return False

    packages = _packages(env, ["PE ONE", "PE TWO", "PE THREE"])
    sessions = [nullcontext(), _FailsToStart()]

    with patch.object(FullReportWorkflow, "_establish_batch_session", side_effect=sessions):
        _generate(env, packages)

    entries = _entries(records)
    assert entries[-1]["status"] == "failed"
    assert entries[-1]["counts"] == {"completed": 1, "failed": 1, "skipped": 0}
    finish = _finishes(entries)[("Start Word session", "PE TWO")]
    assert finish["status"] == "failed"
    errors = _entries_of_type(entries, "error")
    assert len(errors) == 1 and "PE TWO" in errors[0]["message"]


def test_no_step_is_open_while_the_operator_is_prompted(records, env) -> None:
    from src.project_workflow_actions import generate_full_reports_action

    packages = _packages(env, ["PE ONE"])
    workflow = FullReportWorkflow(compiler=_Compiler(), slicer=FakeDocumentSlicer())
    open_steps: list[int] = []

    def prompt(*args, **kwargs):
        lines = [json.loads(line) for line in current_run().path.read_text(encoding="utf-8").splitlines()]
        open_steps.append(len(_entries_of_type(lines, "step_start")) - len(_entries_of_type(lines, "step_finish")))
        return None

    with patch("src.project_workflow_actions.cli_selectors.select_substations_interactive", side_effect=prompt):
        _run_recorded_action(
            "Generate Full Reports",
            lambda: generate_full_reports_action(env, workflow=workflow, target=packages),
            env,
        )

    assert open_steps == [0]
    entries = _entries(records)
    assert [e["name"] for e in _entries_of_type(entries, "step_finish")] == ["Inspect Full Report targets"]
    assert entries[-1]["status"] == "cancelled"
