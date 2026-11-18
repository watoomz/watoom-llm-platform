## Regression completion and receipts
Godot test summaries alone are insufficient: any SCRIPT ERROR/ERROR invalidates a clean validation, even with exit 0 or all printed PASS lines. A test must explicitly complete; an aborted call returning null must fail. Full startup/environment and owned-asset integration require real scene acceptance; logic fixtures should avoid rebuilding unrelated terrain/assets for every unit assertion. Consume the operator-published app-readable JSON under `<project>/.opencode/validation/operator-godot/`; private `/data/ai/helper-scripts/reports` logs require the operator, so do not retry denied reads or bypass permissions. Keep current source hashes and final worker receipt with the coordinator checkpoint.


