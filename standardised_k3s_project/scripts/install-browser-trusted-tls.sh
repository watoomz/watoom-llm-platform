#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Install or repair the browser-trusted Let's Encrypt wildcard for
#   *.internal.homelab.example, issued by cert-manager through Cloudflare DNS-01.
# - Safety: Uses Let's Encrypt staging first, then production, to protect the
#   production rate limit from bad DNS/token configuration.
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

KUBECTL="${KUBECTL:-kubectl}"
CERT_MANAGER_VERSION="${CERT_MANAGER_VERSION:-v1.21.3}"
DOMAIN="${WATOOM_INTERNAL_DOMAIN:-internal.homelab.example}"
TLS_SECRET_NAME="${WATOOM_TLS_SECRET_NAME:-watoom-tls}"
# Fixed: cert-manager.yaml installs into cert-manager, and a ClusterIssuer reads its credentials Secret from that namespace,
# so the rollout checks, the Secret and the Certificates must all use it (an override would split them).
CERT_NAMESPACE=cert-manager
STAGING_ONLY="${STAGING_ONLY:-false}"
ENV_FILE="$ROOT/secrets/.env.local"

# Canonical host-side TLS material consumed by the homelab_rebuild local_tls
# role. The sync keeps it current, so a later rebuild reconciles the Let's
# Encrypt certificate rather than stale material into the watoom-tls Secrets.
CANONICAL_TLS_DIR="${WATOOM_CANONICAL_TLS_DIR:-/data/watoom-local-tls}"

read_env_value() {
  local name="$1"
  local value="${!name:-}"
  if [ -n "$value" ]; then
    printf '%s' "$value"
    return
  fi
  if [ -f "$ENV_FILE" ]; then
    awk -F= -v key="$name" '
      $1 == key {
        value = substr($0, length(key) + 2)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        gsub(/^"|"$/, "", value)
        gsub(/^'\''|'\''$/, "", value)
        print value
        exit
      }
    ' "$ENV_FILE"
  fi
}

CF_TOKEN="$(read_env_value CLOUDFLARE_DNS_API_TOKEN)"
if [ -z "$CF_TOKEN" ]; then
  CF_TOKEN="$(read_env_value CLOUDFLARE_API_TOKEN)"
fi

LE_EMAIL="$(read_env_value LETSENCRYPT_EMAIL)"
if [ -z "$LE_EMAIL" ]; then
  LE_EMAIL="$(read_env_value ACME_EMAIL)"
fi

need() {
  local name="$1"
  local value="$2"
  if [ -z "$value" ]; then
    echo "ERROR: missing $name"
    exit 1
  fi
}

need "CLOUDFLARE_DNS_API_TOKEN or CLOUDFLARE_API_TOKEN" "$CF_TOKEN"
need "LETSENCRYPT_EMAIL or ACME_EMAIL" "$LE_EMAIL"

echo "== Install/upgrade cert-manager $CERT_MANAGER_VERSION =="
$KUBECTL apply -f "https://github.com/cert-manager/cert-manager/releases/download/${CERT_MANAGER_VERSION}/cert-manager.yaml"
$KUBECTL -n cert-manager rollout status deploy/cert-manager --timeout=180s
$KUBECTL -n cert-manager rollout status deploy/cert-manager-cainjector --timeout=180s
$KUBECTL -n cert-manager rollout status deploy/cert-manager-webhook --timeout=180s

echo "== Create Cloudflare DNS API token secret =="
# The token goes in on stdin (--from-file=/dev/stdin), never in argv where `ps` could show it.
printf '%s' "$CF_TOKEN" | $KUBECTL -n "$CERT_NAMESPACE" create secret generic cloudflare-api-token-secret \
  --from-file=api-token=/dev/stdin \
  --dry-run=client -o yaml | $KUBECTL apply -f -

apply_issuer() {
  local name="$1"
  local server="$2"
  cat <<YAML | $KUBECTL apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: $name
spec:
  acme:
    email: $LE_EMAIL
    server: $server
    privateKeySecretRef:
      name: ${name}-account-key
    solvers:
    - dns01:
        cloudflare:
          apiTokenSecretRef:
            name: cloudflare-api-token-secret
            key: api-token
YAML
}

apply_certificate() {
  local cert_name="$1"
  local issuer_name="$2"
  local secret_name="$3"
  cat <<YAML | $KUBECTL apply -f -
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: $cert_name
  namespace: $CERT_NAMESPACE
spec:
  secretName: $secret_name
  issuerRef:
    name: $issuer_name
    kind: ClusterIssuer
  dnsNames:
  - $DOMAIN
  - "*.$DOMAIN"
YAML
}

verify_certificate() {
  local host="glance.$DOMAIN"
  echo "== Verify certificate presented by Traefik for $host =="
  if command -v openssl >/dev/null 2>&1; then
    openssl s_client -connect "${WATOOM_K3S_HTTPS_ENDPOINT:-10.99.20.225:443}" -servername "$host" </dev/null 2>/dev/null \
      | openssl x509 -noout -issuer -subject -dates -ext subjectAltName
  else
    echo "openssl not found; skipping certificate decode"
  fi
}

apply_issuer "letsencrypt-cloudflare-staging" "https://acme-staging-v02.api.letsencrypt.org/directory"
apply_certificate "watoom-internal-wildcard-staging" "letsencrypt-cloudflare-staging" "watoom-internal-wildcard-staging-tls"

echo "== Wait for staging certificate =="
$KUBECTL -n "$CERT_NAMESPACE" wait --for=condition=Ready certificate/watoom-internal-wildcard-staging --timeout=20m

if [ "$STAGING_ONLY" = "true" ]; then
  echo "STAGING_ONLY=true, stopping before production issuance."
  exit 0
fi

apply_issuer "letsencrypt-cloudflare-prod" "https://acme-v02.api.letsencrypt.org/directory"
apply_certificate "watoom-internal-wildcard-prod" "letsencrypt-cloudflare-prod" "watoom-internal-wildcard-prod-tls"

echo "== Wait for production certificate =="
$KUBECTL -n "$CERT_NAMESPACE" wait --for=condition=Ready certificate/watoom-internal-wildcard-prod --timeout=20m

# One mechanism for first install and every renewal (T-0116): validate, update the canonical host material that
# homelab_rebuild's local_tls role reconciles from, then refresh each existing watoom-tls / watoom-code-lan-tls copy.
# Routes already reference watoom-tls, so no route patching or repo-wide apply is needed.
echo "== Distribute the production certificate =="
python3 "$ROOT/scripts/sync-internal-tls.py" --source-namespace "$CERT_NAMESPACE" \
  --source-secret watoom-internal-wildcard-prod-tls --domain "$DOMAIN" --canonical-dir "$CANONICAL_TLS_DIR"
verify_certificate

echo "Renewals: install the daily sync timer with the homelab_rebuild local_tls tasks if not already present."

echo "Done. Browsers should trust https://*.$DOMAIN once local DNS points those names at Traefik."
