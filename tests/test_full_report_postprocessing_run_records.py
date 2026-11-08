"""What a Full Report post-processing Run Record shows (#190), through the fake converter seam."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.postprocessing.converters import FakeDocumentConverter, convert_docx_native_restored
from src.project_workflow_actions import postprocess_full_reports_action
from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE, OperationCancelled
from src.workflow_cli import _run_recorded_action
from src.workflows.full_report_postprocessing import (
    FullReportPostProcessingWorkflow,
    TestsheetPdfNotFoundError,
)
from tests.test_full_report_postprocessing import _create_mock_docx, _create_mock_pdf, _make_mock_env
from tests.test_native_restored_conversion import NO_DELAYS, native_export, restoring

DATE = "04-08-2026"
SUBSTATION_STEP = "Full Report post-processing substation"


class _Converter(FakeDocumentConverter):
    """Raises the error set for any docx or merge output whose name contains the key."""

    def __init__(
        self,
        convert_raises: dict[str, Exception] | None = None,
        merge_raises: dict[str, Exception] | None = None,
        no_output: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self._convert_raises = convert_raises or {}
        self._merge_raises = merge_raises or {}
        self._no_output = no_output

    def convert_docx_to_pdf(self, docx_path, pdf_path, word_app=None, session=None, restore_images=True):
        for name, error in self._convert_raises.items():
            if name in docx_path.name:
                raise error
        return super().convert_docx_to_pdf(docx_path, pdf_path, word_app, session, restore_images)

    def merge_pdfs(self, primary_pdf, secondary_pdf, output_pdf):
        for name, error in self._merge_raises.items():
            if name in output_pdf.name:
                raise error
        if any(name in output_pdf.name for name in self._no_output):
            return output_pdf
        return super().merge_pdfs(primary_pdf, secondary_pdf, output_pdf)


class _RestoringConverter(FakeDocumentConverter):
    """Runs the real export-then-restore path with fake Word and fake restoration."""

    def __init__(self, restore) -> None:
        super().__init__()
        self._restore = restore

    def convert_docx_to_pdf(self, docx_path, pdf_path, word_app=None, session=None, restore_images=True):
        self.last_conversion = convert_docx_native_restored(
            docx_path, pdf_path, native_export(1), restore=self._restore, retry_delays=NO_DELAYS
        )
        return pdf_path


@pytest.fixture
def records(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "records"
    monkeypatch.setenv(RECORD_DIR_OVERRIDE_VARIABLE, str(folder))
    return folder


@pytest.fixture
def env(tmp_path):
    return _make_mock_env(tmp_path)


def _report_folder(env) -> Path:
    return env.base_path / "FULL REPORT" / "RAUB" / "08. AUGUST" / DATE


def _stem(number: int, name: str) -> str:
    return f"{number:03d}. {name} (IR)"


def _reports(env, names: list[str], missing_testsheet: tuple[str, ...] = ()) -> None:
    testsheets = env.base_path / "TESTSHEET" / "RAUB" / "08. AUGUST" / DATE / "processed_testsheet" / "pdf"
    for number, name in enumerate(names, start=1):
        _create_mock_docx(_report_folder(env) / f"{_stem(number, name)}.docx")
        if name not in missing_testsheet:
            _create_mock_pdf(testsheets / f"{_stem(number, name)}.pdf")


def _process(env, converter=None, target=DATE, **options) -> None:
    workflow = FullReportPostProcessingWorkflow(converter=converter or _Converter())
    _run_recorded_action(
        "Post-Process Full Reports", lambda: workflow.process(target, env, **options), env
    )


def _entries(records: Path) -> list[dict]:
    files = list(records.glob("*.jsonl"))
    assert len(files) == 1, f"expected one Run Record, found {files}"
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def _of_type(entries: list[dict], entry_type: str) -> list[dict]:
    return [entry for entry in entries if entry["type"] == entry_type]


def _finishes(entries: list[dict], name: str) -> dict[str, dict]:
    """One step's finishes, keyed by the substation stem in their item."""
    return {
        entry["item"][1]: entry
        for entry in _of_type(entries, "step_finish")
        if entry["name"] == name and "item" in entry
    }


def _step_names(entries: list[dict], stem: str) -> list[str]:
    return [
        entry["name"]
        for entry in _of_type(entries, "step_finish")
        if entry.get("item") == [DATE, stem]
    ]


