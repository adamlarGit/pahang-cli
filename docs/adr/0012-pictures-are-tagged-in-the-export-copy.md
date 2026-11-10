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

A DrawingML group (`wpg:wgp`) or drawing canvas (`wpc`) has one `wp:docPr`, so it gets one stamp. The stamp now names the sources of every picture inside it, and the pixels choose among them. If any picture in the group cannot be traced to a source, the stamp does not narrow at all.

**What Word does (observed 2026-11-10, Word 16, `DocStructureTags=True`, a synthetic DOCX with one group of two pictures, one canvas of two pictures and one plain inline picture, run through the export copy):**

- **Group.** Word writes one Figure for the group, with `/Alt` `PSRID:1 (Grouped Object)` (it appends its own text after the stamp). That Figure's marked content draws only the group's outline rectangle. The two pictures inside are drawn as `/Artifact` sections, untagged and with no stamp.
- **Canvas.** Word drops the canvas's description: no Figure carries the canvas stamp. Each picture inside is its own Figure with `/Alt` null, so no stamp reaches the PDF.
- **Plain inline picture (control).** One Figure with its own stamp, as before.

So in real Word, pictures inside a group or canvas never carry a stamp. They fall through to pixel matching over all sources (ADR 0009). In the probe all four restored by pixels, each to its own source; none was ambiguous. The stamp change above is harmless but does not fire for these pictures. Identity evidence for them would need another route, such as the neighbour inference below.

**Side effect, handled.** Word appends ` (Grouped Object)` to a group's `/Alt`, after the stamp. When the group's own description was empty, stamp removal drops that text too, so the published PDF matches an unstamped export (no description). After a real description it is kept. Only the English text is recognised.

## Inferring a missing stamp (#218)

An image Word did not tag gets identity evidence from its stamped neighbours when the case is unambiguous. If stamps `p` and `p+2` appear on one page and exactly one image is drawn between them in content order, that image is treated as stamped `p+1`. The rule applies only when:

- both neighbours are on the same page and exactly one image sits in the gap,
- exactly one drawing lies between them in the DOCX, and it is in the main document (headers and footers are artifacts outside the reading order, so they are out of scope),
- no figure in the PDF carries a stamp for that drawing.

Every other case falls through to pixels as before. The inferred stamp counts like a real one, so the safety rule still holds (an image also drawn without a stamp is matched by pixels), and pixels stay the gate: if the inferred source disagrees with Word's image, the image keeps Word's copy. Content order is paint order, which can differ from reading order for floating pictures; the pixel gate is what catches that.
