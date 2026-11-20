#!/usr/bin/env bash
# Purpose: Recovery inventory, coverage checks and ordered replacement-host phases.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -eq 0 ]]; then
    printf 'Use inventory, plan, audit, verify-backup, restore-test, capture or run-phase. See docs/guide/disaster-recovery.md.\n'
    exit 0
fi
exec python3 "$SCRIPT_DIR/../tools/recovery/recovery.py" "$@"
