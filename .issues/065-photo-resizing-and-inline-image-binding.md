# Ticket 065: Photo Resizing, InlineImage Binding & Fallback Placeholders

## Parent Map

[Map 061: Quick Report Engine Unstubbing & Photo Integration Map](file:///.issues/061-quick-report-engine-unstubbing-map.md)

## Type

`task` (AFK)

## Status

`OPEN`

## Blocked-By

- [Ticket 064: Raw Photo Discovery & Numerical Range Matching (IR, DG, US, TEV)](file:///.issues/064-photo-discovery-and-range-matching.md)

## Question

How should discovered raw photo paths be converted to `docxtpl.InlineImage` instances with precise cell dimensions (e.g. `width=Mm(...)`), preserving aspect ratio across front pages, substation condition pages, and defect detail pages, while safely defaulting missing photos to empty strings or fallback placeholders?
