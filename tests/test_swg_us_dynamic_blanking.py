"""Comprehensive tests for Switchgear Panel Ultrasound Dynamic Blanking & PRPD Optimization (Issue #42).

Tests:
1. Two-tier evaluation (contract awarded technologies & switchgear compartment eligibility).
2. Normalization of switchgear compartment names:
   - Precedence rule for LINK BOX / LINKBOX / CABLE LINK BOX before generic CABLE.
   - Secondary Compartment / Control / Metering normalization.
3. OpenXML dynamic blanking on swg-panel.docx (rows 21-32, cols 1-8):
   - Cell text cleared
   - Shading (<w:shd>) removed
   - Borders set to <w:val="nil"/>
   - Surrounding TEV cells (cols 11-22) and IR cells (rows 1-20) untouched
   - Simultaneous blanking of US and TEV for IR-only contracts
4. PRPD generation optimization:
   - Non-US compartment (Secondary Compartment, Link Box) or include_us=False skips Chromium / US decoding and returns None.
5. Full Report Scan Adapter integration:
   - Secondary Compartment & Link Box have US blanked; Cable / Breaker / Busbar have US active.
   - Non-US contract: all compartments have US blanked.
   - VCB 7-compartments matrix for US vs TEV.
6. Quick Report CBM render integration:
   - Secondary / Link Box defect has US blanked and empty string context values.
   - Non-US contract has US blanked.
   - IR-only contract has both US and TEV blanked simultaneously.
   - Breaker defect under 3-tech contract preserves US.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import docx
from docx.oxml.ns import qn
import pytest

from src.core.shading import (
    blank_swg_tev_cells,
    blank_swg_us_cells,
    get_cell_shading,
    is_swg_compartment_us_eligible,
    is_swg_us_active,
    is_us_contract_awarded,
    normalize_swg_compartment,
)
from src.core.topology import SwitchgearArchetype
from src.full_report.models import (
    SwitchgearPanelScanSpec,
    SwitchgearScanSpec,
)
from src.full_report.scan_adapters import SwitchgearScanAdapter
from src.full_report.scan_render import FullReportScanPageRendererCore
from src.quick_report.cbm_render import (
    _build_swg_render_context,
    _render_docx_template,
)
from src.quick_report.defects import CbmDefectRecord
from src.quick_report.prpd import generate_prpd_graphs_for_swg_panel


SWG_PANEL_TEMPLATE = Path("templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx")
QR_SWG_PANEL_TEMPLATE = Path("templates/QUICK REPORT/DEFECT IR US TEV/swg-panel.docx")


# ==============================================================================
# 1. Two-Tier Model & Compartment Normalization Tests
# ==============================================================================

class TestSwitchgearCompartmentUsEligibility:
    """Test compartment normalization and US eligibility rules."""

    @pytest.mark.parametrize(
        "raw_comp,expected_norm",
        [
            ("Link Box", "LINK BOX"),
            ("LINKBOX", "LINK BOX"),
            ("Cable Link Box", "LINK BOX"),
            ("CABLE LINKBOX", "LINK BOX"),
            ("LINK-BOX", "LINK BOX"),
            ("CABLE LINK-BOX", "LINK BOX"),
            ("LINK_BOX", "LINK BOX"),
            ("CABLE LINK_BOX", "LINK BOX"),
            ("BOX CABLE LINK", "LINK BOX"),
            ("Secondary Compartment", "SECONDARY COMPARTMENT"),
            ("Secondary", "SECONDARY COMPARTMENT"),
            ("Control Compartment", "SECONDARY COMPARTMENT"),
            ("Control Box", "SECONDARY COMPARTMENT"),
            ("Control", "SECONDARY COMPARTMENT"),
            ("Metering", "SECONDARY COMPARTMENT"),
            ("Breaker Compartment", "BREAKER COMPARTMENT"),
            ("VCB", "BREAKER COMPARTMENT"),
            ("VCB PANEL 1", "BREAKER COMPARTMENT"),
            ("CB", "BREAKER COMPARTMENT"),
            ("CB Compartment", "BREAKER COMPARTMENT"),
            ("Spout", "BREAKER COMPARTMENT"),
            ("CONTACT SPOUT", "BREAKER COMPARTMENT"),
            ("Arc Chamber", "BREAKER COMPARTMENT"),
            ("Cable Compartment", "CABLE COMPARTMENT"),
            ("Cable Box", "CABLE COMPARTMENT"),
            ("Cable Termination", "CABLE COMPARTMENT"),
            ("Cable Lug", "CABLE COMPARTMENT"),
            ("Cable Entry", "CABLE ENTRY"),
            ("Cable Entry Bottom", "CABLE ENTRY"),
            ("Entry Cable", "CABLE ENTRY"),
            ("Cable Inlet", "CABLE ENTRY"),
            ("Busbar", "BUSBAR COMPARTMENT"),
            ("Busbar Compartment", "BUSBAR COMPARTMENT"),
            ("PT Compartment", "PT COMPARTMENT"),
            ("Voltage Transformer", "PT COMPARTMENT"),
            ("Potential Transformer", "PT COMPARTMENT"),
            ("VT", "PT COMPARTMENT"),
            ("VT Compartment", "PT COMPARTMENT"),
            ("Fuse Compartment", "FUSE COMPARTMENT"),
            ("Outgoing Fuse", "FUSE COMPARTMENT"),
            ("Secondary Compartment", "SECONDARY COMPARTMENT"),
            ("Back Compartment", "REAR COMPARTMENT"),
            ("BACK COMPARTMENT", "REAR COMPARTMENT"),
            ("Back", "REAR COMPARTMENT"),
            ("BACK", "REAR COMPARTMENT"),
            ("Rear Compartment", "REAR COMPARTMENT"),
            ("REAR COMPARTMENT", "REAR COMPARTMENT"),
            ("Rear", "REAR COMPARTMENT"),
            ("REAR", "REAR COMPARTMENT"),
            ("Front Compartment", "FRONT COMPARTMENT"),
            ("FRONT COMPARTMENT", "FRONT COMPARTMENT"),
            ("Front", "FRONT COMPARTMENT"),
            ("FRONT", "FRONT COMPARTMENT"),
        ],
    )
    def test_normalize_swg_compartment(self, raw_comp: str, expected_norm: str):
        assert normalize_swg_compartment(raw_comp) == expected_norm

    @pytest.mark.parametrize(
        "comp,expected_eligible",
        [
            # US-Excluded / Blanked
            ("SECONDARY COMPARTMENT", False),
            ("Secondary Compartment", False),
            ("Secondary", False),
            ("Control Compartment", False),
            ("Metering", False),
            ("LINK BOX", False),
            ("Link Box", False),
            ("LINKBOX", False),
            ("Cable Link Box", False),
            ("LINK-BOX", False),
            ("CABLE LINK-BOX", False),
            ("Control Box", False),
            ("Control", False),
            ("", False),
            (None, False),
            # US-Eligible (all standard switchgear compartments)
            ("BREAKER COMPARTMENT", True),
            ("Breaker", True),
            ("VCB", True),
            ("CB", True),
            ("CB Compartment", True),
            ("Spout", True),
            ("Chamber", True),
            ("CABLE COMPARTMENT", True),
            ("Cable Box", True),
            ("PT COMPARTMENT", True),
            ("Voltage Transformer", True),
            ("Potential Transformer", True),
            ("VT", True),
            ("VT Compartment", True),
            ("FUSE COMPARTMENT", True),
            ("Fuse", True),
            ("CABLE ENTRY", True),
            ("Cable Entry", True),
            ("Entry Cable", True),
            ("Cable Inlet", True),
            ("BUSBAR COMPARTMENT", True),
            ("Busbar", True),
            ("BACK COMPARTMENT", True),
            ("Back Compartment", True),
            ("REAR COMPARTMENT", True),
            ("Rear Compartment", True),
            ("FRONT COMPARTMENT", True),
            ("Front Compartment", True),
        ],
    )
    def test_is_swg_compartment_us_eligible(self, comp: str | None, expected_eligible: bool):
        assert is_swg_compartment_us_eligible(comp) is expected_eligible

    def test_link_box_precedence_over_cable(self):
        """Cable Link Box must be normalized to LINK BOX and NOT CABLE COMPARTMENT."""
        norm = normalize_swg_compartment("Cable Link Box")
        assert norm == "LINK BOX"
        assert is_swg_compartment_us_eligible("Cable Link Box") is False


class TestUsContractAwardedTechnologies:
    """Test Tier 1: contract technology evaluation for Ultrasound."""

    @pytest.mark.parametrize(
        "techs,expected",
        [
            (None, True),  # Default 3-tech contract
            ([], True),
            (["IR", "US", "TEV"], True),
            ({"IR", "US", "TEV"}, True),
            (["US"], True),
            ("IR+US+TEV", True),
            (["IR", "US"], True),
            ("IR, US", True),
            ("INFRARED+ULTRASOUND", True),
            (["IR"], False),
            (["TEV"], False),
            (["IR", "TEV"], False),
            ("IR, TEV", False),
            ("INFRARED+TEV", False),
            ("IR", False),
        ],
    )
    def test_is_us_contract_awarded(self, techs, expected):
        assert is_us_contract_awarded(techs) is expected

    def test_is_swg_us_active_combined(self):
        # Tier 1 True + Tier 2 True -> True
        assert is_swg_us_active(["IR", "US", "TEV"], "Cable Compartment") is True
        assert is_swg_us_active(None, "Breaker Compartment") is True
        assert is_swg_us_active(["US"], "Spout") is True
        assert is_swg_us_active(["US"], "Fuse Compartment") is True
        assert is_swg_us_active(["US"], "Cable Entry") is True
        assert is_swg_us_active(["US"], "Busbar Compartment") is True

        # Tier 1 True + Tier 2 False -> False (compartment excluded: Secondary / Link Box)
        assert is_swg_us_active(["IR", "US", "TEV"], "Secondary Compartment") is False
        assert is_swg_us_active(["IR", "US", "TEV"], "Link Box") is False
        assert is_swg_us_active(None, "Cable Link Box") is False
        assert is_swg_us_active(None, "Control Compartment") is False

        # Tier 1 False + Tier 2 True -> False (contract lacks US)
        assert is_swg_us_active(["IR", "TEV"], "Cable Compartment") is False
        assert is_swg_us_active(["IR", "TEV"], "Breaker Compartment") is False
        assert is_swg_us_active(["IR"], "Cable Entry") is False
        assert is_swg_us_active(["IR"], "Busbar") is False

        # Tier 1 False + Tier 2 False -> False
        assert is_swg_us_active(["IR"], "Secondary Compartment") is False
        assert is_swg_us_active(["IR"], "Link Box") is False


# ==============================================================================
# 2. OpenXML Blanking Mechanism Tests
# ==============================================================================

class TestOpenXmlUsBlanking:
    """Validate OpenXML blanking modifies only Ultrasound cells in swg-panel.docx."""

    @pytest.fixture
    def swg_panel_doc(self) -> docx.Document:
        if not SWG_PANEL_TEMPLATE.exists():
            pytest.skip(f"Template not found: {SWG_PANEL_TEMPLATE}")
        return docx.Document(SWG_PANEL_TEMPLATE)

    def test_blank_swg_us_cells_modifies_expected_region(self, swg_panel_doc: docx.Document):
        table = swg_panel_doc.tables[0]
        assert len(table.rows) == 37
        assert len(table.columns) == 24

        # Apply US blanking
        blank_swg_us_cells(swg_panel_doc)

        # 1. Verify all US cells (rows 21..32, cols 1..8) are blanked via python-docx cell interface
        for r_idx in range(21, 33):
            for c_idx in range(1, 9):
                cell = table.rows[r_idx].cells[c_idx]
                assert cell.text.strip() == "", f"Cell ({r_idx}, {c_idx}) text not cleared: {cell.text}"
                tcPr = cell._tc.get_or_add_tcPr()
                shd = tcPr.find(qn("w:shd"))
                assert shd is None or shd.get(qn("w:fill")) in (None, "FFFFFF", "clear"), (
                    f"Cell ({r_idx}, {c_idx}) has unexpected fill: {shd.get(qn('w:fill')) if shd is not None else None}"
                )
                tcBorders = tcPr.find(qn("w:tcBorders"))
                assert tcBorders is not None, f"Cell ({r_idx}, {c_idx}) missing tcBorders"
                for b_name in ("top", "left", "bottom", "right"):
                    b = tcBorders.find(qn(f"w:{b_name}"))
                    assert b is not None, f"Cell ({r_idx}, {c_idx}) missing border {b_name}"
                    assert b.get(qn("w:val")) == "nil", f"Cell ({r_idx}, {c_idx}) border {b_name} not nil"

        # 2. Verify raw XML <w:tc> elements in rows 21..32 (including vMerge continuation rows 23..27 for us.prpd)
        for r_idx in range(21, 33):
            row = table.rows[r_idx]
            col_idx = 0
            for tc in row._tr.findall(qn("w:tc")):
                tcPr = tc.find(qn("w:tcPr"))
                gridSpan_elem = tcPr.find(qn("w:gridSpan")) if tcPr is not None else None
                span = int(gridSpan_elem.attrib.get(qn("w:val"), 1)) if gridSpan_elem is not None else 1
                col_start = col_idx
                col_end = col_idx + span - 1
                col_idx += span

                # US cells (cols 1..8)
                if col_start >= 1 and col_end <= 8:
                    txt = "".join(tc.itertext()).strip()
                    assert txt == "", f"Row {r_idx} cols {col_start}..{col_end} XML text not empty: {txt}"
                    shd = tcPr.find(qn("w:shd")) if tcPr is not None else None
                    assert shd is None or shd.get(qn("w:fill")) in (None, "FFFFFF", "clear")
                    tcBorders = tcPr.find(qn("w:tcBorders")) if tcPr is not None else None
                    assert tcBorders is not None, f"Row {r_idx} cols {col_start}..{col_end} missing tcBorders"
                    for b_name in ("top", "left", "bottom", "right"):
                        b = tcBorders.find(qn(f"w:{b_name}"))
                        assert b is not None, f"Row {r_idx} cols {col_start}..{col_end} missing border {b_name}"
                        assert b.get(qn("w:val")) == "nil", f"Row {r_idx} cols {col_start}..{col_end} border {b_name} not nil"

                # Adjacent left spacer (ending at col 0)
                elif col_end == 0:
                    tcBorders = tcPr.find(qn("w:tcBorders")) if tcPr is not None else None
                    assert tcBorders is not None, f"Row {r_idx} col 0 spacer missing tcBorders"
                    b_right = tcBorders.find(qn("w:right"))
                    assert b_right is not None, f"Row {r_idx} col 0 spacer missing right border"
                    assert b_right.get(qn("w:val")) == "nil", f"Row {r_idx} col 0 spacer right border not nil"

                # Adjacent right spacer (starting at col 9)
                elif col_start == 9:
                    tcBorders = tcPr.find(qn("w:tcBorders")) if tcPr is not None else None
                    assert tcBorders is not None, f"Row {r_idx} col 9 spacer missing tcBorders"
                    b_left = tcBorders.find(qn("w:left"))
                    assert b_left is not None, f"Row {r_idx} col 9 spacer missing left border"
                    assert b_left.get(qn("w:val")) == "nil", f"Row {r_idx} col 9 spacer left border not nil"

        # 3. Verify Row 20 top spacer bottom borders facing US block
        row_20 = table.rows[20]
        col_idx = 0
        for tc in row_20._tr.findall(qn("w:tc")):
            tcPr = tc.find(qn("w:tcPr"))
            gridSpan_elem = tcPr.find(qn("w:gridSpan")) if tcPr is not None else None
            span = int(gridSpan_elem.attrib.get(qn("w:val"), 1)) if gridSpan_elem is not None else 1
            col_start = col_idx
            col_end = col_idx + span - 1
            col_idx += span
            if max(col_start, 1) <= min(col_end, 8):
                tcBorders = tcPr.find(qn("w:tcBorders")) if tcPr is not None else None
                assert tcBorders is not None
                b_bot = tcBorders.find(qn("w:bottom"))
                assert b_bot is not None
                assert b_bot.get(qn("w:val")) == "nil", "Row 20 spacer bottom border facing US not nil"

        # 4. Verify Row 33 bottom spacer top borders facing US block
        row_33 = table.rows[33]
        col_idx = 0
        for tc in row_33._tr.findall(qn("w:tc")):
            tcPr = tc.find(qn("w:tcPr"))
            gridSpan_elem = tcPr.find(qn("w:gridSpan")) if tcPr is not None else None
            span = int(gridSpan_elem.attrib.get(qn("w:val"), 1)) if gridSpan_elem is not None else 1
            col_start = col_idx
            col_end = col_idx + span - 1
            col_idx += span
            if max(col_start, 1) <= min(col_end, 8):
                tcBorders = tcPr.find(qn("w:tcBorders")) if tcPr is not None else None
                assert tcBorders is not None
                b_top = tcBorders.find(qn("w:top"))
                assert b_top is not None
                assert b_top.get(qn("w:val")) == "nil", "Row 33 spacer top border facing US not nil"

        # 5. Verify TEV cells (rows 21..32, cols 11..22) are NOT blanked / corrupted
        cell_tev_head = table.rows[21].cells[11]
        assert "TEV" in cell_tev_head.text.upper()
        tc_tev_prpd = table.rows[23].cells[11]._tc
        tcBorders = tc_tev_prpd.find(qn("w:tcPr")).find(qn("w:tcBorders"))
        assert tcBorders.find(qn("w:top")).get(qn("w:val")) == "single"
        assert tcBorders.find(qn("w:left")).get(qn("w:val")) == "single"

    def test_blank_swg_us_cells_idempotent(self, swg_panel_doc: docx.Document):
        """Blanking twice should not raise errors."""
        blank_swg_us_cells(swg_panel_doc)
        blank_swg_us_cells(swg_panel_doc)
        table = swg_panel_doc.tables[0]
        cell = table.rows[25].cells[3]
        assert cell.text.strip() == ""

    def test_blank_swg_us_cells_supports_iterable_of_documents(self):
        """blank_swg_us_cells must support being passed a list/tuple of Document objects."""
        doc1 = docx.Document(SWG_PANEL_TEMPLATE)
        doc2 = docx.Document(SWG_PANEL_TEMPLATE)
        blank_swg_us_cells([doc1, doc2])
        assert doc1.tables[0].rows[23].cells[1].text.strip() == ""
        assert doc2.tables[0].rows[23].cells[1].text.strip() == ""

    def test_blank_swg_us_cells_ignores_non_24_column_tables(self):
        """Tables not matching exactly 24 columns (e.g. 23 or 25 cols) must not be modified."""
        # 23-column table (tx-hv-sides.docx)
        tx_doc = docx.Document("templates/FULL REPORT/NORMAL IR US TEV/tx-hv-sides.docx")
        t23 = tx_doc.tables[0]
        assert len(t23.columns) == 23
        us_text_before = t23.rows[21].cells[1].text
        blank_swg_us_cells(tx_doc)
        assert t23.rows[21].cells[1].text == us_text_before

        # 25-column synthetic table
        synthetic_doc = docx.Document()
        t25 = synthetic_doc.add_table(rows=35, cols=25)
        t25.rows[21].cells[3].text = "DO_NOT_CLEAR_US"
        blank_swg_us_cells(synthetic_doc)
        assert t25.rows[21].cells[3].text == "DO_NOT_CLEAR_US"

    def test_blank_swg_us_cells_quick_report_template(self):
        """Verify Quick Report template swg-panel.docx US PRPD quadrant borders are all nil."""
        if not QR_SWG_PANEL_TEMPLATE.exists():
            pytest.skip("QR template swg-panel.docx not found.")
        doc = docx.Document(QR_SWG_PANEL_TEMPLATE)
        blank_swg_us_cells(doc)
        table = doc.tables[0]
        for r_idx in range(21, 33):
            row = table.rows[r_idx]
            col_idx = 0
            for tc in row._tr.findall(qn("w:tc")):
                tcPr = tc.find(qn("w:tcPr"))
                gridSpan_elem = tcPr.find(qn("w:gridSpan")) if tcPr is not None else None
                span = int(gridSpan_elem.attrib.get(qn("w:val"), 1)) if gridSpan_elem is not None else 1
                col_start = col_idx
                col_end = col_idx + span - 1
                col_idx += span

                if col_start >= 1 and col_end <= 8:
                    assert "".join(tc.itertext()).strip() == ""
                    tcBorders = tcPr.find(qn("w:tcBorders"))
                    assert tcBorders is not None
                    for b_name in ("top", "left", "bottom", "right"):
                        b = tcBorders.find(qn(f"w:{b_name}"))
                        assert b is not None and b.get(qn("w:val")) == "nil"
                elif col_end == 0:
                    tcBorders = tcPr.find(qn("w:tcBorders"))
                    assert tcBorders is not None
                    assert tcBorders.find(qn("w:right")).get(qn("w:val")) == "nil"
                elif col_start == 9:
                    tcBorders = tcPr.find(qn("w:tcBorders"))
                    assert tcBorders is not None
                    assert tcBorders.find(qn("w:left")).get(qn("w:val")) == "nil"

    def test_simultaneous_us_and_tev_blanking(self, swg_panel_doc: docx.Document):
        """IR-only contracts blank both US (cols 1..8) and TEV (cols 11..22) simultaneously."""
        blank_swg_us_cells(swg_panel_doc)
        blank_swg_tev_cells(swg_panel_doc)

        table = swg_panel_doc.tables[0]
        # Verify both US and TEV quadrants are cleared
        for r_idx in range(21, 33):
            # US cols 1..8
            for c_idx in range(1, 9):
                cell = table.rows[r_idx].cells[c_idx]
                assert cell.text.strip() == ""
                tcBorders = cell._tc.get_or_add_tcPr().find(qn("w:tcBorders"))
                assert tcBorders is not None
                assert tcBorders.find(qn("w:top")).get(qn("w:val")) == "nil"
            # TEV cols 11..22
            for c_idx in range(11, 23):
                cell = table.rows[r_idx].cells[c_idx]
                assert cell.text.strip() == ""
                tcBorders = cell._tc.get_or_add_tcPr().find(qn("w:tcBorders"))
                assert tcBorders is not None
                assert tcBorders.find(qn("w:top")).get(qn("w:val")) == "nil"

        # Verify IR/Visual quadrant (rows 1..20) remains intact
        header_cell = table.rows[7].cells[1]
        assert "IR" in header_cell.text.upper()


# ==============================================================================
# 3. PRPD Optimization Tests
# ==============================================================================

class TestPrpdUsOptimization:
    """Verify generate_prpd_graphs_for_swg_panel skips US for non-US compartments and include_us=False."""

    def test_include_us_false_skips_us(self, tmp_path: Path):
        mock_survey = tmp_path / "mock_survey"
        mock_feeder = mock_survey / "P01_INCOMING"
        mock_feeder.mkdir(parents=True)

        with patch("src.quick_report.prpd.find_swg_feeder_survey_dir", return_value=mock_feeder), \
             patch("src.quick_report.prpd.decode_ultrasonic_phase_plot") as mock_decode_us, \
             patch("src.quick_report.prpd.render_prpd_option_c_image") as mock_render_c:

            us_png, tev_png = generate_prpd_graphs_for_swg_panel(
                survey_root=mock_survey,
                panel_no=1,
                output_dir=tmp_path,
                mode="option_b",
                compartment="BREAKER COMPARTMENT",
                include_us=False,
            )

            # US generation must be skipped completely
            assert us_png is None
            mock_decode_us.assert_not_called()
            mock_render_c.assert_not_called()

    def test_compartment_secondary_skips_us_automatically(self, tmp_path: Path):
        mock_survey = tmp_path / "mock_survey"
        mock_feeder = mock_survey / "P01_INCOMING"
        mock_feeder.mkdir(parents=True)

        with patch("src.quick_report.prpd.find_swg_feeder_survey_dir", return_value=mock_feeder), \
             patch("src.quick_report.prpd.decode_ultrasonic_phase_plot") as mock_decode_us, \
             patch("src.quick_report.prpd.render_prpd_option_c_image") as mock_render_c:

            us_png, tev_png = generate_prpd_graphs_for_swg_panel(
                survey_root=mock_survey,
                panel_no=1,
                output_dir=tmp_path,
                mode="option_c",
                compartment="Secondary Compartment",
                include_us=True,  # Even if True, compartment exclusion suppresses it
            )

            assert us_png is None
            mock_decode_us.assert_not_called()
            for call in mock_render_c.call_args_list:
                html_arg = str(call.kwargs.get("html_file") or call.args[0] if call.args else "")
                assert "Ultrasonic.html" not in html_arg

    def test_compartment_link_box_skips_us_automatically(self, tmp_path: Path):
        mock_survey = tmp_path / "mock_survey"
        mock_feeder = mock_survey / "P01_INCOMING"
        mock_feeder.mkdir(parents=True)

        with patch("src.quick_report.prpd.find_swg_feeder_survey_dir", return_value=mock_feeder), \
             patch("src.quick_report.prpd.decode_ultrasonic_phase_plot") as mock_decode_us, \
             patch("src.quick_report.prpd.render_prpd_option_c_image") as mock_render_c:

            us_png, tev_png = generate_prpd_graphs_for_swg_panel(
                survey_root=mock_survey,
                panel_no=1,
                output_dir=tmp_path,
                mode="option_c",
                compartment="Cable Link Box",
                include_us=True,
            )

            assert us_png is None
            mock_decode_us.assert_not_called()
            for call in mock_render_c.call_args_list:
                html_arg = str(call.kwargs.get("html_file") or call.args[0] if call.args else "")
                assert "Ultrasonic.html" not in html_arg


# ==============================================================================
# 4. Full Report Scan Adapter Integration Tests
# ==============================================================================

class TestFullReportScanAdapterUsBlanking:
    """Validate SwitchgearScanAdapter per-compartment US evaluation and rendering."""

    @pytest.fixture
    def tamco_scan_spec(self) -> SwitchgearScanSpec:
        panel = SwitchgearPanelScanSpec(
            panel_no=1,
            name="INCOMING 1",
            panel_type="TAMCO RMU",
            status="CLOSE",
            load_amp="120",
            heater_amp="0.8",
            cable_type="3Cx300mm2 XLPE",
            serial_no="SN-TAMCO-01",
            us_reading="12",
            us_char="NORMAL",
            tev_reading="18",
            compartments=("CABLE COMPARTMENT", "SECONDARY COMPARTMENT"),
        )
        return SwitchgearScanSpec(
            switchgear_type="RMU SF6",
            manufacturer="TAMCO",
            model="GV3",
            rating="11kV 630A",
            serial_no="SN-BOARD-01",
            archetype=SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY,
            panels=[panel],
        )

    def test_tamco_cable_comp_vs_secondary_comp(self, tamco_scan_spec: SwitchgearScanSpec, tmp_path: Path):
        adapter = SwitchgearScanAdapter(
            swg=tamco_scan_spec,
            substation_info={"name_erms": "PE TEST MOCK"},
            project_technologies=["IR", "US", "TEV"],
        )
        items = adapter.adapt()
        panel_items = [it for it in items if not it.is_overview]
        assert len(panel_items) == 2

        item_cable_comp = panel_items[0]
        item_sec_comp = panel_items[1]

        # Cable Compartment: US is active
        assert item_cable_comp.component_name == "CABLE COMPARTMENT"
        assert item_cable_comp.context.get("__blank_us__") is False
        assert item_cable_comp.context.get("is_us_active") is True
        assert item_cable_comp.context["panel"]["us"]["reading"] != ""

        # Secondary Compartment: US is blanked
        assert item_sec_comp.component_name == "SECONDARY COMPARTMENT"
        assert item_sec_comp.context.get("__blank_us__") is True
        assert item_sec_comp.context.get("is_us_active") is False
        assert item_sec_comp.context["panel"]["us"]["reading"] == ""
        assert item_sec_comp.context["panel"]["us"]["char"] == ""
        assert item_sec_comp.context["panel"]["us"]["severity"] == ""
        assert item_sec_comp.context["panel"]["us"]["prpd"] == ""

        # Render both pages and check OpenXML borders
        renderer = FullReportScanPageRendererCore()
        out_cable_comp = tmp_path / "cable_comp_us.docx"
        out_sec_comp = tmp_path / "sec_comp_us.docx"

        item_cable_comp.render(out_cable_comp, renderer=renderer)
        item_sec_comp.render(out_sec_comp, renderer=renderer)

        doc_sec = docx.Document(out_sec_comp)
        t_sec = doc_sec.tables[0]
        # Secondary Compartment US cells must have nil borders and empty text
        for r_idx in range(21, 33):
            for c_idx in range(1, 9):
                cell = t_sec.rows[r_idx].cells[c_idx]
                assert cell.text.strip() == ""
                tcBorders = cell._tc.get_or_add_tcPr().find(qn("w:tcBorders"))
                assert tcBorders is not None
                assert tcBorders.find(qn("w:top")).get(qn("w:val")) == "nil"

    def test_contract_without_us_blanks_all_compartments(self, tamco_scan_spec: SwitchgearScanSpec, tmp_path: Path):
        """If project awarded technologies is only ['IR', 'TEV'], even Cable Compartment has US blanked."""
        adapter = SwitchgearScanAdapter(
            swg=tamco_scan_spec,
            substation_info={"name_erms": "PE TEST MOCK"},
            project_technologies=["IR", "TEV"],
        )
        items = adapter.adapt()
        panel_items = [it for it in items if not it.is_overview]

        for it in panel_items:
            assert it.context.get("__blank_us__") is True
            assert it.context.get("is_us_active") is False
            assert it.context["panel"]["us"]["reading"] == ""

        # Render Cable Compartment docx and verify nil borders on US quadrant
        renderer = FullReportScanPageRendererCore()
        out_file = tmp_path / "no_us_cable_comp.docx"
        panel_items[0].render(out_file, renderer=renderer)

        doc = docx.Document(out_file)
        t = doc.tables[0]
        cell_us = t.rows[25].cells[3]
        assert cell_us.text.strip() == ""
        tcBorders = cell_us._tc.get_or_add_tcPr().find(qn("w:tcBorders"))
        assert tcBorders is not None
        assert tcBorders.find(qn("w:top")).get(qn("w:val")) == "nil"

    def test_vcb_5_standard_compartments_us_matrix(self):
        """Verify VCB standard 5 compartments: Breaker, Cable, PT, Busbar active; Secondary blanked."""
        panel = SwitchgearPanelScanSpec(
            panel_no=1,
            name="VCB 1",
            panel_type="VCB",
            status="CLOSE",
            load_amp="120",
            heater_amp="0.8",
            serial_no="SN-01",
            us_reading="14",
            tev_reading="18",
            compartments=(
                "BREAKER COMPARTMENT",
                "CABLE COMPARTMENT",
                "BUSBAR COMPARTMENT",
                "PT COMPARTMENT",
                "SECONDARY COMPARTMENT",
            ),
        )
        swg = SwitchgearScanSpec(
            switchgear_type="VCB",
            manufacturer="TAMCO",
            model="GV3",
            rating="11kV 630A",
            serial_no="SN-BOARD-01",
            archetype=SwitchgearArchetype.VCB_CUBICLE,
            panels=[panel],
        )
        adapter = SwitchgearScanAdapter(
            swg=swg,
            substation_info={"name_erms": "PE TEST MOCK"},
            project_technologies=["IR", "US", "TEV"],
        )
        res = adapter.adapt()
        panel_items = {it.component_name: it for it in res.items if not it.is_overview}
        assert len(panel_items) == 5

        # Active US compartments (4 out of 5)
        for comp in (
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "PT COMPARTMENT",
            "BUSBAR COMPARTMENT",
        ):
            assert panel_items[comp].context.get("__blank_us__") is False
            assert panel_items[comp].context.get("is_us_active") is True
            assert panel_items[comp].context["panel"]["us"]["reading"] != ""

        # Blanked US compartment (only Secondary Compartment)
        sec_item = panel_items["SECONDARY COMPARTMENT"]
        assert sec_item.context.get("__blank_us__") is True
        assert sec_item.context.get("is_us_active") is False
        assert sec_item.context["panel"]["us"]["reading"] == ""

    def test_vcb_5_transition_compartments_us_matrix(self):
        """Verify VCB transition 5 compartments: Front, Rear, PT, Busbar active; Secondary blanked."""
        panel = SwitchgearPanelScanSpec(
            panel_no=1,
            name="TRANSITION PANEL",
            panel_type="VCB",
            status="CLOSE",
            load_amp="0",
            heater_amp="0.8",
            serial_no="SN-TRANS-01",
            us_reading="14",
            tev_reading="18",
            compartments=(
                "FRONT COMPARTMENT",
                "REAR COMPARTMENT",
                "BUSBAR COMPARTMENT",
                "PT COMPARTMENT",
                "SECONDARY COMPARTMENT",
            ),
        )
        swg = SwitchgearScanSpec(
            switchgear_type="VCB",
            manufacturer="TAMCO",
            model="GV3",
            rating="11kV 630A",
            serial_no="SN-BOARD-01",
            archetype=SwitchgearArchetype.VCB_CUBICLE,
            panels=[panel],
        )
        adapter = SwitchgearScanAdapter(
            swg=swg,
            substation_info={"name_erms": "PE TEST MOCK"},
            project_technologies=["IR", "US", "TEV"],
        )
        res = adapter.adapt()
        panel_items = {it.component_name: it for it in res.items if not it.is_overview}
        assert len(panel_items) == 5

        # Active US compartments (4 out of 5: Front, Rear, Busbar, PT)
        for comp in (
            "FRONT COMPARTMENT",
            "REAR COMPARTMENT",
            "PT COMPARTMENT",
            "BUSBAR COMPARTMENT",
        ):
            assert panel_items[comp].context.get("__blank_us__") is False
            assert panel_items[comp].context.get("is_us_active") is True
            assert panel_items[comp].context["panel"]["us"]["reading"] != ""

        # Blanked US compartment (only Secondary Compartment)
        sec_item = panel_items["SECONDARY COMPARTMENT"]
        assert sec_item.context.get("__blank_us__") is True
        assert sec_item.context.get("is_us_active") is False
        assert sec_item.context["panel"]["us"]["reading"] == ""


# ==============================================================================
# 5. Quick Report CBM Render Integration Tests
# ==============================================================================

class TestQuickReportCbmRenderUsBlanking:
    """Validate Quick Report _build_swg_render_context and _render_docx_template US blanking."""

    def test_qr_secondary_defect_blanks_us(self, tmp_path: Path):
        if not QR_SWG_PANEL_TEMPLATE.exists():
            pytest.skip("Template swg-panel.docx not found.")

        rec = CbmDefectRecord(
            equipment="VCB PANEL 1",
            technology="IR",
            defect_area="Secondary Compartment",
            us_reading="18.5",
            us_char="TRACKING",
            tev_reading="25.0",
            tev_char="CONTINUOUS",
        )
        context = _build_swg_render_context(rec, overview=False)
        assert context.get("__blank_us__") is True
        assert context.get("is_us_active") is False
        assert context["panel"]["us"]["reading"] == ""
        assert context["panel"]["us"]["char"] == ""

        out_path = tmp_path / "qr_sec_defect_blanked.docx"
        _render_docx_template(QR_SWG_PANEL_TEMPLATE, out_path, context)

        doc = docx.Document(out_path)
        t = doc.tables[0]
        # Row 30, Col 4 is US severity cell; should be cleared and borders nil
        cell_us = t.rows[30].cells[4]
        assert cell_us.text.strip() == ""
        assert get_cell_shading(cell_us) is None
        tcBorders = cell_us._tc.get_or_add_tcPr().find(qn("w:tcBorders"))
        assert tcBorders is not None
        assert tcBorders.find(qn("w:top")).get(qn("w:val")) == "nil"

    def test_qr_link_box_defect_blanks_us(self, tmp_path: Path):
        if not QR_SWG_PANEL_TEMPLATE.exists():
            pytest.skip("Template swg-panel.docx not found.")

        rec = CbmDefectRecord(
            equipment="VCB PANEL 1",
            technology="IR",
            defect_area="Cable Link Box",
            us_reading="18.5",
            us_char="TRACKING",
        )
        context = _build_swg_render_context(rec, overview=False)
        assert context.get("__blank_us__") is True
        assert context.get("is_us_active") is False
        assert context["panel"]["us"]["reading"] == ""

        out_path = tmp_path / "qr_link_box_blanked.docx"
        _render_docx_template(QR_SWG_PANEL_TEMPLATE, out_path, context)

        doc = docx.Document(out_path)
        t = doc.tables[0]
        cell_us = t.rows[30].cells[4]
        assert cell_us.text.strip() == ""
        assert get_cell_shading(cell_us) is None

    def test_qr_contract_without_us_blanks_spout(self, tmp_path: Path):
        if not QR_SWG_PANEL_TEMPLATE.exists():
            pytest.skip("Template swg-panel.docx not found.")

        rec = CbmDefectRecord(
            equipment="VCB PANEL 1",
            technology="TEV",
            defect_area="Spout",
            us_reading="18.5",
            us_char="TRACKING",
            tev_reading="25.0",
        )
        pe_info = {"project_technologies": ["IR", "TEV"]}
        context = _build_swg_render_context(rec, overview=False, pe_info=pe_info)
        assert context.get("__blank_us__") is True
        assert context.get("is_us_active") is False
        assert context["panel"]["us"]["reading"] == ""

        out_path = tmp_path / "qr_spout_contract_no_us.docx"
        _render_docx_template(QR_SWG_PANEL_TEMPLATE, out_path, context)

        doc = docx.Document(out_path)
        t = doc.tables[0]
        cell_us = t.rows[30].cells[4]
        assert cell_us.text.strip() == ""
        assert get_cell_shading(cell_us) is None
        tcBorders = cell_us._tc.get_or_add_tcPr().find(qn("w:tcBorders"))
        assert tcBorders is not None
        assert tcBorders.find(qn("w:top")).get(qn("w:val")) == "nil"

    def test_qr_ir_only_contract_blanks_both_us_and_tev(self, tmp_path: Path):
        """IR-only contract blanks both US and TEV simultaneously."""
        if not QR_SWG_PANEL_TEMPLATE.exists():
            pytest.skip("Template swg-panel.docx not found.")

        rec = CbmDefectRecord(
            equipment="VCB PANEL 1",
            technology="IR",
            defect_area="Breaker",
            ir_reading="65.4",
            us_reading="18.5",
            tev_reading="25.0",
        )
        pe_info = {"project_technologies": ["IR"]}
        context = _build_swg_render_context(rec, overview=False, pe_info=pe_info)
        assert context.get("__blank_us__") is True
        assert context.get("is_us_active") is False
        assert context.get("__blank_tev__") is True
        assert context.get("is_tev_active") is False

        out_path = tmp_path / "qr_ir_only_contract.docx"
        _render_docx_template(QR_SWG_PANEL_TEMPLATE, out_path, context)

        doc = docx.Document(out_path)
        t = doc.tables[0]
        # US cell (Row 30, Col 4) is nil
        cell_us = t.rows[30].cells[4]
        assert cell_us.text.strip() == ""
        assert cell_us._tc.get_or_add_tcPr().find(qn("w:tcBorders")).find(qn("w:top")).get(qn("w:val")) == "nil"

        # TEV cell (Row 30, Col 18) is nil
        cell_tev = t.rows[30].cells[18]
        assert cell_tev.text.strip() == ""
        assert cell_tev._tc.get_or_add_tcPr().find(qn("w:tcBorders")).find(qn("w:top")).get(qn("w:val")) == "nil"

    def test_qr_spout_under_3_tech_contract_preserves_us(self, tmp_path: Path):
        if not QR_SWG_PANEL_TEMPLATE.exists():
            pytest.skip("Template swg-panel.docx not found.")

        rec = CbmDefectRecord(
            equipment="VCB PANEL 1",
            technology="TEV",
            defect_area="Spout",
            us_reading="12.0",
            us_char="NORMAL",
            tev_reading="30.0",
            tev_char="CONTINUOUS",
        )
        pe_info = {"project_technologies": ["IR", "US", "TEV"]}
        context = _build_swg_render_context(rec, overview=False, pe_info=pe_info)
        assert context.get("__blank_us__") is False
        assert context.get("is_us_active") is True
        assert context["panel"]["us"]["reading"] != ""

        out_path = tmp_path / "qr_spout_3tech_preserved_us.docx"
        _render_docx_template(QR_SWG_PANEL_TEMPLATE, out_path, context)

        doc = docx.Document(out_path)
        t = doc.tables[0]
        # Row 30, Col 4 is US severity cell; healthy so shaded 00B050
        cell_us = t.rows[30].cells[4]
        assert cell_us.text.strip() == ""
        assert get_cell_shading(cell_us) == "00B050"
