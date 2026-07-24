# Decision Ticket: Substation Folder Naming, Defect Suffixes, and Pipeline Renaming

## Question

How should substation folder names, technology defect suffixes (`(IR+US+TEV+VI)`), and file renaming be sequenced across Raw Material Creation, Quick Report Generation, and Post-Processing Pipeline stages in Pahang CLI?

## Status

CLOSED (Locked by User)

## Locked Resolution

1. **Pahang Naming Stem Format**:
   - Omits the 8-digit date string `<DDMMYYYY>` from document, testsheet, and folder names.
   - **Pahang Document & Folder Stem**: `<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<DEFECT_SUFFIX>)`
     - *With Defects*: `002. RM CHEROH (IR+US+VI)` or `003. BUKIT KAJANG (IR+VI)`
     - *Without Defects*: `005. KUALA SEMANTAN`

2. **Initial Raw Material Stage (Simple PE Folders)**:
   - User places testsheets and unsorted photos in `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/`.
   - `pahang-cli` creates simple numerical PE folders:
     `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM>/RAW DATA/` (e.g. `001/`, `002/`).
   - Photos (`IR` & `DG`) are sorted into these numerical PE directories based on `TestsheetExtractor` `PhotoRange` bounds.

3. **Quick Report Generation Stage**:
   - Queries ENGR master sheets (`QR03 VI` & `QR03 CBA` in `ENGR-750-39-CBA-PAHANG-2026.xlsx`) for defect indicators.
   - Generates Quick Report Word documents using Pahang stem format:
     `QUICK REPORT/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM_3DIGITS>. <SUBSTATION_NAME> (<DEFECT_SUFFIX>).docx`

4. **Post-Processing Pipeline Renaming Stage**:
   - `rename_files_workflow` reads the authoritative Quick Report `.docx` stems and matches them by numerical PE prefix to:
     1. Rename `TESTSHEET/<STATION>/<MONTH>/<DD-MM-YYYY>/002.xlsx` -> `002. RM CHEROH (IR+US+VI).xlsx`
     2. Rename `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/002/` -> `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/002. RM CHEROH (IR+US+VI)/`
