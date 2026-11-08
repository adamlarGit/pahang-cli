# Run Records

Every project workflow and utility action started from the interactive CLI saves one Run Record. Settings and project management actions are excluded. A failure while selecting a project for a workflow is saved in the fallback location.

## Finding and sharing a record

Records are saved in `<project base path>/logs/`. Utilities without an active, real project, transient utility environments, and failures before project selection use `%LOCALAPPDATA%\pahang-cli\logs\`. A project folder that has disappeared is never recreated just to save a record. If project logging is unwritable, the per-user location is tried. If neither is writable, the workflow continues.

After a failed or partially failed action, the console prints `Run Record: <path>`. Send that one file to the developer. Successful records remain in the same folder without adding a console message. Records contain full request values, local file paths, diagnostic messages, and tracebacks; they contain no copies or hashes of input files.

Files are named `<local timestamp>-<action>-<unique suffix>.jsonl`. Each UTF-8 line is a separate JSON object, written and flushed immediately. Read a record with a text editor. A missing `run_finish` means the action was interrupted, crashed, or hung; the preceding lines remain usable. A process interruption may leave a Step without its finish entry.

## Format

Every entry has `type` and an ISO 8601 UTC `time`.

| Type | Contents |
| --- | --- |
| `run_start` | Action label, project key, and base path when a real project exists |
| `environment` | App version, git SHA, Python, Word and Excel versions; unreadable versions are `unknown` |
| `request` | Full request, including selected dates, substations and options; objects such as converters and sinks are described by type |
| `request_update` | `workflow` identifying an earlier request and `changes` to apply in order |
| `input` | Path, existence, size in bytes, and modified time in UTC; missing paths have null size/time, and an unreadable time is null |
| `input_truncated` | `folder`, `recorded`, `left_out` and `left_out_is_a_minimum`, when a folder held more files than the per-folder limit or its walk stopped early |
| `input_unreadable` | `folder`, a subfolder that couldn't be listed |
| `step_start`, `step_finish` | Step name; finishes add status and duration in seconds, and error text when raised |
| `log` | Logger name, level, message and exception traceback when supplied |
| `progress`, `console` | Existing stdout lines; prompt-toolkit drawing is excluded |
| `warning`, `error` | Message and full traceback when an exception is available |
| `result`, `output` | Returned summary and produced paths |
| `cancelled` | Explicit operator cancellation |
| `run_finish` | Final status and total duration in seconds |

Final statuses are `completed`, `partial_failure` (some batch items failed), `failed` (the whole job failed), or `cancelled` (explicit `OperationCancelled`). Older actions that return normally on cancellation finish as `completed`. Returning an error list alone means partial failure unless the workflow explicitly reports that its whole job failed.

Requests may appear first as selections and later as complete workflow requests. Apply `request_update.changes` over the earlier request with the same `workflow`. Unchanged values are omitted; keys omitted by a later update retain their earlier values. Identical input and output paths and repeated warning text are recorded once. Each error keeps its own entry, even when two substations fail with identical text. An error isn't repeated when the same exception is recorded again, when the same item fails the same way in a second pass, such as inspect then generate, or when a result returns an error already recorded.

Steps measure work, never time spent waiting on prompts. Workflows run through `WorkflowService` have one `Workflow: <name>` Step. Report generation times per-substation composition and Full Report plan building. Other actions may have no Steps.

Input discovery includes selected reports, testsheets, raw photos and archives, raw-data and survey files, resolved templates, and shared workbooks. Quick Report, Full Report, post-processing and the 1-Click pipeline all record the substation's raw-data folder. Directory discovery can include candidate files the workflow doesn't go on to use.

Each folder is listed once per Run and its files are never opened. Junctions and symlinks aren't followed, so files behind them aren't recorded. At most 200 files per folder are recorded, followed by an `input_truncated` entry. The listing stops after 50,000 directory entries; `left_out_is_a_minimum` is then true, because the real total is higher. Change `_MAX_INPUTS_PER_FOLDER` or `_MAX_ENTRIES_WALKED` in `src/run_records.py` to adjust these.

## Developer integration and tests

The action-running layer opens and closes records. Workflows add detail through `current_run()`, whose methods do nothing outside a recorded action. Use `record_request`, `record_inputs`, `record_input_folder`, `record_outputs`, `record_warning`, `record_error`, and `step`. Report a whole-job failure with `record_failure` or `mark_failed`. Nested runs reuse the outer recording context and do not create another file.

Version discovery reads Office installation metadata from the registry and executable files. It never dispatches Word or Excel. Recording errors are swallowed, including errors opening or writing the JSONL file. Console output retains its existing destinations, levels and formatting. During a Run, recording captures `src` logger messages and direct root logging calls: a temporary handler stands in for the root logger's handlers and passes on what they'd have received, and the originals are restored afterwards.

`PAHANG_CLI_RUN_RECORD_DIR` overrides every location, with no fallback. The suite-wide pytest configuration sets it to a temporary folder, including for child processes. Location-policy tests remove the override only while both project and fallback paths point under `tmp_path`. Never use a real project folder to test record writing.

Run tests as described in `docs/agents/testing.md`. Changes to prompts or console capture also need a hand check in a real console; see [the verification notes](run_records_verification.md).
