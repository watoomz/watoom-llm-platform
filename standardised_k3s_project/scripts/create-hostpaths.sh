#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Creates host directories used by hostPath-backed workloads. Run before first deploy or after rebuilding a node so pods can mount expected paths.
# - Style: fail fast, print what is happening, and keep paths rooted in the repo unless the script is intentionally touching host state.
# - Safety: review kubectl, docker, hostPath, VPN, and secret-handling commands before running on a live node.
set -euo pipefail
# Standard host directories used by manifests. /app is app/config/persistence. /data is media/download library data.
dirs=(
  /app/glance  
 /app/grafana/data /app/prometheus/data  
  /app/home-assistant/config 
  /data/iac-web-console/audit
  /data/Movies /data/TV /data/music /data/audiobooks /data/podcasts /data/immich/library /data/downloads /data/downloads/incomplete /data/transcode/plex
)
for d in "${dirs[@]}"; do
  mkdir -p "$d"
  chmod 775 "$d" || true
done
