import pytest
from src.utility_actions import get_utility_actions

def test_utility_actions_registry():
    actions = get_utility_actions()
    assert len(actions) == 14
    
    labels = [a.label for a in actions]
    assert "Create raw material folders" in labels
    assert "Rename files (match names from input dir)" in labels
    assert "Combine PDFs with separator sheet" in labels
    assert "Generate US+TEV survey graphs" in labels
    
    # We won't test the actual execution as it's interactive, just the factory structure
    for action in actions:
        assert callable(action._runner_factory)
