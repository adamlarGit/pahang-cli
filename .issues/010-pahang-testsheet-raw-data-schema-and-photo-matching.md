# Decision Ticket: Pahang Testsheet RAW DATA Schema and Photo Filename Matching

## Question

How should `TestsheetRawData` extract photo ranges from `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM>.xlsx`, and match photos from `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/UNSORTED RAW DATA/`?

## Status

CLOSED (Locked by User)

## Locked Resolution

- **Input Location**: Read testsheet files directly from `TESTSHEET/<STATION_NAME>/<MONTH_FOLDER>/<DD-MM-YYYY>/`.
- **Unsorted Photo Source**: Read raw unsorted photos from `TESTSHEET/<STATION_NAME>/<MONTH_FOLDER>/<DD-MM-YYYY>/UNSORTED RAW DATA/` (`IR/`, `DG/`, `US+TEV/`).
- **PhotoRange Applicability**: `PhotoRange` (numerical start_num and end_num bounds) applies **ONLY to IR and DG** technologies (`FLIR*` for IR, `IMG_*` for DG).
- **US+TEV Structure**: `US` (Ultrasound) and `TEV` (Transient Earth Voltage) raw data use a completely different structure and sorting mechanism, which will be charted and resolved in a dedicated separate Wayfinder session.
- **Pahang Filename Naming**: File stems in Pahang omit the `<DDMMYYYY>` date string and use `<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<DEFECT_SUFFIX>)`.
