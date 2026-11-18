---
name: watoom-change-requests
description: Ask the operator to change a host-side file you cannot edit (for example a worker limit or contract) through an audited, human-approved change request. Use when a job fails because of a host-owned file, not for source in your own project.
---
# Host change requests

You cannot edit host-owned files (they live in the read-only canonical checkout) and you must not try to bypass that. When a failure is caused by one of them, file a change request instead of working around it. First check whether a named option already solves it (for example ESP32 builds accept `"source_profile":"large"`).

1. Create `.opencode/change-requests/` in the current project root if it is missing (any project under `/data/ai/projects/<group>/<project>` works), then write `<id>.json` there (a fresh id `[a-z0-9-]{1,64}`, equal to the file name):
   `{"schema":1,"id":"<id>","file":"<repo-relative path>","old":"<exact text, must match once>","new":"<replacement>","reason":"<why, with the exact error>"}`
   Allowed `file` values (repo-relative; the `standardised_k3s_project/` prefix is optional): `tools/esp32/contract.py`, `tools/esp32/runner.py`, `tools/esp32/worker.py` and `ansible/roles/watoom-code/files/skills/esp32-development/references/operations.md`. `old` must match the file exactly once, including leading spaces and indentation: copy the line verbatim (read it first), do not retype it. Keep edits small: at most 40 changed lines. A rejection names the reason and lists the allowed files.
2. Within about a minute read `.opencode/change-requests/<id>.status.json`. `PENDING_APPROVAL` carries the exact diff; `REJECTED` names the reason (fix and file a new id). `APPLIED` means the operator approved it, the fixed checks passed and it was committed. `CHECK_FAILED` means it was reverted.
3. Never edit a request after review and never reuse an id. Tell the user the id and that approval is needed, then continue with other work; do not poll repeatedly. Use the `wait` tool if you must pause.
4. After `APPLIED`, resubmit the blocked job with a fresh job id.

You cannot approve your own request and no command is run on your behalf.
