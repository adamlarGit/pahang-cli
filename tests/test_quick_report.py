"""Tests for the Quick Report Generation engine."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.project.environment import ProjectEnvironment
from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID
from src.quick_report.cbm_summary import prepare_tech_summary_rows
from src.quick_report.composer import QuickReportComposer
from src.quick_report.defects import CbmDefectRecord, MasterQr03DefectRepository, ViDefectRecord
from src.quick_report.extractor import QuickReportExtractor
from src.quick_report.models import QuickReportStationPlan
from src.quick_report.transformer import QuickReportTransformer
from src.quick_report.utils import normalize_functional_location_input
from src.workflows.models import QuickReportMode, QuickReportRequest, QuickReportResult
from src.workflows.quick_report import QuickReportWorkflow


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
        errors=["Err 1"],
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
        CbmDefectRecord(
            equipment="RMU",
            defect_area="Area 1",
            additional_remarks="Remark 1",
            technology="IR",
            raw_measurement="54.2",
        ),
        CbmDefectRecord(
            equipment="RMU",
            defect_area="Area 1",
            additional_remarks="Remark 1",
            technology="US",
            raw_measurement="12.0",
        ),
        CbmDefectRecord(
            equipment="RMU",
            defect_area="Area 1",
            additional_remarks="Remark 1",
            technology="TEV",
            raw_measurement="24.0",
        ),
        CbmDefectRecord(
            equipment="TX",
            defect_area="Area 2",
            additional_remarks="",
            technology="IR",
            raw_measurement="45.0",
        ),
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


def test_preflight_validation_missing_templates(tmp_path: Path):
    """Verify Stage 1 _validate_preconditions fails fast when an always-required template is missing."""
    tpl_file = tmp_path / "tpl.docx"
    tpl_file.touch()

    env = MagicMock(spec=ProjectEnvironment)
    env.get_vi_front_page_template.return_value = tmp_path / "missing_front_page.docx"
    env.get_template.return_value = tpl_file

    workflow = QuickReportWorkflow()
    req = QuickReportRequest(mode=QuickReportMode.FOLDER, target_folders=["01-01-2026"])

    with pytest.raises(FileNotFoundError, match="VI front page template missing"):
        workflow._validate_preconditions(env, req)


@patch("src.quick_report.extractor.SubstationTestsheetRepository")
def test_workflow_error_isolation(mock_repo_cls, tmp_path: Path):
    """Verify failure in one station does not abort batch in QuickReportWorkflow."""
    mock_repo = Mock()
    mock_repo_cls.return_value = mock_repo

    pkg1 = MagicMock()
    pkg1.station = "STATION 1"
    pkg1.substation_number = 1
    pkg1.data = MagicMock()
    pkg1.data.fl_erms = "FL1"
    pkg1.data.substation_name_erms = "STATION 1"
    pkg1.data.station_name = "STATION 1"

    pkg2 = MagicMock()
    pkg2.station = "STATION 2"
    pkg2.substation_number = 2
    pkg2.data = MagicMock()
    pkg2.data.fl_erms = "FL2"
    pkg2.data.substation_name_erms = "STATION 2"
    pkg2.data.station_name = "STATION 2"

    mock_repo.discover_packages.return_value = [pkg1, pkg2]

    tpl_file = tmp_path / "tpl.docx"
    tpl_file.touch()

    out2_file = tmp_path / "out2.docx"
    out2_file.write_text("dummy")

    env = MagicMock(spec=ProjectEnvironment)
    env.po_number = "42360565"
    env.state = "PAHANG"
    env.get_vi_front_page_template.return_value = tpl_file
    env.get_cbm_summary_template.return_value = tpl_file
    env.get_vi_summary_template.return_value = tpl_file
    env.get_vi_defect_template.return_value = tpl_file
    env.get_template.return_value = tpl_file

    mock_composer = Mock()
    mock_composer.load.side_effect = [Exception("Mock Error"), out2_file]

    workflow = QuickReportWorkflow(composer=mock_composer)
    req = QuickReportRequest(
        mode=QuickReportMode.FOLDER, target_folders=["01-01-2026"]
    )

    with patch.object(workflow.extractor, "extract_defects", return_value=([], [])):
        result = workflow.execute(env, req)

    assert result.reports_generated == 1
    assert len(result.generated_paths) == 1
    assert result.generated_paths[0] == out2_file
    assert len(result.errors) == 1
    assert "Mock Error" in result.errors[0]
    assert "STATION 1" in result.errors[0]


def test_suffix_calculation():
    """Verify Canonical IR+US+TEV+VI suffix generation in QuickReportTransformer."""
    transformer = QuickReportTransformer()

    assert transformer._calculate_suffix([], []) == ("", [])
    assert transformer._calculate_suffix([CbmDefectRecord(technology="IR")], []) == (
        " (IR)",
        ["IR"],
    )
    assert transformer._calculate_suffix(
        [CbmDefectRecord(technology="IR"), CbmDefectRecord(technology="US")], []
    ) == (" (IR+US)", ["IR", "US"])
    assert transformer._calculate_suffix(
        [CbmDefectRecord(technology="IR"), CbmDefectRecord(technology="TEV")], [ViDefectRecord(equipment="SWG")]
    ) == (" (IR+TEV+VI)", ["IR", "TEV", "VI"])
    assert transformer._calculate_suffix([], [ViDefectRecord(equipment="SWG")]) == (" (VI)", ["VI"])
    assert transformer._calculate_suffix([CbmDefectRecord(technology="TEV")], []) == (
        " (TEV)",
        ["TEV"],
    )


@patch("src.quick_report.extractor.SubstationTestsheetRepository")
def test_extractor_folder_path_resolution(mock_repo_cls, tmp_path: Path):
    """Verify QuickReportExtractor resolves existing direct paths and relative testsheet paths."""
    mock_repo = Mock()
    mock_repo_cls.return_value = mock_repo
    mock_repo.discover_packages.return_value = []

    testsheet_dir = tmp_path / "TESTSHEET"
    testsheet_dir.mkdir()
    rel_folder = testsheet_dir / "01-01-2026"
    rel_folder.mkdir()

    direct_folder = tmp_path / "DIRECT_PATH"
    direct_folder.mkdir()

    env = MagicMock(spec=ProjectEnvironment)
    env.po_number = "42360565"
    env.state = "PAHANG"
    env.get_testsheet_dir.return_value = testsheet_dir

    extractor = QuickReportExtractor(repository=mock_repo)

    # Test direct path (Path(str) exists)
    req_direct = QuickReportRequest(
        mode=QuickReportMode.FOLDER, target_folders=[str(direct_folder)]
    )
    extractor.extract(env, req_direct)
    mock_repo.discover_packages.assert_called_with(direct_folder)

    # Test relative path under testsheet dir
    req_rel = QuickReportRequest(
        mode=QuickReportMode.FOLDER, target_folders=["01-01-2026"]
    )
    extractor.extract(env, req_rel)
    mock_repo.discover_packages.assert_called_with(rel_folder)


def test_extractor_raises_for_missing_folder(tmp_path: Path):
    """Verify QuickReportExtractor raises FileNotFoundError when a requested target folder does not exist."""
    testsheet_dir = tmp_path / "TESTSHEET"
    testsheet_dir.mkdir()

    env = MagicMock(spec=ProjectEnvironment)
    env.get_testsheet_dir.return_value = testsheet_dir

    extractor = QuickReportExtractor()
    req = QuickReportRequest(
        mode=QuickReportMode.FOLDER, target_folders=["nonexistent_folder"]
    )

    with pytest.raises(FileNotFoundError, match="Requested target folder does not exist"):
        extractor.extract(env, req)


def test_transformer_output_dir_resolution(tmp_path: Path):
    """Verify 3-tier Pahang output directory structure in QuickReportTransformer._resolve_output_dir."""
    quick_report_dir = tmp_path / "QUICK REPORT"
    env = MagicMock(spec=ProjectEnvironment)
    env.po_number = "42360565"
    env.state = "PAHANG"
    env.get_quick_report_dir.return_value = quick_report_dir

    transformer = QuickReportTransformer()

    # Case 1: 3-tier structure (station, month, date_str) formatted as XX. MONTH
    pkg_3tier = MagicMock()
    pkg_3tier.station = "KUANTAN"
    pkg_3tier.month = "01. JANUARY"
    pkg_3tier.date_str = "01-01-2026"

    out_3tier = transformer._resolve_output_dir(env, pkg_3tier)
    assert out_3tier == quick_report_dir / "KUANTAN" / "01. JANUARY" / "01-01-2026"

    # Case 2: 1-tier structure (date_str only)
    pkg_1tier = MagicMock()
    pkg_1tier.station = ""
    pkg_1tier.month = ""
    pkg_1tier.date_str = "02-01-2026"

    out_1tier = transformer._resolve_output_dir(env, pkg_1tier)
    assert out_1tier == quick_report_dir / "02-01-2026"

    # Case 3: Root structure (no date_str, station, or month)
    pkg_root = MagicMock()
    pkg_root.station = ""
    pkg_root.month = ""
    pkg_root.date_str = ""

    out_root = transformer._resolve_output_dir(env, pkg_root)
    assert out_root == quick_report_dir


def test_master_qr03_defect_repository_empty(tmp_path: Path):
    """Verify MasterQr03DefectRepository raises FileNotFoundError when ENGR files/directory are missing."""
    repo = MasterQr03DefectRepository(tmp_path / "nonexistent")
    with pytest.raises(FileNotFoundError):
        repo.fetch_cbm_defects("12345")
    with pytest.raises(FileNotFoundError):
        repo.fetch_vi_defects("12345")


def test_master_qr03_defect_repository_with_excel(tmp_path: Path):
    """Verify MasterQr03DefectRepository extracts CBM and VI defects strictly from QR03 CBA and QR03 VI sheets."""
    import pandas as pd

    cba_df = pd.DataFrame(
        [
            {
                "FUNCTIONAL LOCATION": "F/L 12345",
                "EQUIPMENT": "RMU SF6",
                "TECHNOLOGY": "IR",
                "BRAND": "ABB",
                "MODEL": "SafePlus",
                "RATING": "11kV",
                "DEFECT AREA": "Cable Compartment",
                "REMARKS": "Hotspot detected",
                "READING": "65.4",
            },
            {
                "FUNCTIONAL LOCATION": "F/L 12345",
                "EQUIPMENT": "RMU SF6",
                "TECHNOLOGY": "US",
                "BRAND": "ABB",
                "MODEL": "SafePlus",
                "RATING": "11kV",
                "DEFECT AREA": "Cable Compartment",
                "REMARKS": "Arcing detected",
                "READING": "18.0",
            },
        ]
    )
    vi_df = pd.DataFrame(
        [
            {
                "FUNCTIONAL LOCATION": "F/L 12345",
                "EQUIPMENT": "SUBSTATION BUILDING",
                "DEFECT AREA": "Door",
                "REMARKS": "Rusty hinge",
            }
        ]
    )

    engr_path = tmp_path / "ENGR-750-36-CBA-TEST-2026.xlsx"
    with pd.ExcelWriter(engr_path, engine="openpyxl") as writer:
        cba_df.to_excel(writer, sheet_name="QR03 CBA", index=False)
        vi_df.to_excel(writer, sheet_name="QR03 VI", index=False)

    repo = MasterQr03DefectRepository(tmp_path)
    cbm = repo.fetch_cbm_defects("12345")
    vi = repo.fetch_vi_defects("12345")

    assert len(cbm) == 2
    assert cbm[0].equipment == "RMU SF6"
    assert cbm[0].technology == "IR"
    assert cbm[0].raw_measurement == "65.4"

    assert len(vi) == 1
    assert vi[0].equipment == "SUBSTATION BUILDING"
    assert vi[0].defect_area == "Door"


def test_build_substation_condition_pairs():
    """Verify equipment pair building in QuickReportTransformer."""
    transformer = QuickReportTransformer()

    # None / Empty pkg fallback
    assert transformer._build_substation_condition_pairs(None) == [
        ("SUBSTATION OVERVIEW", "SIGNBOARD")
    ]

    pkg = MagicMock()
    pkg.data.substation_type = "MRMU SF6"

    pairs = transformer._build_substation_condition_pairs(pkg)
    labels = [p[0] for p in pairs]

    assert "SUBSTATION OVERVIEW" in labels
    assert "SWITCHGEAR 1" in labels
    assert "TRANSFORMER 1" in labels
    assert "FEEDER PILLAR 1" in labels
    assert "BATTERY CHARGER" in labels
    assert "RTU" in labels
    assert "EFI" in labels
    assert "FIRE EXTINGUISHER" in labels
    assert "TRANSFORMER OIL LEVEL INDICATOR" in labels


def test_composer_cbm_defect_pages_with_cbm_defects(tmp_path: Path):
    """Verify composer calls CBM defect pages generation correctly when cbm_defects exist."""
    composer = QuickReportComposer()
    tpl_file = tmp_path / "tpl.docx"
    tpl_file.touch()

    pkg = MagicMock()
    pkg.station = "CAMERON HIGHLAND"
    pkg.substation_number = 1

    pe_info = {"substation": {"name_erms": "CAMERON HIGHLAND"}}
    cbm_defects = (
        CbmDefectRecord(
            equipment="FP (D)",
            technology="IR",
            brand="ABB",
            model="X",
            rating="11kV",
            defect_area="Body",
            additional_remarks="Hotspot",
            ir_reading="50",
            us_reading="",
            tev_reading="",
            raw_measurement="50",
        ),
    )

    from src.quick_report.models import CbmDefectFamilyPlan, CbmDefectGroup

    family_plan = CbmDefectFamilyPlan(
        spec=QUICK_REPORT_FAMILY_SPECS_BY_ID["fp_lvdb"],
        overview_template=tpl_file,
        detail_templates=(("fp_detail", tpl_file),),
        groups=(
            CbmDefectGroup(
                item_key="FP (D)",
                item_suffix="",
                defects=(cbm_defects[0],),
                overview=cbm_defects[0],
            ),
        ),
    )

    plan = QuickReportStationPlan(
        package=pkg,
        pe_info=pe_info,
        cbm_defects=cbm_defects,
        vi_defects=(),
        suffix=" (IR)",
        suffix_parts=("IR",),
        output_dir=tmp_path,
        output_filename="001. CAMERON HIGHLAND (IR).docx",
        final_output_path=tmp_path / "001. CAMERON HIGHLAND (IR).docx",
        condition_pairs=(),
        cond_template_path=None,
        front_page_template=tpl_file,
        cbm_summary_template=tpl_file,
        vi_summary_template=tpl_file,
        vi_defect_template=tpl_file,
        sticker_template=tpl_file,
        cbm_defect_family_plans=(family_plan,),
    )

    with (
        patch(
            "src.quick_report.composer.generate_front_page",
            return_value=tmp_path / "p1.docx",
        ),
        patch(
            "src.quick_report.composer.generate_cbm_tech_summary",
            return_value=tmp_path / "p2a.docx",
        ),
        patch(
            "src.quick_report.composer.generate_cbm_defect_pages",
            return_value=[tmp_path / "p2b.docx"],
        ) as mock_gen_cbm,
        patch(
            "src.quick_report.composer.generate_sticker_page",
            return_value=tmp_path / "p7.docx",
        ),
    ):
        parts = composer._generate_parts(plan, tmp_path)
        assert len(parts) >= 3
        assert mock_gen_cbm.called
        call_args = mock_gen_cbm.call_args[0]
        assert call_args[0] == family_plan
        assert call_args[1] == tmp_path  # temp_dir
        assert call_args[2] == 1  # substation_number
        assert call_args[3] == pe_info  # pe_info


@patch("src.quick_report.composer.pythoncom")
@patch("src.quick_report.composer.win32com.client")
def test_compile_document_word_com_success(
    mock_win32com, mock_pythoncom, tmp_path: Path
):
    """Verify _compile_document uses win32com to copy/paste document parts and saves properly."""
    composer = QuickReportComposer()

    mock_word = MagicMock()
    mock_main_doc = MagicMock()
    mock_part_doc2 = MagicMock()
    mock_rng = MagicMock()

    mock_win32com.Dispatch.return_value = mock_word
    mock_word.Documents.Open.side_effect = [mock_main_doc, mock_part_doc2]
    mock_main_doc.Content = mock_rng
    mock_part_doc2.Paragraphs = []

    part1 = tmp_path / "part1.docx"
    part2 = tmp_path / "part2.docx"
    output_path = tmp_path / "output.docx"

    part1.touch()
    part2.touch()

    composer._compile_document([part1, part2], output_path)

    # Verification
    mock_pythoncom.CoInitialize.assert_called_once()
    mock_win32com.Dispatch.assert_called_once_with("Word.Application")
    assert mock_word.Visible is False
    assert mock_word.DisplayAlerts == 0

    assert mock_word.Documents.Open.call_count == 2
    mock_word.Documents.Open.assert_any_call(str(output_path.resolve()))
    mock_word.Documents.Open.assert_any_call(str(part2.resolve()))

    mock_part_doc2.Content.Copy.assert_called_once()
    mock_part_doc2.Close.assert_called_once_with(False)

    mock_rng.InsertBreak.assert_called_once_with(7)
    assert mock_rng.Paste.call_count == 1

    mock_main_doc.Save.assert_called_once()
    mock_main_doc.Close.assert_called_once_with(False)
    mock_word.Quit.assert_called_once()
    mock_pythoncom.CoUninitialize.assert_called_once()


@patch("src.quick_report.composer.pythoncom")
@patch("src.quick_report.composer.win32com.client")
def test_compile_document_word_com_cleanup_on_error(
    mock_win32com, mock_pythoncom, tmp_path: Path
):
    """Verify _compile_document executes cleanup (Close, Quit, CoUninitialize) when an exception occurs."""
    composer = QuickReportComposer()

    mock_word = MagicMock()
    mock_main_doc = MagicMock()
    mock_part_doc2 = MagicMock()

    mock_win32com.Dispatch.return_value = mock_word
    mock_word.Documents.Open.side_effect = [mock_main_doc, mock_part_doc2]
    mock_part_doc2.Paragraphs = []
    mock_part_doc2.Content.Copy.side_effect = RuntimeError("Copy failed")

    part1 = tmp_path / "part1.docx"
    part2 = tmp_path / "part2.docx"
    output_path = tmp_path / "output.docx"
    part1.touch()
    part2.touch()

    with pytest.raises(RuntimeError, match="Copy failed"):
        composer._compile_document([part1, part2], output_path)

    # Verification of cleanup in finally block
    mock_main_doc.Close.assert_called_once_with(False)
    mock_word.Quit.assert_called_once()
    mock_pythoncom.CoUninitialize.assert_called_once()


def test_generate_cbm_defect_pages_fallback_detail_groups(tmp_path: Path):
    """Verify generate_cbm_defect_pages defensive fallback when detail_groups is missing."""
    from src.quick_report.cbm_defect_pages import generate_cbm_defect_pages
    from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID

    spec = QUICK_REPORT_FAMILY_SPECS_BY_ID["swg"]

    # Create fake template files
    overview_t = tmp_path / "swg_overview.docx"
    panel_t = tmp_path / "swg_panel.docx"
    overview_t.touch()
    panel_t.touch()

    template_paths = {
        spec.overview_template_key: str(overview_t),
        spec.detail_roles[0].template_key: str(panel_t),
    }

    groups = [
        {
            "item_key": "RMU SF6",
            "defects": [{"equipment": "RMU SF6", "technology": "IR"}],
            "overview": {"equipment": "RMU SF6"},
            # detail_groups intentionally missing to test fallback
        }
    ]

    with patch("src.quick_report.cbm_defect_pages._render_docx_template"):
        paths = generate_cbm_defect_pages(
            groups, spec, template_paths, tmp_path, 1, {"pe": "info"}
        )

    assert len(paths) == 2
    assert "SWG OVERVIEW" in paths[0].name
    assert "SWG RMU SF6" in paths[1].name


def test_vi_defect_pages_remove_empty_cell_borders(tmp_path: Path):
    """Verify _remove_empty_cell_borders and cell text clearing on docx table."""
    from docx import Document

    from src.quick_report.vi_defect_pages import _remove_empty_cell_borders

    doc_path = tmp_path / "vi_defect_test.docx"
    doc = Document()
    table = doc.add_table(rows=11, cols=3)
    # Fill cell (4, 0) with dummy text
    cell = table.cell(4, 0)
    cell.paragraphs[0].text = "Dummy defect"
    doc.save(doc_path)

    # Call _remove_empty_cell_borders with active_count=2 (slot 2 at row 4, col 0 is empty)
    _remove_empty_cell_borders(doc_path, 2)

    updated_doc = Document(doc_path)
    updated_cell = updated_doc.tables[0].cell(4, 0)
    assert updated_cell.text == ""
    tcPr = updated_cell._tc.get_or_add_tcPr()
    assert (
        tcPr.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tcBorders"
        )
        is not None
    )


def test_compile_document_paragraph_trimming_infinite_loop_protection(tmp_path: Path):
    """Verify _compile_document breaks out of paragraph trimming loop when paragraph count does not change."""
    composer = QuickReportComposer()

    with (
        patch("src.quick_report.composer.pythoncom"),
        patch("src.quick_report.composer.win32com.client") as mock_win32com,
    ):
        mock_word = MagicMock()
        mock_main_doc = MagicMock()
        mock_part_doc2 = MagicMock()

        mock_win32com.Dispatch.return_value = mock_word
        mock_word.Documents.Open.side_effect = [mock_main_doc, mock_part_doc2]

        mock_paragraph = MagicMock()
        mock_paragraph.Range.Text.strip.return_value = ""
        # Paragraphs count stays at 1 even when Delete() is called (simulating Word COM final paragraph mark)
        mock_paragraphs = MagicMock()
        mock_paragraphs.__len__.return_value = 1
        mock_paragraphs.Last = mock_paragraph
        mock_part_doc2.Paragraphs = mock_paragraphs

        part1 = tmp_path / "part1.docx"
        part2 = tmp_path / "part2.docx"
        output_path = tmp_path / "output.docx"
        part1.touch()
        part2.touch()

        # Should complete without infinite loop
        composer._compile_document([part1, part2], output_path)
        assert mock_paragraph.Range.Delete.call_count == 1


def test_compile_document_paste_before_close(tmp_path: Path):
    """Verify rng.Paste() is executed BEFORE part_doc.Close(False)."""
    composer = QuickReportComposer()

    call_order = []

    with (
        patch("src.quick_report.composer.pythoncom"),
        patch("src.quick_report.composer.win32com.client") as mock_win32com,
    ):
        mock_word = MagicMock()
        mock_main_doc = MagicMock()
        mock_part_doc2 = MagicMock()
        mock_rng = MagicMock()

        mock_win32com.Dispatch.return_value = mock_word
        mock_word.Documents.Open.side_effect = [mock_main_doc, mock_part_doc2]
        mock_main_doc.Content = mock_rng
        mock_part_doc2.Paragraphs = MagicMock()
        mock_part_doc2.Paragraphs.__len__.return_value = 0

        mock_rng.Paste.side_effect = lambda: call_order.append("paste")
        mock_part_doc2.Close.side_effect = lambda arg: call_order.append("close")

        part1 = tmp_path / "part1.docx"
        part2 = tmp_path / "part2.docx"
        output_path = tmp_path / "output.docx"
        part1.touch()
        part2.touch()

        composer._compile_document([part1, part2], output_path)
        assert call_order == ["paste", "close"]


def test_generate_cbm_defect_pages_filename_uniqueness(tmp_path: Path):
    """Verify unique filenames are generated when multiple groups and defects exist."""
    from src.quick_report.cbm_defect_pages import generate_cbm_defect_pages
    from src.quick_report.cbm_family import QUICK_REPORT_FAMILY_SPECS_BY_ID

    spec = QUICK_REPORT_FAMILY_SPECS_BY_ID["swg"]

    overview_t = tmp_path / "swg_overview.docx"
    panel_t = tmp_path / "swg_panel.docx"
    overview_t.touch()
    panel_t.touch()

    template_paths = {
        spec.overview_template_key: str(overview_t),
        spec.detail_roles[0].template_key: str(panel_t),
    }

    groups = [
        {
            "item_key": "RMU SF6",
            "defects": [{"equipment": "RMU SF6"}, {"equipment": "RMU SF6"}],
            "overview": {"equipment": "RMU SF6"},
            "detail_groups": {
                "panel_area": [{"equipment": "RMU SF6"}, {"equipment": "RMU SF6"}]
            },
        },
        {
            "item_key": "RMU SF6",
            "defects": [{"equipment": "RMU SF6"}],
            "overview": {"equipment": "RMU SF6"},
            "detail_groups": {"panel_area": [{"equipment": "RMU SF6"}]},
        },
    ]

    with patch("src.quick_report.cbm_defect_pages._render_docx_template"):
        paths = generate_cbm_defect_pages(
            groups, spec, template_paths, tmp_path, 1, {"pe": "info"}
        )

    filenames = [p.name for p in paths]
    assert len(filenames) == len(
        set(filenames)
    ), f"Duplicate filenames found: {filenames}"
    assert "001_3 SWG OVERVIEW_grp1.docx" in filenames
    assert "001_3 SWG OVERVIEW_grp2.docx" in filenames
    assert "001_3 SWG RMU SF6_grp1_part1.docx" in filenames
    assert "001_3 SWG RMU SF6_grp1_part2.docx" in filenames
    assert "001_3 SWG RMU SF6_grp2.docx" in filenames


def test_vi_defect_pages_remove_empty_cell_borders_exception_handling(
    tmp_path: Path, caplog
):
    """Verify _remove_empty_cell_borders logs a warning and does not crash when an exception occurs."""
    from src.quick_report.vi_defect_pages import _remove_empty_cell_borders

    invalid_path = tmp_path / "non_existent.docx"
    with caplog.at_level(logging.WARNING):
        _remove_empty_cell_borders(invalid_path, 0)

    assert "Failed to remove empty cell borders" in caplog.text


def test_substation_condition_remove_empty_cell_borders_multi_table(tmp_path: Path):
    """Verify _remove_empty_cell_borders_sub_cond dehighlights unused tables in multi-table layout."""
    from docx import Document

    from src.quick_report.substation_condition import (
        _remove_empty_cell_borders_sub_cond,
    )

    doc_path = tmp_path / "sub_cond_multi.docx"
    doc = Document()
    doc.add_table(rows=2, cols=2)
    t1 = doc.add_table(rows=2, cols=2)
    t2 = doc.add_table(rows=2, cols=2)

    doc.tables[0].cell(0, 0).paragraphs[0].text = "Table 0 Active"
    t1.cell(0, 0).paragraphs[0].text = "Table 1 Unused"
    t2.cell(0, 0).paragraphs[0].text = "Table 2 Unused"
    doc.save(doc_path)

    _remove_empty_cell_borders_sub_cond(doc_path, active_count=1)

    updated = Document(doc_path)
    assert updated.tables[0].cell(0, 0).text == "Table 0 Active"
    assert updated.tables[1].cell(0, 0).text == ""
    assert updated.tables[2].cell(0, 0).text == ""

    tcPr1 = updated.tables[1].cell(0, 0)._tc.get_or_add_tcPr()
    assert (
        tcPr1.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tcBorders"
        )
        is not None
    )

    tcPr2 = updated.tables[2].cell(0, 0)._tc.get_or_add_tcPr()
    assert (
        tcPr2.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tcBorders"
        )
        is not None
    )


def test_substation_condition_remove_empty_cell_borders_single_table(tmp_path: Path):
    """Verify _remove_empty_cell_borders_sub_cond dehighlights unused slot rows in single-table layout."""
    from docx import Document

    from src.quick_report.substation_condition import (
        _remove_empty_cell_borders_sub_cond,
    )

    doc_path = tmp_path / "sub_cond_single.docx"
    doc = Document()
    t = doc.add_table(rows=6, cols=2)

    t.cell(0, 0).paragraphs[0].text = "Header 0"
    t.cell(1, 0).paragraphs[0].text = "Photo 0"
    t.cell(2, 0).paragraphs[0].text = "Header 1"
    t.cell(3, 0).paragraphs[0].text = "Photo 1"
    t.cell(4, 0).paragraphs[0].text = "Header 2"
    t.cell(5, 0).paragraphs[0].text = "Photo 2"
    doc.save(doc_path)

    _remove_empty_cell_borders_sub_cond(doc_path, active_count=1)

    updated = Document(doc_path)
    assert updated.tables[0].cell(0, 0).text == "Header 0"
    assert updated.tables[0].cell(1, 0).text == "Photo 0"

    assert updated.tables[0].cell(2, 0).text == ""
    assert updated.tables[0].cell(3, 0).text == ""
    assert updated.tables[0].cell(4, 0).text == ""
    assert updated.tables[0].cell(5, 0).text == ""

    tcPr = updated.tables[0].cell(2, 0)._tc.get_or_add_tcPr()
    assert (
        tcPr.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tcBorders"
        )
        is not None
    )


def test_substation_condition_remove_empty_cell_borders_exception_handling(
    tmp_path: Path, caplog
):
    """Verify _remove_empty_cell_borders_sub_cond logs a warning and handles errors gracefully."""
    from src.quick_report.substation_condition import (
        _remove_empty_cell_borders_sub_cond,
    )

    invalid_path = tmp_path / "non_existent.docx"
    with caplog.at_level(logging.WARNING):
        _remove_empty_cell_borders_sub_cond(invalid_path, 0)

    assert "Failed to remove empty cell borders" in caplog.text


def test_quick_report_fl_mode_fl_erms_matching(monkeypatch, tmp_path: Path):
    """Verify QuickReportWorkflow FL mode filters using TestsheetData.fl_erms without AttributeError."""
    from src.testsheet.models import SubstationTestsheetPackage, TestsheetData

    mock_pkg1 = SubstationTestsheetPackage(
        testsheet_path=Path("test1.xlsx"),
        unsorted_raw_data_dir=Path("dir1"),
        station="CCHL",
        month="05. MAY",
        date_str="2026-05-15",
        substation_number=1,
        data=TestsheetData(
            substation_number=1,
            substation_name_erms="SUBSTATION A",
            fl_erms="CCHL/PCE/J00059",
            fl_site="CCHL/PCE/J00059",
        ),
    )

    mock_pkg2 = SubstationTestsheetPackage(
        testsheet_path=Path("test2.xlsx"),
        unsorted_raw_data_dir=Path("dir2"),
        station="CCHL",
        month="05. MAY",
        date_str="2026-05-15",
        substation_number=2,
        data=TestsheetData(
            substation_number=2,
            substation_name_erms="SUBSTATION B",
            fl_erms="CCHL/PCE/J00060",
            fl_site="CCHL/PCE/J00060",
        ),
    )

    monkeypatch.setattr(
        "src.testsheet.repository.SubstationTestsheetRepository.discover_packages",
        lambda self, folder_path: [mock_pkg1, mock_pkg2],
    )

    tpl_file = tmp_path / "tpl.docx"
    tpl_file.touch()

    env = MagicMock()
    env.get_vi_front_page_template.return_value = tpl_file
    env.get_cbm_summary_template.return_value = tpl_file
    env.get_vi_summary_template.return_value = tpl_file
    env.get_vi_defect_template.return_value = tpl_file
    env.get_template.return_value = tpl_file

    req = QuickReportRequest(
        mode=QuickReportMode.FL,
        target_package_names=("CCHL/PCE/J00059",),
    )

    dummy_path = tmp_path / "dummy.docx"
    dummy_path.write_text("content")

    mock_composer = Mock()
    mock_composer.load.return_value = dummy_path

    workflow = QuickReportWorkflow(composer=mock_composer)
    with patch.object(workflow.extractor, "extract_defects", return_value=([], [])):
        result = workflow.execute(env, req)
    assert result.reports_generated == 1
    assert len(result.generated_paths) == 1


def test_workflow_fetches_defects_from_repository(tmp_path: Path):
    """Regression: QuickReport workflow must call MasterQr03DefectRepository to fetch
    cbm_defects and vi_defects and pass them through to transformer/composer."""
    mock_data = Mock()
    mock_data.substation_name_erms = "KEA FARM"
    mock_data.station_name = "KEA FARM"
    mock_data.date_str = "17-06-2026"
    mock_data.gps_coordinate = "4.123,101.456"
    mock_data.substation_type = "PMU"
    mock_data.building_type = "BRICK"
    mock_data.fl_erms = "CCHL/PCE/J00059"
    mock_data.fl_site = "CCHL/PCE/J00059"

    mock_pkg = Mock()
    mock_pkg.data = mock_data
    mock_pkg.station = "CAMERON HIGHLAND"
    mock_pkg.month = "06. JUNE"
    mock_pkg.date_str = "17-06-2026"
    mock_pkg.substation_number = 303

    sample_cbm = [CbmDefectRecord(equipment="SWG", technology="IR", defect_area="Cable lug")]
    sample_vi = [ViDefectRecord(equipment="SWG", defect_area="Rust", additional_remarks="Mild")]

    tpl_file = tmp_path / "tpl.docx"
    tpl_file.touch()

    env = MagicMock()
    env.get_quick_report_dir.return_value = tmp_path
    env.get_vi_front_page_template.return_value = tpl_file
    env.get_cbm_summary_template.return_value = tpl_file
    env.get_vi_summary_template.return_value = tpl_file
    env.get_vi_defect_template.return_value = tpl_file
    env.get_template.return_value = tpl_file

    req = QuickReportRequest(
        mode=QuickReportMode.FL, target_package_names=("CCHL/PCE/J00059",)
    )

    dummy_path = tmp_path / "dummy.docx"
    dummy_path.write_text("content")

    captured_plan = {}

    def spy_load(plan):
        captured_plan["plan"] = plan
        return dummy_path

    mock_composer = Mock()
    mock_composer.load.side_effect = spy_load

    with (
        patch("src.quick_report.extractor.SubstationTestsheetRepository") as MockRepo,
        patch(
            "src.quick_report.extractor.MasterQr03DefectRepository"
        ) as MockDefectRepo,
    ):
        MockRepo.return_value.discover_packages.return_value = [mock_pkg]

        defect_repo_instance = MockDefectRepo.return_value
        defect_repo_instance.fetch_cbm_defects.return_value = sample_cbm
        defect_repo_instance.fetch_vi_defects.return_value = sample_vi

        workflow = QuickReportWorkflow(composer=mock_composer)
        workflow.execute(env, req)

    assert "plan" in captured_plan
    plan = captured_plan["plan"]
    assert (
        plan.cbm_defects == tuple(sample_cbm)
    ), "cbm_defects not passed through from repository"
    assert (
        plan.vi_defects == tuple(sample_vi)
    ), "vi_defects not passed through from repository"


def test_extract_defects_returns_empty_when_valid_sheet_has_no_matching_fl(tmp_path: Path):
    """Valid ENGR workbook with QR03 CBA/VI sheets but no rows matching the FL → returns ([], [])."""
    import pandas as pd

    cba_df = pd.DataFrame([
        {
            "FUNCTIONAL LOCATION": "F/L 99999",
            "EQUIPMENT": "RMU SF6",
            "TECHNOLOGY": "IR",
            "DEFECT AREA": "Cable Compartment",
            "READING": "65.4",
        }
    ])
    vi_df = pd.DataFrame([
        {
            "FUNCTIONAL LOCATION": "F/L 99999",
            "EQUIPMENT": "SUBSTATION BUILDING",
            "DEFECT AREA": "Door",
        }
    ])

    engr_path = tmp_path / "ENGR-750-36-CBA-TEST-2026.xlsx"
    with pd.ExcelWriter(engr_path, engine="openpyxl") as writer:
        cba_df.to_excel(writer, sheet_name="QR03 CBA", index=False)
        vi_df.to_excel(writer, sheet_name="QR03 VI", index=False)

    pkg = MagicMock()
    pkg.data.fl_erms = "12345"

    env = MagicMock()
    env.storage.get_engr_folder.return_value = tmp_path

    extractor = QuickReportExtractor()
    cbm, vi = extractor.extract_defects(pkg, env)

    assert cbm == []
    assert vi == []


def test_extract_defects_raises_when_engr_folder_missing(tmp_path: Path):
    """Missing ENGR directory → FileNotFoundError, NOT empty lists."""
    pkg = MagicMock()
    pkg.data.fl_erms = "12345"

    env = MagicMock()
    env.storage.get_engr_folder.return_value = tmp_path / "nonexistent"

    extractor = QuickReportExtractor()
    with pytest.raises(FileNotFoundError, match="Required ENGR directory does not exist"):
        extractor.extract_defects(pkg, env)


def test_extract_defects_raises_when_no_engr_workbooks(tmp_path: Path):
    """ENGR directory exists but contains no .xlsx files → FileNotFoundError."""
    pkg = MagicMock()
    pkg.data.fl_erms = "12345"

    env = MagicMock()
    env.storage.get_engr_folder.return_value = tmp_path

    extractor = QuickReportExtractor()
    with pytest.raises(FileNotFoundError, match="No ENGR Excel workbooks found"):
        extractor.extract_defects(pkg, env)


def test_extract_defects_raises_when_qr03_cba_sheet_missing(tmp_path: Path):
    """ENGR workbook exists but missing 'QR03 CBA' sheet → RuntimeError."""
    import pandas as pd

    dummy_df = pd.DataFrame([{"FL": "12345"}])
    engr_path = tmp_path / "ENGR-750-36-CBA-TEST-2026.xlsx"
    with pd.ExcelWriter(engr_path, engine="openpyxl") as writer:
        dummy_df.to_excel(writer, sheet_name="Sheet1", index=False)

    pkg = MagicMock()
    pkg.data.fl_erms = "12345"

    env = MagicMock()
    env.storage.get_engr_folder.return_value = tmp_path

    extractor = QuickReportExtractor()
    with pytest.raises(RuntimeError, match="Missing required sheet 'QR03 CBA'"):
        extractor.extract_defects(pkg, env)


def test_extract_defects_raises_when_qr03_vi_sheet_missing(tmp_path: Path):
    """ENGR workbook exists with QR03 CBA but missing 'QR03 VI' sheet → RuntimeError."""
    import pandas as pd

    cba_df = pd.DataFrame([
        {
            "FUNCTIONAL LOCATION": "F/L 12345",
            "EQUIPMENT": "RMU SF6",
            "TECHNOLOGY": "IR",
            "DEFECT AREA": "Cable Compartment",
            "READING": "65.4",
        }
    ])
    engr_path = tmp_path / "ENGR-750-36-CBA-TEST-2026.xlsx"
    with pd.ExcelWriter(engr_path, engine="openpyxl") as writer:
        cba_df.to_excel(writer, sheet_name="QR03 CBA", index=False)

    pkg = MagicMock()
    pkg.data.fl_erms = "12345"

    env = MagicMock()
    env.storage.get_engr_folder.return_value = tmp_path

    extractor = QuickReportExtractor()
    with pytest.raises(RuntimeError, match="Missing required sheet 'QR03 VI'"):
        extractor.extract_defects(pkg, env)
