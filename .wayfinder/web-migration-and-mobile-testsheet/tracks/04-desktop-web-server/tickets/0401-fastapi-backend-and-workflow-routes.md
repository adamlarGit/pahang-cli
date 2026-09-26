<!-- status: open -->
Part of Track 4: .wayfinder/web-migration-and-mobile-testsheet/tracks/04-desktop-web-server/map.md

# 0401: feat(web): fastapi server & workflow api routes

**What to build:**
The core local HTTP backend in `src/web/app.py`:
- Project routes: get active project metadata, switch project, update configuration (camera, PRPD mode).
- Directory routes: list stations, months, and inspection dates from `WorkspaceStorage`.
- Workflow execution routes: endpoints for `generate_testsheets`, `quick_report`, `full_report`, `update_qr02`, and `whatsapp_report`.

**Blocked by:** None (Frontier)

**Status:** Open

## Acceptance Criteria
- [ ] Implement FastAPI application in `src/web/app.py`.
- [ ] Map request schemas from `src/workflows/models.py` to Pydantic models.
- [ ] Connect workflow execution endpoints to `WorkflowService`.
- [ ] Add unit tests in `tests/web/test_api_routes.py` verifying status codes and response schemas.
