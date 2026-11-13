---
ticket: 235
type: research
map: 221
status: open
updated: 2026-11-13
agent: Claude Code, claude-opus-5-5
---
# Can the IR table values be read from a saved FLIR image without Word?

## Verdict

Not yet written. This ticket has two Paths, and the answer is written from their Path files once both are landed, by the agent the owner names (`docs/agents/research-and-prototypes.md` step 7).

| Path | File | Question |
|------|------|----------|
| file-read | [`path-file-read.md`](path-file-read.md) | Can the four values be read or computed from the image file itself, with no FLIR software? |
| atlas-sdk | [`path-atlas-sdk.md`](path-atlas-sdk.md) | Can the four values be read by FLIR's Atlas SDK from the saved image, and do they match the values Word shows? |

## Change log

- 2026-11-13: the single-Path write-up moved to `path-file-read.md` when the owner reinstated the `atlas-sdk` Path. Its history is in that file's Change log.
