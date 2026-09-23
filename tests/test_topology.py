"""Pure unit test suite for Switchgear Topology Engine (Ticket #49)."""

import pytest

from src.core.topology import (
    BayRole,
    SwitchgearArchetype,
    VoltageClass,
)


def test_domain_enums_values() -> None:
    """Verify enum members and their canonical string values."""
    assert SwitchgearArchetype.VCB_CUBICLE == "VCB_CUBICLE"
    assert SwitchgearArchetype.GIS_CUBICLE == "GIS_CUBICLE"
    assert SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY == "RMU_DUAL_CABLE_ENTRY"
    assert SwitchgearArchetype.RMU_FUSE_CANISTER == "RMU_FUSE_CANISTER"
    assert SwitchgearArchetype.RMU_OIL == "RMU_OIL"
    assert SwitchgearArchetype.RMU_STANDARD == "RMU_STANDARD"

    assert VoltageClass.LV == "LV"
    assert VoltageClass.KV_6_6 == "6.6kV"
    assert VoltageClass.KV_11 == "11kV"
    assert VoltageClass.KV_22 == "22kV"
    assert VoltageClass.KV_33 == "33kV"

    assert BayRole.STANDARD == "STANDARD"
    assert BayRole.TRANSFORMER == "TRANSFORMER"
    assert BayRole.TRANSITION == "TRANSITION"
    assert BayRole.BUS_SECTION == "BUS_SECTION"
    assert BayRole.BUS_COUPLER == "BUS_COUPLER"


def test_classify_voltage_rating() -> None:
    """Verify voltage rating normalization to VoltageClass enum."""
    from src.core.topology import classify_voltage_rating

    assert classify_voltage_rating("11kV") == VoltageClass.KV_11
    assert classify_voltage_rating("11 kV") == VoltageClass.KV_11
    assert classify_voltage_rating("12kV") == VoltageClass.KV_11
    assert classify_voltage_rating("12kV, 630A") == VoltageClass.KV_11
    assert classify_voltage_rating("12 kV 630 A") == VoltageClass.KV_11
    assert classify_voltage_rating("") == VoltageClass.KV_11
    assert classify_voltage_rating("   ") == VoltageClass.KV_11
    assert classify_voltage_rating(None) == VoltageClass.KV_11  # type: ignore[arg-type]

    assert classify_voltage_rating("33kV") == VoltageClass.KV_33
    assert classify_voltage_rating("33 kV, 1250A") == VoltageClass.KV_33

    assert classify_voltage_rating("22kV") == VoltageClass.KV_22
    assert classify_voltage_rating("6.6kV") == VoltageClass.KV_6_6
    assert classify_voltage_rating("LV") == VoltageClass.LV
    assert classify_voltage_rating("415V") == VoltageClass.LV


def test_extract_model_from_manufacturer() -> None:
    """Verify extraction of known model tokens when model is blank."""
    from src.core.topology import extract_model_from_manufacturer

    # Model already explicit
    assert extract_model_from_manufacturer("INDKOM", "INS24") == "INS24"
    assert extract_model_from_manufacturer("TAMCO", "GV3") == "GV3"
    assert extract_model_from_manufacturer("", "FALCON") == "FALCON"

    # Model blank - extract known tokens from manufacturer
    assert extract_model_from_manufacturer("INDKOM INS24", "") == "INS24"
    assert extract_model_from_manufacturer("INDKOM INS-24", "  ") == "INS24"
    assert extract_model_from_manufacturer("Tamco GR1", None) == "GR1"  # type: ignore[arg-type]
    assert extract_model_from_manufacturer("LUCY FALCON BETA", "") == "FALCON"
    assert extract_model_from_manufacturer("Indkom JMW12", "") == "JMW12"
    assert extract_model_from_manufacturer("Lucy VRN2a", "") == "VRN2A"
    assert extract_model_from_manufacturer("Tamco GV3", "") == "GV3"

    # No token present
    assert extract_model_from_manufacturer("SIEMENS", "") == ""
    assert extract_model_from_manufacturer("", "") == ""


