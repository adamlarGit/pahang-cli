"""Unit tests for ProcessingHistoryStore in Pahang CLI."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.testsheet.models import SubstationTestsheetPackage
from src.workflows.history import ProcessingHistoryStore, format_package_history_key


def test_format_package_history_key() -> None:
    pkg = SubstationTestsheetPackage(
        station="RAUB",
        month="01. MAY",
        date_str="01-05-2026",
        substation_number=1,
        testsheet_path=Path("/tmp/testsheet.xlsx"),
        unsorted_raw_data_dir=Path("/tmp/UNSORTED RAW DATA"),
    )
    key = format_package_history_key(pkg)
    assert key == "RAUB/01. MAY/01-05-2026"


def test_processing_history_store_record_and_load(tmp_path: Path) -> None:
    history_file = tmp_path / "test_history.json"
    store = ProcessingHistoryStore(history_file)

    assert store.load() == {}

    pkg = SubstationTestsheetPackage(
        station="RAUB",
        month="01. MAY",
        date_str="01-05-2026",
        substation_number=1,
        testsheet_path=Path("/tmp/testsheet.xlsx"),
        unsorted_raw_data_dir=Path("/tmp/UNSORTED RAW DATA"),
    )

    recorded_keys = store.record_processed_packages([pkg])
    assert recorded_keys == ["RAUB/01. MAY/01-05-2026"]

    loaded_data = store.load()
    assert "RAUB/01. MAY/01-05-2026" in loaded_data
    assert loaded_data["RAUB/01. MAY/01-05-2026"]["files_scanned"] == 1
    assert "last_processed" in loaded_data["RAUB/01. MAY/01-05-2026"]
