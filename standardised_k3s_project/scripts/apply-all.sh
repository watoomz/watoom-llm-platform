#!/usr/bin/env bash
# WatooM registered-manifest reconciliation wrapper
#
# Purpose:
#   Apply ONLY manifests explicitly registered in k3s_manifest_groups.
#   Specialised owners (LLM, Dispatcharr variants, Cloudflare connector, manual jobs,
#   generated secrets, etc.) stay outside this broad path by design.
#
# Preferred path:
#   Use ./ansible-run playbooks/kubernetes.yml when Ansible is available.
# Fallback path:
#   For constrained helper containers such as the IaC Web Console, read the exact
#   same registry and apply only those registered files with kubectl.
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
REGISTRY="$ROOT/ansible/inventories/homelab/group_vars/all.yml"

if [[ ! -f "$REGISTRY" ]]; then
  echo "ERROR: missing manifest registry: $REGISTRY" >&2
  exit 1
fi

# The host/operator path remains Ansible-first.
if [[ -x "$ROOT/ansible-run" ]] && command -v ansible-playbook >/dev/null 2>&1; then
  exec "$ROOT/ansible-run" playbooks/kubernetes.yml
fi

# The web-console image is intentionally small and may not contain Ansible.
# Preserve the same desired-state registry rather than reverting to directory scans.
command -v kubectl >/dev/null 2>&1 || { echo "ERROR: kubectl not found" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found" >&2; exit 1; }

mapfile -t manifests < <(
  python3 - "$REGISTRY" <<'PY'
import sys
from pathlib import Path
try:
    import yaml
except Exception as exc:
    raise SystemExit(f"ERROR: PyYAML is required to read the manifest registry: {exc}")

registry = Path(sys.argv[1])
data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
groups = data.get("k3s_manifest_groups")
if not isinstance(groups, dict):
    raise SystemExit("ERROR: k3s_manifest_groups is missing or is not a mapping")

for group in ("namespaces", "infrastructure", "media", "games", "rbac"):
    entries = groups.get(group, [])
    if not isinstance(entries, list):
        raise SystemExit(f"ERROR: k3s_manifest_groups.{group} is not a list")
    for item in entries:
        if not isinstance(item, str) or not item.strip():
            raise SystemExit(f"ERROR: invalid manifest entry in group {group}: {item!r}")
        print(item)
PY
)

if (( ${#manifests[@]} == 0 )); then
  echo "ERROR: manifest registry is empty" >&2
  exit 1
fi

for rel in "${manifests[@]}"; do
  case "$rel" in
    manifests/*.yml|manifests/*.yaml) ;;
    *) echo "ERROR: registry entry is outside manifests/: $rel" >&2; exit 1 ;;
  esac
  if [[ ! -f "$ROOT/$rel" ]]; then
    echo "ERROR: registered manifest does not exist: $rel" >&2
    exit 1
  fi
  echo "== apply registered $rel =="
  kubectl apply -f "$ROOT/$rel"
done
