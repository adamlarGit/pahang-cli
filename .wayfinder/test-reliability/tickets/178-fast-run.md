<!-- status: closed -->
# #178 Make plain pytest a Fast Run on locked packages

GitHub: https://github.com/adamlarGit/pahang-cli/issues/178
Parent: #177. Branch: `ticket/178-fast-run`.

## Acceptance criteria

- [x] Plain pytest excludes `word` and `live_data`; the documented Full Run selects every test.
- [x] Existing real Word, Excel, and live-data tests have the corresponding markers.
- [x] Unmarked Office starts fail with a message naming the missing `word` marker.
- [x] Small subprocess pytest samples test the guard, including swallowed failures and xfails.
- [x] Documented commands use locked packages and pinned pytest/xdist versions.
- [x] `uv.lock` is unchanged, pytest stays out of `.venv`, and the lockfile rationale is documented.
- [x] Running the suite leaves tracked PE157 benchmark files unchanged.
- [x] README and AGENTS link to Fast Run and Full Run documentation.

## Implementation

The interrupted work already supplied tier markers, sample tests, temporary fixture
outputs, and commands. The final fix recognises CSV activation, `book.xlsx!Sheet1`,
`new:{CLSID}`, and `clsid:CLSID:` before pywin32 can start Office. CSV detection is
conservative because its registered COM handler can be Excel.

## Validation, 2026-11-07

- Before the final fix: 4 guard regression failures, 22 passing tests.
- After the fix: all 26 tier/guard regressions pass. The focused run also included
  one temporarily corrected #179 test (27 passed); that unrelated edit was reverted.
- Fast Run: 2,056 passed, 3 failed, 50 deselected in 275.01 seconds. All three
  failures are explicitly listed in #179: preview whitespace, TX label, PT keywords.
- Office/live-data tier, serial: 35 passed, 8 failed, 4 skipped, 3 XPASS in
  539.91 seconds. The eight failures and three stale XPASS markers exactly match
  the cases already tracked by #179.
- Both tiers together exercised every collected test: 2,091 passed, 11 failed,
  4 skipped, and 3 XPASS. No new failure was found.
- After both runs, `git status --porcelain -- tests/benchmarks` was empty and
  `git diff HEAD -- uv.lock` was empty. No tracked output was changed by the tests.
- Lockfile SHA256: `D100B77D9EA59BC284EDAE24A2BB995EE5343917D8CC164256F61E8CF43CB3B1`.
- `.venv/Lib/site-packages/pytest` is absent. No dependency groups were added.
- Static review found no further concrete issue in the final guard changes.

The broader suite is not claimed green; baseline failure triage belongs to #179,
and speed/parallelism work belongs to #180 and #182.
