# Repository orientation for model-assisted work

Start at the repository root `AGENTS.md` and `standardised_k3s_project/AGENTS.md`, then load only relevant instructions. Production/operator checkout: `/data/github/watoom-standardised-homelab`. Separate model development checkout: `/data/github/watoom-homelab-dev`, branch `dev`, backed by its dedicated local Git server. Repository visibility does not enable the isolated modifying developer tool; preserve its current activation policy.

## Where to look

- `ansible/roles/watoom-code`: durable application policies, native plugins, skills, worker installation and resource templates.
- `ansible/roles/opencode-agent/files/v2-native/agents`: coordinator, builder, investigator, critic and reviewer role boundaries.
- `tools/watoom-code`: native guarded deployment/recovery helpers, capture contracts, regression checks and recorded app source bundles/manifests under `source/`.
- `tools/rig-async-stage` (its `worker-source/` is what the workstation-render-stage role installs), `tools/bazzite-render-worker`: external queue/worker staging. Inspect current live qualification before claiming a route active. Bazzite-first routing remains staged.
- `tools/game-template-catalogue`: pinned Godot sources, owner-requested Unreal archive metadata, safe installation and combined catalogue generation. Actual source projects and original archives are under `/data/ai/game_templates` and are not Git content.
- `config/llm`, `ansible/roles/llm-model-lab`, `tools/llm`: model artifact provenance, serving/controller contracts and ownership. Inspect live state; do not switch models or GPU ownership from historical notes.
- `docs/JOB_REFERENCE.md`, `config/glance/guide`: user-facing workflow references.

Critic evaluates diagnoses/proposed next actions; investigator fills a specific evidence gap; builder implements; reviewer assesses finished outputs; coordinator owns scope/checkpoints. Broad reads do not grant repair or heavy-engine execution. Read `tools/watoom-code/READ_ACCESS_POLICY.md` for native diagnostic approvals and `VISUAL_RECEIPT_CONTRACT.md` for pixel receipt integrity.

Sources can describe staged functionality that is not live. Distinguish source, deployed policy, worker receipt, engine compatibility and actual visual acceptance. Do not import an installed game template into an existing project without explicit scope. Keep purchased originals and unrelated dirty work intact.

Operator refresh: after production `main`, `dev`, `origin/main` and `origin/dev` agree on a published SHA, `python3 tools/watoom-code/dev_workspace/refresh.py <sha>` fast-forwards the clean model dev checkout and its local server under the existing dev serial lock. It preserves task records, rejects active tasks/divergent history and does not enable the developer tool or rewrite its initial-baseline receipt.
