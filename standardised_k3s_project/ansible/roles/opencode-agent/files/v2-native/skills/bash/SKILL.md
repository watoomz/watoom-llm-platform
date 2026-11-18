---
name: bash
description: Use for Bash/shell scripts, command construction, non-interactive automation, process-safe scripting, and shell validation.
---

# Bash

- New automation should normally use `set -Eeuo pipefail`.
- Quote expansions unless intentional splitting/globbing is required.
- Use arrays for argv construction.
- Prefer explicit non-interactive command forms.
- Avoid editors, pagers, REPLs, blanket `yes |`, and unmanaged `command &`.
- Add traps/cleanup for temporary files and owned child processes.
- Validate with `bash -n`; use `shellcheck` when configured.
- Fail closed on ambiguous/destructive state.
