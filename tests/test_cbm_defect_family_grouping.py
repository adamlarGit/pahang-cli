"""Reproduction test asserting that multiple defect rows belonging to an equipment family
produce a single overview page followed by all its individual defect pages in sequence.
Phases are not merged; only family equipment is grouped to produce one overview.
"""

from pathlib import Path
from unittest.mock import MagicMock

from src.quick_report.cbm_defect_pages import CbmDefectPageBuilder
from src.quick_report.cbm_defect_planner import CbmDefectPlanner
from src.quick_report.defects import CbmDefectRecord


def test_multiple_defects_same_family_produces_single_overview_and_individual_defect_pages():
    """Defects for FP TX1 across multiple feeders and phases must group into ONE FP TX1 family group,
    yielding 1 overview page and 6 individual defect pages (total 7 pages), NOT multiple overviews.
    """
    planner = CbmDefectPlanner()

    defects = [
        CbmDefectRecord(
            equipment="FP (J)",
            equipment_id="FP TX1 - OUTGOING F1",
            defect_area="OUTGOING FUSE CONNECTION",
            additional_remarks="RED PHASE",
            technology="IR",
            ir_reading="62.5",
        ),
        CbmDefectRecord(
            equipment="FP (J)",
            equipment_id="FP TX1 - OUTGOING F1",
            defect_area="OUTGOING FUSE CONNECTION",
            additional_remarks="YELLOW PHASE",
            technology="IR",
            ir_reading="60.0",
        ),
        CbmDefectRecord(
            equipment="FP (J)",
            equipment_id="FP TX1 - OUTGOING F2",
            defect_area="OUTGOING FUSE CONNECTION",
            additional_remarks="RED PHASE",
            technology="IR",
            ir_reading="62.9",
        ),
        CbmDefectRecord(
            equipment="FP (J)",
            equipment_id="FP TX1 - OUTGOING F2",
            defect_area="OUTGOING FUSE CONNECTION",
            additional_remarks="YELLOW PHASE",
            technology="IR",
            ir_reading="65.2",
        ),
        CbmDefectRecord(
            equipment="FP (J)",
            equipment_id="FP TX1 - OUTGOING F3",
            defect_area="OUTGOING FUSE CONNECTION",
            additional_remarks="RED PHASE",
            technology="IR",
            ir_reading="62.3",
        ),
        CbmDefectRecord(
            equipment="FP (J)",
            equipment_id="FP TX1 - OUTGOING F3",
            defect_area="OUTGOING FUSE CONNECTION",
            additional_remarks="YELLOW PHASE",
            technology="IR",
            ir_reading="60.1",
        ),
    ]

    env = MagicMock()
    env.get_template.side_effect = lambda k: (
        Path("templates/QUICK REPORT/DEFECT IR/fp-overview.docx")
        if "overview" in k
        else Path("templates/QUICK REPORT/DEFECT IR/fp-individual-defect.docx")
    )

    plans = planner.plan(defects, env)

    # 1. Assert planner produces 1 family plan with 1 equipment family group ("FP TX1")
    assert len(plans) == 1, f"Expected 1 family plan, got {len(plans)}"
    family_plan = plans[0]
    assert len(family_plan.groups) == 1, (
        f"Expected 1 equipment family group ('FP TX1'), but got {len(family_plan.groups)}: "
        f"{[g.item_key for g in family_plan.groups]}"
    )

    # Within the FP TX1 group, all 6 individual defect rows must be preserved (phases not merged)
    group = family_plan.groups[0]
    assert len(group.defects) == 6, (
        f"Expected 6 individual defect records in group, got {len(group.defects)}"
    )

    # 2. Assert page builder produces 1 overview page and 6 individual defect pages
    builder = CbmDefectPageBuilder()
    pages = builder.build(family_plan, {"substation": {"name_erms": "KLG MATTERHORN"}}, 84)

    overview_pages = [p for p in pages if "OVERVIEW" in p.output_filename]
    defect_pages = [p for p in pages if "OVERVIEW" not in p.output_filename]

    assert len(overview_pages) == 1, (
        f"Expected exactly 1 overview page for FP TX1 family, but got {len(overview_pages)}: "
        f"{[p.output_filename for p in overview_pages]}"
    )
    assert len(defect_pages) == 6, (
        f"Expected 6 defect pages (F1 Red, F1 Yellow, F2 Red, F2 Yellow, F3 Red, F3 Yellow), "
        f"but got {len(defect_pages)}: {[p.output_filename for p in defect_pages]}"
    )
    assert len(pages) == 7, f"Expected 7 pages total (1 overview + 6 defect pages), got {len(pages)}"
