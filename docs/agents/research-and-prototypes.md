# Research and prototype tickets

Every agent, in every harness, stores and reports the work of a `wayfinder:research` or `wayfinder:prototype` ticket this way. Where a skill names a different place for results, this file wins.

Path, Ticket Folder and the four claim labels are defined in `docs/agents/factory.md`. The Integration Branch is currently `feature/33kv-system`.

## Steps

1. **Take your Path.** The ticket body names the Ticket Folder and lists the Paths (see [Ticket body](#ticket-body)). Work the Path that names you as owner. If your line of investigation is missing, add it to the body before you start.

   Done when the ticket body names your Path with you as its owner.

2. **Open your own worktree.** Branch from the Integration Branch into a sibling of the repo folder. The Integration Branch worktree stays on its branch.

   ```
   git worktree add ../pahang-cli-wt/<issue>-<path> -b research/<issue>-<path> feature/33kv-system
   ```

   A prototype ticket uses `prototype/<issue>-<path>`.

3. **Write into the Ticket Folder.** Everything you produce goes there from the first file, prototype code included (see [Ticket Folder](#ticket-folder)). Use the [write-up template](#write-up-template) and no other top-level headings.

   Done when every file your write-up cites is inside the Ticket Folder or recorded under Live data read.

4. **Label every claim.** Each row of the Claims table carries one label and the evidence that label requires (see [Claim labels](#claim-labels)).

   Done when no claim in the Verdict is missing from the Claims table.

5. **Land.** From your worktree:

   ```
   git rebase feature/33kv-system
   git diff --name-only feature/33kv-system...HEAD
   git -C <Integration Branch worktree> merge --ff-only <your branch>
   git push origin feature/33kv-system
   ```

   `git worktree list` shows the Integration Branch worktree. Every path the diff prints must sit inside your Ticket Folder. A change to `CONTEXT.md` or `docs/adr/` may ride along in its own commit. If the diff prints anything else, or the merge or the push is refused, stop and report to the owner. Changes to product code go through a spec and a Ticket PR.

   Then set your Path's State in the ticket body to `landed <short sha>`.

6. **Comment once.** Post one comment in the [fixed form](#ticket-comment). A blocker or a question for the owner is the only other comment an agent posts, and it starts with the same `Agent:` line.

7. **Write the answer.** Only for the agent the owner names, once every Path is `landed`. Write `README.md` from the Path files, list under Disputed every claim where two Paths disagree, land it the same way, post the comment with `Path: answer`, then follow `.agents/rules/ticket-lifecycle.md`.

## Ticket body

A research or prototype ticket keeps the `## Question` the `wayfinder` skill defines and adds:

```markdown
## Paths

Folder: `docs/research/223-flir-xml-join/`

| Path | Question | Owner | State |
|------|----------|-------|-------|
| static-cfb | What do the CFB streams of each control hold? | Codex | landed 6fdea7e |
| sdk-tools | Can FLIR's own tools do the join? | Antigravity | open |

## Changes

- 2026-11-10: input changed from the Talapia Part to Part 03 and Part 32 (owner).
```

The body is the current truth. When the question, inputs, pass conditions or Paths change, edit the body and add a dated line under `## Changes` saying what changed and who decided it.

## Ticket Folder

```
docs/research/<issue>-<slug>/
  README.md              the answer
  path-<name>.md         one per Path
  evidence/<name>/       scripts, inputs, outputs and command logs for that Path
```

- The folder name is the one in the ticket body. Names are kebab-case and dates are `YYYY-MM-DD`.
- A ticket with one Path has no Path file. Its owner writes the whole write-up into `README.md` and keeps evidence in `evidence/`.
- A research ticket and its prototype ticket have separate folders and cite each other by path.
- Commit a cited file when it is under 5 MB and holds no client data. For anything else, commit the command that produces it and record the file under Live data read.
- `.scratch/` and `scratch/` are for files no write-up cites.

## Write-up template

`README.md` and every Path file use this shape. A Path file adds `path: <name>` to the frontmatter and a `## Question for this Path` heading before the Verdict.

```markdown
---
ticket: 223
type: research            # research | prototype
map: 221
status: open              # open | answered (set when the ticket closes)
updated: 2026-11-11
agent: Codex, <model>
---
# Can FLIR controls be joined at the XML level without crosstalk?

## Verdict

The answer in one paragraph. A prototype ticket gives pass or fail for each pass condition.

## Claims

| ID | Claim | Label | Evidence |
|----|-------|-------|----------|
| C1 | Rekeying every Instance GUID leaves all viewers loading. | Tested | `evidence/rekey/test_full_rekey.py`, `evidence/rekey/run.log` |
| C2 | The control name is stored in the `.bin` part. | Read | `path-static-cfb.md` C4 |

## Detail

The diagrams, tables and lists the claims rest on. Sub-headings are free here.

## Disputed

README only. One row per claim where Paths disagree, citing both.

## Open questions

## How to reproduce

The commands, in order, from a clean worktree.

## Live data read

| Path | File | Bytes | SHA-256 | Read on |
|------|------|-------|---------|---------|
| `<BASE>/PPU APMM/...` | `Part 32.docx` | 2278628 | `ab12...` | 2026-11-11 |

## Change log

- 2026-11-11: first version (Codex).
```

**Updating.** Rewrite the Verdict and the affected claims in place, add a dated line to the Change log and set `updated`. Claim IDs are permanent. To retract a claim, strike it through in its row and say why in the Change log.

An update lands the same way as the first version. Set the new commit in the Path's State in the ticket body. Post a new summary comment only when the Verdict changes.

**README claims** are the ones the verdict rests on. Each cites the Path claim behind it and carries that claim's label.

## Claim labels

| Label | The Evidence cell holds |
|-------|-------------------------|
| Tested | The script or command and its captured output, both in `evidence/` |
| Read | The source: a repo path, a URL, or a document and section |
| Assumed | `none`, plus the test that would settle it |
| Owner-confirmed | A link to the owner's own comment |

These four are the whole vocabulary for certainty. Every agent comment starts with an `Agent:` line and the owner's never do, which is how an owner's comment is told apart.

## Live data and links

- Live project folders move and change. Cite a live file by its row under Live data read, with `<BASE>` standing for the project base path. Client files stay out of the repo.
- Inside a write-up, link by path: relative to the Ticket Folder for its own files, from the repo root for anything else.
- Cite a commit by its SHA once it is on the Integration Branch. Branch names and machine paths (`file:///`, `C:\...`) go stale, so they stay out of write-ups and comments.

## Ticket comment

```
Agent: Codex, <model>. Path: static-cfb
Verdict: <one to three sentences>
Claims: 6 Tested, 3 Read, 2 Assumed
Open questions: 2
Folder: https://github.com/adamlarGit/pahang-cli/tree/<landed sha>/docs/research/223-flir-xml-join
```

## Citing research in a spec

A spec decision that rests on research or a prototype cites the README claim by folder and ID, for example `223-flir-xml-join C4`.
