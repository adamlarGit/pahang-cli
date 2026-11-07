"""Guard that stops tests without the `word` marker from starting real Word or Excel.

It wraps pywin32's low-level start functions, so mocks of `win32com.client.Dispatch` and
friends never reach it. A blocked start is recorded and fails the test when it is reported,
so a test cannot hide one with `except Exception`, a COM-error skip or an xfail marker.
"""
from __future__ import annotations

import pytest

_OFFICE_PROGID_PREFIXES = ("word.", "excel.")
_OFFICE_CLSIDS = {
    "{000209ff-0000-0000-c000-000000000046}",  # Word.Application
    "{00024500-0000-0000-c000-000000000046}",  # Excel.Application
}
_START_FUNCTIONS = ("connect", "CoCreateInstance", "CoCreateInstanceEx", "GetActiveObject")

_current_item: pytest.Item | None = None
_blocked_starts: list[str] = []
_installed = False


class MissingWordMarker(RuntimeError):
    """An unmarked test tried to start real Word or Excel."""


def _is_office(target: object) -> bool:
    name = str(target).lower()
    return name.startswith(_OFFICE_PROGID_PREFIXES) or name in _OFFICE_CLSIDS


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


def pytest_configure(config: pytest.Config) -> None:
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