def test_resolve_switchgear_archetype() -> None:
    """Verify archetype resolution hierarchy across type, manufacturer, and model."""
    from src.core.topology import resolve_switchgear_archetype

    # 1. VCB priority over manufacturer and model
    assert resolve_switchgear_archetype("VCB", "TAMCO", "GV3") == SwitchgearArchetype.VCB_CUBICLE
    assert resolve_switchgear_archetype("VCB 11kV", "EPE", "") == SwitchgearArchetype.VCB_CUBICLE
    assert resolve_switchgear_archetype("RMU", "TAMCO VCB", "") == SwitchgearArchetype.VCB_CUBICLE

    # 2. GIS priority
    assert resolve_switchgear_archetype("GIS", "ABB", "ZX0") == SwitchgearArchetype.GIS_CUBICLE
    assert resolve_switchgear_archetype("GIS 33kV", "", "") == SwitchgearArchetype.GIS_CUBICLE

    # 3. Oil / OCB priority
    assert resolve_switchgear_archetype("RMU OIL", "LUCY", "VRN2A") == SwitchgearArchetype.RMU_OIL
    assert resolve_switchgear_archetype("RMU OIL", "LUCY", "") == SwitchgearArchetype.RMU_OIL
    assert resolve_switchgear_archetype("OCB", "SOUTH WALES", "") == SwitchgearArchetype.RMU_OIL
    assert resolve_switchgear_archetype("RMU SF6", "LUCY", "VRN2A") == SwitchgearArchetype.RMU_OIL
    assert resolve_switchgear_archetype("RMU SF6", "LUCY VRN2a", "") == SwitchgearArchetype.RMU_OIL

    # 4. Lucy variants -> RMU_DUAL_CABLE_ENTRY
    assert resolve_switchgear_archetype("RMU SF6", "LUCY", "") == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY
    assert resolve_switchgear_archetype("RMU SF6", "SSE LUCY", "") == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY
    assert resolve_switchgear_archetype("RMU SF6", "LUCY ELECTRIC", "") == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY
    assert resolve_switchgear_archetype("RMU SF6", "LUCY SWITCHGEAR", "") == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY
    assert resolve_switchgear_archetype("RMU SF6", "", "FALCON") == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY

    # 5. Tamco -> RMU_DUAL_CABLE_ENTRY
    assert resolve_switchgear_archetype("RMU SF6", "TAMCO", "") == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY
    assert resolve_switchgear_archetype("RMU SF6", "", "GR1") == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY
    assert resolve_switchgear_archetype("RMU SF6", "Tamco GR1", "") == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY

    # 6. Indkom: INS24 -> RMU_FUSE_CANISTER; JMW12 or blank -> RMU_STANDARD
    assert resolve_switchgear_archetype("RMU SF6", "INDKOM", "INS24") == SwitchgearArchetype.RMU_FUSE_CANISTER
    assert resolve_switchgear_archetype("RMU SF6", "INDKOM INS24", "") == SwitchgearArchetype.RMU_FUSE_CANISTER
    assert resolve_switchgear_archetype("RMU SF6", "INDKOM", "JMW12") == SwitchgearArchetype.RMU_STANDARD
    assert resolve_switchgear_archetype("RMU SF6", "INDKOM", "") == SwitchgearArchetype.RMU_STANDARD
    assert resolve_switchgear_archetype("RMU SF6", "INDKOM", "UNKNOWN") == SwitchgearArchetype.RMU_STANDARD

    # 7. MRMU -> RMU_STANDARD
    assert resolve_switchgear_archetype("MRMU", "SCHNEIDER", "") == SwitchgearArchetype.RMU_STANDARD
    assert resolve_switchgear_archetype("MRMU SF6", "", "") == SwitchgearArchetype.RMU_STANDARD
    assert resolve_switchgear_archetype("RMU SF6", "MRMU", "") == SwitchgearArchetype.RMU_STANDARD

    # 8. Generic / unrecognized RMU -> RMU_STANDARD
    assert resolve_switchgear_archetype("RMU SF6", "SIEMENS", "8DJH") == SwitchgearArchetype.RMU_STANDARD
    assert resolve_switchgear_archetype("RMU SF6", "ABB", "SafeRing") == SwitchgearArchetype.RMU_STANDARD
    assert resolve_switchgear_archetype("", "", "") == SwitchgearArchetype.RMU_STANDARD


