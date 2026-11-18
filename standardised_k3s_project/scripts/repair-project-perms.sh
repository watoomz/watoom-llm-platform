#!/usr/bin/env bash
# Make project trees under /data/ai/projects writable for the app user (opencode, uid 1001, group 1009) and codex.
#
#   scripts/repair-project-perms.sh [--dry-run] [project ...]     (default: the list below)
#
# It finds exactly what the app user cannot write (the test runs AS the app user, so ACL masks, ownership and modes are all
# accounted for) and repairs only those entries, by cause:
#   1. owned by root (installs and tools run as root): handed to the project's normal owner
#   2. not covered by an ACL entry for the app user (made by the desktop user's tools): opencode and codex added, plus a default
#      ACL on directories so files created later, even by root, stay writable
#   3. 0644/0755 under an ACL (the mask hides the named entries): group-write added
# Never touched: .git, .opencode, private entries (not world-readable), and the service-owned areas in SKIP.
set -euo pipefail
DRY=0; [[ "${1:-}" == "--dry-run" ]] && { DRY=1; shift; }
cd /data/ai/projects
PROJECTS=("$@"); [[ ${#PROJECTS[@]} -eq 0 ]] && PROJECTS=(games/* homelab/homelab-llm images/generated images/review llm/esp32 llm/pipelines llm/watoom-code)
SKIP=("images/workstation-render-stage")   # owned by the render-transfer service account
APP_USER=opencode; CODEX_USER=codex
as_app() { setpriv --reuid=1001 --regid=1001 --groups=1001,1009 "$@"; }
unwritable() { as_app find "$1" \( -path '*/.git' -o -path '*/.opencode' \) -prune -o \( -type f -o -type d \) -perm -o=r ! -writable -print0 2>/dev/null; }
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
for p in "${PROJECTS[@]}"; do
  [[ -d $p && ! -L $p ]] || continue
  [[ " ${SKIP[*]} " == *" $p "* ]] && { echo "SKIP $p (service-owned)"; continue; }
  read -r uid gid < <(stat -c '%u %g' "$p"); [[ $uid == 0 ]] && { uid=1009; gid=1009; }
  unwritable "$p" > "$tmp"
  n=$(tr -cd '\0' < "$tmp" | wc -c)
  owners=$(xargs -0 -a "$tmp" -r stat -c '%u' 2>/dev/null | sort | uniq -c | sort -rn | head -4 | awk '{printf "%s×uid%s ",$1,$2}')
  printf "%-36s owner %s:%s  not-writable-by-app %-7s %s\n" "$p" "$uid" "$gid" "$n" "$owners"
  [[ $DRY == 1 || $n -eq 0 ]] && continue
  # 1. root-owned -> project owner
  find "$p" \( -path '*/.git' -o -path '*/.opencode' \) -prune -o -user 0 -perm -o=r -exec chown -h "$uid:$gid" {} + 2>&1 | head -3
  # 2+3. whatever is still unwritable: name the app user and codex in the ACL, add group-write
  unwritable "$p" > "$tmp"
  xargs -0 -a "$tmp" -r setfacl -m "u:$APP_USER:rwX,u:$CODEX_USER:rwX" 2>&1 | head -3
  xargs -0 -a "$tmp" -r chmod g+w 2>&1 | head -3
  find "$p" \( -path '*/.git' -o -path '*/.opencode' \) -prune -o -type d -perm -o=r ! -type l -exec setfacl -d -m "u:$APP_USER:rwx,u:$CODEX_USER:rwx" {} + 2>&1 | head -3
  left=$(unwritable "$p" | tr -cd '\0' | wc -c)
  echo "   -> still not writable: $left"
done
echo done
