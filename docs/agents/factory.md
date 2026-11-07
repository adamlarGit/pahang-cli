# Software Factory

The development process around this repo: how tickets become merged code, with agents working in parallel and the human at only a few points. Product vocabulary lives in `CONTEXT.md`, not here.

## Language

**Integration Branch**:
The long-lived branch an effort's Ticket PRs merge into (e.g. `feature/33kv-system`). Only this branch merges to `main`, and only that merge gets a version bump and CHANGELOG entry.
_Avoid_: feature branch (when you mean this), release branch

**Ticket PR**:
A pull request that resolves exactly one `ready-for-agent` issue, targets the Integration Branch, and closes the issue via `Closes #N`.
_Avoid_: agent PR, fix PR

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
Every test, including those using real Word, real Excel and live data. Required before merging into the Integration Branch.
_Avoid_: full test (without saying which run), regression run
