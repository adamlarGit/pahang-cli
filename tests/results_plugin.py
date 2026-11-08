"""Write one JSON Lines record per test, including tests run on xdist workers.

Load it with `-p tests.results_plugin`; plain pytest never loads it. Reports from
every worker reach the controller, so only the controller writes and each test is
recorded once. The Full Run runner reads these records, and #189 builds on them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_TIER_MARKERS = ("word", "live_data")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("results", "per-test result records")
    group.addoption("--results-file", help="JSON Lines file to append results to")
    group.addoption("--grouped-run-id", default="", help="ID shared by every phase of one run")
    group.addoption("--run-phase", default="", help="Name of this phase within the grouped run")


def pytest_configure(config: pytest.Config) -> None:
    results_file = config.getoption("--results-file")
    if results_file and not hasattr(config, "workerinput"):
        config.pluginmanager.register(_ResultWriter(config, Path(results_file)), "results-writer")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Attach marker facts as user properties, which xdist sends back with each report."""
    for item in items:
        tier = "+".join(name for name in _TIER_MARKERS if item.get_closest_marker(name)) or "fast"
        item.user_properties.append(("tier", tier))
        optional = item.get_closest_marker("optional")
        if optional is not None and optional.args:
            item.user_properties.append(("optional_reason", str(optional.args[0])))


def _skip_reason(report: pytest.TestReport) -> str:
    if isinstance(report.longrepr, tuple):
        return str(report.longrepr[2])
    return str(report.longrepr)


class _ResultWriter:
    def __init__(self, config: pytest.Config, path: Path) -> None:
        self._run_id = config.getoption("--grouped-run-id")
        self._phase = config.getoption("--run-phase")
        self._path = path
        self._pending: dict[str, dict[str, Any]] = {}
        self._collection_skips: set[str] = set()

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        record = self._pending.setdefault(
            report.nodeid,
            {"outcome": "passed", "reason": "", "durations": {"setup": 0.0, "call": 0.0, "teardown": 0.0}},
        )
        if report.when in record["durations"]:
            record["durations"][report.when] = report.duration
        record.update(dict(report.user_properties))

        if report.failed:
            record["outcome"] = "failed"
        elif record["outcome"] == "failed":
            pass
        elif hasattr(report, "wasxfail"):
            record["outcome"] = "xfailed" if report.skipped else "xpassed"
            record["reason"] = report.wasxfail
        elif report.skipped:
            record["outcome"] = "skipped"
            record["reason"] = _skip_reason(report)

        # An xdist worker crash is reported once, with no teardown to follow.
        if report.when not in ("setup", "call"):
            self._write(report.nodeid)

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        """Record a module-level skip once, since each xdist worker reports it."""
        if report.skipped and report.nodeid not in self._collection_skips:
            self._collection_skips.add(report.nodeid)
            reason = str(report.longrepr[2]) if isinstance(report.longrepr, tuple) else str(report.longrepr)
            self._append(
                {"test_id": report.nodeid, "tier": "unknown", "outcome": "skipped", "reason": reason, "collection": True}
            )

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        for test_id in list(self._pending):
            self._write(test_id)
        self._append({"event": "phase_end", "collected": session.testscollected})

    def _write(self, test_id: str) -> None:
        record = self._pending.pop(test_id)
        self._append({"test_id": test_id, "tier": "fast", **record})

    def _append(self, entry: dict[str, Any]) -> None:
        line = {"run_id": self._run_id, "phase": self._phase, **entry}
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(line) + "\n")
