"""Unit tests for Full Report Equipment Scan Adapters & PRPD Integration (Ticket #31 / T4.2b).

Validates:
1. Switchgear adapter renders panel scanning pages per manufacturer compartment matrix (D26, D29).
2. Transformer adapter renders unconditional 7-point scanning pages per ADR 0004 and D31.
3. Feeder Pillar and Battery Bank adapters render overview pages with operating parameters.
4. Integrates prpd.py scatter plots, falling back cleanly to "" if survey data is missing (D08).
5. Implements D47 overview page substitution when equipment group has active defects.
6. Context generation across all equipment families.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any
import zipfile

from PIL import Image
import pytest

from src.full_report.models import (
    BatteryBankScanSpec,
    FullReportScanPackage,
    LVDBFeederScanSpec,
    LVDBScanSpec,
    SwitchgearPanelScanSpec,
    SwitchgearScanSpec,
    TransformerScanSpec,
)
from src.core.topology import SwitchgearArchetype
from src.testsheet.models import SwitchgearPanelSpec, SwitchgearSpec
from src.full_report.photo_resolver import PhotoPair, RawPhotoResolver
from src.full_report.scan_adapters import (
    BatteryBankScanAdapter,
    FeederPillarScanAdapter,
    LVDBScanAdapter,
    ScanAdapterResult,
    ScanPageContext,
    ScanRenderItem,
    SwitchgearScanAdapter,
    TransformerScanAdapter,
    adapt_equipment_package,
    find_sliced_overview_page,
)
from src.full_report.scan_render import (
    BANNER_DEFECT_FORWARDING,
    BANNER_HEALTHY_ANALYSIS,
    BANNER_HEALTHY_RECOMMENDATION,
    COLOR_DEFECT,
    COLOR_HEALTHY,
)


@pytest.fixture
def mock_substation_info() -> dict[str, str]:
    return {
        "name_erms": "PE TEST MOCK STATION",
        "date": "28-Aug-2026",
        "time": "11:30 AM",
        "ambient": "32.0 °C",
        "humidity": "65%",
    }


@pytest.fixture
def dummy_image(tmp_path: Path) -> Path:
    img_path = tmp_path / "FLIR0100.jpg"
    im = Image.new("RGB", (64, 48), color=(100, 150, 200))
    im.save(img_path)
    return img_path


@pytest.fixture
def dummy_visual_image(tmp_path: Path) -> Path:
    img_path = tmp_path / "FLIR0100-photo.jpg"
    im = Image.new("RGB", (64, 48), color=(200, 150, 100))
    im.save(img_path)
    return img_path


@pytest.fixture
def dummy_prpd_image(tmp_path: Path) -> Path:
    img_path = tmp_path / "prpd_sample.png"
    im = Image.new("RGB", (80, 40), color=(50, 100, 150))
    im.save(img_path)
    return img_path


class FakePhotoResolver:
    """Test double for RawPhotoResolver."""

    def __init__(self, photo_map: dict[int, tuple[str, str]] | None = None) -> None:
        self.photo_map = photo_map or {}

    def resolve_ir_photo(self, num: Any, warn_if_missing: bool = False) -> str:
        if num is not None and int(num) in self.photo_map:
            return self.photo_map[int(num)][0]
        return ""

    def resolve_visual_photo(self, num: Any, warn_if_missing: bool = False) -> str:
        if num is not None and int(num) in self.photo_map:
            return self.photo_map[int(num)][1]
        return ""

    def resolve_pair(self, num: Any, warn_if_missing: bool = False) -> PhotoPair:
        ir_p = self.resolve_ir_photo(num)
        vis_p = self.resolve_visual_photo(num)
        return PhotoPair(
            ir_photo=ir_p,
            visual_photo=vis_p,
            photo_number=int(num) if num is not None else None,
            ir_path=Path(ir_p) if ir_p else None,
            visual_path=Path(vis_p) if vis_p else None,
        )

    def resolve_cable_split_photo(self, nums: Any, warn_if_missing: bool = False) -> str:
        if isinstance(nums, (list, tuple)) and len(nums) >= 2:
            return self.resolve_ir_photo(nums[1])
        return ""

    def resolve_cable_split_pair(self, nums: Any, warn_if_missing: bool = False) -> PhotoPair:
        if isinstance(nums, (list, tuple)) and len(nums) >= 2:
            return self.resolve_pair(nums[1])
        return PhotoPair()

    def resolve_tx_overview_top_photo(self, num: Any = None, warn_if_missing: bool = False) -> str:
        if num is not None:
            return self.resolve_ir_photo(num)
        return ""

    def resolve_tx_overview_top_pair(self, num: Any = None, warn_if_missing: bool = False) -> PhotoPair:
        if num is not None:
            return self.resolve_pair(num)
        return PhotoPair()


# ==============================================================================
# 1. Switchgear Adapter Tests (D26, D29, D08, D47)
# ==============================================================================

def test_switchgear_adapter_tamco_lucy_compartment_matrix(mock_substation_info: dict[str, str]) -> None:
    """TAMCO/LUCY generates 2 overview pages and 2 scanning pages per panel per D26/D29."""
    swg = SwitchgearScanSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        model="AIR",
        rating="12kV",
        serial_no="SWG-100",
        archetype=SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY,
        overview_compartments=("OVERVIEW", "OVERVIEW BOTTOM"),
        panels=(
            SwitchgearPanelScanSpec(panel_no=1, name="INCOMING 1", compartments=("CABLE COMPARTMENT", "CABLE ENTRY")),
            SwitchgearPanelScanSpec(panel_no=2, name="TX 1 FEEDER", compartments=("CABLE COMPARTMENT", "CABLE ENTRY")),
        ),
        photo_numbers=(10, 11),
    )

    adapter = SwitchgearScanAdapter(swg=swg, substation_info=mock_substation_info)
    result = adapter.adapt()

    assert isinstance(result, ScanAdapterResult)
    assert result.equipment_category == "swg"
    assert result.has_defect is False
    assert result.is_overview_substituted is False

    # 2 overview pages + 2 panels * 2 compartments = 6 total pages
    assert result.page_count == 6
    items = result.items

    # Overviews
    assert items[0].template_name == "swg-overview.docx"
    assert items[0].component_name == "OVERVIEW"
    assert items[0].is_overview is True
    assert items[0].sequence == "p00"
    assert items[0].context["swg"]["area"] == "OVERVIEW"
    assert items[0].context["banner"]["analysis"] == BANNER_HEALTHY_ANALYSIS

    assert items[1].template_name == "swg-overview.docx"
    assert items[1].component_name == "OVERVIEW BOTTOM"
    assert items[1].is_overview is True
    assert items[1].context["swg"]["area"] == "OVERVIEW BOTTOM"

    # Panel 1
    assert items[2].template_name == "swg-panel.docx"
    assert items[2].component_name == "CABLE COMPARTMENT"
    assert items[2].panel_no == 1
    assert items[2].context["panel"]["name"] == "INCOMING 1"
    assert items[2].context["panel"]["area"] == "CABLE COMPARTMENT"

    assert items[3].template_name == "swg-panel.docx"
    assert items[3].component_name == "CABLE ENTRY"
    assert items[3].panel_no == 1
    assert items[3].context["panel"]["area"] == "CABLE ENTRY"

    # Panel 2
    assert items[4].panel_no == 2
    assert items[4].component_name == "CABLE COMPARTMENT"
    assert items[5].panel_no == 2
    assert items[5].component_name == "CABLE ENTRY"


def test_switchgear_adapter_indkom_compartment_matrix(mock_substation_info: dict[str, str]) -> None:
    """INDKOM generates 1 overview page; 1 page per panel (FUSE for TX feeder, CABLE for incomers)."""
    swg = SwitchgearScanSpec(
        switchgear_type="RMU SF6",
        manufacturer="INDKOM",
        archetype=SwitchgearArchetype.RMU_FUSE_CANISTER,
        overview_compartments=("OVERVIEW",),
        panels=(
            SwitchgearPanelScanSpec(panel_no=1, name="INCOMING 1", compartments=("CABLE COMPARTMENT",)),
            SwitchgearPanelScanSpec(panel_no=2, name="TX 1 TEE OFF", compartments=("FUSE COMPARTMENT",)),
        ),
        photo_numbers=(20,),
    )

    adapter = SwitchgearScanAdapter(swg=swg, substation_info=mock_substation_info)
    result = adapter.adapt()

    # 1 overview + 2 panels * 1 = 3 pages
    assert result.page_count == 3
    assert result.items[0].component_name == "OVERVIEW"
    assert result.items[1].component_name == "CABLE COMPARTMENT"
    assert result.items[2].component_name == "FUSE COMPARTMENT"


def test_switchgear_adapter_vcb_standard_5_compartments(mock_substation_info: dict[str, str]) -> None:
    """VCB generates 1 overview and 5 standard compartments per standard panel per D26."""
    vcb_std_comps = (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "PT COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )
    swg = SwitchgearScanSpec(
        switchgear_type="VCB 11kV",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        overview_compartments=("OVERVIEW",),
        panels=(
            SwitchgearPanelScanSpec(
                panel_no=1,
                name="INCOMING 1",
                compartments=vcb_std_comps,
            ),
        ),
        photo_numbers=(30,),
    )

    adapter = SwitchgearScanAdapter(swg=swg, substation_info=mock_substation_info)
    result = adapter.adapt()

    # 1 overview + 1 panel * 5 compartments = 6 pages
    assert result.page_count == 6
    assert result.items[0].component_name == "OVERVIEW"
    panel_compartments = [item.component_name for item in result.items[1:]]
    assert tuple(panel_compartments) == vcb_std_comps


def test_switchgear_adapter_vcb_transition_5_compartments(mock_substation_info: dict[str, str]) -> None:
    """VCB generates 1 overview and 5 transition compartments for a transition panel per D26."""
    vcb_trans_comps = (
        "FRONT COMPARTMENT",
        "REAR COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "PT COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )
    swg = SwitchgearScanSpec(
        switchgear_type="VCB 11kV",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        overview_compartments=("OVERVIEW",),
        panels=(
            SwitchgearPanelScanSpec(
                panel_no=1,
                name="TRANSITION PANEL",
                compartments=vcb_trans_comps,
            ),
        ),
        photo_numbers=(30,),
    )

    adapter = SwitchgearScanAdapter(swg=swg, substation_info=mock_substation_info)
    result = adapter.adapt()

    # 1 overview + 1 panel * 5 compartments = 6 pages
    assert result.page_count == 6
    assert result.items[0].component_name == "OVERVIEW"
    panel_compartments = [item.component_name for item in result.items[1:]]
    assert tuple(panel_compartments) == vcb_trans_comps
    assert tuple(panel_compartments) == (
        "FRONT COMPARTMENT",
        "REAR COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "PT COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )


def test_switchgear_adapter_prpd_integration_and_clean_fallback(
    mock_substation_info: dict[str, str],
    tmp_path: Path,
    dummy_prpd_image: Path,
) -> None:
    """PRPD graphs are injected when present, and fall back cleanly to '' when missing (D08)."""
    swg = SwitchgearScanSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.RMU_STANDARD,
        overview_compartments=("OVERVIEW",),
        panels=(
            SwitchgearPanelScanSpec(panel_no=1, name="PANEL 1", compartments=("CABLE COMPARTMENT",)),
            SwitchgearPanelScanSpec(panel_no=2, name="PANEL 2", compartments=("CABLE COMPARTMENT",)),
        ),
    )

    # Catalog with Panel 1 having US & TEV, Panel 2 having none
    prpd_catalog = {
        "swg": {
            1: {"us": str(dummy_prpd_image), "tev": str(dummy_prpd_image)},
            2: {"us": None, "tev": ""},
        }
    }

    adapter = SwitchgearScanAdapter(
        swg=swg,
        substation_info=mock_substation_info,
        prpd_catalog=prpd_catalog,
    )
    result = adapter.adapt()

    p1_item = result.items[1]
    assert p1_item.context["us"]["prpd"] == str(dummy_prpd_image)
    assert p1_item.context["tev"]["prpd"] == str(dummy_prpd_image)

    p2_item = result.items[2]
    # D08 clean fallback to empty string
    assert p2_item.context["us"]["prpd"] == ""
    assert p2_item.context["tev"]["prpd"] == ""


def test_switchgear_adapter_d47_overview_substitution(
    mock_substation_info: dict[str, str],
    tmp_path: Path,
) -> None:
    """When SWG has active defects, overview page is substituted with sliced QR file (D47)."""
    swg = SwitchgearScanSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.RMU_STANDARD,
        overview_compartments=("OVERVIEW",),
        panels=(
            SwitchgearPanelScanSpec(panel_no=1, name="INCOMING 1", compartments=("CABLE COMPARTMENT",)),
        ),
    )

    # Create dummy sliced overview file
    sliced_ov_file = tmp_path / "swg1_p00_SWG1_OVERVIEW_01.docx"
    sliced_ov_file.write_text("dummy sliced content", encoding="utf-8")

    adapter = SwitchgearScanAdapter(
        swg=swg,
        substation_info=mock_substation_info,
        has_active_defect=True,
        sliced_overview_pages=[sliced_ov_file],
    )
    result = adapter.adapt()

    assert result.has_defect is True
    assert result.is_overview_substituted is True
    ov_item = result.items[0]
    assert ov_item.is_overview is True
    assert ov_item.is_sliced is True
    assert ov_item.sliced_path == sliced_ov_file
    assert ov_item.is_defective is True


def test_switchgear_adapter_defect_forwarding_when_no_slice(
    mock_substation_info: dict[str, str],
) -> None:
    """When SWG has active defect but no sliced file provided, overview banner forwards defect per D30."""
    swg = SwitchgearScanSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.RMU_STANDARD,
        overview_compartments=("OVERVIEW",),
        panels=(
            SwitchgearPanelScanSpec(panel_no=1, name="INCOMING 1", compartments=("CABLE COMPARTMENT",)),
        ),
    )

    adapter = SwitchgearScanAdapter(
        swg=swg,
        substation_info=mock_substation_info,
        has_active_defect=True,
        # No sliced files provided
    )
    result = adapter.adapt()

    assert result.has_defect is True
    assert result.is_overview_substituted is False
    ov_item = result.items[0]
    assert ov_item.is_overview is True
    assert ov_item.is_sliced is False
    assert ov_item.is_defective is True
    assert ov_item.context["banner"]["analysis"] == BANNER_DEFECT_FORWARDING
    assert ov_item.context["banner"]["recommendation"] == BANNER_DEFECT_FORWARDING


# ==============================================================================
# 2. Transformer Adapter Tests (ADR 0004, D31, D08, D48)
# ==============================================================================

def test_transformer_adapter_unconditional_7_point_pages(mock_substation_info: dict[str, str]) -> None:
    """Transformer adapter unconditionally provisions 7 standard pages per ADR 0004 & D31."""
    tx = TransformerScanSpec(
        tx_id="Tx 1",
        rating_kva="1000",
        construction_year="2019",
        manufacturer="MTM",
        serial_no="SN-999",
        type="HERMETICALLY SEALED",
        us_reading="0",
        hv_cable_type="XLPE 3C 240mm2",
        lv_cable_type="PVC 1C 500mm2",
        photo_numbers=(101, 102),
    )

    adapter = TransformerScanAdapter(tx=tx, substation_info=mock_substation_info)
    result = adapter.adapt()

    assert isinstance(result, ScanAdapterResult)
    assert result.equipment_category == "tx"
    assert result.page_count == 7

    expected_specs = [
        ("OVERVIEW", "tx-overview.docx", "s00", True),
        ("OVERVIEW TOP", "tx-overview.docx", "s01", True),
        ("HV BUSHING", "tx-hv-sides.docx", "s02", False),
        ("HV CABLE", "tx-hv-sides.docx", "s03", False),
        ("HV CABLE SPLIT", "tx-hv-sides.docx", "s04", False),
        ("LV BUSHING", "tx-lv-sides.docx", "s05", False),
        ("LV CABLE", "tx-lv-sides.docx", "s06", False),
    ]

    for idx, (comp, tpl, seq, is_ov) in enumerate(expected_specs):
        item = result.items[idx]
        assert item.component_name == comp
        assert item.template_name == tpl
        assert item.sequence == seq
        assert item.is_overview is is_ov
        assert item.context["tx"]["manufacturer"] == "MTM"
        assert item.context["tx"]["rating"] == "1000"


def test_transformer_adapter_hv_cable_split_and_prpd_fallback(
    mock_substation_info: dict[str, str],
    dummy_image: Path,
    dummy_visual_image: Path,
) -> None:
    """Transformer cable split resolves secondary photo, falls back cleanly to '' if absent (ADR 0004/D08)."""
    photo_map = {
        101: (str(dummy_image), str(dummy_visual_image)),
        # 102 (split) is intentionally missing from disk
    }
    fake_resolver = FakePhotoResolver(photo_map)

    tx = TransformerScanSpec(
        tx_id="Tx 1",
        photo_numbers=(101, 102),
    )

    adapter = TransformerScanAdapter(
        tx=tx,
        substation_info=mock_substation_info,
        photo_resolver=fake_resolver,
    )
    result = adapter.adapt()

    # Page 5: HV CABLE SPLIT
    split_item = result.items[4]
    assert split_item.component_name == "HV CABLE SPLIT"
    # Photo 102 missing on disk -> clean '' fallback
    assert split_item.context["ir"]["image"] == ""
    assert split_item.context["visual"]["image"] == ""
    # PRPD missing -> clean '' fallback
    assert split_item.context["us"]["prpd"] == ""


def test_transformer_adapter_d47_overview_substitution(
    mock_substation_info: dict[str, str],
    tmp_path: Path,
) -> None:
    """When TX has active defect, overview page is substituted with sliced QR file (D47)."""
    tx = TransformerScanSpec(tx_id="Tx 1")
    sliced_tx_file = tmp_path / "tx1_s00_TX1_OVERVIEW_01.docx"
    sliced_tx_file.write_text("dummy sliced tx overview", encoding="utf-8")

    adapter = TransformerScanAdapter(
        tx=tx,
        substation_info=mock_substation_info,
        has_active_defect=True,
        sliced_overview_pages=[sliced_tx_file],
    )
    result = adapter.adapt()

    assert result.has_defect is True
    assert result.is_overview_substituted is True
    assert result.items[0].is_sliced is True
    assert result.items[0].sliced_path == sliced_tx_file


# ==============================================================================
# 3. Feeder Pillar & Battery Bank Adapter Tests
# ==============================================================================

def test_lvdb_adapter_renders_overview_with_operating_parameters(
    mock_substation_info: dict[str, str],
) -> None:
    """LVDB adapter renders overview page with operating parameters."""
    lvdb = LVDBScanSpec(
        name="LVDB 1",
        label="LVDB TX1",
        source="TX 1",
        manufacturer="ALGEBRA",
        serial_no="SN-LVDB-01",
        rating="1600A",
        cable_type="4C 300mm2 PVC",
        photo_numbers=(201,),
        feeders=(
            LVDBFeederScanSpec(channel="IN1", cable_type="4C 300mm2 PVC"),
            LVDBFeederScanSpec(channel="OT1", cable_type="4C 185mm2 PVC"),
        ),
    )

    adapter = LVDBScanAdapter(lvdb=lvdb, substation_info=mock_substation_info)
    result = adapter.adapt()

    assert result.equipment_category == "fp"
    assert result.page_count == 1
    item = result.items[0]
    assert item.template_name == "fp-overview.docx"
    assert item.is_overview is True
    assert item.sequence == "f00"
    assert item.context["fp"]["labelsource"] == "LVDB TX1"
    assert item.context["fp"]["manufacturer"] == "ALGEBRA"
    assert item.context["fp"]["rating"] == "1600A"
    assert item.context["fp"]["cabletype"] == "4C 300mm2 PVC"
    assert item.context["banner"]["analysis"] == BANNER_HEALTHY_ANALYSIS


def test_lvdb_adapter_d47_overview_substitution(
    mock_substation_info: dict[str, str],
    tmp_path: Path,
) -> None:
    """LVDB adapter substitutes overview page when defective per D47."""
    lvdb = LVDBScanSpec(name="FP 1", label="FP 1")
    sliced_fp_file = tmp_path / "fp1_f00_FP1_OVERVIEW_01.docx"
    sliced_fp_file.write_text("dummy fp slice", encoding="utf-8")

    adapter = LVDBScanAdapter(
        lvdb=lvdb,
        substation_info=mock_substation_info,
        has_active_defect=True,
        sliced_overview_pages=[sliced_fp_file],
    )
    result = adapter.adapt()

    assert result.has_defect is True
    assert result.is_overview_substituted is True
    assert result.items[0].is_sliced is True
    assert result.items[0].sliced_path == sliced_fp_file


def test_battery_bank_adapter_renders_overview(mock_substation_info: dict[str, str]) -> None:
    """BatteryBank adapter renders overview page with operating parameters."""
    bb = BatteryBankScanSpec(
        name="BATTERY 1",
        manufacturer="SUNPOWER",
        model="SP-110",
        serial_no="BATT-99",
        photo_numbers=(301,),
    )

    adapter = BatteryBankScanAdapter(bb=bb, substation_info=mock_substation_info)
    result = adapter.adapt()

    assert result.equipment_category == "battery"
    assert result.page_count == 1
    item = result.items[0]
    assert item.template_name == "battery-overview.docx"
    assert item.is_overview is True
    assert item.sequence == "b00"
    # Satisfies both battery and batt namespaces
    assert item.context["battery"]["manufacturer"] == "SUNPOWER"
    assert item.context["batt"]["manufacturer"] == "SUNPOWER"
    assert item.context["banner"]["analysis"] == BANNER_HEALTHY_ANALYSIS


# ==============================================================================
# 4. Composite Package & Physical Rendering Integration
# ==============================================================================

def test_adapt_equipment_package_full_station(mock_substation_info: dict[str, str]) -> None:
    """Composite package adapter aggregates all equipment families correctly."""
    swg = SwitchgearScanSpec(
        archetype=SwitchgearArchetype.RMU_STANDARD,
        overview_compartments=("OVERVIEW",),
        panels=(SwitchgearPanelScanSpec(panel_no=1, compartments=("CABLE COMPARTMENT",)),),
    )
    tx = TransformerScanSpec(tx_id="Tx 1")
    lvdb = LVDBScanSpec(name="FP 1")
    bb = BatteryBankScanSpec(name="BATT 1")

    package = FullReportScanPackage(
        substation_number=123,
        station_name="PE COMPOSITE",
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(lvdb,),
        battery_banks=(bb,),
    )

    results = adapt_equipment_package(package=package, substation_info=mock_substation_info)

    assert len(results) == 4
    # SWG: 1 ov + 1 panel = 2
    # TX: 7
    # LVDB: 1
    # BB: 1
    # Total: 11 pages
    total_pages = sum(r.page_count for r in results)
    assert total_pages == 11


def test_scan_render_item_renders_document_with_shading(
    mock_substation_info: dict[str, str],
    tmp_path: Path,
) -> None:
    """ScanRenderItem renders clean .docx template with dynamic cell shading."""
    swg = SwitchgearScanSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.RMU_STANDARD,
        overview_compartments=("OVERVIEW",),
        panels=(SwitchgearPanelScanSpec(panel_no=1, compartments=("CABLE COMPARTMENT",)),),
    )
    adapter = SwitchgearScanAdapter(swg=swg, substation_info=mock_substation_info)
    result = adapter.adapt()

    panel_item = result.items[1]
    out_docx = tmp_path / "rendered_panel.docx"
    rendered_path = panel_item.render(out_docx)

    assert rendered_path.is_file()
    assert rendered_path.stat().st_size > 1000

    # Verify word/document.xml contains healthy green shading
    with zipfile.ZipFile(rendered_path, "r") as z:
        xml_content = z.read("word/document.xml").decode("utf-8")
        assert f'w:fill="{COLOR_HEALTHY}"' in xml_content


def test_scan_adapter_result_render_all(
    mock_substation_info: dict[str, str],
    tmp_path: Path,
) -> None:
    """ScanAdapterResult.render_all renders all items in batch."""
    swg = SwitchgearScanSpec(
        switchgear_type="RMU SF6",
        archetype=SwitchgearArchetype.RMU_STANDARD,
        overview_compartments=("OVERVIEW",),
        panels=(
            SwitchgearPanelScanSpec(panel_no=1, compartments=("CABLE COMPARTMENT",)),
            SwitchgearPanelScanSpec(panel_no=2, compartments=("CABLE COMPARTMENT",)),
        ),
    )
    adapter = SwitchgearScanAdapter(swg=swg, substation_info=mock_substation_info)
    result = adapter.adapt()

    out_dir = tmp_path / "render_all_out"
    paths = result.render_all(out_dir)

    assert len(paths) == 3
    for p in paths:
        assert p.is_file()
        assert p.stat().st_size > 1000


def test_find_sliced_overview_page_matching(tmp_path: Path) -> None:
    """find_sliced_overview_page matches D37 tokens across equipment categories."""
    p_swg = tmp_path / "swg1_p00_TAMCO_OVERVIEW_01.docx"
    p_tx = tmp_path / "tx1_s00_MTM_OVERVIEW_01.docx"
    p_fp = tmp_path / "fp1_f00_ALGEBRA_OVERVIEW_01.docx"
    p_batt = tmp_path / "batt1_b00_SUNPOWER_OVERVIEW_01.docx"
    p_other = tmp_path / "swg1_p02_TAMCO_CABLE_COMPARTMENT_01.docx"

    for f in (p_swg, p_tx, p_fp, p_batt, p_other):
        f.write_text("x", encoding="utf-8")

    all_files = [p_swg, p_tx, p_fp, p_batt, p_other]

    assert find_sliced_overview_page("swg", "swg1", all_files) == p_swg
    assert find_sliced_overview_page("tx", "tx1", all_files) == p_tx
    assert find_sliced_overview_page("fp", "fp1", all_files) == p_fp
    assert find_sliced_overview_page("battery", "batt1", all_files) == p_batt
    assert find_sliced_overview_page("swg", "swg1", [p_other]) is None
    assert find_sliced_overview_page("swg", "swg1", None) is None


def test_raw_testsheet_specs_adaptation(mock_substation_info: dict[str, str]) -> None:
    """Adapters accept raw testsheet specs directly and classify/build scan specs automatically."""
    from src.testsheet.models import (
        BatteryBankSpec,
        LVDBSpec,
        SwitchgearPanelSpec,
        SwitchgearSpec,
        TransformerSpec,
    )

    swg_raw = SwitchgearSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        panels=(SwitchgearPanelSpec(panel_no=1, name="INCOMING 1"),),
    )
    tx_raw = TransformerSpec(tx_id="Tx 1", manufacturer="MTM")
    lvdb_raw = LVDBSpec(name="FP 1", manufacturer="ALGEBRA")
    bb_raw = BatteryBankSpec(name="BATT 1", manufacturer="SUNPOWER")

    res_swg = SwitchgearScanAdapter(swg=swg_raw, substation_info=mock_substation_info).adapt()
    assert res_swg.equipment_category == "swg"
    # TAMCO -> 2 overview pages + 2 panel pages (cable compartment + cable entry) = 4
    assert res_swg.page_count == 4

    res_tx = TransformerScanAdapter(tx=tx_raw, substation_info=mock_substation_info).adapt()
    assert res_tx.page_count == 7

    res_lvdb = LVDBScanAdapter(lvdb=lvdb_raw, substation_info=mock_substation_info).adapt()
    assert res_lvdb.page_count == 1

    res_bb = BatteryBankScanAdapter(bb=bb_raw, substation_info=mock_substation_info).adapt()
    assert res_bb.page_count == 1


def test_missing_template_raises_file_not_found(tmp_path: Path) -> None:
    """ScanRenderItem raises FileNotFoundError if template does not exist."""
    item = ScanRenderItem(
        page_name="Missing",
        template_name="non_existent.docx",
        template_path=tmp_path / "non_existent.docx",
    )
    with pytest.raises(FileNotFoundError):
        item.render(tmp_path / "out.docx")


def test_scan_page_context_dataclass() -> None:
    """ScanPageContext instantiates and holds structured context metadata."""
    spc = ScanPageContext(
        template_name="swg-panel.docx",
        context={"hello": "world"},
        equipment_category="swg",
        component_name="CABLE COMPARTMENT",
        sequence="p01",
        is_overview=False,
        is_defective=True,
        defective_technologies={"IR", "TEV"},
        equipment_id="swg1",
        panel_no=1,
    )
    assert spc.template_name == "swg-panel.docx"
    assert spc.context == {"hello": "world"}
    assert spc.defective_technologies == {"IR", "TEV"}
    assert spc.panel_no == 1


def test_cbm_defects_list_triggers_active_defect(mock_substation_info: dict[str, str]) -> None:
    """Passing cbm_defects triggers defect state on matching equipment."""
    swg = SwitchgearScanSpec(
        archetype=SwitchgearArchetype.RMU_STANDARD,
        overview_compartments=("OVERVIEW",),
        panels=(SwitchgearPanelScanSpec(panel_no=1, compartments=("CABLE COMPARTMENT",)),),
    )
    # Defect list with a switchgear defect filename
    cbm_defects = ["swg1_p01_TAMCO_CABLE_COMPARTMENT_01.docx"]

    adapter = SwitchgearScanAdapter(
        swg=swg,
        substation_info=mock_substation_info,
        cbm_defects=cbm_defects,
    )
    result = adapter.adapt()

    assert result.has_defect is True
    # Overview page should carry defect forwarding prose
    ov_item = result.items[0]
    assert ov_item.is_defective is True
    assert ov_item.context["banner"]["analysis"] == BANNER_DEFECT_FORWARDING


def test_find_sliced_overview_page_multi_unit_disambiguation(tmp_path: Path) -> None:
    """find_sliced_overview_page strictly isolates multi-unit instances (TX1 vs TX2, FP1 vs FP2)."""
    p_tx1 = tmp_path / "tx1_s00_TX1_OVERVIEW_01.docx"
    p_tx2 = tmp_path / "tx2_s00_TX2_OVERVIEW_01.docx"
    p_fp1 = tmp_path / "fp1_f00_FP1_OVERVIEW_01.docx"
    p_fp2 = tmp_path / "fp2_f00_FP2_OVERVIEW_01.docx"

    for f in (p_tx1, p_tx2, p_fp1, p_fp2):
        f.write_text("x", encoding="utf-8")

    all_files = [p_tx1, p_tx2, p_fp1, p_fp2]

    # TX disambiguation
    assert find_sliced_overview_page("tx", "tx1", all_files) == p_tx1
    assert find_sliced_overview_page("tx", "tx2", all_files) == p_tx2
    assert find_sliced_overview_page("tx", "Tx 1", all_files) == p_tx1
    assert find_sliced_overview_page("tx", "Tx 2", all_files) == p_tx2

    # FP disambiguation
    assert find_sliced_overview_page("fp", "fp1", all_files) == p_fp1
    assert find_sliced_overview_page("fp", "fp2", all_files) == p_fp2
    assert find_sliced_overview_page("fp", "FP 1", all_files) == p_fp1
    assert find_sliced_overview_page("fp", "FP 2", all_files) == p_fp2


def test_transformer_component_photo_index_alignment(
    mock_substation_info: dict[str, str],
    dummy_image: Path,
    dummy_visual_image: Path,
) -> None:
    """Transformer photos map to testsheet Rows 33-37 per D05."""
    # Photo numbers 100..104 correspond to:
    # 100: Overview (Row 33)
    # 101: HV Bushing (Row 34)
    # 102: HV Cable (Row 35)
    # 103: LV Bushing (Row 36)
    # 104: LV Cable (Row 37)
    photo_map = {
        i: (f"/path/FLIR0{i}.jpg", f"/path/FLIR0{i}-photo.jpg")
        for i in range(100, 105)
    }
    resolver = FakePhotoResolver(photo_map)

    tx = TransformerScanSpec(
        tx_id="Tx 1",
        photo_numbers=(100, 101, 102, 103, 104),
    )

    adapter = TransformerScanAdapter(
        tx=tx,
        substation_info=mock_substation_info,
        photo_resolver=resolver,
    )
    result = adapter.adapt()

    # Index 0: Overview -> 100
    assert result.items[0].context["ir"]["image"] == "/path/FLIR0100.jpg"
    # Index 2: HV Bushing -> 101
    assert result.items[2].context["ir"]["image"] == "/path/FLIR0101.jpg"
    # Index 3: HV Cable -> 102
    assert result.items[3].context["ir"]["image"] == "/path/FLIR0102.jpg"
    # Index 5: LV Bushing -> 103
    assert result.items[5].context["ir"]["image"] == "/path/FLIR0103.jpg"
    # Index 6: LV Cable -> 104
    assert result.items[6].context["ir"]["image"] == "/path/FLIR0104.jpg"


def test_dynamic_prpd_generation_with_tempfile_no_crash(
    mock_substation_info: dict[str, str],
    tmp_path: Path,
) -> None:
    """Dynamic PRPD resolution handles survey_root without explicit prpd_output_dir using tempfile."""
    survey_dir = tmp_path / "US_TEV_SURVEY"
    survey_dir.mkdir()

    swg = SwitchgearScanSpec(
        archetype=SwitchgearArchetype.RMU_STANDARD,
        overview_compartments=("OVERVIEW",),
        panels=(SwitchgearPanelScanSpec(panel_no=1, compartments=("CABLE COMPARTMENT",)),),
    )

    # Providing survey_root without prpd_output_dir must not trigger NameError on tempfile
    adapter = SwitchgearScanAdapter(
        swg=swg,
        substation_info=mock_substation_info,
        survey_root=survey_dir,
        prpd_output_dir=None,
    )
    result = adapter.adapt()
    assert result.page_count == 2


def test_scan_render_item_to_page_context(mock_substation_info: dict[str, str]) -> None:
    """ScanRenderItem converts cleanly to ScanPageContext."""
    swg = SwitchgearScanSpec(
        archetype=SwitchgearArchetype.RMU_STANDARD,
        overview_compartments=("OVERVIEW",),
        panels=(SwitchgearPanelScanSpec(panel_no=1, compartments=("CABLE COMPARTMENT",)),),
    )
    adapter = SwitchgearScanAdapter(swg=swg, substation_info=mock_substation_info)
    result = adapter.adapt()

    item = result.items[1]
    spc = item.to_page_context()

    assert isinstance(spc, ScanPageContext)
    assert spc.template_name == "swg-panel.docx"
    assert spc.component_name == "CABLE COMPARTMENT"
    assert spc.panel_no == 1
    assert spc.sequence == "p01"
    assert spc.equipment_category == "swg"
    assert spc.is_overview is False
    assert spc.context == item.context


def test_check_has_active_defect_disambiguates_fp_with_tx_in_name() -> None:
    """Verify _check_has_active_defect correctly identifies FP defects without falsely triggering TX defects."""
    from src.full_report.scan_adapters import _check_has_active_defect
    from src.quick_report.defects import CbmDefectRecord

    d_fp = CbmDefectRecord(
        equipment="FP (J)",
        technology="IR",
        defect_area="INCOMING LINK CONNECTION",
        additional_remarks="RED PHASE",
        equipment_id="FP TX1 - INCOMING 1",
    )
    cbm_defects = [d_fp]

    # FP category must detect defect
    assert _check_has_active_defect("fp", "fp1", cbm_defects=cbm_defects) is True
    assert _check_has_active_defect("fp", "FP TX1", cbm_defects=cbm_defects) is True

    # TX category must NOT detect defect from FP TX1
    assert _check_has_active_defect("tx", "TX1", cbm_defects=cbm_defects) is False
    assert _check_has_active_defect("tx", "TX2", cbm_defects=cbm_defects) is False
    assert _check_has_active_defect("tx", "", cbm_defects=cbm_defects) is False

    # SWG category must NOT detect defect from FP TX1
    assert _check_has_active_defect("swg", "swg1", cbm_defects=cbm_defects) is False

    # Now verify true TX defect is detected
    d_tx = CbmDefectRecord(
        equipment="TRANSFORMER",
        technology="IR",
        defect_area="HV BUSHING",
        equipment_id="TX 1",
    )
    tx_defects = [d_tx]
    assert _check_has_active_defect("tx", "TX1", cbm_defects=tx_defects) is True
    assert _check_has_active_defect("tx", "TX2", cbm_defects=tx_defects) is False
    assert _check_has_active_defect("tx", "", cbm_defects=tx_defects) is True
    assert _check_has_active_defect("fp", "fp1", cbm_defects=tx_defects) is False

def test_switchgear_scan_adapter_tev_background_resolution():
    """Verify SwitchgearScanAdapter reads tev_background from substation_info and defaults to '-', never '4'."""
    swg = SwitchgearScanSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        panels=(SwitchgearPanelScanSpec(panel_no=1, panel_feeder_no="P1", name="TX A"),),
    )

    # 1. When substation_info has no TEV background, must default to "-", NOT "4"
    ad_empty = SwitchgearScanAdapter(swg=swg, substation_info={})
    assert ad_empty.tev_background == "-"
    res_empty = ad_empty.adapt()
    panel_item_empty = [it for it in res_empty.items if not it.is_overview][0]
    assert panel_item_empty.context["panel"]["tev"]["bg"] == "-"

    # 2. When substation_info has tev_background="1", must be "1"
    ad_with_bg = SwitchgearScanAdapter(swg=swg, substation_info={"tev_background": "1"})
    assert ad_with_bg.tev_background == "1"
    res_with_bg = ad_with_bg.adapt()
    panel_item_with_bg = [it for it in res_with_bg.items if not it.is_overview][0]
    assert panel_item_with_bg.context["panel"]["tev"]["bg"] == "1"

    # 3. When substation_info has tev_bg="1", must be "1"
    ad_with_tev_bg = SwitchgearScanAdapter(swg=swg, substation_info={"tev_bg": "1"})
    assert ad_with_tev_bg.tev_background == "1"
    res_with_tev_bg = ad_with_tev_bg.adapt()
    panel_item_with_tev_bg = [it for it in res_with_tev_bg.items if not it.is_overview][0]
    assert panel_item_with_tev_bg.context["panel"]["tev"]["bg"] == "1"

    # 4. When substation_info has tev_background="-" or None, must be "-"
    ad_dash = SwitchgearScanAdapter(swg=swg, substation_info={"tev_background": "-"})
    assert ad_dash.tev_background == "-"
    res_dash = ad_dash.adapt()
    panel_item_dash = [it for it in res_dash.items if not it.is_overview][0]
    assert panel_item_dash.context["panel"]["tev"]["bg"] == "-"


def test_defect_isolation_per_transformer_instance() -> None:
    """Verify zero defect leakage between TX1 and TX2 (Bug 8)."""
    from src.full_report.scan_adapters import _check_has_active_defect
    from src.quick_report.defects import CbmDefectRecord

    # 1. Defect explicitly for TX1
    d_tx1 = CbmDefectRecord(
        equipment="TRANSFORMER",
        equipment_id="TX 1",
        defect_area="HV BUSHING",
        technology="IR",
    )
    assert _check_has_active_defect("tx", "tx1", cbm_defects=[d_tx1], total_count=2) is True
    assert _check_has_active_defect("tx", "tx2", cbm_defects=[d_tx1], total_count=2) is False

    # 2. Defect explicitly for TX2
    d_tx2 = CbmDefectRecord(
        equipment="TRANSFORMER",
        equipment_id="TX 2",
        defect_area="LV CABLE",
        technology="US",
    )
    assert _check_has_active_defect("tx", "tx1", cbm_defects=[d_tx2], total_count=2) is False
    assert _check_has_active_defect("tx", "tx2", cbm_defects=[d_tx2], total_count=2) is True

    # 3. Defect with generic LTX/DTX on multi-TX station (total_count=2):
    # Maps to TX1 only, zero leakage to TX2!
    d_generic = CbmDefectRecord(
        equipment="LTX/DTX",
        equipment_id="",
        defect_area="BODY",
        technology="IR",
    )
    assert _check_has_active_defect("tx", "tx1", cbm_defects=[d_generic], total_count=2) is True
    assert _check_has_active_defect("tx", "tx2", cbm_defects=[d_generic], total_count=2) is False

    # 4. Defect with generic CABLE LTX/DTX on single-TX station (total_count=1):
    assert _check_has_active_defect("tx", "tx1", cbm_defects=[d_generic], total_count=1) is True


def test_defect_isolation_per_feeder_pillar_instance() -> None:
    """Verify zero defect leakage between FP1 and FP2 (Bug 8)."""
    from src.full_report.scan_adapters import _check_has_active_defect
    from src.quick_report.defects import CbmDefectRecord

    d_fp1 = CbmDefectRecord(
        equipment="FEEDER PILLAR",
        equipment_id="FP 1",
        defect_area="FUSE BASE",
        technology="IR",
    )
    assert _check_has_active_defect("fp", "fp1", cbm_defects=[d_fp1], total_count=2) is True
    assert _check_has_active_defect("fp", "fp2", cbm_defects=[d_fp1], total_count=2) is False

    d_fp2 = CbmDefectRecord(
        equipment="FEEDER PILLAR",
        equipment_id="FP 2",
        defect_area="BUSBAR",
        technology="IR",
    )
    assert _check_has_active_defect("fp", "fp1", cbm_defects=[d_fp2], total_count=2) is False
    assert _check_has_active_defect("fp", "fp2", cbm_defects=[d_fp2], total_count=2) is True


def test_overview_templates_placeholders_and_activex() -> None:
    """Verify swg-overview, tx-overview, fp-overview have Analysis/Recommendation and ActiveX controls."""
    from pathlib import Path
    import zipfile
    import docx

    tpl_dir = Path("templates/FULL REPORT/NORMAL IR US TEV")
    assert not (tpl_dir / "blackbox-overview.docx").exists(), "blackbox-overview.docx must be removed"

    for tpl_name in ("swg-overview.docx", "tx-overview.docx", "fp-overview.docx"):
        tpl_path = tpl_dir / tpl_name
        assert tpl_path.exists(), f"Template {tpl_name} missing"

        # Check ActiveX preservation
        with zipfile.ZipFile(tpl_path, "r") as zf:
            namelist = zf.namelist()
            assert "word/activeX/activeX1.bin" in namelist, f"ActiveX bin missing in {tpl_name}"
            assert "word/activeX/activeX1.xml" in namelist, f"ActiveX xml missing in {tpl_name}"
            assert "word/activeX/_rels/activeX1.xml.rels" in namelist, f"ActiveX rels missing in {tpl_name}"

        # Check placeholders in table rows 35 & 36
        doc = docx.Document(tpl_path)
        table = doc.tables[0]
        row_texts = [r.cells[0].text.strip() for r in table.rows]
        analysis_rows = [t for t in row_texts if "Analysis:" in t]
        rec_rows = [t for t in row_texts if "Recommendation:" in t]

        assert any("{{ analysis }}" in t for t in analysis_rows), f"{{ analysis }} missing in {tpl_name}"
        assert any("{{ recommendation }}" in t for t in rec_rows), f"{{ recommendation }} missing in {tpl_name}"


def test_switchgear_adapter_strict_zero_fallback(mock_substation_info: dict[str, str]) -> None:
    """Verify missing compartment photo produces blank image strings and does NOT fall back to photo_numbers[0] or cable_photo."""
    fake_resolver = FakePhotoResolver({
        101: ("/photos/IR_101.jpg", "/photos/VIS_101.jpg"),
    })
    panel = SwitchgearPanelScanSpec(
        panel_no=1,
        name="FEEDER 1",
        cable_photo=101,
        breaker_photo=None,
        busbar_photo=None,
        secondary_photo=None,
        photo_numbers=(101,),
        compartments=(
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "SECONDARY COMPARTMENT",
        ),
    )
    swg = SwitchgearScanSpec(
        switchgear_type="VCB 11kV",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        overview_compartments=("OVERVIEW FRONT",),
        panels=(panel,),
        photo_numbers=(50,),
    )
    adapter = SwitchgearScanAdapter(
        swg=swg,
        substation_info=mock_substation_info,
        photo_resolver=fake_resolver,
    )
    result = adapter.adapt()
    items = result.items

    assert items[0].is_overview is True

    # Item 1 is BREAKER COMPARTMENT: breaker_photo is None -> ir.image and visual.image must be blank ""
    breaker_item = items[1]
    assert breaker_item.component_name == "BREAKER COMPARTMENT"
    assert breaker_item.context["ir"]["image"] == ""
    assert breaker_item.context["visual"]["image"] == ""

    # Item 2 is CABLE COMPARTMENT: cable_photo is 101 -> ir.image and visual.image must be resolved
    cable_item = items[2]
    assert cable_item.component_name == "CABLE COMPARTMENT"
    assert cable_item.context["ir"]["image"] == "/photos/IR_101.jpg"
    assert cable_item.context["visual"]["image"] == "/photos/VIS_101.jpg"

    # Item 3 is BUSBAR COMPARTMENT: busbar_photo is None -> blank ""
    busbar_item = items[3]
    assert busbar_item.component_name == "BUSBAR COMPARTMENT"
    assert busbar_item.context["ir"]["image"] == ""
    assert busbar_item.context["visual"]["image"] == ""

    # Item 4 is SECONDARY COMPARTMENT: secondary_photo is None -> blank ""
    sec_item = items[4]
    assert sec_item.component_name == "SECONDARY COMPARTMENT"
    assert sec_item.context["ir"]["image"] == ""
    assert sec_item.context["visual"]["image"] == ""


def test_switchgear_adapter_vcb_transition_front_rear_photo_mapping(mock_substation_info: dict[str, str]) -> None:
    """Verify VCB transition bay maps FRONT COMPARTMENT -> breaker_photo and REAR COMPARTMENT -> cable_photo."""
    fake_resolver = FakePhotoResolver({
        201: ("/photos/IR_201.jpg", "/photos/VIS_201.jpg"),
        202: ("/photos/IR_202.jpg", "/photos/VIS_202.jpg"),
    })
    panel = SwitchgearPanelScanSpec(
        panel_no=1,
        name="TRANSITION",
        breaker_photo=201,  # Should map to FRONT COMPARTMENT
        cable_photo=202,    # Should map to REAR COMPARTMENT
        busbar_photo=None,
        photo_numbers=(201, 202),
        compartments=("FRONT COMPARTMENT", "REAR COMPARTMENT", "BUSBAR COMPARTMENT"),
    )
    swg = SwitchgearScanSpec(
        switchgear_type="VCB 11kV",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        overview_compartments=("OVERVIEW FRONT",),
        panels=(panel,),
        photo_numbers=(50,),
    )
    adapter = SwitchgearScanAdapter(
        swg=swg,
        substation_info=mock_substation_info,
        photo_resolver=fake_resolver,
    )
    result = adapter.adapt()
    items = result.items

    front_item = next(it for it in items if it.component_name == "FRONT COMPARTMENT")
    assert front_item.context["ir"]["image"] == "/photos/IR_201.jpg"
    assert front_item.context["visual"]["image"] == "/photos/VIS_201.jpg"

    rear_item = next(it for it in items if it.component_name == "REAR COMPARTMENT")
    assert rear_item.context["ir"]["image"] == "/photos/IR_202.jpg"
    assert rear_item.context["visual"]["image"] == "/photos/VIS_202.jpg"

    busbar_item = next(it for it in items if it.component_name == "BUSBAR COMPARTMENT")
    assert busbar_item.context["ir"]["image"] == ""
    assert busbar_item.context["visual"]["image"] == ""


def test_switchgear_adapter_overview_photo_mapping_vcb_and_rmu(mock_substation_info: dict[str, str]) -> None:
    """Verify overview photo mapping for VCB (Front=Row 27, Rear=Row 26, Top=Row 28) and RMU."""
    fake_resolver = FakePhotoResolver({
        50: ("/photos/IR_50.jpg", "/photos/VIS_50.jpg"),
        60: ("/photos/IR_60.jpg", "/photos/VIS_60.jpg"),
        70: ("/photos/IR_70.jpg", "/photos/VIS_70.jpg"),
        80: ("/photos/IR_80.jpg", "/photos/VIS_80.jpg"),
        90: ("/photos/IR_90.jpg", "/photos/VIS_90.jpg"),
    })

    # 1. VCB: photo_numbers has [Row 27 (Front), Row 26 (Rear), Row 28 (Top)]
    swg_vcb = SwitchgearScanSpec(
        switchgear_type="VCB 11kV",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        overview_compartments=("OVERVIEW FRONT", "OVERVIEW REAR", "OVERVIEW TOP"),
        panels=(),
        photo_numbers=(50, 60, 70),
    )
    adapter_vcb = SwitchgearScanAdapter(
        swg=swg_vcb,
        substation_info=mock_substation_info,
        photo_resolver=fake_resolver,
    )
    res_vcb = adapter_vcb.adapt()
    assert len(res_vcb.items) == 3
    assert res_vcb.items[0].component_name == "OVERVIEW FRONT"
    assert res_vcb.items[0].context["ir"]["image"] == "/photos/IR_50.jpg"
    assert res_vcb.items[1].component_name == "OVERVIEW REAR"
    assert res_vcb.items[1].context["ir"]["image"] == "/photos/IR_60.jpg"
    assert res_vcb.items[2].component_name == "OVERVIEW TOP"
    assert res_vcb.items[2].context["ir"]["image"] == "/photos/IR_70.jpg"

    # 2. RMU: photo_numbers has [Row 26 (Overview), Row 28 (Overview Bottom/Top)]
    swg_rmu = SwitchgearScanSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY,
        overview_compartments=("OVERVIEW", "OVERVIEW BOTTOM"),
        panels=(),
        photo_numbers=(80, 90),
    )
    adapter_rmu = SwitchgearScanAdapter(
        swg=swg_rmu,
        substation_info=mock_substation_info,
        photo_resolver=fake_resolver,
    )
    res_rmu = adapter_rmu.adapt()
    assert len(res_rmu.items) == 2
    assert res_rmu.items[0].component_name == "OVERVIEW"
    assert res_rmu.items[0].context["ir"]["image"] == "/photos/IR_80.jpg"
    assert res_rmu.items[1].component_name == "OVERVIEW BOTTOM"
    assert res_rmu.items[1].context["ir"]["image"] == "/photos/IR_90.jpg"


def test_switchgear_adapter_panel_serial_number_in_render_context(mock_substation_info: dict[str, str]) -> None:
    """Verify panel.serial_no is passed directly into panel render context."""
    panel = SwitchgearPanelScanSpec(
        panel_no=1,
        name="PANEL 1",
        serial_no="SN-PANEL-9988",
        compartments=("CABLE COMPARTMENT",),
    )
    swg = SwitchgearScanSpec(
        switchgear_type="VCB 11kV",
        manufacturer="TAMCO",
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        overview_compartments=("OVERVIEW FRONT",),
        panels=(panel,),
    )
    adapter = SwitchgearScanAdapter(
        swg=swg,
        substation_info=mock_substation_info,
    )
    result = adapter.adapt()
    panel_item = result.items[1]
    assert panel_item.context["panel"]["serialnumber"] == "SN-PANEL-9988"


def test_switchgear_adapter_33kv_overview_and_cable_entry_fallback(mock_substation_info: dict[str, str]) -> None:
    """Verify 33kV switchgear generates dual Front and Rear overviews, and CABLE ENTRY falls back to breaker_photo."""
    swg_33kv = SwitchgearSpec(
        switchgear_type="RMU SF6 33kV",
        rating="33kV",
        panels=(),
    )
    adapter = SwitchgearScanAdapter(
        swg=swg_33kv,
        substation_info=mock_substation_info,
    )
    result = adapter.adapt()
    ov_comps = [item.component_name for item in result.items if item.is_overview]
    assert ov_comps == ["OVERVIEW FRONT", "OVERVIEW REAR"]

    # CABLE ENTRY fallback test
    panel_cable_entry = SwitchgearPanelSpec(
        panel_no=1,
        name="PANEL 1",
        photo_numbers=(100,),  # only 1 photo in tuple
        breaker_photo=101,     # fallback photo for entry
    )
    swg_dual = SwitchgearSpec(
        switchgear_type="RMU SF6",
        manufacturer="TAMCO",
        model="GV3",
        panels=(panel_cable_entry,),
    )
    resolver = FakePhotoResolver({
        100: ("/photos/IR_100.jpg", "/photos/VIS_100.jpg"),
        101: ("/photos/IR_101.jpg", "/photos/VIS_101.jpg"),
    })
    adapter_dual = SwitchgearScanAdapter(
        swg=swg_dual,
        substation_info=mock_substation_info,
        photo_resolver=resolver,
    )
    res_dual = adapter_dual.adapt()
    cable_entry_items = [it for it in res_dual.items if it.component_name == "CABLE ENTRY"]
    assert len(cable_entry_items) == 1
    assert cable_entry_items[0].context["ir"]["image"] == "/photos/IR_101.jpg"


