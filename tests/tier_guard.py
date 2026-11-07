"""Guard that stops tests without the `word` marker from starting real Word or Excel.

It wraps pywin32's low-level start functions and audits direct OS launches, so mocks
that never launch Office remain usable. A blocked start is recorded and fails the test when it is reported,
so a test cannot hide one with `except Exception`, a COM-error skip or an xfail marker.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import PureWindowsPath

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


def _is_office_file_or_class(target: object) -> bool:
    name = str(target).lower()
    # File monikers can select an item inside a workbook, e.g. book.xlsx!Sheet1.
    file_name = name.split("!", 1)[0]
    # MkParseDisplayName also accepts new:{CLSID} and clsid:CLSID: monikers.
    class_name = re.sub(r"^(?:new:|clsid:)", "", name).split(":", 1)[0]
    class_id = "{" + class_name.strip("{}") + "}"
    return class_id in _OFFICE_CLSIDS or file_name.endswith(_OFFICE_FILE_SUFFIXES)


def _is_office(target: object) -> bool:
    return str(target).lower().startswith(_OFFICE_PROGID_PREFIXES) or _is_office_file_or_class(target)


def _require_word_marker(target: object) -> None:
    if _current_item is not None and _current_item.get_closest_marker("word"):
        return
    where = _current_item.nodeid if _current_item else "Test collection"
    message = (
        f"{where} tried to start real {target} without the `word` marker. "
        "Use a fake, or mark the test with @pytest.mark.word."
    )
    if _current_item is not None:
        _blocked_starts.append(message)
    raise MissingWordMarker(message)


def _guarded(real_start):
    def guarded_start(target, *args, **kwargs):
        if _is_office(target):
            _require_word_marker(target)
        return real_start(target, *args, **kwargs)

    return guarded_start


def _is_office_command(command: object) -> bool:
    if isinstance(command, (list, tuple)):
        executable = os.fsdecode(command[0]) if command else ""
    else:
        # Windows command lines quote executable paths containing spaces.
        match = re.match(r'\s*(?:"([^"]+)"|(\S+))', os.fsdecode(command))
        executable = (match.group(1) or match.group(2)) if match else ""
    return PureWindowsPath(executable).name.lower() in {"winword", "winword.exe", "excel", "excel.exe"}


def _guard_launch(event: str, args: tuple) -> None:
    # Audit hooks preserve Popen's class identity and run before the OS launch.
    if event == "subprocess.Popen":
        executable, command = args[:2]
        target = [executable] if executable is not None else command
        if _is_office_command(target):
            _require_word_marker(target)
    elif event in {"os.startfile", "os.startfile/2"}:
        target = os.fsdecode(args[0])
        if _is_office_file_or_class(target) or _is_office_command([target]):
            _require_word_marker(target)


def is_installed() -> bool:
    return _installed


def install_guard() -> None:
    """Guard COM and direct OS launches. Call once, before test collection."""
    global _installed
    if _installed:
        return
    try:
        import pythoncom
    except ImportError:
        pythoncom = None
    if pythoncom is not None:
        for name in _START_FUNCTIONS:
            setattr(pythoncom, name, _guarded(getattr(pythoncom, name)))
    sys.addaudithook(_guard_launch)
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
