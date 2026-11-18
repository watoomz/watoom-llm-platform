#!/usr/bin/env bash
set -Eeuo pipefail
echo '=== recent boots ==='; journalctl --list-boots --no-pager | tail -12 || true
echo; echo '=== crash-labelled sessions ==='; last -x -n 40 | grep -E 'crash|reboot|shutdown' || true
echo; echo '=== previous-boot high-signal kernel ==='
journalctl -b -1 -k --no-pager 2>/dev/null | grep -Ei 'Out of memory|oom-kill|Killed process|NVRM|Xid|kernel panic|soft lockup|hard lockup|hung task|watchdog|MCE|machine check|hardware error|I/O error|nvme.*error' | tail -300 || true
echo; echo 'READ-ONLY audit complete.'
