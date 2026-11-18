#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Replace the temporary self-signed internal wildcard cert with a
#   browser-trusted Let's Encrypt wildcard issued through Cloudflare DNS-01.
# - Safety: Uses Let's Encrypt staging first, then production, to protect the
#   production rate limit from bad DNS/token configuration.
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

KUBECTL="${KUBECTL:-kubectl}"
CERT_MANAGER_VERSION="${CERT_MANAGER_VERSION:-v1.21.1}"
DOMAIN="${WATOOM_INTERNAL_DOMAIN:-internal.homelab.example}"
TLS_SECRET_NAME="${WATOOM_TLS_SECRET_NAME:-watoom-tls}"
# Fixed: cert-manager.yaml installs into cert-manager, and a ClusterIssuer reads its credentials Secret from that namespace,
# so the rollout checks, the Secret and the Certificates must all use it (an override would split them).
CERT_NAMESPACE=cert-manager
STAGING_ONLY="${STAGING_ONLY:-false}"
ENV_FILE="$ROOT/secrets/.env.local"

# Canonical host-side TLS material consumed by the homelab_rebuild local_tls
# role. A deliberate Let's Encrypt migration must update this source of truth,
# otherwise a later rebuild could reconcile the previous self-signed material
# back into the watoom-tls Secrets.
CANONICAL_TLS_DIR="${WATOOM_CANONICAL_TLS_DIR:-/data/watoom-local-tls}"
CANONICAL_TLS_CERT="${WATOOM_CANONICAL_TLS_CERT:-$CANONICAL_TLS_DIR/tls.crt}"
CANONICAL_TLS_KEY="${WATOOM_CANONICAL_TLS_KEY:-$CANONICAL_TLS_DIR/tls.key}"

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

persist_canonical_tls_material() {
  local source_secret="$1"
  local tmp_dir cert_pub key_pub
  tmp_dir="$(mktemp -d)"

  cleanup_canonical_tmp() {
    rm -rf "$tmp_dir"
  }
  trap cleanup_canonical_tmp RETURN

  echo "== Persist production certificate into canonical host TLS material =="
  $KUBECTL -n "$CERT_NAMESPACE" get secret "$source_secret" -o jsonpath='{.data.tls\.crt}' | base64 -d > "$tmp_dir/tls.crt"
  $KUBECTL -n "$CERT_NAMESPACE" get secret "$source_secret" -o jsonpath='{.data.tls\.key}' | base64 -d > "$tmp_dir/tls.key"

  # Fail closed before changing canonical material.
  openssl x509 -in "$tmp_dir/tls.crt" -noout >/dev/null
  openssl pkey -in "$tmp_dir/tls.key" -noout >/dev/null

  cert_pub="$(openssl x509 -in "$tmp_dir/tls.crt" -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum | awk '{print $1}')"
  key_pub="$(openssl pkey -in "$tmp_dir/tls.key" -pubout -outform DER | sha256sum | awk '{print $1}')"
  if [[ -z "$cert_pub" || "$cert_pub" != "$key_pub" ]]; then
    echo "ERROR: production certificate/private key mismatch; canonical TLS material was not changed" >&2
    return 1
  fi

  install -d -m 0700 "$CANONICAL_TLS_DIR"
  install -m 0644 "$tmp_dir/tls.crt" "$CANONICAL_TLS_CERT.new"
  install -m 0600 "$tmp_dir/tls.key" "$CANONICAL_TLS_KEY.new"
  mv -f "$CANONICAL_TLS_CERT.new" "$CANONICAL_TLS_CERT"
  mv -f "$CANONICAL_TLS_KEY.new" "$CANONICAL_TLS_KEY"

  echo "Canonical TLS material updated: $CANONICAL_TLS_CERT / $CANONICAL_TLS_KEY"
}

copy_tls_secret_to_namespaces() {
  local source_secret="$1"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' RETURN

  $KUBECTL -n "$CERT_NAMESPACE" get secret "$source_secret" -o jsonpath='{.data.tls\.crt}' | base64 -d > "$tmp_dir/tls.crt"
  $KUBECTL -n "$CERT_NAMESPACE" get secret "$source_secret" -o jsonpath='{.data.tls\.key}' | base64 -d > "$tmp_dir/tls.key"

  echo "== Copy $TLS_SECRET_NAME into app namespaces =="
  $KUBECTL get ns -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | while read -r ns; do
    case "$ns" in
      ""|cert-manager|kube-*) continue ;;
    esac
    $KUBECTL -n "$ns" create secret tls "$TLS_SECRET_NAME" \
      --cert="$tmp_dir/tls.crt" \
      --key="$tmp_dir/tls.key" \
      --dry-run=client -o yaml | $KUBECTL apply -f -
  done
}

patch_internal_ingressroutes() {
  echo "== Ensure internal Traefik routes reference $TLS_SECRET_NAME =="
  if ! $KUBECTL get crd ingressroutes.traefik.io >/dev/null 2>&1; then
    echo "IngressRoute CRD not found; skipping Traefik route patch"
    return
  fi

  $KUBECTL get ingressroute -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}' | while read -r ns name; do
    [ -n "${ns:-}" ] && [ -n "${name:-}" ] || continue
    if $KUBECTL -n "$ns" get ingressroute "$name" -o yaml | grep -q "$DOMAIN"; then
      $KUBECTL -n "$ns" patch ingressroute "$name" --type=merge \
        -p "{\"spec\":{\"tls\":{\"secretName\":\"$TLS_SECRET_NAME\"}}}"
    fi
  done
}

apply_repo_routes() {
  echo "== Apply repo manifests so route TLS config is permanent =="
  "$ROOT/scripts/apply-all.sh" "$ROOT"
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

persist_canonical_tls_material "watoom-internal-wildcard-prod-tls"
copy_tls_secret_to_namespaces "watoom-internal-wildcard-prod-tls"
patch_internal_ingressroutes
apply_repo_routes
verify_certificate

echo "Done. Browsers should trust https://*.$DOMAIN once local DNS points those names at Traefik."
