Completed At: 2026-07-25T15:16:00+08:00
File Path: `file:///C:/Users/ADAM/Desktop/pahang-cli/.issues/028-photo-retrieval-resizing-and-placeholders.md`

# Photo Retrieval, Aspect Ratio Resizing, and Fallback Placeholders

Labels: wayfinder:research
Parent: [Map: Quick Report Generation for Pahang](file:///.issues/024-quick-report-generation-pahang-map.md)
Blocked-By: [Quick Report Composer Architecture and Template Engine](file:///.issues/025-quick-report-composer-architecture.md)

## Question

How should raw thermal (IR) and digital (DG) photos be extracted from `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM>/RAW DATA/`, bound to `docxtpl.InlineImage` with explicit cell width constraints, re-indexed for OpenXML thermal control identity safety, and handled with "NO IMAGE AVAILABLE" placeholders when missing?

## Answer

1. **Option A Stubbing Architecture**:
   - Establish stem-based matching interface (`Option A`), with photo discovery for DG, IR, US, and TEV isolated behind TODO stubs for a dedicated future map.
2. **DG Photo Handling**:
   - Fall back to `""` (empty string) so DG photos render empty in output files.
3. **IR / US / TEV Stubs**:
   - Provide clean interface stubs with explicit `TODO` markers for IR, US, and TEV file extraction.