def test_batch_keeps_one_record_with_timed_stages_for_each_substation(records, env) -> None:
    _reports(env, ["ONE", "TWO"])

    _process(env)

    entries = _entries(records)
    for stem in (_stem(1, "ONE"), _stem(2, "TWO")):
        assert _step_names(entries, stem) == [
            "Validate testsheet PDF",
            "Convert Full Report to PDF",
            "Merge testsheet PDF",
            "Embed survey ultrasound",
            SUBSTATION_STEP,
        ]
    for finish in _of_type(entries, "step_finish"):
        assert finish["status"] == "completed"
        assert isinstance(finish["duration_seconds"], float)
    assert entries[-1]["status"] == "completed"
    assert entries[-1]["counts"] == {"completed": 2, "failed": 0, "skipped": 0}
    assert len(_of_type(entries, "output")) == 2


def test_stages_sit_inside_the_substation_step(records, env) -> None:
    _reports(env, ["ONE"])

    _process(env)

    stem = _stem(1, "ONE")
    timeline = [
        (entry["type"], entry["name"])
        for entry in _entries(records)
        if entry["type"] in ("step_start", "step_finish") and entry.get("item") == [DATE, stem]
    ]
    opened = timeline.index(("step_start", SUBSTATION_STEP))
    closed = timeline.index(("step_finish", SUBSTATION_STEP))
    assert ("step_finish", "Convert Full Report to PDF") in timeline[opened:closed]
    assert ("step_finish", "Merge testsheet PDF") in timeline[opened:closed]


def test_multipart_report_has_a_conversion_per_part_and_both_merges(records, env) -> None:
    folder = _report_folder(env)
    stem = _stem(1, "ONE")
    _create_mock_docx(folder / f"{stem} - Part 01.docx")
    _create_mock_docx(folder / f"{stem} - Part 02.docx")
    _create_mock_pdf(env.base_path / "TESTSHEET" / "RAUB" / "08. AUGUST" / DATE / "processed_testsheet" / "pdf" / f"{stem}.pdf")

    _process(env)

    entries = _entries(records)
    assert _step_names(entries, stem) == [
        "Validate testsheet PDF",
        "Convert Full Report to PDF",
        "Convert Full Report to PDF",
        "Merge Full Report parts",
        "Merge testsheet PDF",
        "Embed survey ultrasound",
        SUBSTATION_STEP,
    ]
    assert entries[-1]["counts"] == {"completed": 1, "failed": 0, "skipped": 0}


def test_word_restart_between_substations_is_timed_inside_the_later_one(records, env) -> None:
    class Session:
        word_app = None

        def restart_word(self) -> bool:
            return True

    _reports(env, ["ONE", "TWO"])

    _process(env, com_session=Session())

    entries = _entries(records)
    assert "Restart Word" not in _step_names(entries, _stem(1, "ONE"))
    assert "Restart Word" in _step_names(entries, _stem(2, "TWO"))


def test_a_word_restart_failure_is_a_warning_and_the_substation_still_completes(records, env) -> None:
    class Session:
        word_app = None

        def restart_word(self) -> bool:
            raise RuntimeError("Word would not restart")

    _reports(env, ["ONE", "TWO"])

    _process(env, com_session=Session())

    entries = _entries(records)
    assert any("Word would not restart" in w["message"] for w in _of_type(entries, "warning"))
    assert entries[-1]["status"] == "completed"
    assert entries[-1]["counts"] == {"completed": 2, "failed": 0, "skipped": 0}


def test_failed_validation_is_identifiable_and_later_substations_continue(records, env) -> None:
    _reports(env, ["BAD", "GOOD"], missing_testsheet=("BAD",))
    converter = _Converter()

    _process(env, converter)

    entries = _entries(records)
    bad, good = _stem(1, "BAD"), _stem(2, "GOOD")
    assert _finishes(entries, "Validate testsheet PDF")[bad]["status"] == "failed"
    assert _finishes(entries, SUBSTATION_STEP)[bad]["status"] == "failed"
    assert "Convert Full Report to PDF" not in _step_names(entries, bad)
    assert _finishes(entries, SUBSTATION_STEP)[good]["status"] == "completed"
    assert len([e for e in _of_type(entries, "error") if bad in e["message"]]) == 1
    assert entries[-1]["status"] == "partial_failure"
    assert entries[-1]["counts"] == {"completed": 1, "failed": 1, "skipped": 0}
    assert len(converter.convert_docx_calls) == 1


