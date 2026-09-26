<!-- status: open -->
Part of Track 4: .wayfinder/web-migration-and-mobile-testsheet/tracks/04-desktop-web-server/map.md

# 0403: feat(web): colleague desktop launcher batch script

**What to build:**
A zero-friction desktop launch script `start_webapp.bat` for colleagues running Windows laptops:
1. Detects or creates the local Python virtual environment (`.venv`).
2. Checks for updated dependencies from `pyproject.toml`.
3. Starts the Uvicorn web server in the background.
4. Opens the default browser to `http://127.0.0.1:8000`.
5. Gracefully terminates the server when the user closes the command prompt window.

**Blocked by:** 0401, 0402

**Status:** Open

## Acceptance Criteria
- [ ] Create `start_webapp.bat` in the repository root.
- [ ] Ensure non-interactive execution (never halts on prompts unless an error occurs).
- [ ] Automatically launch system browser once Uvicorn health check endpoint reports ready.
- [ ] Test on Windows Command Prompt and PowerShell.
