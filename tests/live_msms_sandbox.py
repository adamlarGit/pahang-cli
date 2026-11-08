"""Put a temporary copy of a live MSMS project back in its unprocessed state.

The live project has already been through Consolidate, Enrich and Propagate, so its
exports have moved to COMPLETED and its workbooks are filled in. These helpers undo
that in a copy, then compare the rebuilt workbooks with the live ones, which the
operator has confirmed are correct. Never pass them a live folder to modify.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import openpyxl

TOTAL_PE_SHEET = "DataCycle1"
NO_WORK_ORDER = "NO WORK ORDER"

# Work Orders shared by a 132/11kV and a 132/33kV row. Until #197 is fixed the pipeline
# fills only one of each pair, so these are the only values allowed to differ from live.
# Remove both constants, and the checks that use them, when #197 is fixed.
SHARED_WORK_ORDERS = frozenset({"W1616875", "W1616870"})
SHARED_WORK_ORDER_FLS = frozenset(
    {"CKTN/PMU/J00001", "CKTN/PMU/G00004", "CKLS/PMU/J00001", "CKLS/PMU/G00001"}
)

_ENRICHED_COLUMNS = {4: "substation name", 5: "FL", 6: "cycle date", 7: "substation number"}
_SHARED_WORK_ORDER_COLUMNS = frozenset({5, 7})


def clear_enrichment(data_msms: Path) -> None:
    """Blank the columns Enrich MSMS fills in."""
    wb = openpyxl.load_workbook(data_msms)
    ws = wb.active
    for row in range(2, ws.max_row + 1):
        for column in _ENRICHED_COLUMNS:
            ws.cell(row, column).value = None
    wb.save(data_msms)
    wb.close()


def clear_work_orders(total_pe: Path) -> None:
    """Blank the column Propagate WO fills in."""
    wb = openpyxl.load_workbook(total_pe)
    ws = wb[TOTAL_PE_SHEET]
    for row in range(2, ws.max_row + 1):
        ws.cell(row, 6).value = None
    wb.save(total_pe)
    wb.close()


def restore_unprocessed_python(python_dir: Path) -> None:
    """Undo Consolidate, Enrich and Propagate in a temporary copy of a PYTHON folder."""
    msms_dir = python_dir / "MSMS"
    for export in (msms_dir / "COMPLETED").glob("*.xls"):
        shutil.move(str(export), msms_dir / export.name)

    data_msms = python_dir / "DATA MSMS.xlsx"
    wb = openpyxl.load_workbook(data_msms)
    ws = wb.active
    ws.delete_rows(2, ws.max_row)
    wb.save(data_msms)
    wb.close()

    clear_work_orders(python_dir / "TOTAL PE.xlsx")


def read_data_msms(path: Path) -> dict[Any, tuple[Any, ...]]:
    """Return DATA MSMS rows keyed by Work Order."""
    wb = openpyxl.load_workbook(path, data_only=True)
    rows = {row[0]: row[:7] for row in wb.active.iter_rows(min_row=2, values_only=True) if row[0] not in (None, "")}
    wb.close()
    return rows


def read_work_orders(path: Path) -> dict[Any, Any]:
    """Return TOTAL PE Work Orders keyed by functional location."""
    wb = openpyxl.load_workbook(path, data_only=True)
    rows = wb[TOTAL_PE_SHEET].iter_rows(min_row=2, values_only=True)
    work_orders = {row[1]: row[5] for row in rows if row[1] not in (None, "")}
    wb.close()
    return work_orders


def assert_enrichment_matches_live(rebuilt_path: Path, live_path: Path) -> int:
    """Check every enriched cell against the live workbook and return the row count."""
    rebuilt = read_data_msms(rebuilt_path)
    live = read_data_msms(live_path)
    assert set(rebuilt) == set(live), "Rebuilt DATA MSMS has different Work Orders from live"

    for work_order, live_row in live.items():
        for column, label in _ENRICHED_COLUMNS.items():
            if work_order in SHARED_WORK_ORDERS and column in _SHARED_WORK_ORDER_COLUMNS:
                continue
            rebuilt_value = str(rebuilt[work_order][column - 1])[:10]
            live_value = str(live_row[column - 1])[:10]
            assert rebuilt_value == live_value, f"{work_order} {label}: {rebuilt_value!r} != live {live_value!r}"
    return len(live)


def assert_work_orders_match_live(rebuilt_path: Path, live_path: Path) -> int:
    """Check every propagated Work Order against live and return how many were written."""
    rebuilt = read_work_orders(rebuilt_path)
    live = read_work_orders(live_path)
    assert set(rebuilt) == set(live), "Rebuilt TOTAL PE has different functional locations from live"

    for fl, live_wo in live.items():
        if fl in SHARED_WORK_ORDER_FLS:
            assert rebuilt[fl] in (None, live_wo), f"{fl}: {rebuilt[fl]!r} is neither blank nor live {live_wo!r}"
        elif live_wo == NO_WORK_ORDER:
            assert rebuilt[fl] is None, f"{fl}: expected no Work Order, got {rebuilt[fl]!r}"
        else:
            assert rebuilt[fl] == live_wo, f"{fl}: {rebuilt[fl]!r} != live {live_wo!r}"
    return sum(1 for work_order in rebuilt.values() if work_order is not None)