def test_failed_validation_with_fail_fast_stops_before_any_conversion(records, env) -> None:
    _reports(env, ["BAD", "GOOD"], missing_testsheet=("BAD",))
    converter = _Converter()

    _process(env, converter, fail_fast=True)

    entries = _entries(records)
    bad = _stem(1, "BAD")
    assert converter.convert_docx_calls == []
    assert _finishes(entries, SUBSTATION_STEP)[bad]["status"] == "failed"
    assert len(_of_type(entries, "error")) == 1
    assert _of_type(entries, "error")[0]["exception_type"] == TestsheetPdfNotFoundError.__name__
    assert entries[-1]["status"] == "failed"


@pytest.mark.parametrize(
    ("converter", "failing_stage"),
    [
        (_Converter(convert_raises={"BAD": RuntimeError("Word lost the document")}), "Convert Full Report to PDF"),
        (_Converter(merge_raises={"BAD": RuntimeError("merge lost the document")}), "Merge testsheet PDF"),
    ],
)
def test_conversion_or_merge_failure_is_identifiable_with_a_traceback(
    records, env, capsys, converter, failing_stage
) -> None:
    _reports(env, ["BAD", "GOOD"])

    _process(env, converter)

    entries = _entries(records)
    bad, good = _stem(1, "BAD"), _stem(2, "GOOD")
    assert _finishes(entries, failing_stage)[bad]["status"] == "failed"
    assert _finishes(entries, SUBSTATION_STEP)[bad]["status"] == "failed"
    assert _finishes(entries, SUBSTATION_STEP)[good]["status"] == "completed"
    errors = [e for e in _of_type(entries, "error") if bad in e["message"]]
    assert len(errors) == 1
    assert "lost the document" in errors[0]["traceback"]
    assert entries[-1]["status"] == "partial_failure"
    assert f"Run Record: {next(records.glob('*.jsonl'))}" in capsys.readouterr().out


def test_failure_with_fail_fast_stops_the_batch_and_records_one_error(records, env) -> None:
    _reports(env, ["BAD", "GOOD"])
    converter = _Converter(convert_raises={"BAD": RuntimeError("Word lost the document")})

    _process(env, converter, fail_fast=True)

    entries = _entries(records)
    assert _finishes(entries, SUBSTATION_STEP)[_stem(1, "BAD")]["status"] == "failed"
    assert _stem(2, "GOOD") not in _finishes(entries, SUBSTATION_STEP)
    assert len(_of_type(entries, "error")) == 1
    assert entries[-1]["status"] == "failed"
    assert entries[-1]["counts"] == {"completed": 0, "failed": 1, "skipped": 0}


def test_a_returned_error_cannot_be_recorded_as_success(records, env) -> None:
    _reports(env, ["EMPTY", "GOOD"])

    _process(env, _Converter(no_output=("EMPTY",)))

    entries = _entries(records)
    empty = _stem(1, "EMPTY")
    assert _finishes(entries, SUBSTATION_STEP)[empty]["status"] == "failed"
    assert len([e for e in _of_type(entries, "error") if empty in e["message"]]) == 1
    assert entries[-1]["status"] == "partial_failure"
    assert entries[-1]["counts"] == {"completed": 1, "failed": 1, "skipped": 0}


def test_a_folder_locked_by_another_run_fails_its_substations(records, env) -> None:
    _reports(env, ["ONE", "TWO"])

    with patch("src.workflows.full_report_postprocessing.FolderLock.acquire", return_value=None):
        _process(env)

    entries = _entries(records)
    assert {finish["status"] for finish in _finishes(entries, SUBSTATION_STEP).values()} == {"failed"}
    assert entries[-1]["status"] == "failed"
    assert entries[-1]["counts"] == {"completed": 0, "failed": 2, "skipped": 0}


def test_nine_successes_and_one_failure_is_a_partial_failure(records, env) -> None:
    names = [f"PE {letter}" for letter in "ABCDEFGHIJ"]
    _reports(env, names)

    _process(env, _Converter(convert_raises={"PE H": RuntimeError("broken")}))

    entries = _entries(records)
    assert entries[-1]["status"] == "partial_failure"
    assert entries[-1]["counts"] == {"completed": 9, "failed": 1, "skipped": 0}
    assert len(_of_type(entries, "output")) == 9


