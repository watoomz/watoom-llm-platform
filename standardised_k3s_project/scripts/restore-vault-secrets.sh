#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Restores Vaultwarden-related secrets into Kubernetes from saved local material.
# - Style: fail fast, print what is happening, and keep paths rooted in the repo unless the script is intentionally touching host state.
# - Safety: review kubectl, docker, hostPath, VPN, and secret-handling commands before running on a live node.
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VAULT_FILE="${VAULT_FILE:-$ROOT/secrets-vault/env.local.vault}"
OUT_FILE="${OUT_FILE:-$ROOT/secrets/.env.local}"
VAULT_PASSWORD_FILE="${VAULT_PASSWORD_FILE:-/data/secrets/homelab-host/ansible-vault-password.txt}"

if [[ ! -f "$VAULT_FILE" ]]; then
  echo "ERROR: missing vault file: $VAULT_FILE" >&2
  exit 1
fi

if [[ ! -f "$VAULT_PASSWORD_FILE" ]]; then
  cat >&2 <<MSG
ERROR: missing vault password file: $VAULT_PASSWORD_FILE

Restore it from your password manager, or set VAULT_PASSWORD_FILE to the
correct path before running this script.
MSG
  exit 1
fi

mkdir -p "$(dirname "$OUT_FILE")"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

ansible-vault view --vault-password-file "$VAULT_PASSWORD_FILE" "$VAULT_FILE" >"$tmp"

if [[ -w "$(dirname "$OUT_FILE")" ]] || [[ -w "$OUT_FILE" ]]; then
  install -m 0600 "$tmp" "$OUT_FILE"
else
  sudo install -m 0600 "$tmp" "$OUT_FILE"
fi

echo "Restored encrypted secrets to $OUT_FILE"
