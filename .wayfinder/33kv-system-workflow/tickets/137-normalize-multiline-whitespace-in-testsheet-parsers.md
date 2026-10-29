<!-- status: in-progress -->
# Ticket #137: fix(testsheet): normalize multiline whitespace and control characters in testsheet cell parsers

## Parent
Part of #90 / #92

## What to build
When technicians enter substation equipment names or metadata in Excel testsheets with manual line breaks (e.g. Alt+Enter creating '33kV TRANSITION\n(BUS - SECTION)'), the parser must collapse all internal whitespace sequences containing \r, \n, or \t into single spaces. This prevents raw control characters from entering domain models (such as switchgear panels, transformers, and substation metadata headers) while preserving readable single-line names.

## Acceptance criteria
- [x] Cell string cleaner collapses internal carriage returns, newlines, and tabs (\r\n, \n, \r, \t) into a single space and strips outer padding.
- [x] Switchgear panel names, feeder names, and header metadata parsed from testsheets with multiline cell entries produce clean single-line strings.
- [x] Unit tests verify multiline string normalization across clean_val and switchgear panel extraction without regressions on existing single-line, numeric, or empty cells.

## Blocked by
None (can start immediately).
