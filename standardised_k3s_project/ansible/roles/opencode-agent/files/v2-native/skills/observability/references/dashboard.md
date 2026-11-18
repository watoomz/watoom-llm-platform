# WatooM observability reference

- Sparse local-LLM requests are often clearer as counts over a meaningful window than rounded req/s.
- llama.cpp completion counters may describe completed work rather than instantaneous in-flight throughput.
- Filter health-check noise from operational log panels.
- Prefer source dashboard JSON/IaC over live-only Grafana edits.
