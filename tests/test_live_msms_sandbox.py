"""The live-MSMS sandbox undoes processing in a copy and allows only the #197 differences."""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from tests.live_msms_sandbox import (
    TOTAL_PE_SHEET,
    assert_enrichment_matches_live,
    assert_work_orders_match_live,
    read_data_msms,
    read_work_orders,
    restore_unprocessed_python,
)


def _write_msms(path: Path, rows: list[list[object]]) -> None:
    wb = openpyxl.Workbook()
    wb.active.append(["WO", "LOC", "DESC", "NAME", "FL", "DATE", "NO"])
    for row in rows:
        wb.active.append(row)
    wb.save(path)


def _write_pe(path: Path, rows: list[tuple[str, str | None]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = TOTAL_PE_SHEET
    ws.append(["NO", "FL", "NAME", "DATE", "TYPE", "WO"])
    for number, (fl, work_order) in enumerate(rows, start=1):
        ws.append([number, fl, "NAME", "2026-10-07", "PMU", work_order])
    wb.save(path)


def test_restore_returns_exports_and_clears_processed_data(tmp_path: Path) -> None:
    python_dir = tmp_path / "PYTHON"
    (python_dir / "MSMS" / "COMPLETED").mkdir(parents=True)
    (python_dir / "MSMS" / "COMPLETED" / "1.xls").write_text("export", encoding="utf-8")
    _write_msms(python_dir / "DATA MSMS.xlsx", [["W1", "L", "D", "N", "F", "2026-10-07", 1]])
    _write_pe(python_dir / "TOTAL PE.xlsx", [("A/B/C", "W1")])

    restore_unprocessed_python(python_dir)

    assert (python_dir / "MSMS" / "1.xls").exists()
    assert not (python_dir / "MSMS" / "COMPLETED" / "1.xls").exists()
    assert read_data_msms(python_dir / "DATA MSMS.xlsx") == {}
    assert read_work_orders(python_dir / "TOTAL PE.xlsx") == {"A/B/C": None}


def test_shared_work_order_row_may_stay_blank_until_197(tmp_path: Path) -> None:
    rebuilt, live = tmp_path / "rebuilt.xlsx", tmp_path / "live.xlsx"
    _write_pe(rebuilt, [("CKTN/PMU/J00001", "W1616875"), ("CKTN/PMU/G00004", None), ("A/B/C", None)])
    _write_pe(live, [("CKTN/PMU/J00001", "W1616875"), ("CKTN/PMU/G00004", "W1616875"), ("A/B/C", "NO WORK ORDER")])

    assert assert_work_orders_match_live(rebuilt, live) == 1


def test_wrong_work_order_on_an_ordinary_row_still_fails(tmp_path: Path) -> None:
    rebuilt, live = tmp_path / "rebuilt.xlsx", tmp_path / "live.xlsx"
    _write_pe(rebuilt, [("A/B/C", "W2")])
    _write_pe(live, [("A/B/C", "W1")])

    with pytest.raises(AssertionError, match="A/B/C"):
        assert_work_orders_match_live(rebuilt, live)


def test_wrong_value_on_a_shared_work_order_row_still_fails(tmp_path: Path) -> None:
    rebuilt, live = tmp_path / "rebuilt.xlsx", tmp_path / "live.xlsx"
    _write_pe(rebuilt, [("CKTN/PMU/G00004", "W9")])
    _write_pe(live, [("CKTN/PMU/G00004", "W1616875")])

    with pytest.raises(AssertionError, match="CKTN/PMU/G00004"):
        assert_work_orders_match_live(rebuilt, live)


def test_enrichment_allows_only_the_shared_fl_and_number(tmp_path: Path) -> None:
    rebuilt, live = tmp_path / "rebuilt.xlsx", tmp_path / "live.xlsx"
    _write_msms(rebuilt, [["W1616875", "L", "D", "NAME", "CKTN/PMU/J00001", "2026-10-10", 12]])
    _write_msms(live, [["W1616875", "L", "D", "NAME", "CKTN/PMU/G00004", "2026-10-10", 13]])

    assert assert_enrichment_matches_live(rebuilt, live) == 1

    _write_msms(rebuilt, [["W1616875", "L", "D", "OTHER", "CKTN/PMU/J00001", "2026-10-10", 12]])
    with pytest.raises(AssertionError, match="substation name"):
        assert_enrichment_matches_live(rebuilt, live)


def test_enrichment_difference_on_an_ordinary_work_order_still_fails(tmp_path: Path) -> None:
    rebuilt, live = tmp_path / "rebuilt.xlsx", tmp_path / "live.xlsx"
    _write_msms(rebuilt, [["W1", "L", "D", "NAME", "X/Y/Z", "2026-10-10", 1]])
    _write_msms(live, [["W1", "L", "D", "NAME", "A/B/C", "2026-10-10", 1]])

    with pytest.raises(AssertionError, match="W1 FL"):
        assert_enrichment_matches_live(rebuilt, live)
