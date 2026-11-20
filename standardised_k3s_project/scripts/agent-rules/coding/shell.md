# Shell rules
- Determine the intended shell before using shell-specific syntax; quote expansions and avoid unsafe splitting/globbing.
- Preserve idempotence in administrative scripts; run bash -n for Bash and ShellCheck when already available/configured.
- Avoid broad destructive commands and broad Git operations.
- Commands intended for the user's interactive terminal must not use top-level exit, shell-replacing exec, or top-level set -e patterns that can unexpectedly terminate the terminal.
- Standalone executable scripts may use set -Eeuo pipefail and exit where appropriate.
