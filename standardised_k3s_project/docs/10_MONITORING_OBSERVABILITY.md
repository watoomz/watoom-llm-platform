# Monitoring and Observability

## Current stack

| Component | Role |
|---|---|
| Prometheus | metrics collection and local alert rules |
| Grafana | dashboards |
| kube-state-metrics | Kubernetes object metrics |
| node-exporter | host metrics |
| Loki | log storage/query |
| Vector `vector-router-syslog` | RouterOS syslog ingestion |
| SNMP exporter | RouterOS SNMP scrape adapter |
| MKTXP | additional router metrics |
| DCGM exporter | NVIDIA GPU metrics |
| watoom-opencode-observability | OpenCode/router observability |

Grafana: `https://grafana.internal.homelab.example`
Prometheus: `https://prometheus.internal.homelab.example`

## router metrics

```text
RouterOS SNMP
  -> snmp-exporter.monitoring.svc.cluster.local:9116
  -> Prometheus
  -> Grafana
```

Vector listens for router syslog on host UDP 1514 and forwards/query-enables it through Loki according to the current monitoring manifests.

Keep SNMP credentials/community values in managed secret/config sources. Do not hard-code real credential values in this guide.

## LLM/GPU monitoring

DCGM exporter provides GPU metrics. The repository also contains a Qwen/llama.cpp Grafana dashboard and llama.cpp deployments expose metrics endpoints.

Useful checks:

```bash
nvidia-smi
kubectl -n monitoring get deploy,ds,svc
kubectl -n llama-cpp get deploy,pod
```

## Alerting status

Prometheus has local rules for conditions including exporter availability, filesystem pressure, sustained load and memory pressure. At the source-document baseline there was **no Alertmanager notification target configured**; alerts are visible in Prometheus/Grafana unless that architecture is changed later.

## Minimum post-change health signals

- k3s node Ready
- unexpected pod failures/pending states absent
- root, `/app`, `/data` capacity within limits
- Pi-hole DNS operational
- Traefik routes healthy
- Grafana and Prometheus reachable
- Docker stacks running as intended
- GPU visible when LLM workload is expected

## Controller and Mesh signals

Monitor the controller, Mesh bridge and credential timer alongside GPU metrics. A successful inactive recovery oneshot is normal. Controller state/journals and production job records under `/data/ai/llama-mesh/jobs` explain ownership transitions; retain them rather than treating them as disposable logs. Normal idle snapshot is `qwen-ready`, owner null, uncertain false; a live Mesh owner is not itself an outage.

Read-only commands and expected states: [operations runbook](13_OPERATIONS_RUNBOOK.md). Generation counters and VRAM usage are transient; never hard-code an idle generation as a health requirement.
