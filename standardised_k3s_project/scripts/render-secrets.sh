#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Renders generated secret manifests from local secret material. Generated files should not be treated as templates.
# - Style: fail fast, print what is happening, and keep paths rooted in the repo unless the script is intentionally touching host state.
# - Safety: review kubectl, docker, hostPath, VPN, and secret-handling commands before running on a live node.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/secrets/.env.local"
OUT_DIR="$ROOT/manifests/05-secrets"

[ -f "$ENV_FILE" ] || {
  echo "ERROR: missing $ENV_FILE"
  exit 1
}

mkdir -p "$OUT_DIR"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

need() {
  local name="$1"
  [ -n "${!name:-}" ] || {
    echo "ERROR: missing required value: $name"
    exit 1
  }
}

b64() {
  printf '%s' "$1" | base64 -w0
}



need GRAFANA_ADMIN_USER
need GRAFANA_ADMIN_PASSWORD

cat > "$OUT_DIR/grafana-secrets-generated.yml" <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: grafana-secrets
  namespace: monitoring
type: Opaque
data:
  GF_SECURITY_ADMIN_USER: $(b64 "$GRAFANA_ADMIN_USER")
  GF_SECURITY_ADMIN_PASSWORD: $(b64 "$GRAFANA_ADMIN_PASSWORD")
YAML

if [ -n "${GLANCE_CHANGE_APPROVAL_PIN_HASH:-}" ]; then
cat > "$OUT_DIR/glance-change-approval-generated.yml" <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: glance-change-approval
  namespace: glance
type: Opaque
data:
  pin-hash: $(b64 "$GLANCE_CHANGE_APPROVAL_PIN_HASH")
YAML
fi

echo "Generated:"
ls -1 "$OUT_DIR"/*-generated.yml
