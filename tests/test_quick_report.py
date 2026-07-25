"""Tests for the Quick Report Generation engine."""

from __future__ import annotations

import pytest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.quick_report.utils import normalize_functional_location_input
from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID
from src.quick_report.cbm_render import prepare_tech_summary_rows
from src.quick_report.composer import QuickReportComposer
from src.workflows.models import QuickReportResult, QuickReportRequest, QuickReportMode
from src.project.environment import ProjectEnvironment


def test_fl_normalization():
    """Verify functional location normalization."""
    assert normalize_functional_location_input(" F/L 12345 ") == "12345"
    assert normalize_functional_location_input("f/l 12345") == "12345"
    assert normalize_functional_location_input("12345") == "12345"
    assert normalize_functional_location_input("  F/L   AB-CD  ") == "AB-CD"


def test_quick_report_result_enrichment():
    """Verify QuickReportResult fields."""
    result = QuickReportResult(
        reports_generated=2,
        generated_paths=[Path("a.docx"), Path("b.docx")],
        warnings=["Warn 1"],
        errors=["Err 1"]
    )
    assert result.reports_generated == 2
    assert len(result.generated_paths) == 2
    assert len(result.warnings) == 1
    assert len(result.errors) == 1


def test_family_spec_lookup():
    """Verify all 5 CBM family specs are registered."""
    assert "fp_lvdb" in QUICK_REPORT_FAMILY_SPECS_BY_ID
    assert "swg" in QUICK_REPORT_FAMILY_SPECS_BY_ID
    assert "tx" in QUICK_REPORT_FAMILY_SPECS_BY_ID
    assert "blackbox" in QUICK_REPORT_FAMILY_SPECS_BY_ID
    assert "battery" in QUICK_REPORT_FAMILY_SPECS_BY_ID


def test_cbm_tech_summary_pairing():
    """Verify CBM tech summary 1-to-1 IR/US/TEV pairing behavior."""
    defects = [
        {"equipment": "RMU", "defect_area": "Area 1", "additional_remarks": "Remark 1", "technology": "IR", "temperature": "54.2"},
        {"equipment": "RMU", "defect_area": "Area 1", "additional_remarks": "Remark 1", "technology": "US", "us_value": "12.0"},
        {"equipment": "RMU", "defect_area": "Area 1", "additional_remarks": "Remark 1", "technology": "TEV", "tev_value": "24.0"},
        {"equipment": "TX", "defect_area": "Area 2", "additional_remarks": "", "technology": "IR", "temperature": "45.0"},
    ]
    rows = prepare_tech_summary_rows(defects)
    assert len(rows) == 2
    
    rmu_row = next(r for r in rows if r.equipment == "RMU")
    assert rmu_row.ir_reading == "54.2 °C"
    assert rmu_row.us_reading == "12dB"
    assert rmu_row.tev_reading == "24dB"
    
    tx_row = next(r for r in rows if r.equipment == "TX")
    assert tx_row.ir_reading == "45.0 °C"
    assert tx_row.us_reading == "-"
    assert tx_row.tev_reading == "-"


@patch("src.quick_report.composer.SubstationTestsheetRepository")
def test_composer_error_isolation(mock_repo_cls):
    """Verify failure in one station does not abort batch."""
    mock_repo = Mock()
    mock_repo_cls.return_value = mock_repo
    
    pkg1 = MagicMock()
    pkg1.station = "STATION 1"
    pkg1.data = MagicMock()
    
    pkg2 = MagicMock()
    pkg2.station = "STATION 2"
    pkg2.data = MagicMock()
    
    mock_repo.discover_packages.return_value = [pkg1, pkg2]
    
    composer = QuickReportComposer()
    
    # Force pkg1 to raise an error during processing
    with patch.object(composer, "_process_station", side_effect=[Exception("Mock Error"), Path("out2.docx")]):
        env = MagicMock(spec=ProjectEnvironment)
        
        # Use mock Path to avoid real filesystem exists() check
        mock_dir = MagicMock()
        mock_folder = MagicMock()
        mock_folder.exists.return_value = True
        mock_dir.__truediv__.return_value = mock_folder
        env.get_testsheet_dir.return_value = mock_dir
        
        req = QuickReportRequest(mode=QuickReportMode.FOLDER, target_folders=["01-01-2026"])
        
        result = composer.compose(env, req)
        
        assert result.reports_generated == 1
        assert len(result.generated_paths) == 1
        assert result.generated_paths[0] == Path("out2.docx")
        assert len(result.errors) == 1
        assert "Mock Error" in result.errors[0]
        assert "STATION 1" in result.errors[0]


def test_suffix_calculation():
    """Verify Canonical IR+US+TEV+VI suffix generation."""
    composer = QuickReportComposer()
    
    assert composer._calculate_suffix([], []) == ""
    assert composer._calculate_suffix([{"technology": "IR"}], []) == " (IR)"
    assert composer._calculate_suffix([{"technology": "IR"}, {"technology": "US"}], []) == " (IR+US)"
    assert composer._calculate_suffix([{"technology": "IR"}, {"technology": "TEV"}], [{"id": "1"}]) == " (IR+TEV+VI)"
    assert composer._calculate_suffix([], [{"id": "1"}]) == " (VI)"
    assert composer._calculate_suffix([{"technology": "TEV"}], []) == " (TEV)"