def test_every_substation_failing_is_a_failed_run(records, env, capsys) -> None:
    _reports(env, ["ONE", "TWO"])

    _process(env, _Converter(convert_raises={"ONE": RuntimeError("x"), "TWO": RuntimeError("x")}))

    entries = _entries(records)
    assert entries[-1]["status"] == "failed"
    assert entries[-1]["counts"] == {"completed": 0, "failed": 2, "skipped": 0}
    assert "Run Record:" in capsys.readouterr().out


def test_no_documents_found_is_a_failed_run(records, env) -> None:
    _process(env, target="01-01-2026")

    entries = _entries(records)
    assert entries[-1]["status"] == "failed"
    assert len(_of_type(entries, "error")) == 1
    assert entries[-1]["counts"]["completed"] == 0


def test_cancelling_after_a_completed_substation_keeps_its_output(records, env, capsys) -> None:
    _reports(env, ["DONE", "STOPPED", "LATER"])
    converter = _Converter(convert_raises={"STOPPED": OperationCancelled("Operator stopped")})

    _process(env, converter)

    entries = _entries(records)
    done, stopped = _stem(1, "DONE"), _stem(2, "STOPPED")
    assert _finishes(entries, SUBSTATION_STEP)[done]["status"] == "completed"
    assert _finishes(entries, SUBSTATION_STEP)[stopped]["status"] == "cancelled"
    assert _stem(3, "LATER") not in _finishes(entries, SUBSTATION_STEP)
    assert [Path(e["path"]).name for e in _of_type(entries, "output")] == [f"{done}.pdf"]
    assert (_report_folder(env) / f"{done}.pdf").exists()
    assert _of_type(entries, "error") == []
    assert entries[-1]["status"] == "cancelled"
    assert entries[-1]["counts"] == {"completed": 1, "failed": 0, "skipped": 0}
    assert "Run Record:" not in capsys.readouterr().out


def test_ctrl_c_after_a_completed_substation_is_cancelled_and_keeps_its_output(records, env, capsys) -> None:
    _reports(env, ["DONE", "STOPPED", "LATER"])

    with pytest.raises(KeyboardInterrupt):
        _process(env, _Converter(convert_raises={"STOPPED": KeyboardInterrupt()}))

    entries = _entries(records)
    done, stopped = _stem(1, "DONE"), _stem(2, "STOPPED")
    assert _finishes(entries, SUBSTATION_STEP)[done]["status"] == "completed"
    assert _finishes(entries, SUBSTATION_STEP)[stopped]["status"] == "cancelled"
    assert [Path(e["path"]).name for e in _of_type(entries, "output")] == [f"{done}.pdf"]
    assert _of_type(entries, "error") == []
    assert entries[-1]["status"] == "cancelled"
    assert entries[-1]["counts"] == {"completed": 1, "failed": 0, "skipped": 0}
    assert "Run Record:" not in capsys.readouterr().out


def test_ctrl_c_after_a_failed_substation_still_shows_the_record_path(records, env, capsys) -> None:
    _reports(env, ["BAD", "STOPPED"])
    converter = _Converter(convert_raises={"BAD": RuntimeError("broken"), "STOPPED": KeyboardInterrupt()})

    with pytest.raises(KeyboardInterrupt):
        _process(env, converter)

    entries = _entries(records)
    assert entries[-1]["status"] == "cancelled"
    assert entries[-1]["counts"] == {"completed": 0, "failed": 1, "skipped": 0}
    assert f"Run Record: {next(records.glob('*.jsonl'))}" in capsys.readouterr().out


def test_request_and_actual_inputs_are_recorded_without_copies(records, env) -> None:
    _reports(env, ["ONE"])
    stem = _stem(1, "ONE")

    _process(env, _Converter())

    entries = _entries(records)
    request = _of_type(entries, "request")[0]["request"]
    assert request == {
        "workflow": "Full Report Post-Processing",
        "target": DATE,
        "station": None,
        "fail_fast": False,
        "output_dir": None,
    }
    inputs = {Path(entry["path"]).name: entry for entry in _of_type(entries, "input")}
    for name in (f"{stem}.docx", f"{stem}.pdf"):
        assert inputs[name]["exists"] is True
        assert inputs[name]["size"] > 0
        assert inputs[name]["modified"]
        assert set(inputs[name]) == {"type", "time", "path", "exists", "size", "modified"}


