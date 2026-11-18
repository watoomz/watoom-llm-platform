---
name: observability
description: Use for Prometheus, Grafana, Loki, metrics exporters, dashboards, logging pipelines, and telemetry correctness.
---

# Observability

- Verify the metric/log actually exists before changing a dashboard query.
- Distinguish exporter semantics from presentation/query semantics.
- Prefer meaningful units/windows for sparse long-running workloads.
- Do not turn a missing metric into a fabricated dashboard value.
- For counters use `rate`/`increase` according to the question being displayed.
- Validate PromQL/LogQL directly against the backend before declaring a panel fixed.

## WatooM dashboard conventions

- Sparse local-LLM requests are often clearer as counts over a meaningful window than rounded req/s.
- llama.cpp completion counters may describe completed work rather than instantaneous in-flight throughput.
- Filter health-check noise from operational log panels.
- Prefer source dashboard JSON/IaC over live-only Grafana edits.
