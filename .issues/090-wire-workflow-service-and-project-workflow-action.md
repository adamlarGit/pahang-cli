# Ticket 090: Wire WorkflowService Seam & Project Workflow Action #1

Labels: wayfinder:task
Parent: [Map 086: Generate TESTSHEET Folder Structure Workflow Map](file:///.issues/086-generate-testsheet-folder-structure-map.md)
Status: Completed

## Question

How should the new `GenerateTestsheetFolderStructureWorkflow` be exposed through `WorkflowService` and registered as Action #1 in `PROJECT_WORKFLOW_ACTIONS` within `src/project_workflow_actions.py`?

## Resolution / Agreed Architecture

1. **WorkflowService Seam (`src/workflows/service.py`)**:
   - Add method:
     ```python
     def run_generate_testsheet_folder(
         self,
         environment: ProjectEnvironment,
         request: GenerateTestsheetFolderRequest,
     ) -> GenerateTestsheetFolderResult:
         from src.workflows.generate_testsheet_folder import GenerateTestsheetFolderStructureWorkflow
         return GenerateTestsheetFolderStructureWorkflow().execute(environment, request)
     ```

2. **Project Workflow Action (`src/project_workflow_actions.py`)**:
   - Implement `GenerateTestsheetFolderAction(ProjectWorkflowAction)`:
     - Prompts station via `select_or_create_testsheet_station(environment)`.
     - Prompts month via `select_or_create_testsheet_month(environment, station)`.
     - Prompts dates via `prompt_target_inspection_dates()`.
     - Calls `service.run_generate_testsheet_folder(environment, request)`.
     - Prints minimal single-line summary:
       `print(f"Successfully generated folder structure for {result.station} / {result.month} ({result.total_dates_processed} date{'s' if result.total_dates_processed != 1 else ''}).")`

3. **Menu Registration**:
   - Register `GenerateTestsheetFolderAction("Generate TESTSHEET Folder Structure")` as the **first entry (1)** in `PROJECT_WORKFLOW_ACTIONS`.
