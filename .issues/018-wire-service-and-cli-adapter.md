# Task: Wire WorkflowService and CLI Adapter Integration

Labels: wayfinder:task
Type: task
Status: open
Blocked by: 017

## Question

Connect the new Update QR02 CBA workflow to the existing `WorkflowService` and `UpdateQr02CbaAction` CLI adapter so it's accessible from the interactive menu.

## Specification

### 1. `src/workflows/service.py` — Replace stub

```python
def run_update_qr02_cba(self, environment, request) -> UpdateQr02CbaResult:
    from src.update_qr02_cba_workflow import run_update_qr02_cba
    return run_update_qr02_cba(environment, request)
```

### 2. `src/workflows/models.py` — Verify request/result models

Ensure `UpdateQr02CbaRequest` and `UpdateQr02CbaResult` have:
- `target_package_names: tuple[str, ...]` — folder filter
- `progress_sink` — callback
- `records_updated: int` — result count
- `master_path: Path` — output ENGR path (may need to become a list since multiple ENGR files can be updated)

### 3. `src/project_workflow_actions.py` — Adapt `UpdateQr02CbaAction`

Update the CLI adapter to use Pahang's 3-tier folder selection (`select_pahang_date_folder`) instead of flat folder listing. The Auto/All/Select mode selector is already implemented.

### 4. Update `CONTEXT.md`

Add new domain terms if any emerged (e.g., `Qr02Repository`, `ENGR Station Code`).
