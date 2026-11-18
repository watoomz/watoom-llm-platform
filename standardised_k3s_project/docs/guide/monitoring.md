---
title: Monitoring and alerting
nav: Monitoring
summary: Metrics, logs and alert rules — what is collected, where it is visible and what each alert means.
---

## Stack

```text
node-exporter ─┐ (+ WatooM textfile metrics every 2 min)
kube-state-metrics ─┤
DCGM exporter (GPU) ─┤
SNMP exporter / MKTXP (router) ─┼──► Prometheus :9090 ──► Grafana :3000
WatooM observability :9108 ─┤            │ alert rules
llama.cpp /metrics ─┘            ▼
                             Prometheus Alerts page, Grafana, Glance

RouterOS syslog ──UDP 1514──► Vector ──► Loki :3100 ──► Grafana Explore
```

All components run in namespace `monitoring`. There is no Alertmanager: alerts are visible in Prometheus, Grafana and Glance, and are not pushed to a notification channel.

## Alert rules

| Group | Alert | Meaning |
|---|---|---|
| `watoom-node-health` | `WatoomNodeExporterDown` | Host metrics missing |
| | `WatoomRootDiskHigh`, `WatoomAppDiskHigh`, `WatoomDataDiskHigh` | Filesystem pressure on `/`, `/app`, `/data` |
| | `WatoomNodeLoadHigh`, `WatoomMemoryLow` | Sustained CPU load or low available memory |
| `watoom-platform` | `WatoomRootDiskAbove80`, `WatoomDataVolumeAbove90` | Capacity thresholds (90% for 30 min on `/data`, `/app`) |
| | `WatoomPodEvicted` | Kubelet evicted a pod (usually disk or memory pressure) |
| | `WatoomSystemdUnitFailed` | A host unit is in `failed` state |
| | `WatoomBackupStale`, `WatoomOffhostBackupStale` | WatooM Code backup or its off-host pull is overdue |
| | `WatoomNodeTextfileStale` | The textfile metrics publisher stopped |
| `watoom-opencode-local-llm` | `WatoomQwenCoderUnavailable` | Primary model not serving |
| | `WatoomGpuMemoryCritical` | VRAM near exhaustion |
| | `WatoomLlmRouterRepeatedFailures` | Router errors over the window |
| | `WatoomQwenTruncationObserved` | Responses hit the output limit |
| | `WatoomOpenCodeWatchdogActivated`, `WatoomOpenCodeCompactionFrequencyHigh` | Agent runtime stalled, or context compacting unusually often |
| | `WatoomOpenCodeObservabilityExporterDown` | The WatooM exporter is down |

Rules are defined in `manifests/10-infrastructure/monitoring/`. Query live state:

```bash
kubectl -n monitoring exec deploy/prometheus -- wget -qO- http://127.0.0.1:9090/api/v1/alerts \
  | jq -r '.data.alerts[] | select(.state=="firing") | .labels.alertname'
```

## GPU and model signals

DCGM provides utilisation, VRAM, power and temperature. llama.cpp exposes `/metrics` (tokens per second, KV usage, slot state). The WatooM exporter adds controller phase and owner, router failures and agent watchdog metrics.

The controller's normal idle snapshot is `phase=qwen-ready`, `owner=null`, `uncertain=false`. A non-null owner during a Mesh job or model switch is expected, not an outage.

## Post-change health

After any change, confirm:

- node `Ready`, no unexpected `Pending`/`Failed` pods
- `/`, `/app`, `/data` below alert thresholds
- Pi-hole resolving, Traefik routes answering
- Grafana and Prometheus reachable, no new firing alerts
- Compose stacks running
- GPU visible and the primary model serving when inference is expected

```bash
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
systemctl --failed --no-pager
docker compose ls
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
```
