# WatooM — Software design (cross-project integration)

The canonical, rendered software design document lives in the guide and is published to Glance:

- Source: [`docs/guide/software-design.md`](guide/software-design.md)
- Rendered: `https://glance.internal.homelab.example/guide/software-design.html`

It documents how the separately developed WatooM projects — the homelab IaC in this repository, the
LLM/agent platform (WatooM Code, native agents, `llm-router` and the GPU-ownership controller),
`games/`, `images/` and the media stack — are wired into one system that shares a single host, GPU
and k3s cluster. Each integration seam is shown with the real code at that seam: inference routing
and GPU leases, the coordinator guard's vision-review evidence flow, the Glance observability spine,
and the change-control / publishing split.

Edit the guide source, then regenerate with the documentation renderer
(`scripts/render-glance-guide.py`); do not hand-edit the generated HTML. See
[`docs/16_DOCUMENTATION_MAINTENANCE.md`](16_DOCUMENTATION_MAINTENANCE.md).