def test_resolve_overview_compartments() -> None:
    """Verify overview compartment views for all archetypes."""
    from src.core.topology import resolve_overview_compartments

    # VCB / GIS -> 3 views
    assert resolve_overview_compartments(SwitchgearArchetype.VCB_CUBICLE) == (
        "OVERVIEW FRONT",
        "OVERVIEW REAR",
        "OVERVIEW TOP",
    )
    assert resolve_overview_compartments(SwitchgearArchetype.GIS_CUBICLE) == (
        "OVERVIEW FRONT",
        "OVERVIEW REAR",
        "OVERVIEW TOP",
    )

    # INDKOM INS24 -> 2 views
    assert resolve_overview_compartments(SwitchgearArchetype.RMU_FUSE_CANISTER) == (
        "OVERVIEW",
        "OVERVIEW TOP",
    )

    # TAMCO & LUCY -> 2 views
    assert resolve_overview_compartments(SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY) == (
        "OVERVIEW",
        "OVERVIEW BOTTOM",
    )

    # RMU OIL -> 2 views
    assert resolve_overview_compartments(SwitchgearArchetype.RMU_OIL) == (
        "OVERVIEW",
        "OVERVIEW BOTTOM",
    )

    # RMU Standard -> 1 view
    assert resolve_overview_compartments(SwitchgearArchetype.RMU_STANDARD) == (
        "OVERVIEW",
    )


def test_classify_bay_role() -> None:
    """Verify unified bay role classification across keywords."""
    from src.core.topology import classify_bay_role

    # 1. Bus Section
    assert classify_bay_role(name="BUS SECTION") == BayRole.BUS_SECTION
    assert classify_bay_role(panel_type="BUS-SECTION") == BayRole.BUS_SECTION
    assert classify_bay_role(name="B/S 1") == BayRole.BUS_SECTION
    assert classify_bay_role(name="BUS SEC 2") == BayRole.BUS_SECTION
    assert classify_bay_role(name="SECTION 1") == BayRole.BUS_SECTION
    assert classify_bay_role(name="SEKSYEN 1") == BayRole.BUS_SECTION
    assert classify_bay_role(name="SEC 1") == BayRole.BUS_SECTION

    # 2. Bus Coupler
    assert classify_bay_role(name="BUS COUPLER") == BayRole.BUS_COUPLER
    assert classify_bay_role(name="BUS-COUPLER") == BayRole.BUS_COUPLER
    assert classify_bay_role(name="BUS TIE") == BayRole.BUS_COUPLER
    assert classify_bay_role(name="BUS-TIE") == BayRole.BUS_COUPLER
    assert classify_bay_role(panel_feeder_no="B/C") == BayRole.BUS_COUPLER
    assert classify_bay_role(name="COUPLER") == BayRole.BUS_COUPLER

    # 3. Transition
    assert classify_bay_role(name="TRANSITION") == BayRole.TRANSITION
    assert classify_bay_role(panel_type="TRANSITION PANEL") == BayRole.TRANSITION
    assert classify_bay_role(name="PERALIHAN") == BayRole.TRANSITION
    assert classify_bay_role(name="TRANSISYEN") == BayRole.TRANSITION
    assert classify_bay_role(name="TOOLS") == BayRole.TRANSITION

    # 4. Transformer
    assert classify_bay_role(name="TX 1") == BayRole.TRANSFORMER
    assert classify_bay_role(panel_feeder_no="TX2") == BayRole.TRANSFORMER
    assert classify_bay_role(name="TRANSFORMER 1") == BayRole.TRANSFORMER
    assert classify_bay_role(name="ALATUBAH 1") == BayRole.TRANSFORMER
    assert classify_bay_role(name="TEE-OFF") == BayRole.TRANSFORMER
    assert classify_bay_role(name="TEE OFF") == BayRole.TRANSFORMER
    assert classify_bay_role(name="1000KVA TX") == BayRole.TRANSFORMER
    assert classify_bay_role(name="TX 500 KVA") == BayRole.TRANSFORMER
    assert classify_bay_role(name="SUIS FIUS 1") == BayRole.TRANSFORMER
    assert classify_bay_role(name="FIUS ALATUBAH") == BayRole.TRANSFORMER

    # 5. Standard feeders (including SPARE, regular line names)
    assert classify_bay_role(name="FEEDER 1") == BayRole.STANDARD
    assert classify_bay_role(name="INCOMING 1") == BayRole.STANDARD
    assert classify_bay_role(name="OUTGOING") == BayRole.STANDARD
    assert classify_bay_role(name="SPARE") == BayRole.STANDARD
    assert classify_bay_role(name="PE KUALA LIPIS") == BayRole.STANDARD
    assert classify_bay_role(name="PUMP HOUSE") == BayRole.STANDARD
    assert classify_bay_role() == BayRole.STANDARD


