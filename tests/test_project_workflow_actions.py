
from unittest.mock import MagicMock, patch
from pathlib import Path
from src.project_workflow_actions import QuickReportAction

def test_quick_report_action_browse_dates_multi():
    env = MagicMock()
    action = QuickReportAction("Test Action")
    
    mock_workflow = MagicMock()
    
    with patch("src.project_workflow_actions.cli_selectors.select_one", return_value="browse_dates"), \
         patch("src.project_workflow_actions.cli_selectors.select_pahang_inspection_dates_interactive", return_value=(Path("01-09-2026"), Path("02-09-2026"))), \
         patch("src.project_workflow_actions.QuickReportWorkflow", return_value=mock_workflow):
         
         mock_inspection = MagicMock()
         mock_inspection.missing_templates = []
         mock_inspection.errors = []
         mock_inspection.targets = [MagicMock(station="ROMPIN"), MagicMock(station="KUANTAN")]
         mock_workflow.inspect.return_value = mock_inspection
         
         with patch("src.project_workflow_actions.cli_selectors.select_multiple", return_value=["ROMPIN", "KUANTAN"]):
             action.execute(env)
             
         mock_workflow.generate.assert_called_once()
         args, kwargs = mock_workflow.generate.call_args
         assert args[0] == (Path("01-09-2026"), Path("02-09-2026"))
         assert args[1] == env
         assert kwargs["station"] == ["ROMPIN", "KUANTAN"]

def test_quick_report_action_enter_dates_multi():
    env = MagicMock()
    action = QuickReportAction("Test Action")
    
    mock_workflow = MagicMock()
    
    with patch("src.project_workflow_actions.cli_selectors.select_one", return_value="enter_dates"), \
         patch("src.project_workflow_actions.cli_selectors.prompt_target_inspection_dates_with_ranges", return_value=(Path("01-09-2026"),)), \
         patch("src.project_workflow_actions.QuickReportWorkflow", return_value=mock_workflow):
         
         mock_inspection = MagicMock()
         mock_inspection.missing_templates = []
         mock_inspection.errors = []
         mock_inspection.targets = [MagicMock(station="ROMPIN")]
         mock_workflow.inspect.return_value = mock_inspection
         
         action.execute(env)
             
         mock_workflow.generate.assert_called_once()
         args, kwargs = mock_workflow.generate.call_args
         assert args[0] == (Path("01-09-2026"),)
         assert args[1] == env
         assert "station" not in kwargs or kwargs["station"] is None

from src.project_workflow_actions import generate_full_reports_action

def test_generate_full_reports_action_multi_date_prefix():
    env = MagicMock()
    mock_workflow = MagicMock()
    
    with patch("src.project_workflow_actions.cli_selectors.select_one", return_value="browse_dates"), \
         patch("src.project_workflow_actions.cli_selectors.select_pahang_inspection_dates_interactive", return_value=(Path("01-09-2026"), Path("02-09-2026"))):
         
         mock_inspection = MagicMock()
         mock_inspection.total_count = 2
         mock_inspection.missing_templates = []
         mock_inspection.errors = []
         
         item1 = MagicMock(substation_name="PE 1", is_ready=True, date_str="01-09-2026")
         item2 = MagicMock(substation_name="PE 2", is_ready=False, date_str="02-09-2026")
         mock_inspection.targets = [item1, item2]
         
         mock_workflow.inspect.return_value = mock_inspection
         
         with patch("src.project_workflow_actions.cli_selectors.select_substations_interactive", return_value=[item1, item2]) as mock_select:
             generate_full_reports_action(env, workflow=mock_workflow)
             
         mock_select.assert_called_once()
         args, kwargs = mock_select.call_args
         get_title = kwargs["get_title"]
         
         assert get_title(item1) == "[01-09-2026] PE 1 [READY]"
         assert get_title(item2) == "[02-09-2026] PE 2 [NOT READY]"
