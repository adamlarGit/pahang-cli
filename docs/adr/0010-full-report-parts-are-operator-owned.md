# Full Report Parts Are Operator-Owned Once Created

Status: Accepted

After generation, every Full Report Part is edited by hand for thermogram qualitative analysis. Once a Part exists under its final name it therefore belongs to the operator, and the Generate Full Reports workflow never overwrites, compares, or deletes it. Resume builds only the missing Parts. Rebuild, which needs explicit confirmation, moves existing Parts to `_superseded/<timestamp>/` in the date folder. Parts the current plan no longer produces get the same treatment. Completion is judged by file existence alone, which is safe because a Part is written to a temporary name and renamed only after Word finishes saving it.

## Considered Options

- **Automatic staleness detection, by comparing Part and input file dates or recording input fingerprints.** Rejected. Operator edits make every Part look modified, so the check gives false positives. Date comparisons also break when a Full Report is generated on a different day from its Quick Report. A false positive would silently destroy hours of analysis.
- **Deleting existing Parts on every run (the previous behaviour).** Rejected for the same reason: a single crash-and-rerun wiped all operator edits.
