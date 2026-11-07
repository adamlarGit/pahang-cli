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
| `input` | Path, existence, size in bytes, and modified time in UTC; missing paths have null size/time |
| `step_start`, `step_finish` | Step name; finishes add status and duration in seconds, and error text when raised |
| `log` | Logger name, level, message and exception traceback when supplied |
| `progress`, `console` | Existing stdout lines; prompt-toolkit drawing is excluded |
| `warning`, `error` | Message and full traceback when an exception is available |
| `result`, `output` | Returned summary and produced paths |
| `cancelled` | Explicit operator cancellation |
| `run_finish` | Final status and total duration in seconds |

Final statuses are `completed`, `completed_with_errors` (some batch items failed), `failed` (the whole job failed), or `cancelled` (explicit `OperationCancelled`). Older actions that return normally on cancellation finish as `completed`. Returning an error list alone means partial failure unless the workflow explicitly reports that its whole job failed.

Requests may appear first as selections and later as complete workflow requests. Apply `request_update.changes` over the earlier request with the same `workflow`. Unchanged values are omitted; keys omitted by a later update retain their earlier values. Identical input/output paths and repeated warning/error messages are deduplicated; an error can acquire a later traceback.

Every action has an `Execute action` Step. Report generation also times per-substation composition and Full Report plan building. Input discovery includes selected reports, testsheets, raw photos and archives, survey files, resolved templates, and shared workbooks. Directory discovery can include additional candidate files, without reading their contents.

## Developer integration and tests

The action-running layer opens and closes records. Workflows add detail through `current_run()`, whose methods do nothing outside a recorded action. Use `record_request`, `record_inputs`, `record_input_folder`, `record_outputs`, `record_warning`, `record_error`, and `step`. Report a whole-job failure with `record_failure` or `mark_failed`. Nested runs reuse the outer recording context and do not create another file.

Version discovery reads Office installation metadata from the registry and executable files. It never dispatches Word or Excel. Recording errors are swallowed, including errors opening or writing the JSONL file. Console output retains its existing destinations, levels and formatting; recording captures `src` logger messages and direct root logging calls. The CLI does not reconfigure logging handlers during an action.

`PAHANG_CLI_RUN_RECORD_DIR` overrides every location, with no fallback. The suite-wide pytest configuration sets it to a temporary folder, including for child processes. Location-policy tests remove the override only while both project and fallback paths point under `tmp_path`. Never use a real project folder to test record writing.

Run focused validation with `uv run --with pytest python -m pytest tests/test_run_records.py -q`. Console compatibility also requires an interactive Windows console check; see the ticket verification notes.