def test_dynamic_presence_gates() -> None:
    """Verify empirical PT gate and pure photo presence secondary gate."""
    from src.core.topology import eval_pt_gate, eval_secondary_gate

    # PT Gate: requires pt_photo is not None OR has_pt_measurement is True
    assert eval_pt_gate(pt_photo=105) is True
    assert eval_pt_gate(has_pt_measurement=True) is True
    assert eval_pt_gate(pt_photo=105, has_pt_measurement=True) is True
    assert eval_pt_gate(pt_photo=None, has_pt_measurement=False) is False
    assert eval_pt_gate() is False

    # Secondary Gate: requires secondary_photo is not None
    assert eval_secondary_gate(secondary_photo=520) is True
    assert eval_secondary_gate(secondary_photo=None) is False
    assert eval_secondary_gate() is False


def test_resolve_panel_compartments_vcb_and_gis() -> None:
    """Verify VCB and GIS cubicle compartment resolution with dynamic presence gates."""
    from src.core.topology import resolve_panel_compartments

    for arch in (SwitchgearArchetype.VCB_CUBICLE, SwitchgearArchetype.GIS_CUBICLE):
        # Standard bay without PT -> 4 compartments (Breaker, Cable, Busbar, Secondary)
        assert resolve_panel_compartments(
            archetype=arch,
            bay_role=BayRole.STANDARD,
            pt_photo=None,
            has_pt_measurement=False,
        ) == (
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )

        # Standard bay with PT (photo) -> 5 compartments
        assert resolve_panel_compartments(
            archetype=arch,
            bay_role=BayRole.STANDARD,
            pt_photo=104,
            has_pt_measurement=False,
        ) == (
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "PT COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )

        # Standard bay with PT (measurement only) -> 5 compartments
        assert resolve_panel_compartments(
            archetype=arch,
            bay_role=BayRole.STANDARD,
            pt_photo=None,
            has_pt_measurement=True,
        ) == (
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "PT COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )

        # Transformer bay with PT -> 5 compartments
        assert resolve_panel_compartments(
            archetype=arch,
            bay_role=BayRole.TRANSFORMER,
            pt_photo=201,
        ) == (
            "BREAKER COMPARTMENT",
            "CABLE COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "PT COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )

        # Transition bay without secondary photo -> 3 compartments (Front, Rear, Busbar)
        assert resolve_panel_compartments(
            archetype=arch,
            bay_role=BayRole.TRANSITION,
            secondary_photo=None,
        ) == (
            "FRONT COMPARTMENT",
            "REAR COMPARTMENT",
            "BUSBAR COMPARTMENT",
        )

        # Transition bay with secondary photo -> 4 compartments (Front, Rear, Busbar, Secondary)
        assert resolve_panel_compartments(
            archetype=arch,
            bay_role=BayRole.TRANSITION,
            secondary_photo=520,
        ) == (
            "FRONT COMPARTMENT",
            "REAR COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )

        # Transition bays NEVER emit PT compartment even if pt_photo is set
        assert resolve_panel_compartments(
            archetype=arch,
            bay_role=BayRole.TRANSITION,
            secondary_photo=520,
            pt_photo=999,
            has_pt_measurement=True,
        ) == (
            "FRONT COMPARTMENT",
            "REAR COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )

        # Bus Section bay -> always 4 compartments (Breaker, Rear, Busbar, Secondary)
        assert resolve_panel_compartments(
            archetype=arch,
            bay_role=BayRole.BUS_SECTION,
        ) == (
            "BREAKER COMPARTMENT",
            "REAR COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )

        # Bus Coupler bay -> always 4 compartments (Breaker, Rear, Busbar, Secondary)
        assert resolve_panel_compartments(
            archetype=arch,
            bay_role=BayRole.BUS_COUPLER,
        ) == (
            "BREAKER COMPARTMENT",
            "REAR COMPARTMENT",
            "BUSBAR COMPARTMENT",
            "SECONDARY COMPARTMENT",
        )


def test_resolve_panel_compartments_rmu() -> None:
    """Verify RMU compartment blueprints across all RMU archetypes and roles."""
    from src.core.topology import resolve_panel_compartments

    # RMU_DUAL_CABLE_ENTRY (Tamco, all Lucy) -> 2 panels for all roles
    assert resolve_panel_compartments(
        SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY,
        bay_role=BayRole.STANDARD,
    ) == ("CABLE COMPARTMENT", "CABLE ENTRY")
    assert resolve_panel_compartments(
        SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY,
        bay_role=BayRole.TRANSFORMER,
    ) == ("CABLE COMPARTMENT", "CABLE ENTRY")

    # RMU_FUSE_CANISTER (Indkom INS24)
    # Transformer role -> ("FUSE COMPARTMENT",)
    assert resolve_panel_compartments(
        SwitchgearArchetype.RMU_FUSE_CANISTER,
        bay_role=BayRole.TRANSFORMER,
    ) == ("FUSE COMPARTMENT",)
    # Standard role -> ("CABLE COMPARTMENT",)
    assert resolve_panel_compartments(
        SwitchgearArchetype.RMU_FUSE_CANISTER,
        bay_role=BayRole.STANDARD,
    ) == ("CABLE COMPARTMENT",)

    # RMU_OIL -> ("CABLE COMPARTMENT", "CABLE ENTRY")
    assert resolve_panel_compartments(
        SwitchgearArchetype.RMU_OIL,
        bay_role=BayRole.STANDARD,
    ) == ("CABLE COMPARTMENT", "CABLE ENTRY")
    assert resolve_panel_compartments(
        SwitchgearArchetype.RMU_OIL,
        bay_role=BayRole.TRANSFORMER,
    ) == ("CABLE COMPARTMENT", "CABLE ENTRY")

    # RMU_STANDARD (Generic RMU, Indkom JMW12, MRMU) -> ("CABLE COMPARTMENT",)
    assert resolve_panel_compartments(
        SwitchgearArchetype.RMU_STANDARD,
        bay_role=BayRole.STANDARD,
    ) == ("CABLE COMPARTMENT",)
    assert resolve_panel_compartments(
        SwitchgearArchetype.RMU_STANDARD,
        bay_role=BayRole.TRANSFORMER,
    ) == ("CABLE COMPARTMENT",)

    # String coercion for archetype and bay_role
    assert resolve_panel_compartments(
        "RMU_FUSE_CANISTER",
        bay_role="TRANSFORMER",
    ) == ("FUSE COMPARTMENT",)
    assert resolve_panel_compartments(
        "RMU_FUSE_CANISTER",
        bay_role="STANDARD",
    ) == ("CABLE COMPARTMENT",)


def test_switchgear_topology_engine_facade() -> None:
    """Verify SwitchgearTopologyEngine facade methods and unpacking."""
    from src.core.topology import BoardClassification, SwitchgearTopologyEngine

    engine = SwitchgearTopologyEngine()

    # 1. Board classification
    board = engine.classify_board(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        model="GV3",
        rating="11kV 630A",
    )
    assert isinstance(board, BoardClassification)
    assert board.archetype == SwitchgearArchetype.VCB_CUBICLE
    assert board.voltage_class == VoltageClass.KV_11
    assert board.overview_compartments == (
        "OVERVIEW FRONT",
        "OVERVIEW REAR",
        "OVERVIEW TOP",
    )

    # Tuple unpacking support: archetype, voltage_class, overviews
    arch, volt, overviews = board
    assert arch == SwitchgearArchetype.VCB_CUBICLE
    assert volt == VoltageClass.KV_11
    assert len(overviews) == 3

    # Static method call support
    board_static = SwitchgearTopologyEngine.classify_board(
        switchgear_type="RMU SF6",
        manufacturer="INDKOM INS24",
        model="",
        rating="12kV",
    )
    assert board_static.archetype == SwitchgearArchetype.RMU_FUSE_CANISTER
    assert board_static.voltage_class == VoltageClass.KV_11
    assert board_static.overview_compartments == ("OVERVIEW", "OVERVIEW TOP")

    # 2. Panel compartment resolution via facade
    # VCB Standard with PT photo
    vcb_comps = engine.resolve_panel_compartments(
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        bay_role=BayRole.STANDARD,
        pt_photo=301,
    )
    assert vcb_comps == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "PT COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )

    # VCB Transition bay with secondary photo
    trans_comps = engine.resolve_panel_compartments(
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        name="TRANSITION",
        secondary_photo=520,
    )
    assert trans_comps == (
        "FRONT COMPARTMENT",
        "REAR COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )

    # RMU Fuse Canister TX feeder
    rmu_comps = engine.resolve_panel_compartments(
        archetype=SwitchgearArchetype.RMU_FUSE_CANISTER,
        name="TX 1",
    )
    assert rmu_comps == ("FUSE COMPARTMENT",)


def test_topology_engine_with_objects_and_dicts() -> None:
    """Verify engine classification and panel resolution with objects, dicts, and sentinel values."""
    from src.core.topology import (
        SwitchgearArchetype,
        SwitchgearTopologyEngine,
        VoltageClass,
        eval_pt_gate,
        eval_secondary_gate,
    )
    from src.testsheet.models import SwitchgearPanelSpec, SwitchgearSpec

    engine = SwitchgearTopologyEngine()

    # 1. SwitchgearSpec object input to classify_board
    swg = SwitchgearSpec(
        switchgear_type="VCB",
        manufacturer="TAMCO",
        model="GV3",
        rating="11kV",
    )
    board = engine.classify_board(swg=swg)
    assert board.archetype == SwitchgearArchetype.VCB_CUBICLE
    assert board.voltage_class == VoltageClass.KV_11

    # 2. Dict input to classify_board
    swg_dict = {
        "switchgear_type": "RMU SF6",
        "manufacturer": "LUCY ELECTRIC",
        "model": "",
        "rating": "33kV",
    }
    board_dict = engine.classify_board(swg=swg_dict)
    assert board_dict.archetype == SwitchgearArchetype.RMU_DUAL_CABLE_ENTRY
    assert board_dict.voltage_class == VoltageClass.KV_33

    # 3. SwitchgearPanelSpec object input to resolve_panel_compartments
    panel = SwitchgearPanelSpec(
        panel_no=1,
        panel_feeder_no="F01",
        name="FEEDER 1",
        panel_type="VCB",
    )
    # Standard VCB without PT evidence -> 4 compartments
    comps = engine.resolve_panel_compartments(
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        panel=panel,
    )
    assert comps == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )

    # 4. Dict input with dynamic gates
    panel_dict = {
        "name": "FEEDER 2",
        "panel_feeder_no": "F02",
        "pt_photo": 401,
        "secondary_photo": 402,
        "has_pt_measurement": False,
    }
    comps_dict = engine.resolve_panel_compartments(
        archetype=SwitchgearArchetype.VCB_CUBICLE,
        panel=panel_dict,
    )
    assert comps_dict == (
        "BREAKER COMPARTMENT",
        "CABLE COMPARTMENT",
        "BUSBAR COMPARTMENT",
        "PT COMPARTMENT",
        "SECONDARY COMPARTMENT",
    )

    # 5. Sentinel values in gates
    assert eval_pt_gate(pt_photo="-") is False
    assert eval_pt_gate(pt_photo="") is False
    assert eval_pt_gate(pt_photo="None") is False
    assert eval_secondary_gate(secondary_photo="-") is False
    assert eval_secondary_gate(secondary_photo="") is False
    assert eval_secondary_gate(secondary_photo="None") is False


def test_review_feedback_edge_cases() -> None:
    """Verify edge cases flagged in code review."""
    from src.core import eval_pt_gate, eval_secondary_gate
    from src.core.topology import (
        BayRole,
        SwitchgearArchetype,
        VoltageClass,
        classify_bay_role,
        classify_voltage_rating,
        resolve_switchgear_archetype,
    )

    # 1. Module export of gates in src.core
    assert callable(eval_pt_gate)
    assert callable(eval_secondary_gate)

    # 2. Voltage classification false-positive protection (kA vs kV, amperes)
    assert classify_voltage_rating("11kV, 630A, 33kA") == VoltageClass.KV_11
    assert classify_voltage_rating("330A") == VoltageClass.KV_11
    assert classify_voltage_rating("220A") == VoltageClass.KV_11
    assert classify_voltage_rating("33kV") == VoltageClass.KV_33
    assert classify_voltage_rating("22kV") == VoltageClass.KV_22

    # 3. MRMU precedence over Tamco/Lucy fallback
    assert resolve_switchgear_archetype("MRMU", "TAMCO", "") == SwitchgearArchetype.RMU_STANDARD
    assert resolve_switchgear_archetype("RMU SF6", "TAMCO MRMU", "") == SwitchgearArchetype.RMU_STANDARD

    # 4. Transformer keyword field scope: checked on name and panel_feeder_no only, not panel_type
    assert classify_bay_role(name="FEEDER 1", panel_feeder_no="F01", panel_type="TX") == BayRole.STANDARD
    assert classify_bay_role(name="TX 1", panel_feeder_no="F01", panel_type="") == BayRole.TRANSFORMER
    assert classify_bay_role(name="", panel_feeder_no="TX2", panel_type="") == BayRole.TRANSFORMER





