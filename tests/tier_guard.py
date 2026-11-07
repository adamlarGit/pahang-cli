"""Guard that stops tests without the `word` marker from starting real Word or Excel.

It wraps pywin32's low-level start functions, so mocks of `win32com.client.Dispatch` and
friends never reach it. A blocked start is recorded and fails the test when it is reported,
so a test cannot hide one with `except Exception`, a COM-error skip or an xfail marker.
"""
from __future__ import annotations

import re

import pytest

_OFFICE_PROGID_PREFIXES = ("word.", "excel.")
_OFFICE_CLSIDS = {
    "{000209ff-0000-0000-c000-000000000046}",  # Word.Application
    "{00024500-0000-0000-c000-000000000046}",  # Excel.Application
}
_OFFICE_FILE_SUFFIXES = (
    ".doc", ".docx", ".docm", ".dot", ".dotx", ".dotm", ".rtf",
    ".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".xltm", ".csv",
)
_START_FUNCTIONS = ("connect", "CoCreateInstance", "CoCreateInstanceEx", "GetActiveObject", "MkParseDisplayName")

_current_item: pytest.Item | None = None
_blocked_starts: list[str] = []
_installed = False


class MissingWordMarker(RuntimeError):
    """An unmarked test tried to start real Word or Excel."""


def _is_office(target: object) -> bool:
    name = str(target).lower()
    # File monikers can select an item inside a workbook, e.g. book.xlsx!Sheet1.
    file_name = name.split("!", 1)[0]
    # MkParseDisplayName also accepts new:{CLSID} and clsid:CLSID: monikers.
    class_name = re.sub(r"^(?:new:|clsid:)", "", name).split(":", 1)[0]
    class_id = "{" + class_name.strip("{}") + "}"
    return (
        name.startswith(_OFFICE_PROGID_PREFIXES)
        or class_id in _OFFICE_CLSIDS
        or file_name.endswith(_OFFICE_FILE_SUFFIXES)
    )


def _guarded(real_start):
    def guarded_start(target, *args, **kwargs):
        if _is_office(target) and (_current_item is None or not _current_item.get_closest_marker("word")):
            where = _current_item.nodeid if _current_item else "Test collection"
            message = (
                f"{where} tried to start real {target} without the `word` marker. "
                "Use a fake, or mark the test with @pytest.mark.word."
            )
            if _current_item is not None:
                _blocked_starts.append(message)
            raise MissingWordMarker(message)
        return real_start(target, *args, **kwargs)

    return guarded_start


def is_installed() -> bool:
    return _installed


def install_guard() -> None:
    """Wrap pywin32's start functions. Call once, before any test is collected."""
    global _installed
    if _installed:
        return
    try:
        import pythoncom
    except ImportError:
        return
    for name in _START_FUNCTIONS:
        setattr(pythoncom, name, _guarded(getattr(pythoncom, name)))
    _installed = True


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):
    global _current_item
    _current_item = item
    _blocked_starts.clear()
    try:
        return (yield)
    finally:
        _current_item = None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    report = yield
    if _blocked_starts:
        report.outcome = "failed"
        report.longrepr = "\n".join(_blocked_starts)
        if hasattr(report, "wasxfail"):
            del report.wasxfail
        _blocked_starts.clear()
    return report
