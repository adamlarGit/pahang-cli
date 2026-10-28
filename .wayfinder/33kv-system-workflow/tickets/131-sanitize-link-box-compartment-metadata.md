<!-- status: closed -->
# Ticket #131: feat(full-report): sanitize LINK BOX compartment metadata and voltage grading

## Parent
Part of #101

## What to build
When generating Full Report switchgear panel pages for any panel whose compartment is 'LINK BOX', sanitize the scan page metadata in `swg-panel.docx` so that:
- `Equipment` (swg.type) is displayed as 'LINK BOX' (instead of the switchgear cubicle type such as 'GIS' or 'VCB').
- `Manufacturer`, `Model`, `Area`, `Serial No`, `Heater (A)`, `CB Position`, `Busbar Position`, and `Cable Type` are displayed as dash '-'.
- `Rating` dynamically reflects the system operating voltage ('33kV' for 33kV switchgears, '11kV' for 11kV switchgears) rather than the switchgear design insulation rating (e.g. '36kV').
- `Panel No` (panel.linknumber), `Panel Name` (panel.name), `Load (A)` (panel.loadamp), and thermals (`Spot 1`, `Spot 2`, `Avg`, `Delta T`, `Ambient`) are preserved from the parent panel.
- Ultrasound and TEV measurement blocks remain blanked out.
This rule applies across all 11kV and 33kV Full Report generation workflows.

## Acceptance criteria
- [x] In `src/full_report/scan_adapters.py`, when `comp_name == 'LINK BOX'`, the scan context overrides switchgear and panel fields:
  - `swg.type` = `'LINK BOX'`
  - `swg.manufacturer`, `swg.model`, `panel.area`, `panel.serialnumber`, `panel.serial_no`, `panel.heateramp`, `panel.breakerstatus`, `panel.busbarposition`, `panel.cabletype` = `'-'`
  - `swg.rating` = `'33kV'` (if `self.is_33kv` or voltage class is 33kV) else `'11kV'`
- [x] Parent panel attributes (`panel.linknumber`, `panel.name`, `panel.loadamp`, IR/thermal readings) are preserved without distortion.
- [x] Ultrasound and TEV cells on `swg-panel.docx` continue to be cleanly blanked.
- [x] Unit tests in `tests/` verify the Link Box sanitization context for both 33kV and 11kV switchgear adapters.

## Blocked by
#130
