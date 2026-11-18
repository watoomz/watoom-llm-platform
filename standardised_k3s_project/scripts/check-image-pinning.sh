#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Audits manifests for floating image tags. Prefer digest-pinned images for repeatable rebuilds, and keep fallback tag comments beside digests for humans.
# - Style: fail fast, print what is happening, and keep paths rooted in the repo unless the script is intentionally touching host state.
# - Safety: review kubectl, docker, hostPath, VPN, and secret-handling commands before running on a live node.
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

cd "$ROOT"

echo "Images that should be pinned or reviewed:"
find manifests \
  -path manifests/05-secrets -prune -o \
  -type f \( -name '*.yml' -o -name '*.yaml' \) -print |
while read -r file; do
  case "$file" in
    *.before-*|*.bak|*.tmp) continue ;;
  esac
  { grep -nE 'image:[[:space:]]+[^[:space:]]+:(latest|release|stable)$' "$file" 2>/dev/null || true; } |
    sed "s#^#$file:#"
done

cat <<'NOTE'

Policy:
  - For critical workloads, prefer explicit version tags or digest pins.
  - For fast-moving hobby apps, :latest is acceptable only when documented and
    covered by the live image lock report.
  - Refresh the lock report after a known-good rebuild:
      scripts/export-live-image-lock.sh
NOTE
