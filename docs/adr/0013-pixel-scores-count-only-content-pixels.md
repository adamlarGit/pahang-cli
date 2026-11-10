# 13. Pixel Scores Count Only the Pixels That Carry Content

Date: 2026-11-10
Status: Accepted (2026-11-10, after measuring Sentosa, Talapia, 094 and APMM Part 32)
Adds to: [ADR 0009](./0009-native-export-with-source-image-restoration.md) and [ADR 0012](./0012-pictures-are-tagged-in-the-export-copy.md). Replaces the whole-image percentage rule that ADR 0012 loosened to 1.0%.

## Decision

A pixel comparison now scores the share of **content pixels** that differ strongly. A content pixel is one darker than grey level 245 in either image; the white paper around it is not counted. "Differ strongly" is unchanged (grey difference of 48 or more). The score is used everywhere the whole-image percentage was: accepting the best candidate, dismissing a runner-up, comparing two candidates with each other, and the pre-write self-check.

| Rule | Threshold |
| --- | --- |
| Accept the best candidate | 0.5% of content pixels or less (unchanged number) |
| Dismiss a runner-up as a different picture | at least 1.0% and at least 5x the best (unchanged numbers) |
| Two candidates within 0.5% of each other | ambiguous, Word's copy is kept (ADR 0009) |

The numbers stay; what changed is what they are a percentage of. Pixels stay the final gate behind a stamp (ADR 0012). The owner prefers identity evidence over pixel rules, so this does not tighten anything: it replaces a measure that gets thinner with a measure that does not.

## Measurements

Native Word exports of the four proof reports (334 images, 324 true matches judged by their picture stamps, 2026-11-10). Whole-image is the old score, content is the new one.

| | Whole-image | Content |
| --- | ---: | ---: |
| True matches, worst | 0.092% | 0.092% |
| Sentosa US/TEV panels (629x199), nearest twin | 1.35-1.50% | 10.9-11.9% |
| 094 US/TEV panels, nearest twin | 2.57-3.0% | 14.6-17% |
| APMM Part 32 US panels (733x232, 629x199), nearest twin | 0.185-0.19% | 1.0-1.12% |
| APMM Part 32 colour sliver (13x171), nearest different bar | 0.58-3.5% | 0.58-3.5% (the sliver is all content, so the two scores agree) |
| Sentosa PRPD graphs (753x566 vs 701x525), nearest | 0.21-0.29% | 0.20-0.27% |

True matches never exceed 0.092%. Panel twins that sat 1.35% from their own source, only 1.35x the 1.0% line, now sit about 11% away, 11x the line. Panels that the whole-image score could not tell from their own source (APMM Part 32, 0.19%) now score 1.0-1.12%. The colour sliver and the two PRPD graph sizes were already told apart or kept ambiguous as before; those are the same picture drawn near-identically, and stay ambiguous.

The images that are still genuinely ambiguous (two candidates within 0.5% of each other) keep Word's version, as in ADR 0009.

## Proof

With picture stamps turned off, the four reports gave zero ambiguous images, zero wrong-source substitutions against the stamped result, and no image that differs from what the previous rule delivered. Sentosa's near-twin panels on pages 6-8 are matched to their own sources by pixels alone. Talapia still leaves 10 images unmatched without stamps (thermograms and previews Word rescales), as before.

## Accepted limits

- The thresholds come from four reports. A picture that is mostly white and differs only by a thin line could score high on a small content area; it fails the accept rule and keeps Word's copy, which is the safe direction.
- 245 as the white cut-off treats a very light picture as empty: two near-white images would score 0 against each other. Such a pair has nothing to restore and is not seen in the proof reports.
