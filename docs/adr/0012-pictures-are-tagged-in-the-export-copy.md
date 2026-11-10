# 12. Pictures Are Tagged in the Export Copy So Restoration Can Read Back Which Is Which

Date: 2026-11-10
Status: Accepted (2026-11-10, after the #214 proof on Sentosa, Talapia, 094 and APMM Part 32)
Adds to: [ADR 0009](./0009-native-export-with-source-image-restoration.md) and [ADR 0011](./0011-full-report-converts-from-disconnected-copy.md). Does not replace either.

## Decision

The copy that Word exports (ADR 0011) now also gives every DOCX picture the description `PSRID:<n>`, where `n` counts the drawings (`wp:docPr`) or picture-holding VML shape (`v:shape`, used by the FLIR thermogram previews) in document order, then headers and footers. Word writes that description into the PDF as the `/Alt` text of the picture's tagged element (a Figure, or an InlineShape for VML). Source Image Restoration reads it back through image (looking inside Word's metafile forms), marked-content number, tagged element, `/Alt`, and uses it to narrow an image's candidates to the picture Word drew.

- Pixels stay the gate. The stamped source must still match Word's image within the usual tolerance. If it does not, the image keeps Word's copy (unmatched), and no other candidate is tried.
- Word stores identical pictures once, so an image can carry several stamps. Its candidates are all the sources those stamps name, and the pixels choose among them.
- An image with no stamp, with a stamp the DOCX does not explain, or that is also drawn somewhere without a stamp, is matched by pixels over all sources as in ADR 0009.
- If several candidates look alike, the image stays ambiguous and keeps Word's copy, as in ADR 0009.
- After matching, restoration puts each figure's original description back, so the stamps never reach the deliverable.
- The operator's DOCX is never modified. Any report with pictures now opens the copy, not only reports with FLIR controls. If the copy fails, conversion opens the original and falls back to pixel matching, with the ADR 0011 warning.

## Why

Pixels cannot tell apart panels that differ only in a few table digits. In the #212 proof, Sentosa's US/TEV panels differed by 1.35-1.46% of pixels and APMM Part 32's 13x171 colour sliver by 1.17%, and any rule on that margin gets thinner the more alike the readings are (all-normal readings). The stamp identifies the picture directly. The pixel rule was also loosened (runner-up cleared at 1.0% and 5x the best score, was 1.5%) to serve as the fallback.

## Accepted limits

- Pictures in text boxes, tables and headers read back only if Word tags them; others fall back to pixels.
- Needs `DocStructureTags=True` in the export, which is already set.

## Groups and canvases (#216)

A DrawingML group (`wpg:wgp`) or drawing canvas (`wpc`) has one `wp:docPr`, so it gets one stamp. The stamp names the sources of every picture inside it, and the pixels choose among them. Word is either tagging the group as one Figure, so every image in it carries that stamp, or tagging each child with no stamp, so each image falls back to pixels over all sources. Both outcomes restore. If any picture in the group cannot be traced to a source, the stamp does not narrow at all.

What Word actually writes into the PDF structure for a group of two pictures has not been observed yet. The synthetic tests cover the one-Figure case and the unstamped case; a real-Word probe should confirm which one happens.
