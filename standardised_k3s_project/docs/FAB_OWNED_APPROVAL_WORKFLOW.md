# Owned Fab library and approval workflow
The public catalog is `/data/ai/assets/catalog/fab-owned.json`, built from authenticated server `epic-fab list --json`. Initial refresh: 629 entries. It contains no credentials or signed download URLs. Native skill `watoom-fab-owned-assets` documents discovery, owner question, request and preparation acceptance.

Operator commands use `tools/fab/owned_catalog.py`:
- `refresh` refreshes authenticated inventory (no downloads).
- `request --project ... --asset-id ... --reason ... --preparation-plan ...` creates project request and canonical hash.
- `approve --request ... --owner-approval-evidence ...` only after actual human approval; root-only, private immutable request binding.
- `fulfill --approval <hash>` uses existing downloader and Toolkit index, preserving checksums/partials and returning a project receipt. It never executes acquired code. Repeated fulfillment is rejected for reconciliation.

The maintained watoom-fab-approvals.timer polls project requests once per minute. A root-owned worker matches the same project coordinator session, completed native question tool, exact request hash/ID/project/title/reason/plan and explicit Approve download answer. It creates a private approval, fulfills via the existing downloader/index and resumes that same session for preparation. Agent-written files and prose alone never approve downloads. Preparation follows supported existing workers; complete textures/materials/dependencies and target-engine validation are required before READY. Unsupported formats/operations are explicit gaps, not silent fallbacks. All assets remain candidates independent of portability. No new acquisition was approved by setup.
