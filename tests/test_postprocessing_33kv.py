"""Unit and integration tests for 33kV post-processing pipeline (Ticket #097).

Covers:
1. Pre-flight integrity validation and file renaming synchronization with PPU/SSU naming and dynamic defect suffixes.
2. Sequential voltage-aware sheet selection and sorting (select_and_sort_sheets).
3. Programmatic per-sheet PageSetup in ComDocumentConverter.
4. Signature anchor geometries across Switchgear, TX, and VI layouts in replace_pce_images.
5. 33kV diagonal borders blank cell scanning across Switchgear, TX (5 groups + merged cells), and VI (unslashed).
6. Multi-orientation deliverable stitching into canonical <STEM>.pdf.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import openpyxl
from PIL import Image as PILImage
from PyPDF2 import PdfReader
import pytest

from src.postprocessing.converters import (
    ComDocumentConverter,
    FakeDocumentConverter,
    classify_sheet_layout,
    select_and_sort_sheets,
)
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.workflows.diagonal_borders import (
    SWITCHGEAR_33KV_RANGES,
    TX_33KV_RANGES,
    process_workbook,
)
from src.workflows.models import PostProcessingMode, PostProcessingRequest
from src.workflows.postprocessing_pipeline import (
    PostProcessingPipelineWorkflow,
    run_postprocessing_pipeline,
)
from src.workflows.postprocessing_preflight import (
    PreFlightValidationError,
    validate_postprocessing_preflight,
)
from src.workflows.rename_files import rename_files_match
from src.workflows.replace_signatures import SIGNATURE_LAYOUT_REGISTRY, replace_pce_images
from tests.fixtures.ppu_workbook_factory import create_ppu_testsheet_workbook


@pytest.fixture
def mock_env_33kv(tmp_path: Path) -> ProjectEnvironment:
    """Provide an isolated 33kV ProjectEnvironment backed by tmp_path."""
    meta = ProjectMetadata(
        key="test_33kv",
        name="Test 33kV Project",
        base_path=str(tmp_path),
        state="pahang",
        po_number="PO-42394550",
        voltage_type="33kV",
        year="2026",
        cycle="Cycle 4",
        technologies=("IR", "US", "TEV"),
    )
    storage = LocalWorkspaceStorage(tmp_path)
    return ProjectEnvironment(metadata=meta, storage=storage)


@pytest.fixture
def sample_sig_png(tmp_path: Path) -> Path:
    """Create a temporary PNG signature image for testing."""
    png_path = tmp_path / "signatures" / "tested_by" / "sig1.png"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    img = PILImage.new("RGBA", (120, 60), color=(0, 0, 255, 255))
    img.save(png_path)
    return png_path


# ==============================================================================
# 1. Pre-Flight Validation & Renaming Sync (PPU/SSU & Dynamic Defect Suffixes)
# ==============================================================================


class TestPreflightAndRenamingSync33kV:
    """Pre-flight integrity and file renaming synchronization for 33kV packages."""

    def test_preflight_validation_pairs_with_dynamic_defect_suffixes(
        self, mock_env_33kv: ProjectEnvironment
    ) -> None:
        """Pair 33kV Quick Report (.docx), testsheet (.xlsx), and raw material directory by numerical prefix."""
        date_str = "07-10-2026"
        qr_dir = mock_env_33kv.get_quick_report_dir() / date_str
        ts_dir = mock_env_33kv.get_testsheet_dir() / date_str
        raw_dir = mock_env_33kv.get_raw_material_dir() / date_str

        qr_dir.mkdir(parents=True)
        ts_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)

        # Quick report has defect suffix (VI), testsheet does not, raw material has (VI)
        (qr_dir / "09. PPU SEMAMBU YARD 33-11kV (VI).docx").write_text("docx")
        (ts_dir / "09. PPU SEMAMBU YARD 33-11kV.xlsx").write_text("xlsx")
        (raw_dir / "09. PPU SEMAMBU YARD 33-11kV (VI)").mkdir()

        result = validate_postprocessing_preflight(mock_env_33kv, date_str)
        assert result.is_valid
        assert result.quick_report_count == 1
        assert result.testsheet_count == 1
        assert result.raw_material_count == 1

    def test_preflight_validation_detects_numerical_prefix_mismatch(
        self, mock_env_33kv: ProjectEnvironment
    ) -> None:
        """Fail fast when counts match but numerical prefixes differ between QR and TS."""
        date_str = "08-10-2026"
        qr_dir = mock_env_33kv.get_quick_report_dir() / date_str
        ts_dir = mock_env_33kv.get_testsheet_dir() / date_str

        qr_dir.mkdir(parents=True)
        ts_dir.mkdir(parents=True)

        (qr_dir / "09. PPU SEMAMBU YARD 33-11kV (VI).docx").write_text("docx")
        (ts_dir / "10. PPU SEMAMBU YARD 33-11kV.xlsx").write_text("xlsx")

        with pytest.raises(PreFlightValidationError) as exc_info:
            validate_postprocessing_preflight(mock_env_33kv, date_str)

        assert "Numerical prefix mismatch" in str(exc_info.value)

    def test_rename_files_match_synchronizes_33kv_testsheets_and_raw_material(
        self, tmp_path: Path
    ) -> None:
        """rename_files_match pairs 33kV QR and testsheets/folders by numerical prefix and renames them."""
        qr_dir = tmp_path / "QUICK_REPORT"
        ts_dir = tmp_path / "TESTSHEET"
        raw_dir = tmp_path / "RAW_MATERIAL"

        qr_dir.mkdir()
        ts_dir.mkdir()
        raw_dir.mkdir()

        # Input: Quick Report with dynamic defect suffix
        (qr_dir / "09. PPU SEMAMBU YARD 33-11kV (VI).docx").write_text("docx")

        # Output Testsheet: initially without defect suffix
        (ts_dir / "09. PPU SEMAMBU YARD 33-11kV.xlsx").write_text("xlsx")

        # Output Raw Material: initially without defect suffix
        (raw_dir / "09. PPU SEMAMBU YARD 33-11kV").mkdir()

        # Rename testsheet
        summary_ts = rename_files_match(qr_dir, ts_dir, target_type="testsheet")
        assert len(summary_ts.renamed) == 1
        assert (ts_dir / "09. PPU SEMAMBU YARD 33-11kV (VI).xlsx").exists()

        # Rename raw material folder
        summary_raw = rename_files_match(qr_dir, raw_dir, target_type="raw_material")
        assert len(summary_raw.renamed) == 1
        assert (raw_dir / "09. PPU SEMAMBU YARD 33-11kV (VI)").is_dir()


# ==============================================================================
# 2. Sequential Voltage-Aware Sheet Selection (select_and_sort_sheets)
# ==============================================================================


class TestSheetSelectionAndSorting33kV:
    """Voltage-aware sequential sheet ordering across 33kV and 11kV workbooks."""

    def test_select_and_sort_sheets_33kv_full_sequential_order(self) -> None:
        """Sort sheets: 33kV (Main) -> 33kV (Extra) (1..N) -> 11kV (Main) -> 11kV (Extra) (1..N) -> TX -> VI."""
        sheets = [
            "RAW DATA",
            "Visual Inspec.",
            "11kV (Extra) (2)",
            "11kV (Main)",
            "33kV (Extra) (3)",
            "33kV (Main)",
            "TX",
            "33kV (Extra)",
            "11kV (Extra)",
            "33kV (Extra) (2)",
            "33kV (Extra Template)",
        ]

        result = select_and_sort_sheets(sheets)

        expected = [
            "33kV (Main)",
            "33kV (Extra)",
            "33kV (Extra) (2)",
            "33kV (Extra) (3)",
            "11kV (Main)",
            "11kV (Extra)",
            "11kV (Extra) (2)",
            "TX",
            "Visual Inspec.",
        ]
        assert result == expected
        assert "RAW DATA" not in result
        assert "33kV (Extra Template)" not in result

    def test_select_and_sort_sheets_preserves_11kv_ordering(self) -> None:
        """Preserve existing PCE Testsheet first and PCE VI last ordering for 11kV workbooks."""
        sheets = [
            "PCE VI",
            "PCE Testsheet (2)",
            "PCE VI (2)",
            "PCE Testsheet",
        ]

        result = select_and_sort_sheets(sheets)

        expected = [
            "PCE Testsheet",
            "PCE Testsheet (2)",
            "PCE VI",
            "PCE VI (2)",
        ]
        assert result == expected

    def test_select_and_sort_sheets_honors_explicit_target_sheets(self) -> None:
        """When target_sheets is specified, return matching sheets in specified order."""
        sheets = ["33kV (Main)", "TX", "RAW DATA", "Visual Inspec."]
        targets = ["TX", "33kV (Main)"]

        result = select_and_sort_sheets(sheets, target_sheets=targets)
        assert result == ["TX", "33kV (Main)"]


# ==============================================================================
# 3. Signature Anchor Geometries (replace_pce_images)
# ==============================================================================


class TestSignatureAnchorGeometries33kV:
    """Signature placement and placeholder sanitization across 3 sheet families."""

    def test_replace_signatures_33kv_placeholder_mode(
        self, tmp_path: Path, sample_sig_png: Path
    ) -> None:
        """Verify anchor coordinates for Switchgear (E77/L77), TX (F73/R73), and VI (D82/M82)."""
        xlsx_file = tmp_path / "33kv_testsheet.xlsx"
        create_ppu_testsheet_workbook(
            path=xlsx_file,
            has_33kv=True,
            has_11kv=False,
            include_tx_sheet=True,
            include_signature_placeholders=True,
        )

        out_file = tmp_path / "33kv_testsheet_signed.xlsx"
        replace_pce_images(
            xlsx_file,
            photo1_path=sample_sig_png,
            photo2_path=sample_sig_png,
            output_path=out_file,
            mode="placeholder",
        )

        wb = openpyxl.load_workbook(out_file)

        # 1. Switchgear: Vendor at E76:F81, TNB at L75:M80
        ws_swg = wb["33kV (Main)"]
        assert ws_swg["E77"].value is None  # Placeholder text stripped
        assert ws_swg["L77"].value is None
        assert len(ws_swg._images) == 2
        img_vendor_swg = ws_swg._images[0]
        img_tnb_swg = ws_swg._images[1]

        assert (
            img_vendor_swg.anchor._from.col,
            img_vendor_swg.anchor._from.colOff,
            img_vendor_swg.anchor._from.row,
            img_vendor_swg.anchor._from.rowOff,
        ) == (4, 113500, 75, 152400)
        assert (
            img_vendor_swg.anchor.to.col,
            img_vendor_swg.anchor.to.colOff,
            img_vendor_swg.anchor.to.row,
            img_vendor_swg.anchor.to.rowOff,
        ) == (6, 163500, 80, 63500)

        assert (
            img_tnb_swg.anchor._from.col,
            img_tnb_swg.anchor._from.colOff,
            img_tnb_swg.anchor._from.row,
            img_tnb_swg.anchor._from.rowOff,
        ) == (11, 50000, 74, 692150)
        assert (
            img_tnb_swg.anchor.to.col,
            img_tnb_swg.anchor.to.colOff,
            img_tnb_swg.anchor.to.row,
            img_tnb_swg.anchor.to.rowOff,
        ) == (13, 100000, 79, 190500)

        # 2. Transformer: Vendor at F73:G76, TNB at R73:S76
        ws_tx = wb["TX"]
        assert ws_tx["F73"].value is None
        assert ws_tx["R73"].value is None
        assert len(ws_tx._images) == 2
        img_vendor_tx = ws_tx._images[0]
        img_tnb_tx = ws_tx._images[1]

        assert (
            img_vendor_tx.anchor._from.col,
            img_vendor_tx.anchor._from.colOff,
            img_vendor_tx.anchor._from.row,
            img_vendor_tx.anchor._from.rowOff,
        ) == (5, 50000, 72, 25400)
        assert (
            img_vendor_tx.anchor.to.col,
            img_vendor_tx.anchor.to.colOff,
            img_vendor_tx.anchor.to.row,
            img_vendor_tx.anchor.to.rowOff,
        ) == (7, 200000, 76, 0)

        assert (
            img_tnb_tx.anchor._from.col,
            img_tnb_tx.anchor._from.colOff,
            img_tnb_tx.anchor._from.row,
            img_tnb_tx.anchor._from.rowOff,
        ) == (17, 50000, 72, 25400)
        assert (
            img_tnb_tx.anchor.to.col,
            img_tnb_tx.anchor.to.colOff,
            img_tnb_tx.anchor.to.row,
            img_tnb_tx.anchor.to.rowOff,
        ) == (19, 200000, 76, 0)

        # 3. Visual Inspection: Vendor at D82:G87, TNB at M82:P87
        ws_vi = wb["Visual Inspec."]
        assert ws_vi["D82"].value is None
        assert ws_vi["M82"].value is None
        assert len(ws_vi._images) == 2
        img_vendor_vi = ws_vi._images[0]
        img_tnb_vi = ws_vi._images[1]

        assert (
            img_vendor_vi.anchor._from.col,
            img_vendor_vi.anchor._from.colOff,
            img_vendor_vi.anchor._from.row,
            img_vendor_vi.anchor._from.rowOff,
        ) == (3, 100000, 81, 25400)
        assert (
            img_vendor_vi.anchor.to.col,
            img_vendor_vi.anchor.to.colOff,
            img_vendor_vi.anchor.to.row,
            img_vendor_vi.anchor.to.rowOff,
        ) == (6, 200000, 86, -25400)

        assert (
            img_tnb_vi.anchor._from.col,
            img_tnb_vi.anchor._from.colOff,
            img_tnb_vi.anchor._from.row,
            img_tnb_vi.anchor._from.rowOff,
        ) == (12, 100000, 81, 25400)
        assert (
            img_tnb_vi.anchor.to.col,
            img_tnb_vi.anchor.to.colOff,
            img_tnb_vi.anchor.to.row,
            img_tnb_vi.anchor.to.rowOff,
        ) == (15, 200000, 86, -25400)

        wb.close()

    def test_replace_signatures_33kv_mode_none_strips_text_only(
        self, tmp_path: Path
    ) -> None:
        """In mode='none', cleanly remove {{signvendor}} and {{signtnb}} text without inserting images."""
        xlsx_file = tmp_path / "33kv_testsheet_none.xlsx"
        create_ppu_testsheet_workbook(
            path=xlsx_file,
            has_33kv=True,
            has_11kv=False,
            include_tx_sheet=True,
            include_signature_placeholders=True,
        )

        out_file = tmp_path / "33kv_testsheet_cleaned.xlsx"
        replace_pce_images(
            xlsx_file,
            photo1_path=None,
            photo2_path=None,
            output_path=out_file,
            mode="none",
        )

        wb = openpyxl.load_workbook(out_file)
        for sname in ("33kV (Main)", "TX", "Visual Inspec."):
            ws = wb[sname]
            assert len(ws._images) == 0

        assert wb["33kV (Main)"]["E77"].value is None
        assert wb["33kV (Main)"]["L77"].value is None
        assert wb["TX"]["F73"].value is None
        assert wb["TX"]["R73"].value is None
        assert wb["Visual Inspec."]["D82"].value is None
        assert wb["Visual Inspec."]["M82"].value is None
        wb.close()

    def test_signature_layout_registry_calibrated_coordinates(self) -> None:
        """Declarative registry must define calibrated coordinates for switchgear, transformer, and visual_inspection."""
        assert "switchgear" in SIGNATURE_LAYOUT_REGISTRY
        assert "transformer" in SIGNATURE_LAYOUT_REGISTRY
        assert "visual_inspection" in SIGNATURE_LAYOUT_REGISTRY

        # Switchgear: Vendor E76:F81, TNB L75:M80
        swg = SIGNATURE_LAYOUT_REGISTRY["switchgear"]
        assert (swg.vendor_from.col, swg.vendor_from.col_off, swg.vendor_from.row, swg.vendor_from.row_off) == (4, 113500, 75, 152400)
        assert (swg.vendor_to.col, swg.vendor_to.col_off, swg.vendor_to.row, swg.vendor_to.row_off) == (6, 163500, 80, 63500)
        assert (swg.tnb_from.col, swg.tnb_from.col_off, swg.tnb_from.row, swg.tnb_from.row_off) == (11, 50000, 74, 692150)
        assert (swg.tnb_to.col, swg.tnb_to.col_off, swg.tnb_to.row, swg.tnb_to.row_off) == (13, 100000, 79, 190500)

        # Transformer: Vendor F73:G76, TNB R73:S76
        tx = SIGNATURE_LAYOUT_REGISTRY["transformer"]
        assert (tx.vendor_from.col, tx.vendor_from.col_off, tx.vendor_from.row, tx.vendor_from.row_off) == (5, 50000, 72, 25400)
        assert (tx.vendor_to.col, tx.vendor_to.col_off, tx.vendor_to.row, tx.vendor_to.row_off) == (7, 200000, 76, 0)
        assert (tx.tnb_from.col, tx.tnb_from.col_off, tx.tnb_from.row, tx.tnb_from.row_off) == (17, 50000, 72, 25400)
        assert (tx.tnb_to.col, tx.tnb_to.col_off, tx.tnb_to.row, tx.tnb_to.row_off) == (19, 200000, 76, 0)

        # Visual Inspection: Vendor D82:G87, TNB M82:P87
        vi = SIGNATURE_LAYOUT_REGISTRY["visual_inspection"]
        assert (vi.vendor_from.col, vi.vendor_from.col_off, vi.vendor_from.row, vi.vendor_from.row_off) == (3, 100000, 81, 25400)
        assert (vi.vendor_to.col, vi.vendor_to.col_off, vi.vendor_to.row, vi.vendor_to.row_off) == (6, 200000, 86, -25400)
        assert (vi.tnb_from.col, vi.tnb_from.col_off, vi.tnb_from.row, vi.tnb_from.row_off) == (12, 100000, 81, 25400)
        assert (vi.tnb_to.col, vi.tnb_to.col_off, vi.tnb_to.row, vi.tnb_to.row_off) == (15, 200000, 86, -25400)

    def test_33kv_extra_template_merged_cells_e77_f77(self) -> None:
        """33kV softcopy testsheet template on sheet '33kV (Extra) (2)' must have E77:F77 merged."""
        template_path = Path("templates/TESTSHEET 33kV/33kV_softcopy_testsheet_v1.0.xlsx")
        wb = openpyxl.load_workbook(template_path)
        ws_extra2 = wb["33kV (Extra) (2)"]
        merged_ranges = [str(r) for r in ws_extra2.merged_cells.ranges]
        wb.close()
        assert "E77:F77" in merged_ranges


# ==============================================================================
# 4. Diagonal Borders Scan Ranges & Merged Cells (diagonal_borders.py)
# ==============================================================================


class TestDiagonalBorders33kV:
    """Diagonal borders scanning across Switchgear, TX (5 groups), and VI (unslashed)."""

    def test_diagonal_borders_switchgear_tx_and_vi_ranges(self, tmp_path: Path) -> None:
        """Verify Switchgear scans C15:U62, TX scans 5 groups, and VI is strictly unslashed."""
        xlsx_file = tmp_path / "33kv_diagonals.xlsx"
        wb = create_ppu_testsheet_workbook(
            has_33kv=True,
            has_11kv=False,
            include_tx_sheet=True,
            transformer_ratings=["15 MVA"],
        )

        # 1. Switchgear sheet: leave blank cells in measurement grid C15:U62
        ws_swg = wb["33kV (Main)"]
        ws_swg["C20"] = ""  # blank cell in C15:U62
        ws_swg["B10"] = ""  # outside range, should NOT be slashed

        # 2. TX sheet: blank cells in the 5 defined groups
        ws_tx = wb["TX"]
        ws_tx["F15"] = ""  # Group 1 (F14:AD28)
        ws_tx["F35"] = ""  # Group 2 (F33:AD47)
        ws_tx["D52"] = ""  # Group 3 (D51:F54)
        ws_tx["D58"] = ""  # Group 4 (D57:O58)
        ws_tx["C65"] = ""  # Group 5 (C62:Q71)
        ws_tx["B5"] = ""   # outside groups, should NOT be slashed

        # 3. Visual Inspection sheet: blank cells should remain strictly unslashed
        ws_vi = wb["Visual Inspec."]
        ws_vi["C10"] = ""
        ws_vi["D15"] = ""

        wb.save(xlsx_file)
        wb.close()

        # Run process_workbook
        out_file = Path(process_workbook(xlsx_file))

        wb_res = openpyxl.load_workbook(out_file)

        # Check Switchgear
        ws_swg_res = wb_res["33kV (Main)"]
        assert ws_swg_res["C20"].border.diagonalUp is True
        assert ws_swg_res["B10"].border.diagonalUp is not True

        # Check TX
        ws_tx_res = wb_res["TX"]
        assert ws_tx_res["F15"].border.diagonalUp is True
        assert ws_tx_res["F35"].border.diagonalUp is True
        assert ws_tx_res["D52"].border.diagonalUp is True
        assert ws_tx_res["D58"].border.diagonalUp is True
        assert ws_tx_res["C65"].border.diagonalUp is True
        assert ws_tx_res["B5"].border.diagonalUp is not True

        # Check Visual Inspection: 0 diagonal cells
        ws_vi_res = wb_res["Visual Inspec."]
        assert ws_vi_res["C10"].border.diagonalUp is not True
        assert ws_vi_res["D15"].border.diagonalUp is not True

        # Confirm all cells in VI are unslashed
        slashed_vi = [
            c.coordinate
            for row in ws_vi_res.iter_rows()
            for c in row
            if c.border and c.border.diagonalUp
        ]
        assert len(slashed_vi) == 0

        wb_res.close()

    def test_diagonal_borders_merged_cells_preservation(self, tmp_path: Path) -> None:
        """In TX sheet, merged cell groups evaluate top-left cell safely."""
        xlsx_file = tmp_path / "33kv_merged_tx.xlsx"
        wb = openpyxl.Workbook()
        ws_tx = wb.active
        ws_tx.title = "TX"

        # Merged range in Group 3 (D51:F54)
        ws_tx.merge_cells("D51:F51")
        ws_tx["D51"] = ""  # blank top-left cell

        # Another merged range with non-blank value
        ws_tx.merge_cells("D52:F52")
        ws_tx["D52"] = "Active LVDB Rating"

        wb.save(xlsx_file)
        wb.close()

        out_file = Path(process_workbook(xlsx_file))
        wb_res = openpyxl.load_workbook(out_file)
        ws_res = wb_res["TX"]

        # Blank merged cell group (evaluated via top-left cell D51) should be slashed
        assert ws_res["D51"].border.diagonalUp is True

        # Populated merged cell group (top-left cell D52 has text) should NOT be slashed
        assert ws_res["D52"].border.diagonalUp is not True
        wb_res.close()


# ==============================================================================
# 5. Programmatic Per-Sheet PageSetup (ComDocumentConverter)
# ==============================================================================


class TestComDocumentConverterPageSetup33kV:
    """Independent PageSetup properties configuration on each sheet before COM export."""

    def test_configure_target_page_setup_switchgear_landscape(self) -> None:
        """Switchgear sheet gets Landscape A4, 2.83 pt side margins, 0 pt top/bottom margins."""
        converter = ComDocumentConverter()
        mock_sheet = MagicMock()
        mock_sheet.Name = "33kV (Main)"

        converter._configure_target_page_setup(mock_sheet)

        assert mock_sheet.PageSetup.PaperSize == 9
        assert mock_sheet.PageSetup.Orientation == 2  # xlLandscape
        assert mock_sheet.PageSetup.LeftMargin == 2.83
        assert mock_sheet.PageSetup.RightMargin == 2.83
        assert mock_sheet.PageSetup.TopMargin == 0
        assert mock_sheet.PageSetup.BottomMargin == 0
        assert mock_sheet.PageSetup.FitToPagesWide == 1
        assert mock_sheet.PageSetup.FitToPagesTall is False
        assert mock_sheet.PageSetup.Zoom is False

    def test_configure_target_page_setup_tx_landscape(self) -> None:
        """Transformer sheet gets Landscape A4, 2.83 pt side margins, 0 pt top/bottom margins."""
        converter = ComDocumentConverter()
        mock_sheet = MagicMock()
        mock_sheet.Name = "TX"

        converter._configure_target_page_setup(mock_sheet)

        assert mock_sheet.PageSetup.PaperSize == 9
        assert mock_sheet.PageSetup.Orientation == 2  # xlLandscape
        assert mock_sheet.PageSetup.LeftMargin == 2.83
        assert mock_sheet.PageSetup.RightMargin == 2.83
        assert mock_sheet.PageSetup.TopMargin == 0
        assert mock_sheet.PageSetup.BottomMargin == 0
        assert mock_sheet.PageSetup.FitToPagesWide == 1
        assert mock_sheet.PageSetup.FitToPagesTall is False
        assert mock_sheet.PageSetup.Zoom is False

    def test_configure_target_page_setup_visual_inspection_portrait(self) -> None:
        """Visual inspection sheet gets Portrait A4, 18 pt side margins, 54 pt top/bottom margins."""
        converter = ComDocumentConverter()
        mock_sheet = MagicMock()
        mock_sheet.Name = "Visual Inspec."

        converter._configure_target_page_setup(mock_sheet)

        assert mock_sheet.PageSetup.PaperSize == 9
        assert mock_sheet.PageSetup.Orientation == 1  # xlPortrait
        assert mock_sheet.PageSetup.LeftMargin == 18.0
        assert mock_sheet.PageSetup.RightMargin == 18.0
        assert mock_sheet.PageSetup.TopMargin == 54.0
        assert mock_sheet.PageSetup.BottomMargin == 54.0
        assert mock_sheet.PageSetup.FitToPagesWide == 1
        assert mock_sheet.PageSetup.FitToPagesTall is False
        assert mock_sheet.PageSetup.Zoom is False

    def test_configure_target_page_setup_11kv_fallback(self) -> None:
        """Existing 11kV sheets retain standard landscape settings with FitToPagesTall=1."""
        converter = ComDocumentConverter()
        mock_sheet = MagicMock()
        mock_sheet.Name = "PCE Testsheet"

        converter._configure_target_page_setup(mock_sheet)

        assert mock_sheet.PageSetup.PaperSize == 9
        assert mock_sheet.PageSetup.Orientation == 2
        assert mock_sheet.PageSetup.FitToPagesWide == 1
        assert mock_sheet.PageSetup.FitToPagesTall == 1


# ==============================================================================
# 6. Deliverable Stitching Pipeline End-to-End
# ==============================================================================


class TestDeliverableStitching33kV:
    """Full post-processing pipeline producing consolidated <STEM>.pdf."""

    def test_deliverable_stitching_multi_orientation_pdf(
        self, mock_env_33kv: ProjectEnvironment, sample_sig_png: Path
    ) -> None:
        """Verify pipeline produces <STEM>.pdf containing portrait QR, landscape SWG/TX, and portrait VI."""
        date_folder = "07-10-2026"
        qr_dir = mock_env_33kv.get_quick_report_dir() / date_folder
        ts_dir = mock_env_33kv.get_testsheet_dir() / date_folder
        raw_dir = mock_env_33kv.get_raw_material_dir() / date_folder

        qr_dir.mkdir(parents=True)
        ts_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)

        stem = "09. PPU SEMAMBU YARD 33-11kV (VI)"
        docx_path = qr_dir / f"{stem}.docx"
        xlsx_path = ts_dir / "09. PPU SEMAMBU YARD 33-11kV.xlsx"
        raw_mat = raw_dir / "09. PPU SEMAMBU YARD 33-11kV (VI)"
        raw_mat.mkdir()

        # Create Quick Report dummy
        docx_path.write_text("dummy quick report")

        # Create 33kV testsheet with 33kV (Main), TX, and Visual Inspec.
        create_ppu_testsheet_workbook(
            path=xlsx_path,
            substation_number=9,
            substation_name="PPU SEMAMBU YARD 33-11kV",
            fl_number="CGBG-PPU-SMBU",
            has_33kv=True,
            has_11kv=False,
            include_tx_sheet=True,
            include_signature_placeholders=True,
        )

        converter = FakeDocumentConverter()
        req = PostProcessingRequest(
            mode=PostProcessingMode.BY_DATE,
            target_dates=(date_folder,),
            vendor_signature_path=sample_sig_png,
            tnb_signature_path=sample_sig_png,
            apply_signatures=True,
            converter=converter,
        )

        summary = run_postprocessing_pipeline(mock_env_33kv, req)

        assert len(summary.processed_packages) == 1
        assert len(summary.final_deliverables) == 1
        deliverable_pdf = summary.final_deliverables[0]
        assert deliverable_pdf.exists()
        assert deliverable_pdf.name == f"{stem}.pdf"

        # Verify page orientations in merged PDF
        reader = PdfReader(str(deliverable_pdf))
        # Total pages: 1 (QR docx) + 3 (33kV Main, TX, Visual Inspec.) = 4 pages
        assert len(reader.pages) == 4

        # Page 0: Quick Report DOCX -> Portrait (h > w)
        p0 = reader.pages[0]
        assert float(p0.mediabox.height) > float(p0.mediabox.width)

        # Page 1: 33kV (Main) -> Landscape (w > h)
        p1 = reader.pages[1]
        assert float(p1.mediabox.width) > float(p1.mediabox.height)

        # Page 2: TX -> Landscape (w > h)
        p2 = reader.pages[2]
        assert float(p2.mediabox.width) > float(p2.mediabox.height)

        # Page 3: Visual Inspec. -> Portrait (h > w)
        p3 = reader.pages[3]
        assert float(p3.mediabox.height) > float(p3.mediabox.width)


# ==============================================================================
# 7. Edge Cases & Robustness Probes (Step 2 - Break It)
# ==============================================================================


class TestEdgeCasesAndRobustnessProbes33kV:
    """Rigorous probes covering placeholder spacing, jpg directory signatures, naming resilience, and preflight prefixes."""

    def test_replace_signatures_with_whitespace_in_placeholders(
        self, tmp_path: Path, sample_sig_png: Path
    ) -> None:
        """Placeholders containing spaces (e.g. {{ signvendor }} or {{ signtnb }}) must be recognized and replaced."""
        xlsx_file = tmp_path / "whitespace_placeholders.xlsx"
        wb = create_ppu_testsheet_workbook(
            path=xlsx_file,
            has_33kv=True,
            has_11kv=False,
            include_tx_sheet=False,
            include_signature_placeholders=False,
        )
        ws = wb["33kV (Main)"]
        ws["E77"] = "  {{ signvendor }}  "
        ws["L77"] = "{{   signtnb   }}"
        wb.save(xlsx_file)
        wb.close()

        out_file = tmp_path / "whitespace_signed.xlsx"
        replace_pce_images(
            xlsx_file,
            photo1_path=sample_sig_png,
            photo2_path=sample_sig_png,
            output_path=out_file,
            mode="placeholder",
        )

        wb_res = openpyxl.load_workbook(out_file)
        ws_res = wb_res["33kV (Main)"]
        assert ws_res["E77"].value is None
        assert ws_res["L77"].value is None
        assert len(ws_res._images) == 2
        wb_res.close()

    def test_replace_signatures_loads_jpg_from_directory(
        self, tmp_path: Path
    ) -> None:
        """Directories containing .jpg or .jpeg signature files must be supported."""
        sig_dir = tmp_path / "jpg_signatures"
        sig_dir.mkdir()
        jpg_path = sig_dir / "tested_by.jpg"
        img = PILImage.new("RGB", (100, 50), color=(255, 0, 0))
        img.save(jpg_path)

        xlsx_file = tmp_path / "test_jpg_sig.xlsx"
        create_ppu_testsheet_workbook(
            path=xlsx_file,
            has_33kv=True,
            has_11kv=False,
            include_tx_sheet=False,
            include_signature_placeholders=True,
        )

        out_file = tmp_path / "test_jpg_sig_out.xlsx"
        replace_pce_images(
            xlsx_file,
            photo1_path=sig_dir,
            photo2_path=sig_dir,
            output_path=out_file,
            mode="placeholder",
        )

        wb_res = openpyxl.load_workbook(out_file)
        ws_res = wb_res["33kV (Main)"]
        assert len(ws_res._images) == 2
        assert ws_res._images[0].format == "jpeg"
        wb_res.close()

    def test_classify_sheet_layout_naming_resilience(self) -> None:
        """Visual inspection sheets named '33kV Visual Inspec.' or with multiple spaces must not be classified as switchgear or unknown."""
        assert classify_sheet_layout("33kV Visual Inspec.") == "visual_inspection"
        assert classify_sheet_layout("33kV Visual Inspection") == "visual_inspection"
        assert classify_sheet_layout("Visual  Inspection") == "visual_inspection"
        assert classify_sheet_layout("Visual   Inspec.") == "visual_inspection"
        assert classify_sheet_layout("33kV VI") == "visual_inspection"
        assert classify_sheet_layout("11kV VI") == "visual_inspection"
        assert classify_sheet_layout("33 kV VI") == "visual_inspection"
        assert classify_sheet_layout("11 kV VI") == "visual_inspection"
        assert classify_sheet_layout("33kV VI (1)") == "visual_inspection"
        assert classify_sheet_layout("11kV VI_2") == "visual_inspection"
        assert classify_sheet_layout("VI") == "visual_inspection"
        assert classify_sheet_layout("VI-01") == "visual_inspection"
        assert classify_sheet_layout("VI/US") == "visual_inspection"
        assert classify_sheet_layout("33kV VI/US") == "visual_inspection"
        assert classify_sheet_layout("VI.01") == "visual_inspection"
        assert classify_sheet_layout("VI1") == "visual_inspection"
        assert classify_sheet_layout("Vibration") == "unknown"
        assert classify_sheet_layout("33kV Vibration") == "switchgear"
        assert classify_sheet_layout("33 kV Vibration") == "switchgear"
        assert classify_sheet_layout("33kV  (Main)") == "switchgear"
        assert classify_sheet_layout("33 kV (Main)") == "switchgear"
        assert classify_sheet_layout("11kV  (Extra)") == "switchgear"
        assert classify_sheet_layout("11 kV (Extra)") == "switchgear"

    def test_select_and_sort_sheets_whitespace_and_extra_numbering_resilience(self) -> None:
        """Sheet selection and sorting handles multiple spaces and non-parenthesized extra numbering (e.g. '33kV (Extra) 2')."""
        sheets = [
            "Visual  Inspection",
            "33kV (Extra) 2",
            "11kV  (Main)",
            "33kV  (Main)",
            "TX",
            "33kV (Extra)",
            "RAW DATA",
        ]
        sorted_sheets = select_and_sort_sheets(sheets)
        assert sorted_sheets == [
            "33kV  (Main)",
            "33kV (Extra)",
            "33kV (Extra) 2",
            "11kV  (Main)",
            "TX",
            "Visual  Inspection",
        ]

        # Space-separated voltage tokens and standalone switchgear sheets must not be dropped
        assert select_and_sort_sheets(["33 kV (Main)", "33 kV VI", "TX"]) == [
            "33 kV (Main)",
            "TX",
            "33 kV VI",
        ]
        assert select_and_sort_sheets(["33kV", "TX", "33kV VI"]) == [
            "33kV",
            "TX",
            "33kV VI",
        ]

    def test_preflight_validation_rejects_missing_numerical_prefix(
        self, mock_env_33kv: ProjectEnvironment
    ) -> None:
        """Pre-flight validation fails when files in date folder lack numerical prefixes."""
        date_str = "09-10-2026"
        qr_dir = mock_env_33kv.get_quick_report_dir() / date_str
        ts_dir = mock_env_33kv.get_testsheet_dir() / date_str
        qr_dir.mkdir(parents=True)
        ts_dir.mkdir(parents=True)

        (qr_dir / "PPU SEMAMBU YARD 33-11kV.docx").write_text("docx")
        (ts_dir / "PPU SEMAMBU YARD 33-11kV.xlsx").write_text("xlsx")

        with pytest.raises(PreFlightValidationError) as exc_info:
            validate_postprocessing_preflight(mock_env_33kv, date_str)
        assert "missing numerical prefix" in str(exc_info.value).lower()

    def test_preflight_validation_rejects_duplicate_numerical_prefixes(
        self, mock_env_33kv: ProjectEnvironment
    ) -> None:
        """Pre-flight validation fails when multiple files share the same numerical prefix."""
        date_str = "10-10-2026"
        qr_dir = mock_env_33kv.get_quick_report_dir() / date_str
        ts_dir = mock_env_33kv.get_testsheet_dir() / date_str
        qr_dir.mkdir(parents=True)
        ts_dir.mkdir(parents=True)

        (qr_dir / "01. PPU ALPHA.docx").write_text("docx")
        (qr_dir / "01. PPU BETA.docx").write_text("docx")
        (ts_dir / "01. PPU ALPHA.xlsx").write_text("xlsx")
        (ts_dir / "01. PPU BETA.xlsx").write_text("xlsx")

        with pytest.raises(PreFlightValidationError) as exc_info:
            validate_postprocessing_preflight(mock_env_33kv, date_str)
        assert "duplicate numerical prefix" in str(exc_info.value).lower()

    def test_fake_document_converter_filters_unpopulated_extra_sheets(
        self, tmp_path: Path
    ) -> None:
        """FakeDocumentConverter strictly excludes unpopulated extra template sheets from generated PDF."""
        xlsx_file = tmp_path / "33kv_unpopulated_extra.xlsx"
        create_ppu_testsheet_workbook(
            path=xlsx_file,
            has_33kv=True,
            has_11kv=False,
            extra_panels_33kv=([],),  # 33kV (Extra) sheet exists but has 0 panels (unpopulated B15/C15)
            include_tx_sheet=True,
        )

        converter = FakeDocumentConverter()
        pdf_file = tmp_path / "out.pdf"
        converter.convert_testsheet_to_pdf(xlsx_file, pdf_file)

        reader = PdfReader(str(pdf_file))
        # Expected sheets: 33kV (Main), TX, Visual Inspec. (total 3 pages, NOT 4 pages)
        assert len(reader.pages) == 3

