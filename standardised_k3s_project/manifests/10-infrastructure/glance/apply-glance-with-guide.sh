#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
kubectl apply -f "$HERE/glance.yml"
if [[ -f "$HERE/99-glance-guide-integration.yml" ]]; then
  kubectl apply -f "$HERE/99-glance-guide-integration.yml"
fi
kubectl -n glance rollout restart deployment/glance
kubectl -n glance rollout status deployment/glance --timeout=180s
