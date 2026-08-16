"""Unit and integration tests for Ingest MSMS CSV Workflow (src/workflows/ingest_msms_csv.py)."""

from __future__ import annotations

import hashlib
from pathlib import Path
import pytest

from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.ingest_msms_csv import (
    IngestMsmsCsvAuditor,
    IngestMsmsCsvExtractor,
    IngestMsmsCsvFilter,
    IngestMsmsCsvLoader,
    IngestMsmsCsvPlan,
    IngestMsmsCsvPreflightGuard,
    IngestMsmsCsvTransformer,
    IngestMsmsCsvWorkflow,
    extract_date_from_filename,
)
from src.workflows.models import IngestMsmsCsvRequest, IngestMsmsCsvResult


@pytest.fixture
def mock_env(tmp_path: Path) -> ProjectEnvironment:
    meta = ProjectMetadata(
        key="pahang_2026",
        name="Pahang 2026 Test",
        po_number="PO42289580",
        state="Pahang",
        voltage_type="11kV",
        year="2026",
        cycle="2",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(tmp_path),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    return ProjectEnvironment(metadata=meta, storage=storage)


SAMPLE_CSV_HEADER = "WONUM,TNBLOCATION,METERNAME,METER.DESCRIPTION,TNBNEWREADING,TNBNEWREADINGDATE,ACTSTART,ACTFINISH,TNBCOMMENTS\n"
SAMPLE_CSV_ROW = "200000000001,CCHL/PCEJ00002/11KV/1,TH_S11_RMUCBL1_AVG_PE13R,PCE: TH RMU: Cable Comp 1 Avg Temp,,,,,\n"


def test_extract_date_from_filename_variants() -> None:
    # DDMMYYYY suffix
    assert extract_date_from_filename("TNBWOCREATEWOMETER_02062026.csv") == "02-06-2026"
    assert extract_date_from_filename("TNBWOCREATEWOMETER_12082026.csv") == "12-08-2026"

    # DD-MM-YYYY suffix / prefix
    assert extract_date_from_filename("CBMS_05-08-2026.csv") == "05-08-2026"
    assert extract_date_from_filename("05-08-2026_001.csv") == "05-08-2026"
    assert extract_date_from_filename("15-12-2026.csv") == "15-12-2026"

    # DD.MM.YYYY
    assert extract_date_from_filename("04.08.2026.csv") == "04-08-2026"
    assert extract_date_from_filename("PCE_DATA_04.08.2026_EXPORT.csv") == "04-08-2026"

    # DD_MM_YYYY
    assert extract_date_from_filename("DATA_04_08_2026.csv") == "04-08-2026"

    # ISO YYYY-MM-DD
    assert extract_date_from_filename("MSMS_2026-08-04.csv") == "04-08-2026"
    assert extract_date_from_filename("2026-08-04.csv") == "04-08-2026"

    # Invalid / Unparseable
    with pytest.raises(ValueError, match="Could not extract valid date"):
        extract_date_from_filename("random_filename_without_date.csv")

    with pytest.raises(ValueError, match="Could not extract valid date"):
        extract_date_from_filename("99999999.csv")


def test_preflight_guard_missing_raw_dir(mock_env: ProjectEnvironment) -> None:
    assert mock_env.storage.get_msms_dir() == mock_env.storage.root_path / "PYTHON" / "MSMS"
    assert mock_env.storage.get_msms_raw_data_dir() == mock_env.storage.root_path / "PYTHON" / "MSMS" / "RAW DATA"
    assert mock_env.storage.get_msms_to_be_filled_dir() == mock_env.storage.root_path / "PYTHON" / "MSMS" / "TO BE FILLED"
    assert mock_env.storage.get_msms_completed_dir() == mock_env.storage.root_path / "PYTHON" / "MSMS" / "COMPLETED"

    guard = IngestMsmsCsvPreflightGuard()
    with pytest.raises(FileNotFoundError, match="MSMS RAW DATA directory not found"):
        guard.validate(mock_env)


def test_preflight_guard_empty_raw_dir(mock_env: ProjectEnvironment) -> None:
    raw_dir = mock_env.storage.get_msms_raw_data_dir()
    raw_dir.mkdir(parents=True)
    guard = IngestMsmsCsvPreflightGuard()
    with pytest.raises(FileNotFoundError, match="No CSV files found in RAW DATA"):
        guard.validate(mock_env)


def test_extractor_validates_required_headers(tmp_path: Path) -> None:
    extractor = IngestMsmsCsvExtractor()
    raw_dir = tmp_path / "RAW"
    raw_dir.mkdir()

    # Valid CSV
    valid_csv = raw_dir / "valid.csv"
    valid_csv.write_text(SAMPLE_CSV_HEADER + SAMPLE_CSV_ROW, encoding="utf-8")

    files = extractor.extract_files(raw_dir)
    assert len(files) == 1
    assert files[0] == valid_csv

    # Invalid CSV (missing METERNAME)
    invalid_csv = raw_dir / "invalid.csv"
    invalid_csv.write_text("WONUM,TNBLOCATION,SOME_OTHER_COL\n1,2,3\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing required CSV headers"):
        extractor.extract_files(raw_dir)


def test_filter_skips_content_hash_duplicates(tmp_path: Path) -> None:
    filter_stage = IngestMsmsCsvFilter()
    raw_dir = tmp_path / "RAW"
    to_be_filled_dir = tmp_path / "FILLED"
    raw_dir.mkdir()
    to_be_filled_dir.mkdir()

    content1 = SAMPLE_CSV_HEADER + SAMPLE_CSV_ROW
    content2 = SAMPLE_CSV_HEADER + "200000000002,CCHL/PCEJ00002/11KV/2,TH_S11_RMUCBL2_AVG_PE13R,Desc,,,,,\n"

    # File already existing in to_be_filled
    existing_file = to_be_filled_dir / "02-06-2026_001.csv"
    existing_file.write_text(content1, encoding="utf-8")

    # Raw files: one identical to existing, one new
    raw1 = raw_dir / "TNBWOCREATEWOMETER_02062026.csv"
    raw1.write_text(content1, encoding="utf-8")

    raw2 = raw_dir / "CBMS_05-08-2026.csv"
    raw2.write_text(content2, encoding="utf-8")

    to_process, duplicates = filter_stage.filter_files([raw1, raw2], to_be_filled_dir)
    assert to_process == [raw2]
    assert duplicates == [raw1]


def test_transformer_builds_canonical_names_and_increments_indices(tmp_path: Path) -> None:
    transformer = IngestMsmsCsvTransformer()
    to_be_filled_dir = tmp_path / "FILLED"
    to_be_filled_dir.mkdir()

    # Pre-existing file on 05-08-2026
    (to_be_filled_dir / "05-08-2026_001.csv").write_text("dummy", encoding="utf-8")

    raw1 = tmp_path / "CBMS_05-08-2026.csv"
    raw2 = tmp_path / "CBMS_05-08-2026_second.csv"
    raw3 = tmp_path / "04.08.2026.csv"

    plan = transformer.build_plan([raw1, raw2, raw3], to_be_filled_dir, duplicates=[])

    assert len(plan.mappings) == 3
    # 05-08-2026 should get index 002 and 003
    assert plan.mappings[0] == (raw1, to_be_filled_dir / "05-08-2026_002.csv")
    assert plan.mappings[1] == (raw2, to_be_filled_dir / "05-08-2026_003.csv")
    # 04-08-2026 starts at 001
    assert plan.mappings[2] == (raw3, to_be_filled_dir / "04-08-2026_001.csv")


def test_workflow_end_to_end_moves_files(mock_env: ProjectEnvironment) -> None:
    raw_dir = mock_env.storage.get_msms_raw_data_dir()
    filled_dir = mock_env.storage.get_msms_to_be_filled_dir()
    raw_dir.mkdir(parents=True)
    filled_dir.mkdir(parents=True)

    f1 = raw_dir / "TNBWOCREATEWOMETER_02062026.csv"
    f1.write_text(SAMPLE_CSV_HEADER + SAMPLE_CSV_ROW, encoding="utf-8")

    f2 = raw_dir / "04.08.2026.csv"
    f2.write_text(SAMPLE_CSV_HEADER + "200000000002,LOC,METER,DESC,,,,,\n", encoding="utf-8")

    workflow = IngestMsmsCsvWorkflow()
    request = IngestMsmsCsvRequest()
    result = workflow.execute(mock_env, request)

    assert result.files_ingested == 2
    assert result.files_skipped_duplicate == 0
    assert len(result.ingested_files) == 2

    # Files moved from raw to filled
    assert not f1.exists()
    assert not f2.exists()
    assert (filled_dir / "02-06-2026_001.csv").exists()
    assert (filled_dir / "04-08-2026_001.csv").exists()


def test_workflow_ingest_from_python_msms_to_be_filled(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    python_to_be_filled = tmp_path / "PYTHON" / "MSMS" / "TO BE FILLED"
    python_to_be_filled.mkdir(parents=True)

    raw_file = python_to_be_filled / "TNBWOCREATEWOMETER_02062026.csv"
    raw_file.write_text(SAMPLE_CSV_HEADER + SAMPLE_CSV_ROW, encoding="utf-8")

    workflow = IngestMsmsCsvWorkflow()
    result = workflow.execute(mock_env)

    assert result.files_ingested == 1
    assert result.files_skipped_duplicate == 0
    assert not raw_file.exists()
    canonical_file = python_to_be_filled / "02-06-2026_001.csv"
    assert canonical_file.exists()
    assert canonical_file.read_text(encoding="utf-8") == SAMPLE_CSV_HEADER + SAMPLE_CSV_ROW


def test_workflow_ingest_from_python_msms_raw_data(mock_env: ProjectEnvironment, tmp_path: Path) -> None:
    python_raw = tmp_path / "PYTHON" / "MSMS" / "RAW DATA"
    python_raw.mkdir(parents=True)

    raw_file = python_raw / "CBMS_05-08-2026.csv"
    raw_file.write_text(SAMPLE_CSV_HEADER + SAMPLE_CSV_ROW, encoding="utf-8")

    workflow = IngestMsmsCsvWorkflow()
    result = workflow.execute(mock_env)

    assert result.files_ingested == 1
    assert result.files_skipped_duplicate == 0
    assert not raw_file.exists()
    # Should be placed into the resolved to_be_filled directory
    to_be_filled_dir = mock_env.storage.get_msms_to_be_filled_dir()
    canonical_file = to_be_filled_dir / "05-08-2026_001.csv"
    assert canonical_file.exists()

