<!-- status: open -->
Part of Track 3: .wayfinder/web-migration-and-mobile-testsheet/tracks/03-mobile-offline-pwa/map.md

# 0302: feat(pwa): mobile inspection form wizard

**What to build:**
A responsive, touch-friendly multi-step form wizard tailored for on-site inspection data entry on smartphones:
- Step 1: Substation Info (Station dropdown, PE number, Substation name, Date picker, PO number, Voltage).
- Step 2: Switchgear Panels (Add/remove panels, panel name, breaker serial, contact resistance, insulation resistance, UltraTEV values).
- Step 3: Transformer & Feeder Pillar (TX rating, serial, oil/winding temp, FP status).
- Step 4: Visual Inspection Checklist (Categorized Pass/Fail/NA toggle buttons, remarks).
- Step 5: Defects & Summary (Logged defects, severity rating, tester name).

**Blocked by:** 0301

**Status:** Open

## Acceptance Criteria
- [ ] Build multi-step wizard UI with clear step progress indicator.
- [ ] Implement Project Profile screen establishing session defaults (PO number, voltage type, tester name, TNB rep, default station) to eliminate repetitive typing (`D-MASTER.20`).
- [ ] Provide quick per-substation dropdown override for Station to support multi-station inspection days (`D-MASTER.20`).
- [ ] Implement autosave to SQLite OPFS on every field change so no inputs are lost.
- [ ] Capture thermal (`IR`) and digital (`DG`) photo index ranges (`D-MASTER.14`).
- [ ] Support dynamic panel rows for switchgear configurations (VCB / RMU).
- [ ] Quick-select toggles for visual checklist (Pass by default to minimize repetitive taps).
- [ ] Form validation before marking inspection as completed.
