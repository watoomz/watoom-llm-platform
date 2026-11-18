# WatooM Script Rules

These rules apply under `standardised_k3s_project/scripts/`.

## Style

- Use `#!/usr/bin/env bash`.
- Prefer `set -Eeuo pipefail` for maintained Bash scripts unless there is a documented reason not to.
- Quote variable expansions.
- Use `[[ ... ]]` for Bash conditionals.
- Use functions for substantial scripts and a clear main flow.
- Validate required commands, paths, arguments, and environment variables before mutation.
- Emit clear section headers and PASS/FAIL output for operational scripts.

## Safety

- Make targeted backups under `/tmp` before replacing managed files.
- Preserve unrelated dirty-worktree changes.
- Never use broad Git cleanup/reset/checkout/restore.
- Never stage, commit, or push unless explicitly requested.
- Avoid `sudo -i`; commands are normally run with the caller's existing privilege.
- Do not hard-code secrets.
- Do not introduce a parallel installer/package manager when an existing project helper already owns that function.
- For destructive or irreversible operations, require explicit scope and add a dry-run/precheck when practical.

## Validation

- Run `bash -n` on generated/modified Bash scripts.
- Use `shellcheck` when already available/configured; do not install it as a side effect.
- For scripts that deploy or mutate infrastructure, verify both the source change and the resulting live state.
