"""Unit tests for WorkspaceStorage MSMS directory extensions."""
from pathlib import Path
import pytest

from src.project.storage import LocalWorkspaceStorage, WorkspaceStorage


def test_workspace_storage_msms_path_resolvers(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path)
    
    assert storage.get_msms_dir() == tmp_path / "PYTHON" / "MSMS"
    assert storage.get_msms_raw_data_dir() == tmp_path / "PYTHON" / "MSMS" / "RAW DATA"
    assert storage.get_msms_to_be_filled_dir() == tmp_path / "PYTHON" / "MSMS" / "TO BE FILLED"
    assert storage.get_msms_completed_dir() == tmp_path / "PYTHON" / "MSMS" / "COMPLETED"
    assert storage.get_python_msms_dir() == tmp_path / "PYTHON" / "MSMS"
    assert storage.get_python_msms_completed_dir() == tmp_path / "PYTHON" / "MSMS" / "COMPLETED"
    assert storage.get_data_msms_path() == tmp_path / "PYTHON" / "DATA MSMS.xlsx"


def test_workspace_storage_initialization_creates_msms_folders(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path)
    storage._initialize_project_workspace()
    
    assert storage.get_msms_dir().is_dir()
    assert storage.get_msms_raw_data_dir().is_dir()
    assert storage.get_msms_to_be_filled_dir().is_dir()
    assert storage.get_msms_completed_dir().is_dir()
    assert storage.get_python_msms_dir().is_dir()
    assert storage.get_python_msms_completed_dir().is_dir()
    assert not (tmp_path / "MSMS").exists()


def test_workspace_storage_list_msms_files(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path)
    
    # When directories do not exist yet
    assert storage.list_msms_xls_files() == []
    assert storage.list_msms_raw_csv_files() == []
    assert storage.list_msms_to_be_filled_csv_files() == []
    
    # Create directories and mock files
    msms_dir = storage.get_msms_dir()
    msms_dir.mkdir(parents=True, exist_ok=True)
    (msms_dir / "b_wo.xls").touch()
    (msms_dir / "a_wo.xls").touch()
    (msms_dir / "notes.txt").touch()
    
    raw_dir = storage.get_msms_raw_data_dir()
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "2026-01-02.csv").touch()
    (raw_dir / "2026-01-01.csv").touch()
    
    to_be_filled_dir = storage.get_msms_to_be_filled_dir()
    to_be_filled_dir.mkdir(parents=True, exist_ok=True)
    (to_be_filled_dir / "pending.csv").touch()
    
    xls_files = storage.list_msms_xls_files()
    assert len(xls_files) == 2
    assert xls_files[0].name == "a_wo.xls"
    assert xls_files[1].name == "b_wo.xls"
    
    raw_csvs = storage.list_msms_raw_csv_files()
    assert len(raw_csvs) == 2
    assert raw_csvs[0].name == "2026-01-01.csv"
    assert raw_csvs[1].name == "2026-01-02.csv"
    
    filled_csvs = storage.list_msms_to_be_filled_csv_files()
    assert len(filled_csvs) == 1
    assert filled_csvs[0].name == "pending.csv"


def test_repositories_workspace_storage_import() -> None:
    # Verify module re-export from src.repositories.workspace_storage
    from src.repositories.workspace_storage import LocalWorkspaceStorage as RepStorage
    from src.repositories.workspace_storage import WorkspaceStorage as RepStorageABC
    assert RepStorage is LocalWorkspaceStorage
    assert RepStorageABC is WorkspaceStorage


def test_workspace_storage_raw_csv_fallback_discovery(tmp_path: Path) -> None:
    storage = LocalWorkspaceStorage(tmp_path)

    # 1. When RAW DATA is empty / nonexistent, discover non-canonical CSVs from TO BE FILLED
    to_be_filled = storage.get_msms_to_be_filled_dir()
    to_be_filled.mkdir(parents=True, exist_ok=True)
    (to_be_filled / "TNBWOCREATEWOMETER_02062026.csv").touch()
    (to_be_filled / "02-06-2026_001.csv").touch()

    raw_files = storage.list_msms_raw_csv_files()
    assert len(raw_files) == 1
    assert raw_files[0].name == "TNBWOCREATEWOMETER_02062026.csv"

    # 2. When RAW DATA has CSVs, it takes precedence and TO BE FILLED is not checked
    raw_dir = storage.get_msms_raw_data_dir()
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "raw_export.csv").touch()

    raw_files_2 = storage.list_msms_raw_csv_files()
    assert len(raw_files_2) == 1
    assert raw_files_2[0].name == "raw_export.csv"

    # Root MSMS folder is never created or touched
    assert not (tmp_path / "MSMS").exists()

