"""Comprehensive test suite for src/core/contract.py deep module (ContractScope).

Covers:
1. ContractScope value object construction, defaults, immutability, and container protocols.
2. Universal factory ContractScope.from_source() permutations:
   - None & empty dicts (defaulting to standard 3-technology contract).
   - Dicts with flat technology keys ('technologies', 'project_technologies', 'contract').
   - Dicts with nested metadata/project keys.
   - Objects with .technologies, .contract, or .metadata.
   - String expressions with composite delimiters ('+', ',', '/').
   - U/S alias protection against token fracturing.
   - Negative sentinels ('-', 'NONE', 'NORMAL', 'N/A', 'TIADA') standalone and mixed.
3. Switchgear two-tier eligibility methods on ContractScope:
   - is_swg_tev_active(compartment)
   - is_swg_us_active(compartment)
4. Functional backward-compatible wrappers and domain normalizers.
5. Re-exports in src.core and integration on ProjectEnvironment.contract.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
import pytest

from src.core import ContractScope as CoreContractScope
from src.core.contract import (
    ContractScope,
    DEFAULT_AWARDED_TECHNOLOGIES,
    is_swg_tev_active,
    is_swg_us_active,
    is_tev_contract_awarded,
    is_us_contract_awarded,
    normalize_swg_compartment,
)
from src.project.models import ProjectMetadata
from src.project.environment import ProjectEnvironment
from src.project.storage import LocalWorkspaceStorage


class TestContractScopeCore:
    """Test ContractScope dataclass core behavior, properties, and immutability."""

    def test_default_construction_awards_all_three_technologies(self):
        scope = ContractScope()
        assert scope.has_ir is True
        assert scope.has_us is True
        assert scope.has_tev is True
        assert scope.awarded_technologies == DEFAULT_AWARDED_TECHNOLOGIES
        assert scope.technologies == DEFAULT_AWARDED_TECHNOLOGIES

    def test_frozen_immutability(self):
        scope = ContractScope(["IR", "US"])
        with pytest.raises(FrozenInstanceError):
            scope._technologies = frozenset({"TEV"})  # type: ignore

    def test_equality_and_hashing(self):
        scope1 = ContractScope(["IR", "US"])
        scope2 = ContractScope({"US", "IR"})
        scope3 = ContractScope(["IR", "TEV"])

        assert scope1 == scope2
        assert hash(scope1) == hash(scope2)
        assert scope1 != scope3

    def test_container_protocol(self):
        scope = ContractScope(["IR", "US"])
        assert "IR" in scope
        assert "ir" in scope
        assert "US" in scope
        assert "u/s" in scope
        assert "TEV" not in scope
        assert len(scope) == 2
        assert set(iter(scope)) == {"IR", "US"}
        assert bool(scope) is True

        empty_scope = ContractScope(frozenset())
        assert bool(empty_scope) is False
        assert len(empty_scope) == 0

    def test_repr_string(self):
        scope = ContractScope(["TEV", "IR"])
        assert repr(scope) == "ContractScope(['IR', 'TEV'])"

    def test_is_awarded_with_synonyms(self):
        scope = ContractScope(["IR", "US"])
        assert scope.is_awarded("IR") is True
        assert scope.is_awarded("infrared") is True
        assert scope.is_awarded("thermal") is True
        assert scope.is_awarded("US") is True
        assert scope.is_awarded("ultrasound") is True
        assert scope.is_awarded("U/S") is True
        assert scope.is_awarded("u / s") is True
        assert scope.is_awarded("TEV") is False
        assert scope.is_awarded("transient") is False
        assert scope.is_awarded("") is False
        assert scope.is_awarded("-") is False


class TestContractScopeFromSource:
    """Test universal factory ContractScope.from_source() permutations."""

    def test_from_none_source_defaults_to_standard_contract(self):
        scope = ContractScope.from_source(None)
        assert scope.has_ir is True
        assert scope.has_us is True
        assert scope.has_tev is True
        assert scope.awarded_technologies == frozenset({"IR", "US", "TEV"})

    def test_from_contract_scope_instance_passthrough(self):
        orig = ContractScope(["IR", "US"])
        resolved = ContractScope.from_source(orig)
        assert resolved is orig

    def test_from_empty_dict_defaults_to_standard_contract(self):
        scope = ContractScope.from_source({})
        assert scope.has_ir is True
        assert scope.has_us is True
        assert scope.has_tev is True

    def test_from_dict_with_contract_scope(self):
        custom = ContractScope(["TEV"])
        scope = ContractScope.from_source({"contract": custom})
        assert scope is custom

    def test_from_dict_with_technologies_list(self):
        scope = ContractScope.from_source({"technologies": ["IR", "US"]})
        assert scope.has_ir is True
        assert scope.has_us is True
        assert scope.has_tev is False

    def test_from_dict_with_project_technologies_string(self):
        scope = ContractScope.from_source({"project_technologies": "IR+TEV"})
        assert scope.has_ir is True
        assert scope.has_us is False
        assert scope.has_tev is True

    def test_from_dict_with_nested_project_dict(self):
        data = {
            "substation": "PPU BENTONG",
            "project": {"technologies": ["US"]},
        }
        scope = ContractScope.from_source(data)
        assert scope.has_ir is False
        assert scope.has_us is True
        assert scope.has_tev is False

    def test_from_dict_with_nested_metadata_object(self):
        meta = SimpleNamespace(technologies=["IR", "US", "TEV"])
        data = {"metadata": meta}
        scope = ContractScope.from_source(data)
        assert scope.has_ir is True
        assert scope.has_us is True
        assert scope.has_tev is True

    def test_from_dict_with_nested_contract_scope(self):
        inner_contract = ContractScope(["IR"])
        data = {"project": {"contract": inner_contract}}
        scope = ContractScope.from_source(data)
        assert scope is inner_contract

    def test_from_object_with_technologies(self):
        obj = SimpleNamespace(technologies=["TEV"])
        scope = ContractScope.from_source(obj)
        assert scope.has_ir is False
        assert scope.has_us is False
        assert scope.has_tev is True

    def test_from_object_with_contract_scope(self):
        custom = ContractScope(["IR", "US"])
        obj = SimpleNamespace(contract=custom)
        scope = ContractScope.from_source(obj)
        assert scope is custom

    def test_from_string_delimiters(self):
        s1 = ContractScope.from_source("IR+US+TEV")
        assert s1.awarded_technologies == frozenset({"IR", "US", "TEV"})

        s2 = ContractScope.from_source("IR, US")
        assert s2.awarded_technologies == frozenset({"IR", "US"})

        s3 = ContractScope.from_source("IR/TEV")
        assert s3.awarded_technologies == frozenset({"IR", "TEV"})

        s4 = ContractScope.from_source("U/S")
        assert s4.awarded_technologies == frozenset({"US"})

        s5 = ContractScope.from_source("IR/U/S")
        assert s5.awarded_technologies == frozenset({"IR", "US"})

    def test_from_negative_sentinels_standalone(self):
        sentinels = ["-", "--", "NONE", "NORMAL", "HEALTHY", "NO DEFECT", "N/A", "NA", "NIL", "EMPTY", "FALSE", "0", "TIADA", ""]
        for sentinel in sentinels:
            scope = ContractScope.from_source(sentinel)
            assert scope.has_ir is False
            assert scope.has_us is False
            assert scope.has_tev is False
            assert scope.awarded_technologies == frozenset()

    def test_from_negative_sentinels_sequence(self):
        scope = ContractScope.from_source(["-", "NONE", "NORMAL"])
        assert scope.has_ir is False
        assert scope.has_us is False
        assert scope.has_tev is False
        assert scope.awarded_technologies == frozenset()

    def test_from_mixed_negative_sentinels_and_technologies(self):
        scope1 = ContractScope.from_source("IR, -")
        assert scope1.awarded_technologies == frozenset({"IR"})

        scope2 = ContractScope.from_source("NONE+US")
        assert scope2.awarded_technologies == frozenset({"US"})

        scope3 = ContractScope.from_source(["N/A", "TEV", "NORMAL"])
        assert scope3.awarded_technologies == frozenset({"TEV"})

    def test_from_unconfigured_mock_defaults_to_standard_contract(self):
        from unittest.mock import MagicMock
        mock_obj = MagicMock()
        scope = ContractScope.from_source(mock_obj)
        assert scope.awarded_technologies == frozenset({"IR", "US", "TEV"})

    def test_from_mock_spec_project_environment(self):
        from unittest.mock import MagicMock
        mock_env = MagicMock(spec=ProjectEnvironment)
        scope = ContractScope.from_source(mock_env)
        assert scope.awarded_technologies == frozenset({"IR", "US", "TEV"})

    def test_from_mock_with_configured_technologies(self):
        from unittest.mock import MagicMock
        mock_env = MagicMock(spec=ProjectEnvironment)
        mock_env.technologies = ["IR", "US"]
        scope = ContractScope.from_source(mock_env)
        assert scope.awarded_technologies == frozenset({"IR", "US"})

    def test_from_mock_with_configured_contract(self):
        from unittest.mock import MagicMock
        mock_env = MagicMock(spec=ProjectEnvironment)
        mock_env.contract = ContractScope(["TEV"])
        scope = ContractScope.from_source(mock_env)
        assert scope.awarded_technologies == frozenset({"TEV"})


class TestSwitchgearEligibilityMethods:
    """Test is_swg_tev_active and is_swg_us_active on ContractScope."""

    def test_swg_tev_active_full_contract(self):
        scope = ContractScope(["IR", "US", "TEV"])
        # TEV-Eligible compartments
        assert scope.is_swg_tev_active("BREAKER COMPARTMENT") is True
        assert scope.is_swg_tev_active("VCB") is True
        assert scope.is_swg_tev_active("CABLE COMPARTMENT") is True
        assert scope.is_swg_tev_active("PT COMPARTMENT") is True
        assert scope.is_swg_tev_active("FUSE COMPARTMENT") is True

        # Blanked compartments
        assert scope.is_swg_tev_active("CABLE ENTRY") is False
        assert scope.is_swg_tev_active("BUSBAR COMPARTMENT") is False
        assert scope.is_swg_tev_active("SECONDARY COMPARTMENT") is False
        assert scope.is_swg_tev_active("LINK BOX") is False
        assert scope.is_swg_tev_active("") is False
        assert scope.is_swg_tev_active(None) is False

    def test_swg_tev_inactive_when_contract_lacks_tev(self):
        scope = ContractScope(["IR", "US"])
        # Even eligible compartments are inactive
        assert scope.is_swg_tev_active("BREAKER COMPARTMENT") is False
        assert scope.is_swg_tev_active("CABLE COMPARTMENT") is False
        assert scope.is_swg_tev_active("PT COMPARTMENT") is False
        assert scope.is_swg_tev_active("FUSE COMPARTMENT") is False

    def test_swg_us_active_full_contract(self):
        scope = ContractScope(["IR", "US", "TEV"])
        # US-Eligible compartments (all standard compartments)
        assert scope.is_swg_us_active("BREAKER COMPARTMENT") is True
        assert scope.is_swg_us_active("CABLE COMPARTMENT") is True
        assert scope.is_swg_us_active("PT COMPARTMENT") is True
        assert scope.is_swg_us_active("FUSE COMPARTMENT") is True
        assert scope.is_swg_us_active("CABLE ENTRY") is True
        assert scope.is_swg_us_active("BUSBAR COMPARTMENT") is True

        # US-Excluded compartments
        assert scope.is_swg_us_active("SECONDARY COMPARTMENT") is False
        assert scope.is_swg_us_active("Secondary") is False
        assert scope.is_swg_us_active("Control Compartment") is False
        assert scope.is_swg_us_active("LINK BOX") is False
        assert scope.is_swg_us_active("Link Box") is False
        assert scope.is_swg_us_active("Cable Link Box") is False
        assert scope.is_swg_us_active("") is False
        assert scope.is_swg_us_active(None) is False

    def test_swg_us_inactive_when_contract_lacks_us(self):
        scope = ContractScope(["IR", "TEV"])
        # Even eligible compartments are inactive
        assert scope.is_swg_us_active("BREAKER COMPARTMENT") is False
        assert scope.is_swg_us_active("CABLE COMPARTMENT") is False
        assert scope.is_swg_us_active("CABLE ENTRY") is False
        assert scope.is_swg_us_active("BUSBAR COMPARTMENT") is False


class TestFunctionalBackwardCompatibility:
    """Verify that standalone module-level functions in src.core.contract maintain backward compatibility."""

    def test_is_tev_contract_awarded(self):
        assert is_tev_contract_awarded(None) is True
        assert is_tev_contract_awarded([]) is True
        assert is_tev_contract_awarded(["IR", "US", "TEV"]) is True
        assert is_tev_contract_awarded(["TEV"]) is True
        assert is_tev_contract_awarded(["IR", "US"]) is False
        assert is_tev_contract_awarded(["IR"]) is False

    def test_is_us_contract_awarded(self):
        assert is_us_contract_awarded(None) is True
        assert is_us_contract_awarded([]) is True
        assert is_us_contract_awarded(["IR", "US", "TEV"]) is True
        assert is_us_contract_awarded(["US"]) is True
        assert is_us_contract_awarded(["IR", "TEV"]) is False
        assert is_us_contract_awarded(["IR"]) is False

    def test_is_swg_tev_active(self):
        assert is_swg_tev_active(["IR", "TEV"], "Breaker Compartment") is True
        assert is_swg_tev_active(["IR", "TEV"], "Cable Entry") is False
        assert is_swg_tev_active(["IR"], "Breaker Compartment") is False

    def test_is_swg_us_active(self):
        assert is_swg_us_active(["IR", "US"], "Cable Entry") is True
        assert is_swg_us_active(["IR", "US"], "Secondary Compartment") is False
        assert is_swg_us_active(["IR"], "Cable Entry") is False

    def test_normalize_swg_compartment_precedences(self):
        assert normalize_swg_compartment("Cable Link Box") == "LINK BOX"
        assert normalize_swg_compartment("LINKBOX") == "LINK BOX"
        assert normalize_swg_compartment("Cable Entry") == "CABLE ENTRY"
        assert normalize_swg_compartment("VCB") == "BREAKER COMPARTMENT"
        assert normalize_swg_compartment("Secondary") == "SECONDARY COMPARTMENT"
        assert normalize_swg_compartment("Control") == "SECONDARY COMPARTMENT"
        assert normalize_swg_compartment("Busbar") == "BUSBAR COMPARTMENT"
        assert normalize_swg_compartment("Cable Box") == "CABLE COMPARTMENT"


class TestCoreAndEnvironmentIntegration:
    """Verify re-export in src.core and integration on ProjectEnvironment."""

    def test_core_reexport(self):
        assert CoreContractScope is ContractScope

    def test_project_environment_contract_property(self, tmp_path):
        meta = ProjectMetadata(
            key="test_env",
            name="Test Substation",
            base_path=str(tmp_path),
            state="pahang",
            po_number="PO123",
            voltage_type="11kV",
            year="2026",
            cycle="Cycle 1",
            technologies=("IR", "US"),
        )
        storage = LocalWorkspaceStorage(tmp_path)
        env = ProjectEnvironment(metadata=meta, storage=storage)

        contract = env.contract
        assert isinstance(contract, ContractScope)
        assert contract.has_ir is True
        assert contract.has_us is True
        assert contract.has_tev is False
        assert env.get_cbm_defect_folder_name() == "DEFECT IR US"


class TestRobustnessAndEdgeCases:
    """Rigorous tests probing edge cases, non-iterables, and dictionary precedence."""

    def test_dict_empty_sequence_project_technologies(self):
        scope = ContractScope.from_source({"project_technologies": []})
        assert scope.awarded_technologies == frozenset()
        assert scope.has_ir is False

    def test_nested_dict_empty_sequence_project_technologies(self):
        scope = ContractScope.from_source({"project": {"project_technologies": []}})
        assert scope.awarded_technologies == frozenset()
        assert scope.has_ir is False

    def test_simplenamespace_with_project_technologies(self):
        obj = SimpleNamespace(project_technologies=["IR", "US"])
        scope = ContractScope.from_source(obj)
        assert scope.awarded_technologies == frozenset({"IR", "US"})
        assert scope.has_ir is True
        assert scope.has_us is True
        assert scope.has_tev is False

    def test_simplenamespace_with_callable_technologies(self):
        obj = SimpleNamespace(technologies=lambda: ["US"])
        scope = ContractScope.from_source(obj)
        assert scope.awarded_technologies == frozenset({"US"})

    def test_arbitrary_object_defaults_without_type_error(self):
        obj = SimpleNamespace(foo="bar", count=42)
        scope = ContractScope.from_source(obj)
        assert scope.awarded_technologies == DEFAULT_AWARDED_TECHNOLOGIES

        plain_obj = object()
        scope_plain = ContractScope.from_source(plain_obj)
        assert scope_plain.awarded_technologies == DEFAULT_AWARDED_TECHNOLOGIES

    def test_non_iterable_inputs_handled_safely(self):
        # 0 and False are negative sentinels
        scope_zero = ContractScope.from_source(0)
        assert scope_zero.awarded_technologies == frozenset()

        scope_false = ContractScope.from_source(False)
        assert scope_false.awarded_technologies == frozenset()

        # Non-sentinel arbitrary numbers are normalized as strings
        scope_num = ContractScope.from_source(123)
        assert scope_num.awarded_technologies == frozenset({"123"})
        assert scope_num.has_ir is False
        assert scope_num.has_us is False
        assert scope_num.has_tev is False

    def test_lowercase_frozenset_normalization(self):
        scope = ContractScope(frozenset(["ir", "us"]))
        assert scope.has_ir is True
        assert scope.has_us is True
        assert scope.awarded_technologies == frozenset({"IR", "US"})

    def test_is_awarded_none_safety(self):
        scope = ContractScope(["IR", "US"])
        assert scope.is_awarded(None) is False
        assert None not in scope

    def test_functional_wrappers_with_contract_scope_instances(self):
        empty_scope = ContractScope([])
        assert is_tev_contract_awarded(empty_scope) is False
        assert is_us_contract_awarded(empty_scope) is False
        assert is_swg_tev_active(empty_scope, "Breaker Compartment") is False
        assert is_swg_us_active(empty_scope, "Cable Entry") is False

        tev_scope = ContractScope(["IR", "TEV"])
        assert is_tev_contract_awarded(tev_scope) is True
        assert is_us_contract_awarded(tev_scope) is False
        assert is_swg_tev_active(tev_scope, "Breaker Compartment") is True
        assert is_swg_us_active(tev_scope, "Cable Entry") is False

    def test_scan_adapters_contract_initialization(self):
        from src.full_report.scan_adapters import SwitchgearScanAdapter, TransformerScanAdapter
        from src.testsheet.models import SwitchgearSpec, TransformerSpec

        swg_spec = SwitchgearSpec(switchgear_type="VCB")
        swg_adapter = SwitchgearScanAdapter(
            swg=swg_spec,
            substation_info={"name_site": "TEST SITE"},
            project_technologies=["IR", "US"],
        )
        assert swg_adapter.contract.has_tev is False
        assert swg_adapter.contract.has_us is True
        assert swg_adapter.project_technologies == frozenset({"IR", "US"})

        tx_spec = TransformerSpec(tx_id="TX 1")
        tx_adapter = TransformerScanAdapter(
            tx=tx_spec,
            substation_info={"technologies": ["IR", "TEV"]},
        )
        assert tx_adapter.contract.has_us is False
        assert tx_adapter.contract.has_tev is True
        assert tx_adapter.project_technologies == frozenset({"IR", "TEV"})

