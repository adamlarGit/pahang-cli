# Photo Retrieval, Aspect Ratio Resizing, and Fallback Placeholders

Labels: wayfinder:research
Parent: [Map: Quick Report Generation for Pahang](file:///.issues/024-quick-report-generation-pahang-map.md)
Blocked-By: [Quick Report Composer Architecture and Template Engine](file:///.issues/025-quick-report-composer-architecture.md)

## Question

How should raw thermal (IR) and digital (DG) photos be extracted from `RAW MATERIAL/<STATION>/<MONTH>/<DD-MM-YYYY>/<PE_NUM>/RAW DATA/`, bound to `docxtpl.InlineImage` with explicit cell width constraints, re-indexed for OpenXML thermal control identity safety, and handled with "NO IMAGE AVAILABLE" placeholders when missing?