def test_no_step_is_open_while_the_operator_is_prompted(records, env) -> None:
    _reports(env, ["ONE"])
    workflow = FullReportPostProcessingWorkflow(converter=_Converter())
    open_steps_at_prompts: list[int] = []

    def note_open_steps() -> None:
        entries = _entries(records)
        open_steps_at_prompts.append(len(_of_type(entries, "step_start")) - len(_of_type(entries, "step_finish")))

    def choose(targets, **_options):
        note_open_steps()
        return list(targets)

    def confirm(*_args, **_options):
        note_open_steps()
        return True

    with (
        patch("src.project_workflow_actions.cli_selectors.select_substations_interactive", side_effect=choose),
        patch("src.project_workflow_actions.cli_selectors.confirm", side_effect=confirm),
    ):
        _run_recorded_action(
            "Post-Process Full Reports",
            lambda: postprocess_full_reports_action(env, workflow=workflow, target=str(_report_folder(env))),
            env,
        )

    assert open_steps_at_prompts == [0, 0]
    entries = _entries(records)
    assert [e["status"] for e in _of_type(entries, "step_finish") if e["name"] == "Inspect Full Report documents"] == [
        "completed"
    ]
    assert entries[-1]["status"] == "completed"


def test_not_ready_substation_found_by_inspection_is_a_warning(records, env) -> None:
    _reports(env, ["BAD"], missing_testsheet=("BAD",))
    workflow = FullReportPostProcessingWorkflow(converter=_Converter())

    _run_recorded_action("Inspect", lambda: workflow.inspect(DATE, env), env)

    entries = _entries(records)
    assert [w for w in _of_type(entries, "warning") if _stem(1, "BAD") in w["message"]]
    assert entries[-1]["status"] == "completed"


def test_restoration_outside_a_batch_leaves_the_result_counts_alone(records, tmp_path) -> None:
    docx = _create_mock_docx(tmp_path / DATE / "X - Part 01.docx")

    def action():
        convert_docx_native_restored(
            docx, tmp_path / "out.pdf", native_export(1), restore=restoring(), retry_delays=NO_DELAYS
        )
        return SimpleNamespace(converted_count=1, failed_count=0)

    _run_recorded_action("Convert", action)

    assert _entries(records)[-1]["counts"] == {"completed": 1, "failed": 0, "skipped": "unknown"}


def test_an_inspection_error_is_recorded_when_other_targets_are_found(records, env) -> None:
    _reports(env, ["ONE"])
    missing = _report_folder(env) / "002. GONE (IR).docx"
    targets = [_report_folder(env) / f"{_stem(1, 'ONE')}.docx", missing]
    workflow = FullReportPostProcessingWorkflow(converter=_Converter())

    _run_recorded_action("Inspect", lambda: workflow.inspect(targets, env), env)

    entries = _entries(records)
    assert [e for e in _of_type(entries, "error") if "GONE" in e["message"]]
    assert entries[-1]["status"] == "partial_failure"


def test_restoration_is_timed_inside_the_conversion_with_the_same_identity(records, env) -> None:
    folder = _report_folder(env)
    stem = _stem(1, "ONE")
    _create_mock_docx(folder / f"{stem} - Part 01.docx")
    _create_mock_pdf(env.base_path / "TESTSHEET" / "RAUB" / "08. AUGUST" / DATE / "processed_testsheet" / "pdf" / f"{stem}.pdf")

    _process(env, _RestoringConverter(restoring()))

    entries = _entries(records)
    names = _step_names(entries, stem)
    assert names.index("Restore source images") < names.index("Convert Full Report to PDF")
    assert _finishes(entries, "Restore source images")[stem]["status"] == "completed"


def test_restoration_falling_back_is_a_warning_and_the_substation_still_completes(records, env) -> None:
    _reports(env, ["ONE"])

    def failing_restore(snapshot, native, out):
        raise RuntimeError("restoration exploded")

    _process(env, _RestoringConverter(failing_restore))

    entries = _entries(records)
    stem = _stem(1, "ONE")
    assert _finishes(entries, "Restore source images")[stem]["status"] == "completed"
    assert _finishes(entries, SUBSTATION_STEP)[stem]["status"] == "completed"
    assert any("restoration exploded" in w["message"] for w in _of_type(entries, "warning"))
    assert entries[-1]["status"] == "completed"
    assert entries[-1]["counts"] == {"completed": 1, "failed": 0, "skipped": 0}
