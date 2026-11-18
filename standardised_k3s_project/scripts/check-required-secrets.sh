#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Checks whether required generated Kubernetes secret files exist before deploying workloads that depend on private tokens or passwords.
# - Style: fail fast, print what is happening, and keep paths rooted in the repo unless the script is intentionally touching host state.
# - Safety: review kubectl, docker, hostPath, VPN, and secret-handling commands before running on a live node.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export KUBECONFIG

required=(
  "monitoring/grafana-secrets"
  "glance/glance-secrets"
)

missing=0
for item in "${required[@]}"; do
  ns="${item%%/*}"
  secret="${item##*/}"
  if kubectl -n "$ns" get secret "$secret" >/dev/null 2>&1; then
    printf 'OK      %s/%s\n' "$ns" "$secret"
  else
    printf 'MISSING %s/%s\n' "$ns" "$secret"
    missing=1
  fi
done

exit "$missing"
