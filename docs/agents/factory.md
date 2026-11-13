# Software Factory

The development process around this repo: how tickets become merged code, with agents working in parallel and the human at only a few points. Product vocabulary lives in `CONTEXT.md`, not here.

## Language

**Integration Branch**:
The long-lived branch an effort's Ticket PRs merge into (e.g. `feature/33kv-system`). Only this branch merges to `main`, and only that merge gets a version bump and CHANGELOG entry.
_Avoid_: feature branch (when you mean this), release branch

**Ticket PR**:
A pull request that resolves exactly one `ready-for-agent` issue, targets the Integration Branch, and closes the issue via `Closes #N`.
_Avoid_: agent PR, fix PR

**Path**:
One line of investigation under a research or prototype ticket, with its own question and exactly one owning agent. A ticket has one or more.
_Avoid_: track, thread, workstream

**Ticket Folder**:
The one folder on the Integration Branch holding everything a research or prototype ticket produced: its answer, its Path write-ups and the evidence they cite.
_Avoid_: research note, scratch folder

**Tested**:
Claim label. The agent ran it, and the command and its output are kept as evidence.
_Avoid_: proved, validated, verified

**Read**:
Claim label. A cited source states it and the agent did not run it.
_Avoid_: confirmed, known

**Assumed**:
Claim label. Neither run nor found in a source.
_Avoid_: likely, expected

**Owner-confirmed**:
Claim label. The owner checked it and said so in their own comment, which the claim links to.
_Avoid_: confirmed by HITL, human-verified

**Golden Benchmark**:
A frozen set of source inputs plus the report output and folder tree they're known to produce, used to catch differences automatically instead of by eye. Synthetic ones live in the repo; real-site ones live in the Benchmark Vault.
_Avoid_: fixture (when you mean the whole input-and-expected-output set), snapshot

**Benchmark Vault**:
A read-only folder outside the repo holding frozen, operator-approved copies of a small number of real sites in the client workspace layout. Golden Benchmarks are read from it; live project folders never are.
_Avoid_: reference folder, live samples

**Sandbox Workspace**:
A throwaway project base path assembled per worktree from Benchmark Vault sites, which agents and pre-merge validation run the CLI against. Never a live project base path.
_Avoid_: test workspace, staging

**Fast Run**:
The default test run during development. It excludes tests that need real Word or Excel, or live project data.
_Avoid_: unit tests (it also includes integration tests that use fakes), smoke test

**Full Run**:
Every test, including those using real Word, real Excel and live data. Required before merging the Integration Branch into `main`. Otherwise run when the owner asks.
_Avoid_: full test (without saying which run), regression run
