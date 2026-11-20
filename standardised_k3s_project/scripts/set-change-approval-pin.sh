#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Creates or rotates the operator PIN for approving model change requests in Glance and stores it in the encrypted vault.
# - The PIN and its salted hash go into secrets-vault/env.local.vault (encrypted, committed), secrets/.env.local (ignored) and the
#   root-only /root/.watoom-change-request-pin. The cluster Secret glance-change-approval holds only the salted hash.
# - Safety: nothing secret is printed; commit secrets-vault/env.local.vault afterwards.
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
VAULT_FILE="${VAULT_FILE:-$ROOT/secrets-vault/env.local.vault}"
VAULT_PASSWORD_FILE="${VAULT_PASSWORD_FILE:-/data/secrets/homelab-host/ansible-vault-password.txt}"
[[ -f "$VAULT_FILE" && -f "$VAULT_PASSWORD_FILE" ]] || { echo "ERROR: missing vault file or password file" >&2; exit 1; }
tmp="$(mktemp)"; new="$(mktemp)"; trap 'rm -f "$tmp" "$new"' EXIT
ansible-vault view --vault-password-file "$VAULT_PASSWORD_FILE" "$VAULT_FILE" | grep -v -E '^(CHANGE_REQUEST_PIN|GLANCE_CHANGE_APPROVAL_PIN_HASH)=' >"$tmp"
python3 "$ROOT/tools/change-requests/change_request.py" set-pin --env >>"$tmp"
cp "$tmp" "$new"
ansible-vault encrypt --vault-password-file "$VAULT_PASSWORD_FILE" --output "$VAULT_FILE" "$new" >/dev/null
install -m 0600 "$tmp" "$ROOT/secrets/.env.local"
bash "$ROOT/scripts/render-secrets.sh" >/dev/null
kubectl apply -f "$ROOT/manifests/05-secrets/glance-change-approval-generated.yml"
kubectl -n glance rollout restart deploy/glance
kubectl -n glance rollout status deploy/glance --timeout=180s
echo "Done. Your PIN is stored in the vault (CHANGE_REQUEST_PIN) and in /root/.watoom-change-request-pin."
echo "Commit secrets-vault/env.local.vault so the new PIN is part of the repo."
