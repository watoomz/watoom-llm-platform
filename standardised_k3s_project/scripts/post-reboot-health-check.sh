#!/usr/bin/env bash
# WatooM operator notes:
# - Purpose: Runs the standard after-reboot health checks for DNS, HTTPS routes, pods, and key services.
# - Style: fail fast, print what is happening, and keep paths rooted in the repo unless the script is intentionally touching host state.
# - Safety: review kubectl, docker, hostPath, VPN, and secret-handling commands before running on a live node.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
LAN_IP="${LAN_IP:-10.99.20.225}"
DMZ_IP="${DMZ_IP:-192.168.250.225}"
LAN_IFACE="${LAN_IFACE:-enp34s0.20}"
DMZ_IFACE="${DMZ_IFACE:-enp35s0}"

export KUBECONFIG

section() {
  printf '\n== %s ==\n' "$1"
}

code_for() {
  local host="$1"
  curl --noproxy '*' -k -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 5 --max-time 12 \
    --resolve "${host}.internal.homelab.example:443:${LAN_IP}" \
    "https://${host}.internal.homelab.example/" 2>/dev/null || true
}

section "Network"
ip -br addr show dev "$LAN_IFACE" || true
ip -br addr show dev "$DMZ_IFACE" || true
ip route | grep -E 'default|10\.5\.20|192\.168\.0' || true
ping -c 2 -W 2 10.99.20.1 || true

section "Kubernetes"
kubectl get nodes -o wide
kubectl get pods -A | grep -E 'CrashLoopBackOff|CreateContainerConfigError|ImagePullBackOff|ErrImagePull|Pending|Error|Unknown|ContainerCreating' || echo "OK: no obvious problem pods"

section "DNS"
for h in pihole glance immich grafana prometheus vaultwarden iac-console; do
  ans="$(dig +short "@${LAN_IP}" "${h}.internal.homelab.example" A | tail -n1 || true)"
  printf '%-12s %s\n' "$h" "${ans:-no-answer}"
done

section "HTTPS routes"
for h in pihole glance immich grafana prometheus audiobookshelf bazarr dispatcharr jellyfin lidarr plex prowlarr qbittorrent radarr sabnzbd seerr sonarr vaultwarden iac-console; do
  printf '%-16s %s\n' "$h" "$(code_for "$h")"
done

section "Game services"
kubectl get svc -A -o wide | grep -E 'cs2|dayz|enshrouded|valheim|minecraft|arma' || true

section "Game and VPN ports on host"
ss -lntup | grep -E '27015|2302|2303|2304|2305|2456|2457|2458|2459|15636|15637|25565|25566|8095|51820|51821' || true

section "Docker edge stacks"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E 'wg-easy|azuracast|stream-' || true

section "Disks"
df -h / /app /data

section "Desktop"
systemctl is-active plasmalogin.service || true
systemctl get-default || true
nvidia-smi --query-gpu=name,driver_version,memory.total,temperature.gpu --format=csv,noheader || true
google-chrome --version || true
docker --version || true
docker compose version || true
docker-compose --version || true

section "Audio"
cat /proc/asound/cards 2>/dev/null || true
if id watoom >/dev/null 2>&1 && [[ -d /run/user/$(id -u watoom) ]]; then
  sudo -u watoom XDG_RUNTIME_DIR="/run/user/$(id -u watoom)" pactl list short sinks 2>/dev/null || true
fi

section "Result"
echo "Health check complete."
