<!-- status: closed -->
# #183 - Save a Run Record for every workflow execution

Parent specification: [#177](https://github.com/adamlarGit/pahang-cli/issues/177).
Ticket: [#183](https://github.com/adamlarGit/pahang-cli/issues/183).
Branch: `ticket/183-run-records`.

## Acceptance criteria

- [x] Every project workflow and utility action produces one flushed JSON Lines Run Record.
- [x] Failures include full tracebacks and show the Run Record path on the console.
- [x] Interrupted executions leave readable records without a run_finish entry.
- [x] Records include versions, project key, full request, input metadata, outputs, warnings, errors, and timed Steps.
- [x] Version capture never starts Word or Excel.
- [x] Logger and progress output are captured while console behavior stays unchanged.
- [x] Transient utilities and absent project folders use the per-user fallback without creating logs in the typed folder.
- [x] Unwritable recording locations never stop an action.
- [x] Suite-wide test isolation prevents Run Records from reaching real project folders, including subprocesses.
- [x] Behavior is tested through fake actions at the action-running layer against temporary paths.
- [x] Interactive prompts were manually checked in a real Windows console; results are captured in PR-ready verification notes.

## Implementation and verification

The action wrapper opens one fail-open Run Record, records exceptions before generic action handling discards their tracebacks, and displays the path on failure. Workflows add requests, selected inputs, outputs, batch failures, and useful timed Steps. Settings/project management remain excluded.

See [operator and format documentation](../../../docs/workflows/run_records.md) and [verification notes](../../../docs/workflows/run_records_verification.md). Implementation verified; full-suite baseline failures and the Windows encoding limitation are documented in the verification notes.
