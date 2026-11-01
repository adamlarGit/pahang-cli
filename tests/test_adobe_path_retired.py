"""Ticket #148: the Adobe PDF virtual-printer path is gone; the native path and session printer setup remain."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.postprocessing as postprocessing
import src.postprocessing.converters as converters
from src.postprocessing.converters import (
    BatchComSession,
    ComDocumentConverter,
    FakeDocumentConverter,
)

TRY_ADOBE = "try_adobe_" + "printer"

RETIRED_MODULE_SYMBOLS = (
    "terminate_stray_acrobat_processes",
    "terminate_hung_dis" + "tiller_processes",
    "ensure_session_dis" + "tiller_warmed",
    "_ensure_session_dis" + "tiller_warmed",
    "_terminate_processes_by_filter",
    "drain_word_spooler",
    "get_printer_jobs_info",
    "get_active_printer_job_ids",
    "wait_for_printer_job_drain",
    "purge_printer_" + "jobs",
    "ConversionFeedback" + "Monitor",
    "ConversionFeedbackState",
    "compute_dynamic_conversion_timeout",
    "probe_two_tier_pdf_completion",
)

RETIRED_CONVERTER_METHODS = (
    "_convert_docx_via_adobe_pdf",
    "_find_adobe_pdf_printer",
    "_is_dis" + "tiller_available",
    "_export_fixed_format_isolated",
    "_configure_adobe_printer",
    "_wait_for_pdf",
    "get_conversion_timeout",
    "_register_printer_job_control",
    "_cleanup_printer_job_control",
    "_suppress_view_print_output",
    "_detect_dis" + "tiller_joboptions_preset",
    "_set_transient_dis" + "tiller_joboptions",
    "_restore_dis" + "tiller_joboptions",
)


@pytest.mark.parametrize("name", RETIRED_MODULE_SYMBOLS)
def test_retired_module_symbols_are_gone(name: str) -> None:
    assert not hasattr(converters, name)
    assert not hasattr(postprocessing, name)


@pytest.mark.parametrize("name", RETIRED_CONVERTER_METHODS)
def test_retired_converter_methods_are_gone(name: str) -> None:
    assert not hasattr(ComDocumentConverter, name)
    assert not hasattr(FakeDocumentConverter, name)


@pytest.mark.parametrize("cls", [ComDocumentConverter, FakeDocumentConverter])
def test_converters_reject_the_adobe_options(cls: type) -> None:
    params = inspect.signature(cls.__init__).parameters
    assert TRY_ADOBE not in params
    assert "adobe_timeout" not in params
    with pytest.raises(TypeError):
        cls(**{TRY_ADOBE: False})


def test_batch_com_session_has_no_distiller_state() -> None:
    session = BatchComSession(word_app=MagicMock(), excel_app=MagicMock())
    with session:
        assert not hasattr(session, "dis" + "tiller_app")


def test_batch_session_never_warms_a_distiller(monkeypatch) -> None:
    dispatched: list[str] = []
    monkeypatch.setattr("win32com.client.Dispatch", lambda prog_id, *a, **k: dispatched.append(prog_id))
    with BatchComSession(word_app=MagicMock(), excel_app=MagicMock()):
        pass
    assert dispatched == []


def test_configure_uniform_printer_runs_once_per_batch_session_for_each_app() -> None:
    word, excel = MagicMock(), MagicMock()
    with (
        patch("src.postprocessing.converters._start_word", return_value=word) as start_word,
        patch("src.postprocessing.converters.configure_uniform_printer") as configure,
        patch("win32com.client.DispatchEx", return_value=excel),
        patch("pythoncom.CoInitialize"),
        patch("pythoncom.CoUninitialize"),
    ):
        with BatchComSession():
            pass
    start_word.assert_called_once_with(True)  # _start_word configures Word itself
    configure.assert_called_once_with(excel)


def test_safe_unlink_with_retry_is_a_plain_retrying_unlink(tmp_path: Path) -> None:
    f = tmp_path / "locked.tmp"
    f.write_text("x")
    attempts = {"n": 0}
    real_unlink = Path.unlink

    def flaky(self, *a, **k):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise PermissionError("locked")
        return real_unlink(self, *a, **k)

    with patch.object(Path, "unlink", flaky), patch("time.sleep"):
        assert converters.safe_unlink_with_retry(f, max_attempts=5, total_wait=1.0) is True
    assert attempts["n"] == 3
    assert not f.exists()


def test_safe_replace_with_retry_is_a_plain_retrying_replace(tmp_path: Path) -> None:
    src, dst = tmp_path / "s.tmp", tmp_path / "d.tmp"
    src.write_text("new")
    dst.write_text("old")
    attempts = {"n": 0}
    import os

    real_replace = os.replace

    def flaky(a, b):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise PermissionError("locked")
        return real_replace(a, b)

    with patch("os.replace", flaky), patch("time.sleep"):
        assert converters.safe_replace_with_retry(src, dst, max_attempts=3, total_wait=1.0) is True
    assert dst.read_text() == "new"
    assert attempts["n"] == 2


def test_retry_helpers_do_not_scan_for_processes(tmp_path: Path) -> None:
    source = inspect.getsource(converters)
    assert "wmi" not in source.lower()
    assert "acrobat" not in source.lower()


def test_configure_uniform_printer_is_applied_to_the_real_word_app_once_per_session() -> None:
    word, excel = MagicMock(), MagicMock()
    with (
        patch("win32com.client.DispatchEx", side_effect=[word, excel]),
        patch("src.postprocessing.converters.configure_uniform_printer") as configure,
        patch("pythoncom.CoInitialize"),
        patch("pythoncom.CoUninitialize"),
    ):
        with BatchComSession():
            pass
    assert [c.args[0] for c in configure.call_args_list] == [word, excel]
