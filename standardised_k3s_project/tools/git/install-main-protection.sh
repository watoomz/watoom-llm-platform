#!/bin/sh
# Install the main-protection hooks for every git clone under /data/ai/projects (root-owned hooks dir).
# Usage: install-main-protection.sh [--dry-run]
set -eu
SRC="$(cd "$(dirname "$0")" && pwd)/hooks"
DEST=/data/ai/helper-scripts/git-hooks
if [ "${1:-}" != "--dry-run" ]; then
  mkdir -p "$DEST"; install -m 0755 -o root -g root "$SRC/reference-transaction" "$SRC/pre-push" "$DEST/"
fi
# Never touch the IDX checkout/backup (owner rule) or third-party upstream clones.
skip() { case "$1" in */work/idx-smb-kerberos*|*/moss-image/src|*/watoom-code/upstream-*|*/watoom-code/opencode-*) return 0;; esac; return 1; }
for g in $(find /data/ai/projects -maxdepth 4 -name .git \( -type d -o -type f \) 2>/dev/null); do
  repo=$(dirname "$g")
  if skip "$repo"; then echo "skipped $repo"; continue; fi
  if [ "${1:-}" = "--dry-run" ]; then echo "would protect $repo"; elif git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then git -C "$repo" config core.hooksPath "$DEST"; echo "protected $repo"; else echo "not a usable git repo, skipped $repo"; fi
done
