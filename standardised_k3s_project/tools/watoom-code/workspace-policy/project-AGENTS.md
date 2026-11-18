<!-- WATOOM HOMELAB LLM PROJECT v2 -->
# Agent Export & LLM project
These rules apply only when the Git root is `/data/ai/projects/homelab/homelab-llm`; other checkouts retain their own policies.
Repository: /data/ai/projects/homelab/homelab-llm, independent dev-based clone.
Branch: agent/homelab-llm. WatooM-Code/OpenCode models integrate only into `dev`, after validation; they never modify, merge or push `main`, so main is never broken by an unreviewed model change. Only the owner's operator assistant (Claude Code), when the owner asks, publishes validated fixes to `main`. Never force-push, rewrite history or use broad staging.
Canonical /data/github/watoom-standardised-homelab is read-only inside OpenCode.
Use watoom-homelab-ai and search the native/imported skill catalogue for the task. Existing agents, model and memory integrations remain global; discover them rather than installing replacements.
Keep checkpoints under .opencode/work/<task>/progress.md and project artifacts under .opencode/artifacts/. Record evidence, changes, validation, blockers and next action before yielding.
New sessions and descendants are tool-guarded to this checkout. Direct read/write/edit are available; shell/code, arbitrary native delegates and workers are unavailable until an OS sandbox is qualified. Do not claim full filesystem isolation. Ask the operator for the specific unsupported operation rather than attempting a bypass.
Do not relocate existing sessions or enroll IDX. Preserve ses_e810b0717ffdZUwatZP7vCnD3T and ses_e80e049e4ffeByyrVKa8ez81Vi and the IDX checkout/backup.
Keep production state, models, assets and volumes in their existing locations. No automatic production deployment, network changes, purchases, model switching or broad cleanup.
<!-- END WATOOM HOMELAB LLM PROJECT -->
