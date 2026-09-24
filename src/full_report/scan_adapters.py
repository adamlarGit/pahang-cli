"""Equipment Scan Adapters & PRPD Integration for Full Report (Ticket #31 / T4.2b).

Constructs template contexts, resolves IR and paired visual photos via RawPhotoResolver,
generates PRPD waveform graphs via prpd.py, and handles defective overview page substitution
per D47 across all equipment families:
- Switchgear (D26, D29)
- Transformer 7-point (ADR 0004, D31)
- Feeder Pillar / LVDB
- Battery Bank
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Sequence

from src.core.contract import (
    ContractScope,
    is_swg_compartment_tev_eligible,
    is_swg_compartment_us_eligible,
)
from src.core.topology import SwitchgearArchetype, SwitchgearTopologyEngine, VoltageClass
from src.core.normalizers import (
    format_busbar_position,
    format_date_cbm,
    format_db_int,
    format_heater_amp,
    format_load_amp,
    format_testsheet_time,
    normalize_tx_id,
    normalize_tx_model,
    normalize_us_characteristic,
)
from src.full_report.models import (
    BatteryBankScanSpec,
    FullReportScanPackage,
    LVDBScanSpec,
    SwitchgearPanelScanSpec,
    SwitchgearScanSpec,
    TransformerScanSpec,
    has_hv_cable_split,
)
from src.full_report.photo_resolver import RawPhotoResolver
from src.full_report.scan_render import (
    BANNER_DEFECT_FORWARDING,
    BANNER_HEALTHY_ANALYSIS,
    BANNER_HEALTHY_RECOMMENDATION,
    FullReportScanPageRendererCore,
)
from src.quick_report.prpd import (
    discover_ultratev_survey_dir,
    generate_prpd_graphs_for_swg_panel,
    generate_prpd_graphs_for_transformer,
)
from src.testsheet.models import (
    BatteryBankSpec,
    LVDBSpec,
    SubstationEquipmentPackage,
    SwitchgearSpec,
    TransformerSpec,
)

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATES_DIR = Path("templates/FULL REPORT/NORMAL IR US TEV")


@dataclass
class ScanPageContext:
    """Strongly-typed container for scanning page template rendering context."""

    template_name: str
    context: dict[str, Any]
    equipment_category: str  # "swg", "tx", "fp", "battery"
    component_name: str  # e.g. "OVERVIEW", "CABLE COMPARTMENT", "HV BUSHING"
    sequence: str = ""  # e.g. "p00", "p01", "s00", "f00"
    is_overview: bool = False
    is_defective: bool = False
    defective_technologies: set[str] = field(default_factory=set)
    equipment_id: str = ""
    panel_no: int | None = None


@dataclass
class ScanRenderItem:
    """Represents a single scanning page in the document Bill of Materials."""

    page_name: str
    template_name: str
    template_path: Path | None = None
    context: dict[str, Any] = field(default_factory=dict)
    equipment_category: str = ""
    component_name: str = ""
    sequence: str = ""
    is_overview: bool = False
    is_sliced: bool = False
    sliced_path: Path | None = None
    is_defective: bool = False
    defective_technologies: set[str] = field(default_factory=set)
    equipment_id: str = ""
    panel_no: int | None = None

    def render(
        self,
        output_path: Path | str,
        renderer: FullReportScanPageRendererCore | None = None,
    ) -> Path:
        """Render this scan page item to output_path.

        If is_sliced is True and sliced_path exists, copies the sliced file directly.
        Otherwise renders the docxtpl template with dynamic OpenXML cell and banner shading.
        """
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if self.is_sliced and self.sliced_path and Path(self.sliced_path).is_file():
            shutil.copy2(str(self.sliced_path), str(out_p))
            return out_p

        if not self.template_path or not Path(self.template_path).is_file():
            raise FileNotFoundError(f"Template path not found: {self.template_path}")

        r = renderer or FullReportScanPageRendererCore()
        return r.render(
            template_path=self.template_path,
            output_path=out_p,
            context=self.context,
            defective_technologies=self.defective_technologies,
            is_defective=self.is_defective,
            overview=self.is_overview,
        )

    def to_page_context(self) -> ScanPageContext:
        """Convert render item metadata to strongly-typed ScanPageContext."""
        return ScanPageContext(
            template_name=self.template_name,
            context=self.context,
            equipment_category=self.equipment_category,
            component_name=self.component_name,
            sequence=self.sequence,
            is_overview=self.is_overview,
            is_defective=self.is_defective,
            defective_technologies=set(self.defective_technologies),
            equipment_id=self.equipment_id,
            panel_no=self.panel_no,
        )


@dataclass
class ScanAdapterResult:
    """Result of running an equipment scan adapter."""

    equipment_category: str
    equipment_id: str
    items: tuple[ScanRenderItem, ...] = ()
    has_defect: bool = False
    is_overview_substituted: bool = False

    @property
    def page_count(self) -> int:
        return len(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def __getitem__(self, index: int) -> ScanRenderItem:
        return self.items[index]

    def render_all(
        self,
        output_dir: Path | str,
        renderer: FullReportScanPageRendererCore | None = None,
    ) -> list[Path]:
        """Render all items into output_dir using sequential naming."""
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        rendered_paths: list[Path] = []
        r = renderer or FullReportScanPageRendererCore()

        for idx, item in enumerate(self.items, 1):
            stem = (
                f"{item.equipment_category}_{item.sequence}_{item.component_name}_{idx:02d}"
                .replace(" ", "_")
                .replace("/", "_")
                .lower()
            )
            out_file = out_dir / f"{stem}.docx"
            rendered = item.render(out_file, renderer=r)
            rendered_paths.append(rendered)

        return rendered_paths


# ==============================================================================
# Helper Functions
# ==============================================================================

def _clean_str(val: Any, default: str = "-") -> str:
    """Clean string or return default if empty or None."""
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _format_substation_context(substation_info: dict[str, Any] | None) -> dict[str, str]:
    """Format standard substation metadata context block."""
    info = substation_info or {}
    raw_date = info.get("date", "")
    raw_time = info.get("time", "")

    return {
        "name_erms": _clean_str(info.get("name_erms") or info.get("name") or info.get("substation_name")),
        "date": format_date_cbm(raw_date) if raw_date else "-",
        "time": format_testsheet_time(raw_time) if raw_time else "-",
        "ambient": _clean_str(info.get("ambient")),
        "humidity": _clean_str(info.get("humidity")),
    }


def find_sliced_overview_page(
    category: str,
    instance_or_id: str,
    candidates: Sequence[Path | str] | None,
) -> Path | None:
    """Find a matching sliced overview docx file for D47 substitution."""
    if not candidates:
        return None

    cat_upper = category.upper()
    inst_clean = re.sub(r"[^A-Za-z0-9]", "", str(instance_or_id)).upper()
    digits = re.findall(r"\d+", inst_clean)
    inst_num = digits[0] if digits else "1"

    for cand in candidates:
        p = Path(cand)
        if not p.is_file() or p.suffix.lower() != ".docx":
            continue
        name_upper = p.name.upper()

        # Check for overview tokens
        if not any(k in name_upper for k in ("OVERVIEW", "P00", "F00", "S00", "B00")):
            continue

        # Match category and instance
        if cat_upper in ("SWG", "SWITCHGEAR"):
            if any(k in name_upper for k in ("SWG", "RMU", "VCB", "P00")):
                if not any(f"SWG{d}" in name_upper for d in ("1", "2", "3", "4", "5") if d != inst_num):
                    return p
        elif cat_upper in ("TX", "TRANSFORMER"):
            if "TX" in name_upper or "S00" in name_upper:
                # Disambiguate TX1 vs TX2
                if f"TX{inst_num}" in name_upper or f"TX_{inst_num}" in name_upper or f"TX0{inst_num}" in name_upper:
                    return p
                if not any(f"TX{d}" in name_upper for d in ("1", "2", "3", "4") if d != inst_num):
                    return p
        elif cat_upper in ("FP", "LVDB", "FEEDER_PILLAR"):
            if any(k in name_upper for k in ("FP", "LVDB", "F00")):
                # Disambiguate FP1 vs FP2
                if f"FP{inst_num}" in name_upper or f"FP_{inst_num}" in name_upper or f"LVDB{inst_num}" in name_upper:
                    return p
                if not any(f"FP{d}" in name_upper for d in ("1", "2", "3", "4") if d != inst_num):
                    return p
        elif cat_upper in ("BATTERY", "BATT"):
            if any(k in name_upper for k in ("BATT", "BATTERY", "B00")):
                return p

    return None


def _check_has_active_defect(
    category: str,
    equipment_id: str = "",
    explicit_flag: bool | None = None,
    cbm_defects: Sequence[Any] | None = None,
    total_count: int = 1,
) -> bool:
    """Evaluate whether an equipment instance/group has an active defect."""
    if explicit_flag is not None:
        return explicit_flag

    if not cbm_defects:
        return False

    cat_upper = category.upper()
    id_upper = equipment_id.upper().strip()
    id_norm = re.sub(r"\s+", "", id_upper)

    target_digits = re.findall(r"\d+", id_norm)
    target_num = target_digits[0] if target_digits else "1"

    for d in cbm_defects:
        eq_name = ""
        eq_id = ""
        fname = ""

        if isinstance(d, dict):
            eq_name = str(d.get("equipment") or d.get("equipment_category") or "")
            eq_id = str(d.get("equipment_id") or "")
            fname = str(d.get("filename") or "")
        elif hasattr(d, "equipment") or hasattr(d, "equipment_category"):
            eq_name = str(getattr(d, "equipment", "") or getattr(d, "equipment_category", "") or "")
            eq_id = str(getattr(d, "equipment_id", "") or "")
            if hasattr(d, "filename") and d.filename:
                fname = str(d.filename)
        elif isinstance(d, Path):
            fname = d.name
        elif isinstance(d, str):
            fname = d

        eq_upper = eq_name.upper()
        eq_id_upper = eq_id.upper()
        combined_eq = f"{eq_upper} {eq_id_upper}".strip()
        fname_upper = fname.upper()

        is_fp = (
            any(k in eq_upper for k in ("FP", "FEEDER PILLAR", "LVDB", "CABLE FP"))
            or any(k in eq_id_upper for k in ("FP", "FEEDER PILLAR", "LVDB"))
            or any(k in fname_upper for k in ("FP", "FEEDER PILLAR", "LVDB"))
        )
        is_swg = (
            any(k in eq_upper for k in ("SWG", "RMU", "VCB", "SWITCHGEAR", "MRMU", "GIS", "EARTHING", "CABLE SWG"))
            or any(k in fname_upper for k in ("SWG", "RMU", "VCB", "SWITCHGEAR"))
        )
        is_tx = (
            any(k in eq_upper for k in ("TRANSFORMER", "TX", "LTX", "DTX", "PTX", "CABLE LTX", "CABLE DTX", "CABLE PTX"))
            or any(k in eq_id_upper for k in ("TX", "LTX", "DTX", "PTX"))
            or any(k in fname_upper for k in ("TRANSFORMER", "TX", "LTX", "DTX", "PTX"))
        ) and not is_fp
        is_batt = "BATT" in eq_upper or "BATT" in fname_upper

        if cat_upper in ("SWG", "SWITCHGEAR"):
            if is_swg:
                return True

        elif cat_upper in ("TX", "TRANSFORMER"):
            if is_tx:
                # Extract explicit transformer instance number from defect record
                found_nums = (
                    re.findall(r"(?:TX|TRANSFORMER|S)\s*0*(\d+)", combined_eq)
                    or re.findall(r"\b0*(\d+)\b", eq_id_upper)
                    or re.findall(r"(?:TX|S)\s*0*(\d+)", fname_upper)
                )
                if found_nums:
                    if found_nums[0] == target_num:
                        return True
                else:
                    # No explicit TX number: on single-TX station or for TX1, maps to TX1 (zero leakage to TX2)
                    if total_count <= 1 or target_num == "1":
                        return True

        elif cat_upper in ("FP", "LVDB"):
            if is_fp:
                # Extract explicit FP instance number from defect record
                found_nums = (
                    re.findall(r"(?:FP|FEEDER\s*PILLAR|LVDB|F)\s*0*(\d+)", combined_eq)
                    or re.findall(r"\b0*(\d+)\b", eq_id_upper)
                    or re.findall(r"(?:FP|LVDB|F)\s*0*(\d+)", fname_upper)
                )
                if found_nums:
                    if found_nums[0] == target_num:
                        return True
                else:
                    # No explicit FP number: on single-FP station or for FP1, maps to FP1 (zero leakage to FP2)
                    if total_count <= 1 or target_num == "1":
                        return True

        elif cat_upper in ("BATTERY", "BATT"):
            if is_batt:
                return True

    return False


def _resolve_swg_overview_photo_num(
    archetype: SwitchgearArchetype,
    ov_area: str,
    photo_numbers: tuple[int, ...],
) -> int | None:
    """Map switchgear overview compartment view to photo number per ADR 0005.

    - VCB / GIS:
      - OVERVIEW FRONT: Row 27 photo (photo_numbers[0])
      - OVERVIEW REAR: Row 26 photo (photo_numbers[1])
      - OVERVIEW TOP: Row 28 photo (photo_numbers[2])
    - RMU:
      - OVERVIEW: Row 26 photo (photo_numbers[0])
      - OVERVIEW TOP / OVERVIEW BOTTOM: Row 28 photo (photo_numbers[1])
    """
    if not photo_numbers:
        return None

    if archetype in (SwitchgearArchetype.VCB_CUBICLE, SwitchgearArchetype.GIS_CUBICLE):
        if ov_area == "OVERVIEW FRONT" and len(photo_numbers) > 0:
            return photo_numbers[0]
        elif ov_area == "OVERVIEW REAR" and len(photo_numbers) > 1:
            return photo_numbers[1]
        elif ov_area == "OVERVIEW TOP" and len(photo_numbers) > 2:
            return photo_numbers[2]
        elif ov_area == "OVERVIEW" and len(photo_numbers) > 0:
            return photo_numbers[0]
        return None
    else:
        if ov_area == "OVERVIEW" and len(photo_numbers) > 0:
            return photo_numbers[0]
        elif ov_area in ("OVERVIEW TOP", "OVERVIEW BOTTOM") and len(photo_numbers) > 1:
            return photo_numbers[1]
        return None


# ==============================================================================
# 1. Switchgear Scan Adapter (D26, D29, D08, D47)
# ==============================================================================

class SwitchgearScanAdapter:
    """Adapter rendering Switchgear overview and panel scanning pages per D26/D29."""

    def __init__(
        self,
        swg: SwitchgearSpec | SwitchgearScanSpec,
        substation_info: dict[str, Any] | None = None,
        *,
        photo_resolver: RawPhotoResolver | None = None,
        survey_root: Path | str | None = None,
        prpd_catalog: dict[str, Any] | None = None,
        prpd_output_dir: Path | str | None = None,
        prpd_mode: str = "option_c",
        templates_dir: Path | str | None = None,
        sliced_overview_pages: Sequence[Path | str] | None = None,
        has_active_defect: bool | None = None,
        cbm_defects: Sequence[Any] | None = None,
        tev_background: str | int | None = None,
        project_technologies: Sequence[str] | set[str] | None = None,
    ) -> None:
        self.swg = swg
        self.substation_info = substation_info or {}
        self.photo_resolver = photo_resolver
        self.survey_root = Path(survey_root) if survey_root else None
        self.prpd_catalog = prpd_catalog or {}
        self.prpd_output_dir = Path(prpd_output_dir) if prpd_output_dir else None
        self.prpd_mode = prpd_mode
        self.templates_dir = Path(templates_dir) if templates_dir else DEFAULT_TEMPLATES_DIR
        self.sliced_overview_pages = sliced_overview_pages or ()
        self.cbm_defects = cbm_defects or ()
        self.contract = (
            ContractScope.from_source(project_technologies)
            if project_technologies is not None
            else ContractScope.from_source(self.substation_info)
        )
        self.project_technologies = self.contract.awarded_technologies

        if tev_background is not None and str(tev_background).strip() and str(tev_background).strip() != "-":
            self.tev_background = str(tev_background).strip()
        else:
            raw_bg = self.substation_info.get("tev_background") or self.substation_info.get("tev_bg")
            if raw_bg is not None and str(raw_bg).strip() and str(raw_bg).strip() not in ("-", "None", "N/A"):
                self.tev_background = str(raw_bg).strip()
            else:
                self.tev_background = "-"

        # Classify switchgear archetype and voltage class via SwitchgearTopologyEngine
        if isinstance(swg, SwitchgearScanSpec):
            if swg.archetype != SwitchgearArchetype.RMU_STANDARD:
                self.archetype = swg.archetype
            else:
                board = SwitchgearTopologyEngine.classify_board(
                    switchgear_type=swg.switchgear_type,
                    manufacturer=swg.manufacturer,
                    model=swg.model,
                    rating=swg.rating,
                    swg=swg,
                )
                self.archetype = board.archetype
            self.voltage_class = swg.voltage_class
        else:
            board = SwitchgearTopologyEngine.classify_board(
                switchgear_type=getattr(swg, "switchgear_type", ""),
                manufacturer=getattr(swg, "manufacturer", ""),
                model=getattr(swg, "model", ""),
                rating=getattr(swg, "rating", ""),
                swg=swg,
            )
            self.archetype = getattr(swg, "archetype", None) or board.archetype
            self.voltage_class = getattr(swg, "voltage_class", None) or board.voltage_class
            # Backward compatibility for legacy tests specifying INDKOM without model
            mfg_upper = str(getattr(swg, "manufacturer", "")).strip().upper()
            model_str = str(getattr(swg, "model", "")).strip().upper()
            if mfg_upper == "INDKOM" and not model_str and not getattr(swg, "archetype", None):
                self.archetype = SwitchgearArchetype.RMU_FUSE_CANISTER

        self.has_active_defect = _check_has_active_defect(
            category="swg",
            equipment_id="swg1",
            explicit_flag=has_active_defect,
            cbm_defects=self.cbm_defects,
        )

    def adapt(self) -> ScanAdapterResult:
        """Construct Bill of Materials items for switchgear scanning pages."""
        items: list[ScanRenderItem] = []
        sub_ctx = _format_substation_context(self.substation_info)

        # ----------------------------------------------------------------------
        # 1. Overview Scanning Pages (D26 / D47)
        # ----------------------------------------------------------------------
        overview_comps = (
            self.swg.overview_compartments
            if isinstance(self.swg, SwitchgearScanSpec) and self.swg.overview_compartments
            else SwitchgearTopologyEngine.resolve_overview_compartments(
                self.archetype, voltage_class=self.voltage_class
            )
        )

        # Check for D47 overview substitution
        sliced_ov = find_sliced_overview_page("swg", "swg1", self.sliced_overview_pages)
        is_ov_substituted = self.has_active_defect and sliced_ov is not None

        if is_ov_substituted:
            # D47: Finalized overview page(s) sliced directly from Quick Report
            items.append(
                ScanRenderItem(
                    page_name=f"SWG Overview - {overview_comps[0]} (Sliced QR)",
                    template_name="swg-overview.docx",
                    template_path=self.templates_dir / "swg-overview.docx",
                    context={},
                    equipment_category="swg",
                    component_name=overview_comps[0],
                    sequence="p00",
                    is_overview=True,
                    is_sliced=True,
                    sliced_path=sliced_ov,
                    is_defective=True,
                    equipment_id="swg1",
                )
            )
            # Check if a secondary sliced overview page exists (e.g. OVERVIEW BOTTOM)
            if len(overview_comps) > 1:
                sliced_bottom = None
                for cand in self.sliced_overview_pages:
                    c_up = str(cand).upper()
                    if ("BOTTOM" in c_up or "P00_01" in c_up or "P00B" in c_up) and Path(cand).is_file():
                        sliced_bottom = Path(cand)
                        break
                if sliced_bottom:
                    items.append(
                        ScanRenderItem(
                            page_name=f"SWG Overview - {overview_comps[1]} (Sliced QR)",
                            template_name="swg-overview.docx",
                            template_path=self.templates_dir / "swg-overview.docx",
                            context={},
                            equipment_category="swg",
                            component_name=overview_comps[1],
                            sequence="p00_01",
                            is_overview=True,
                            is_sliced=True,
                            sliced_path=sliced_bottom,
                            is_defective=True,
                            equipment_id="swg1",
                        )
                    )
        else:
            # Rendered overview page(s)
            for ov_idx, ov_area in enumerate(overview_comps):
                seq = "p00" if ov_idx == 0 else f"p00_{ov_idx}"
                ov_name = f"SWG Overview - {ov_area}"

                ir_num = _resolve_swg_overview_photo_num(self.archetype, ov_area, self.swg.photo_numbers)
                if ir_num is not None and self.photo_resolver:
                    ir_img = self.photo_resolver.resolve_ir_photo(ir_num)
                    vis_img = self.photo_resolver.resolve_visual_photo(ir_num)
                else:
                    ir_img = ""
                    vis_img = ""

                banner_analysis = BANNER_DEFECT_FORWARDING if self.has_active_defect else BANNER_HEALTHY_ANALYSIS
                banner_rec = BANNER_DEFECT_FORWARDING if self.has_active_defect else BANNER_HEALTHY_RECOMMENDATION

                ov_ctx = {
                    "substation": sub_ctx,
                    "swg": {
                        "type": _clean_str(self.swg.switchgear_type, "RMU SF6"),
                        "manufacturer": _clean_str(self.swg.manufacturer),
                        "model": _clean_str(self.swg.model),
                        "rating": _clean_str(self.swg.rating),
                        "area": ov_area,
                        "serialnumber": _clean_str(self.swg.serial_no),
                        "analysis": banner_analysis,
                        "recommendation": banner_rec,
                    },
                    "ir": {
                        # Deprecated: FLIR ActiveX CIRViewer object is preserved in normal docx templates;
                        # docxtpl leaves <w:object> untouched. Kept for backward compatibility with adapter queries.
                        "image": ir_img,
                        "severity": "-",
                        "reading": "-",
                    },
                    "visual": {
                        "image": vis_img,
                    },
                    "banner": {
                        "analysis": banner_analysis,
                        "recommendation": banner_rec,
                    },
                    "analysis": banner_analysis,
                    "recommendation": banner_rec,
                }

                items.append(
                    ScanRenderItem(
                        page_name=ov_name,
                        template_name="swg-overview.docx",
                        template_path=self.templates_dir / "swg-overview.docx",
                        context=ov_ctx,
                        equipment_category="swg",
                        component_name=ov_area,
                        sequence=seq,
                        is_overview=True,
                        is_sliced=False,
                        is_defective=self.has_active_defect,
                        equipment_id="swg1",
                    )
                )

        # ----------------------------------------------------------------------
        # 2. Panel Scanning Pages (D26 / D29)
        # ----------------------------------------------------------------------
        is_vcb = self.archetype in (
            SwitchgearArchetype.VCB_CUBICLE,
            SwitchgearArchetype.GIS_CUBICLE,
        )

        for panel in self.swg.panels:
            p_no = panel.panel_no
            p_name = panel.name or f"PANEL {p_no}"
            seq = f"p{p_no:02d}"

            compartments = (
                panel.compartments
                if isinstance(panel, SwitchgearPanelScanSpec) and panel.compartments
                else SwitchgearTopologyEngine.resolve_panel_compartments(archetype=self.archetype, panel=panel)
            )

            for comp_idx, comp_name in enumerate(compartments):
                # IR & Visual photo mapping: Strict 1-to-1 photo pairing & zero fallback
                ir_num = None
                if is_vcb:
                    if comp_name in ("BREAKER COMPARTMENT", "FRONT COMPARTMENT"):
                        ir_num = panel.breaker_photo
                    elif comp_name in ("CABLE COMPARTMENT", "REAR COMPARTMENT"):
                        ir_num = panel.cable_photo
                    elif comp_name == "BUSBAR COMPARTMENT":
                        ir_num = panel.busbar_photo
                    elif comp_name == "PT COMPARTMENT":
                        ir_num = panel.pt_photo
                    elif comp_name == "SECONDARY COMPARTMENT":
                        ir_num = panel.secondary_photo
                    else:
                        ir_num = None
                else:
                    # RMU Archetypes:
                    if comp_name == "CABLE COMPARTMENT":
                        ir_num = panel.cable_photo if panel.cable_photo is not None else (panel.photo_numbers[0] if panel.photo_numbers else None)
                    elif comp_name == "FUSE COMPARTMENT":
                        ir_num = panel.cable_photo if panel.cable_photo is not None else (panel.photo_numbers[0] if panel.photo_numbers else None)
                    elif comp_name == "CABLE ENTRY":
                        ir_num = (
                            panel.photo_numbers[1]
                            if (panel.photo_numbers and len(panel.photo_numbers) > 1)
                            else panel.breaker_photo
                        )
                    else:
                        ir_num = None

                # Strict Zero-Fallback: if ir_num is None, no photo is resolved
                if ir_num is not None and self.photo_resolver:
                    ir_img = self.photo_resolver.resolve_ir_photo(ir_num)
                    vis_img = self.photo_resolver.resolve_visual_photo(ir_num)
                else:
                    ir_img = ""
                    vis_img = ""

                # Evaluate TEV and US activity via Two-Tier model:
                comp_tev_active = self.contract.is_swg_tev_active(comp_name)
                comp_us_active = self.contract.is_swg_us_active(comp_name)

                # Resolve PRPD graphs for panel and compartment
                us_prpd, tev_prpd = self._resolve_prpd(
                    panel_no=p_no,
                    panel_name=p_name,
                    compartment=comp_name,
                    include_tev=comp_tev_active,
                    include_us=comp_us_active,
                )

                # Format parameters
                h_amp = format_heater_amp(panel.heater_amp, is_vcb=is_vcb)
                bus_pos = format_busbar_position(f"{p_name} {panel.panel_feeder_no}", is_vcb=is_vcb)
                us_char_norm = normalize_us_characteristic(panel.us_char, default="NORMAL")

                if comp_us_active:
                    us_ctx = {
                        "reading": format_db_int(panel.us_reading),
                        "char": us_char_norm,
                        "severity": "NORMAL",
                        "prpd": us_prpd,
                    }
                else:
                    us_ctx = {
                        "reading": "",
                        "char": "",
                        "severity": "",
                        "prpd": "",
                    }

                if comp_tev_active:
                    tev_ctx = {
                        "bg": format_db_int(self.tev_background),
                        "reading": format_db_int(panel.tev_reading),
                        "ppc": _clean_str(panel.tev_ppc),
                        "char": _clean_str(panel.tev_char),
                        "severity": "NORMAL",
                        "prpd": tev_prpd,
                    }
                else:
                    tev_ctx = {
                        "bg": "",
                        "reading": "",
                        "ppc": "",
                        "char": "",
                        "severity": "",
                        "prpd": "",
                    }

                panel_ctx = {
                    "substation": sub_ctx,
                    "swg": {
                        "type": _clean_str(self.swg.switchgear_type, "RMU SF6"),
                        "manufacturer": _clean_str(self.swg.manufacturer),
                        "model": _clean_str(self.swg.model),
                        "rating": _clean_str(self.swg.rating),
                        "serialnumber": _clean_str(self.swg.serial_no),
                    },
                    "panel": {
                        "name": p_name,
                        "linknumber": _clean_str(panel.panel_feeder_no or str(p_no)),
                        "feeder_no": _clean_str(panel.panel_feeder_no or ""),
                        "area": comp_name,
                        "serialnumber": _clean_str(panel.serial_no),
                        "serial_no": _clean_str(panel.serial_no),
                        "heateramp": h_amp,
                        "breakerstatus": _clean_str(panel.status, "CLOSE"),
                        "busbarposition": bus_pos,
                        "cabletype": _clean_str(panel.cable_type),
                        "loadamp": format_load_amp(panel.load_amp) if panel.load_amp else "-",
                        "analysis": BANNER_HEALTHY_ANALYSIS,
                        "recommendation": BANNER_HEALTHY_RECOMMENDATION,
                        "ir": {
                            "reading": "-",
                            "severity": "NORMAL",
                        },
                        "us": us_ctx,
                        "tev": tev_ctx,
                    },
                    "ir": {
                        # Deprecated: FLIR ActiveX CIRViewer object is preserved in normal docx templates;
                        # docxtpl leaves <w:object> untouched. Kept for backward compatibility with adapter queries.
                        "image": ir_img,
                        "reading": "-",
                        "severity": "NORMAL",
                    },
                    "visual": {
                        "image": vis_img,
                    },
                    "us": us_ctx,
                    "tev": tev_ctx,
                    "banner": {
                        "analysis": BANNER_HEALTHY_ANALYSIS,
                        "recommendation": BANNER_HEALTHY_RECOMMENDATION,
                    },
                    "analysis": BANNER_HEALTHY_ANALYSIS,
                    "recommendation": BANNER_HEALTHY_RECOMMENDATION,
                    "__blank_tev__": not comp_tev_active,
                    "is_tev_active": comp_tev_active,
                    "__blank_us__": not comp_us_active,
                    "is_us_active": comp_us_active,
                }

                items.append(
                    ScanRenderItem(
                        page_name=f"Panel {p_no} ({p_name}) - {comp_name}",
                        template_name="swg-panel.docx",
                        template_path=self.templates_dir / "swg-panel.docx",
                        context=panel_ctx,
                        equipment_category="swg",
                        component_name=comp_name,
                        sequence=seq,
                        is_overview=False,
                        is_sliced=False,
                        is_defective=False,
                        panel_no=p_no,
                        equipment_id="swg1",
                    )
                )

        return ScanAdapterResult(
            equipment_category="swg",
            equipment_id="swg1",
            items=tuple(items),
            has_defect=self.has_active_defect,
            is_overview_substituted=is_ov_substituted,
        )

    def _resolve_prpd(
        self,
        panel_no: int,
        panel_name: str = "",
        compartment: str | None = None,
        include_tev: bool = True,
        include_us: bool = True,
    ) -> tuple[str, str]:
        """Resolve US and TEV PRPD waveform image file paths, falling back to clean '' per D08."""
        should_gen_tev = include_tev and (compartment is None or is_swg_compartment_tev_eligible(compartment))
        should_gen_us = include_us and (compartment is None or is_swg_compartment_us_eligible(compartment))

        # 1. Catalog lookup
        if self.prpd_catalog and "swg" in self.prpd_catalog:
            swg_cat = self.prpd_catalog["swg"]
            if panel_no in swg_cat:
                entry = swg_cat[panel_no]
                us_p = str(entry.get("us") or "") if should_gen_us else ""
                tev_p = str(entry.get("tev") or "") if should_gen_tev else ""
                return us_p, tev_p

        # 2. Dynamic generation via prpd.py if survey directory is available
        if self.survey_root and self.survey_root.exists():
            s_root = discover_ultratev_survey_dir(self.survey_root) or self.survey_root
            out_d = self.prpd_output_dir or Path(tempfile.gettempdir())
            try:
                us_png, tev_png = generate_prpd_graphs_for_swg_panel(
                    survey_root=s_root,
                    panel_no=panel_no,
                    output_dir=out_d,
                    panel_name=panel_name,
                    mode=self.prpd_mode,
                    compartment=compartment,
                    include_tev=should_gen_tev,
                    include_us=should_gen_us,
                )
                return (str(us_png) if us_png else ""), (str(tev_png) if tev_png else "")
            except Exception as exc:
                logger.warning("Failed to generate PRPD graphs for SWG panel %d: %s", panel_no, exc)

        return "", ""


# ==============================================================================
# 2. Transformer Scan Adapter (ADR 0004, D31, D08, D48)
# ==============================================================================

class TransformerScanAdapter:
    """Adapter rendering unconditional 7-point Transformer scanning pages per ADR 0004 & D31."""

    def __init__(
        self,
        tx: TransformerSpec | TransformerScanSpec,
        substation_info: dict[str, Any] | None = None,
        *,
        tx_index: int = 1,
        photo_resolver: RawPhotoResolver | None = None,
        survey_root: Path | str | None = None,
        prpd_catalog: dict[str, Any] | None = None,
        prpd_output_dir: Path | str | None = None,
        prpd_mode: str = "option_c",
        templates_dir: Path | str | None = None,
        sliced_overview_pages: Sequence[Path | str] | None = None,
        has_active_defect: bool | None = None,
        cbm_defects: Sequence[Any] | None = None,
        total_tx_count: int = 1,
        project_technologies: Sequence[str] | set[str] | None = None,
    ) -> None:
        self.tx = tx
        self.substation_info = substation_info or {}
        self.tx_index = tx_index
        self.photo_resolver = photo_resolver
        self.survey_root = Path(survey_root) if survey_root else None
        self.prpd_catalog = prpd_catalog or {}
        self.prpd_output_dir = Path(prpd_output_dir) if prpd_output_dir else None
        self.prpd_mode = prpd_mode
        self.templates_dir = Path(templates_dir) if templates_dir else DEFAULT_TEMPLATES_DIR
        self.sliced_overview_pages = sliced_overview_pages or ()
        self.cbm_defects = cbm_defects or ()
        self.total_tx_count = total_tx_count
        self.contract = (
            ContractScope.from_source(project_technologies)
            if project_technologies is not None
            else ContractScope.from_source(self.substation_info)
        )
        self.project_technologies = self.contract.awarded_technologies

        self.tx_id_str = normalize_tx_id(getattr(tx, "tx_id", None), default_idx=tx_index)
        self.has_active_defect = _check_has_active_defect(
            category="tx",
            equipment_id=self.tx_id_str,
            explicit_flag=has_active_defect,
            cbm_defects=self.cbm_defects,
            total_count=self.total_tx_count,
        )

    def adapt(self) -> ScanAdapterResult:
        """Construct Bill of Materials items for unconditional 7-point transformer scanning."""
        items: list[ScanRenderItem] = []
        sub_ctx = _format_substation_context(self.substation_info)

        # 7 canonical components per ADR 0004 & D31
        components = [
            ("OVERVIEW", "tx-overview.docx", "s00", True),
            ("OVERVIEW TOP", "tx-overview.docx", "s01", True),
            ("HV BUSHING", "tx-hv-sides.docx", "s02", False),
            ("HV CABLE", "tx-hv-sides.docx", "s03", False),
            ("HV CABLE SPLIT", "tx-hv-sides.docx", "s04", False),
            ("LV BUSHING", "tx-lv-sides.docx", "s05", False),
            ("LV CABLE", "tx-lv-sides.docx", "s06", False),
        ]
        if not has_hv_cable_split(self.tx):
            components = [c for c in components if c[0] != "HV CABLE SPLIT"]

        # Check for D47 overview substitution
        sliced_ov = find_sliced_overview_page("tx", self.tx_id_str, self.sliced_overview_pages)
        is_ov_substituted = self.has_active_defect and sliced_ov is not None

        # Resolve PRPD US graph for HV sides
        us_prpd = self._resolve_prpd_us()

        for idx, (comp_name, tpl_name, seq, is_ov) in enumerate(components):
            page_name = f"{self.tx_id_str} - {comp_name}"

            # D47 Overview substitution for Page 1
            if idx == 0 and is_ov_substituted:
                items.append(
                    ScanRenderItem(
                        page_name=f"{page_name} (Sliced QR)",
                        template_name=tpl_name,
                        template_path=self.templates_dir / tpl_name,
                        context={},
                        equipment_category="tx",
                        component_name=comp_name,
                        sequence=seq,
                        is_overview=True,
                        is_sliced=True,
                        sliced_path=sliced_ov,
                        is_defective=True,
                        equipment_id=self.tx_id_str,
                    )
                )
                continue

            # Banner prose: defect forwarding if TX has active defect and overview page, else healthy
            is_def = self.has_active_defect if is_ov else False
            banner_analysis = BANNER_DEFECT_FORWARDING if is_def else BANNER_HEALTHY_ANALYSIS
            banner_rec = BANNER_DEFECT_FORWARDING if is_def else BANNER_HEALTHY_RECOMMENDATION

            # Resolve photos based on component
            ir_img, vis_img = self._resolve_photos_for_component(comp_name)

            # Location & Cable type
            location = "HV SIDE" if "HV" in comp_name else ("LV SIDE" if "LV" in comp_name else "-")
            cable_type = self.tx.hv_cable_type if "HV" in comp_name else (
                self.tx.lv_cable_type if "LV" in comp_name else (self.tx.hv_cable_type or self.tx.lv_cable_type or "-")
            )

            raw_rating = _clean_str(self.tx.rating_kva)
            tx_rating = "-" if raw_rating.upper() in ("NOT ACCESSIBLE", "-", "N/A", "NONE", "NAN", "") else raw_rating
            raw_sn = _clean_str(self.tx.serial_no)
            tx_sn = "-" if raw_sn.upper() in ("NOT ACCESSIBLE", "-", "N/A", "NONE", "NAN", "") else raw_sn

            tx_block = {
                "manufacturer": _clean_str(self.tx.manufacturer),
                "model": normalize_tx_model(getattr(self.tx, "model", None) or getattr(self.tx, "type", None)),
                "rating": tx_rating,
                "number": self.tx_id_str,
                "panel": self.tx_id_str,
                "location": location,
                "area": comp_name,
                "serialnumber": tx_sn,
                "cabletype": _clean_str(cable_type),
                "analysis": banner_analysis,
                "recommendation": banner_rec,
            }

            us_char_norm = normalize_us_characteristic(self.tx.us_char, default="NORMAL")

            ctx: dict[str, Any] = {
                "substation": sub_ctx,
                "tx": tx_block,
                "panel": {"name": self.tx_id_str, "linknumber": self.tx_id_str},
                "ir": {
                    # Deprecated: FLIR ActiveX CIRViewer object is preserved in normal docx templates;
                    # docxtpl leaves <w:object> untouched. Kept for backward compatibility with adapter queries.
                    "image": ir_img,
                    "severity": "-" if is_ov else "NORMAL",
                    "reading": "-",
                },
                "visual": {
                    "image": vis_img,
                },
                "banner": {
                    "analysis": banner_analysis,
                    "recommendation": banner_rec,
                },
                "analysis": banner_analysis,
                "recommendation": banner_rec,
            }

            if "hv-sides" in tpl_name:
                ctx["us"] = {
                    "reading": format_db_int(self.tx.us_reading),
                    "char": us_char_norm,
                    "severity": "NORMAL",
                    "prpd": us_prpd,
                }
                tx_block["us"] = ctx["us"]

            items.append(
                ScanRenderItem(
                    page_name=page_name,
                    template_name=tpl_name,
                    template_path=self.templates_dir / tpl_name,
                    context=ctx,
                    equipment_category="tx",
                    component_name=comp_name,
                    sequence=seq,
                    is_overview=is_ov,
                    is_sliced=False,
                    is_defective=is_def,
                    equipment_id=self.tx_id_str,
                )
            )

        return ScanAdapterResult(
            equipment_category="tx",
            equipment_id=self.tx_id_str,
            items=tuple(items),
            has_defect=self.has_active_defect,
            is_overview_substituted=is_ov_substituted,
        )

    def _resolve_photos_for_component(self, comp_name: str) -> tuple[str, str]:
        """Resolve IR and visual photos for a specific transformer component."""
        if not self.photo_resolver:
            return "", ""

        nums = self.tx.photo_numbers or ()

        if comp_name == "OVERVIEW":
            num = nums[0] if len(nums) > 0 else None
            return self.photo_resolver.resolve_ir_photo(num), self.photo_resolver.resolve_visual_photo(num)

        if comp_name == "OVERVIEW TOP":
            # D48: Fallback to None / "" if not explicitly mapped
            num = nums[1] if len(nums) > 1 and len(nums) >= 7 else None
            return (
                self.photo_resolver.resolve_tx_overview_top_photo(num),
                self.photo_resolver.resolve_tx_overview_top_pair(num).visual_photo,
            )

        if comp_name == "HV CABLE SPLIT":
            # ADR 0004: Secondary cable split photo resolution
            split_p = self.photo_resolver.resolve_cable_split_pair(nums)
            return split_p.ir_photo, split_p.visual_photo

        # Other standard components: HV BUSHING, HV CABLE, LV BUSHING, LV CABLE
        # Aligned with testsheet Rows 33-37 per D05 (Row 33: Ov, Row 34: HVB, Row 35: HVC, Row 36: LVB, Row 37: LVC)
        comp_index_map = {
            "HV BUSHING": 1,
            "HV CABLE": 2,
            "LV BUSHING": 3,
            "LV CABLE": 4,
        }
        idx = comp_index_map.get(comp_name, 0)
        num = nums[idx] if len(nums) > idx else (nums[0] if len(nums) > 0 else None)
        return self.photo_resolver.resolve_ir_photo(num), self.photo_resolver.resolve_visual_photo(num)

    def _resolve_prpd_us(self) -> str:
        """Resolve Transformer US PRPD waveform image file path, falling back to clean '' per D08."""
        # 1. Catalog lookup
        if self.prpd_catalog and "tx" in self.prpd_catalog:
            tx_cat = self.prpd_catalog["tx"]
            if self.tx_index in tx_cat:
                entry = tx_cat[self.tx_index]
                return str(entry.get("us") or "")

        # 2. Dynamic generation via prpd.py
        if self.survey_root and self.survey_root.exists():
            s_root = discover_ultratev_survey_dir(self.survey_root) or self.survey_root
            out_d = self.prpd_output_dir or Path(tempfile.gettempdir())
            try:
                us_png, _ = generate_prpd_graphs_for_transformer(
                    survey_root=s_root,
                    tx_idx=self.tx_index,
                    output_dir=out_d,
                    mode=self.prpd_mode,
                )
                return str(us_png) if us_png else ""
            except Exception as exc:
                logger.warning("Failed to generate PRPD US graph for TX %d: %s", self.tx_index, exc)

        return ""


# ==============================================================================
# 3. Feeder Pillar / LVDB Scan Adapter
# ==============================================================================

class LVDBScanAdapter:
    """Adapter rendering Feeder Pillar / LVDB overview scanning page."""

    def __init__(
        self,
        lvdb: LVDBSpec | LVDBScanSpec,
        substation_info: dict[str, Any] | None = None,
        *,
        photo_resolver: RawPhotoResolver | None = None,
        templates_dir: Path | str | None = None,
        sliced_overview_pages: Sequence[Path | str] | None = None,
        has_active_defect: bool | None = None,
        cbm_defects: Sequence[Any] | None = None,
        total_fp_count: int = 1,
    ) -> None:
        self.lvdb = lvdb
        self.substation_info = substation_info or {}
        self.photo_resolver = photo_resolver
        self.templates_dir = Path(templates_dir) if templates_dir else DEFAULT_TEMPLATES_DIR
        self.sliced_overview_pages = sliced_overview_pages or ()
        self.cbm_defects = cbm_defects or ()
        self.total_fp_count = total_fp_count

        self.name_str = _clean_str(getattr(lvdb, "name", "FP 1"), "FP 1")
        self.has_active_defect = _check_has_active_defect(
            category="fp",
            equipment_id=self.name_str,
            explicit_flag=has_active_defect,
            cbm_defects=self.cbm_defects,
            total_count=self.total_fp_count,
        )

    def adapt(self) -> ScanAdapterResult:
        """Construct Bill of Materials items for Feeder Pillar scanning page."""
        sub_ctx = _format_substation_context(self.substation_info)
        page_name = f"{self.name_str} - OVERVIEW"

        # Check for D47 overview substitution
        sliced_ov = find_sliced_overview_page("fp", self.name_str, self.sliced_overview_pages)
        is_ov_substituted = self.has_active_defect and sliced_ov is not None

        if is_ov_substituted:
            item = ScanRenderItem(
                page_name=f"{page_name} (Sliced QR)",
                template_name="fp-overview.docx",
                template_path=self.templates_dir / "fp-overview.docx",
                context={},
                equipment_category="fp",
                component_name="OVERVIEW",
                sequence="f00",
                is_overview=True,
                is_sliced=True,
                sliced_path=sliced_ov,
                is_defective=True,
                equipment_id=self.name_str,
            )
            return ScanAdapterResult(
                equipment_category="fp",
                equipment_id=self.name_str,
                items=(item,),
                has_defect=self.has_active_defect,
                is_overview_substituted=True,
            )

        # Rendered overview
        banner_analysis = BANNER_DEFECT_FORWARDING if self.has_active_defect else BANNER_HEALTHY_ANALYSIS
        banner_rec = BANNER_DEFECT_FORWARDING if self.has_active_defect else BANNER_HEALTHY_RECOMMENDATION

        ir_num = self.lvdb.photo_numbers[0] if self.lvdb.photo_numbers else None
        ir_img = self.photo_resolver.resolve_ir_photo(ir_num) if self.photo_resolver else ""
        vis_img = self.photo_resolver.resolve_visual_photo(ir_num) if self.photo_resolver else ""

        label_source = (
            getattr(self.lvdb, "name", None)
            or getattr(self.lvdb, "label", None)
            or getattr(self.lvdb, "source", None)
            or "FP"
        )

        fp_ctx = {
            "substation": sub_ctx,
            "fp": {
                "labelsource": label_source,
                "manufacturer": _clean_str(self.lvdb.manufacturer),
                "model": _clean_str(getattr(self.lvdb, "model", "-")),
                "rating": _clean_str(self.lvdb.rating),
                "area": "OVERVIEW",
                "serialnumber": _clean_str(self.lvdb.serial_no),
                "cabletype": _clean_str(self.lvdb.cable_type),
                "feederno": "-",
                "loadamp": "-",
                "analysis": banner_analysis,
                "recommendation": banner_rec,
            },
            "ir": {
                # Deprecated: FLIR ActiveX CIRViewer object is preserved in normal docx templates;
                # docxtpl leaves <w:object> untouched. Kept for backward compatibility with adapter queries.
                "image": ir_img,
                "severity": "-",
                "reading": "-",
            },
            "visual": {
                "image": vis_img,
            },
            "banner": {
                "analysis": banner_analysis,
                "recommendation": banner_rec,
            },
            "analysis": banner_analysis,
            "recommendation": banner_rec,
        }

        item = ScanRenderItem(
            page_name=page_name,
            template_name="fp-overview.docx",
            template_path=self.templates_dir / "fp-overview.docx",
            context=fp_ctx,
            equipment_category="fp",
            component_name="OVERVIEW",
            sequence="f00",
            is_overview=True,
            is_sliced=False,
            is_defective=self.has_active_defect,
            equipment_id=self.name_str,
        )

        return ScanAdapterResult(
            equipment_category="fp",
            equipment_id=self.name_str,
            items=(item,),
            has_defect=self.has_active_defect,
            is_overview_substituted=False,
        )


# Canonical alias
FeederPillarScanAdapter = LVDBScanAdapter


# ==============================================================================
# 4. Battery Bank Scan Adapter
# ==============================================================================

class BatteryBankScanAdapter:
    """Adapter rendering Battery Bank overview scanning page."""

    def __init__(
        self,
        bb: BatteryBankSpec | BatteryBankScanSpec,
        substation_info: dict[str, Any] | None = None,
        *,
        photo_resolver: RawPhotoResolver | None = None,
        templates_dir: Path | str | None = None,
        sliced_overview_pages: Sequence[Path | str] | None = None,
        has_active_defect: bool | None = None,
        cbm_defects: Sequence[Any] | None = None,
    ) -> None:
        self.bb = bb
        self.substation_info = substation_info or {}
        self.photo_resolver = photo_resolver
        self.templates_dir = Path(templates_dir) if templates_dir else DEFAULT_TEMPLATES_DIR
        self.sliced_overview_pages = sliced_overview_pages or ()
        self.cbm_defects = cbm_defects or ()

        self.name_str = _clean_str(getattr(bb, "name", "BATTERY 1"), "BATTERY 1")
        self.has_active_defect = _check_has_active_defect(
            category="battery",
            equipment_id=self.name_str,
            explicit_flag=has_active_defect,
            cbm_defects=self.cbm_defects,
        )

    def adapt(self) -> ScanAdapterResult:
        """Construct Bill of Materials items for Battery Bank scanning page."""
        sub_ctx = _format_substation_context(self.substation_info)
        page_name = f"{self.name_str} - OVERVIEW"

        # Check for D47 overview substitution
        sliced_ov = find_sliced_overview_page("battery", self.name_str, self.sliced_overview_pages)
        is_ov_substituted = self.has_active_defect and sliced_ov is not None

        if is_ov_substituted:
            item = ScanRenderItem(
                page_name=f"{page_name} (Sliced QR)",
                template_name="battery-overview.docx",
                template_path=self.templates_dir / "battery-overview.docx",
                context={},
                equipment_category="battery",
                component_name="OVERVIEW",
                sequence="b00",
                is_overview=True,
                is_sliced=True,
                sliced_path=sliced_ov,
                is_defective=True,
                equipment_id=self.name_str,
            )
            return ScanAdapterResult(
                equipment_category="battery",
                equipment_id=self.name_str,
                items=(item,),
                has_defect=self.has_active_defect,
                is_overview_substituted=True,
            )

        # Rendered overview
        banner_analysis = BANNER_DEFECT_FORWARDING if self.has_active_defect else BANNER_HEALTHY_ANALYSIS
        banner_rec = BANNER_DEFECT_FORWARDING if self.has_active_defect else BANNER_HEALTHY_RECOMMENDATION

        ir_num = self.bb.photo_numbers[0] if self.bb.photo_numbers else None
        ir_img = self.photo_resolver.resolve_ir_photo(ir_num) if self.photo_resolver else ""
        vis_img = self.photo_resolver.resolve_visual_photo(ir_num) if self.photo_resolver else ""

        batt_block = {
            "number": self.name_str,
            "manufacturer": _clean_str(self.bb.manufacturer),
            "model": _clean_str(self.bb.model),
            "serialnumber": _clean_str(self.bb.serial_no),
            "rating": _clean_str(getattr(self.bb, "rating", "-")),
            "area": "OVERVIEW",
            "analysis": banner_analysis,
            "recommendation": banner_rec,
        }

        ctx = {
            "substation": sub_ctx,
            "battery": batt_block,
            "batt": batt_block,  # Support both namespace conventions
            "ir": {
                # Deprecated: FLIR ActiveX CIRViewer object is preserved in normal docx templates;
                # docxtpl leaves <w:object> untouched. Kept for backward compatibility with adapter queries.
                "image": ir_img,
                "severity": "-",
                "reading": "-",
            },
            "visual": {
                "image": vis_img,
            },
            "banner": {
                "analysis": banner_analysis,
                "recommendation": banner_rec,
            },
            "analysis": banner_analysis,
            "recommendation": banner_rec,
        }

        item = ScanRenderItem(
            page_name=page_name,
            template_name="battery-overview.docx",
            template_path=self.templates_dir / "battery-overview.docx",
            context=ctx,
            equipment_category="battery",
            component_name="OVERVIEW",
            sequence="b00",
            is_overview=True,
            is_sliced=False,
            is_defective=self.has_active_defect,
            equipment_id=self.name_str,
        )

        return ScanAdapterResult(
            equipment_category="battery",
            equipment_id=self.name_str,
            items=(item,),
            has_defect=self.has_active_defect,
            is_overview_substituted=False,
        )


# ==============================================================================
# 5. Composite Package Dispatcher
# ==============================================================================

def adapt_equipment_package(
    package: FullReportScanPackage | SubstationEquipmentPackage,
    substation_info: dict[str, Any] | None = None,
    *,
    photo_resolver: RawPhotoResolver | None = None,
    survey_root: Path | str | None = None,
    prpd_catalog: dict[str, Any] | None = None,
    prpd_output_dir: Path | str | None = None,
    templates_dir: Path | str | None = None,
    sliced_overview_pages: Sequence[Path | str] | None = None,
    cbm_defects: Sequence[Any] | None = None,
    project_technologies: Sequence[str] | set[str] | None = None,
) -> list[ScanAdapterResult]:
    """Adapt all equipment in a scan package into an ordered list of ScanAdapterResults."""
    results: list[ScanAdapterResult] = []

    # 1. Switchgears
    for swg in getattr(package, "switchgears", ()):
        adapter = SwitchgearScanAdapter(
            swg=swg,
            substation_info=substation_info,
            photo_resolver=photo_resolver,
            survey_root=survey_root,
            prpd_catalog=prpd_catalog,
            prpd_output_dir=prpd_output_dir,
            templates_dir=templates_dir,
            sliced_overview_pages=sliced_overview_pages,
            cbm_defects=cbm_defects,
            project_technologies=project_technologies,
        )
        results.append(adapter.adapt())

    # 2. Transformers
    for tx_idx, tx in enumerate(getattr(package, "transformers", ()), 1):
        adapter = TransformerScanAdapter(
            tx=tx,
            substation_info=substation_info,
            tx_index=tx_idx,
            photo_resolver=photo_resolver,
            survey_root=survey_root,
            prpd_catalog=prpd_catalog,
            prpd_output_dir=prpd_output_dir,
            templates_dir=templates_dir,
            sliced_overview_pages=sliced_overview_pages,
            cbm_defects=cbm_defects,
            project_technologies=project_technologies,
        )
        results.append(adapter.adapt())

    # 3. LVDB / Feeder Pillars
    for lvdb in getattr(package, "lvdb_specs", ()):
        adapter = LVDBScanAdapter(
            lvdb=lvdb,
            substation_info=substation_info,
            photo_resolver=photo_resolver,
            templates_dir=templates_dir,
            sliced_overview_pages=sliced_overview_pages,
            cbm_defects=cbm_defects,
        )
        results.append(adapter.adapt())

    # 4. Battery Banks
    for bb in getattr(package, "battery_banks", ()):
        adapter = BatteryBankScanAdapter(
            bb=bb,
            substation_info=substation_info,
            photo_resolver=photo_resolver,
            templates_dir=templates_dir,
            sliced_overview_pages=sliced_overview_pages,
            cbm_defects=cbm_defects,
        )
        results.append(adapter.adapt())

    return results


__all__ = [
    "DEFAULT_TEMPLATES_DIR",
    "ScanPageContext",
    "ScanRenderItem",
    "ScanAdapterResult",
    "find_sliced_overview_page",
    "SwitchgearScanAdapter",
    "TransformerScanAdapter",
    "LVDBScanAdapter",
    "FeederPillarScanAdapter",
    "BatteryBankScanAdapter",
    "adapt_equipment_package",
]
