#!/usr/bin/env bash
# Purpose: Recovery inventory, coverage checks and ordered replacement-host phases.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$SCRIPT_DIR" ]]; then
    printf 'FAIL: cannot resolve recovery source directory\n' >&2
    exit 1
fi
if [[ $# -eq 0 ]]; then
    printf 'Use inventory, plan, audit, verify-backup, restore-test, capture or run-phase. See docs/guide/disaster-recovery.md.\n'
    exit 0
fi
python3 "$SCRIPT_DIR/../tools/recovery/recovery.py" "$@"
status=$?
exit "$status"
