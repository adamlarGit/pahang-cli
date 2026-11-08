"""Suite-wide test configuration."""

from __future__ import annotations

import os
import shutil
import tempfile

from src.run_records import RECORD_DIR_OVERRIDE_VARIABLE
from tests.tier_guard import install_guard, pytest_runtest_makereport, pytest_runtest_protocol  # noqa: F401

install_guard()

_record_dir: str | None = None


def pytest_configure() -> None:
    """Send every Run Record written during a test run to a temporary folder.

    This has to be the default for the whole suite, not something a test opts in
    to. Any test that runs an action, including one that reads the active project,
    would otherwise write into a real project's logs/ folder or the real
    %LOCALAPPDATA%. An environment variable also covers subprocesses and xdist
    workers. tests/test_run_records.py lifts it only inside tmp_path.
    """
    global _record_dir
    _record_dir = tempfile.mkdtemp(prefix="pahang-test-run-records-")
    os.environ[RECORD_DIR_OVERRIDE_VARIABLE] = _record_dir


def pytest_unconfigure() -> None:
    os.environ.pop(RECORD_DIR_OVERRIDE_VARIABLE, None)
    if _record_dir is not None:
        shutil.rmtree(_record_dir, ignore_errors=True)
