#!/usr/bin/env bash
set -euo pipefail
REPO="${REPO:-/data/github/watoom-standardised-homelab/standardised_k3s_project}"
MODE="${1:-standard}"
TARGET="${2:-$REPO}"
case "$MODE" in fast|standard|full) ;; *) echo "Usage: $0 {fast|standard|full} [target-root]" >&2; exit 2;; esac
ENGINE_DIR="$REPO/ansible/roles/ansible_lint_api/files"
export PYTHONPATH="$ENGINE_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 "$ENGINE_DIR/watoom_ansible_validate.py" "$MODE" --root "$TARGET" --json-out "$TARGET/.watoom-ansible-validation.json"
