# Overnight fixes — 22 October 2026 (Brisbane)

Owner requested a pause and overnight issue repair. The native coordinator interruption left no active sessions; the hourly automation is PAUSED. Do not resume without the owner asking.

## Production source and IaC
- Read-only critic/investigator/reviewer instructions now document explicitly allowed game and Blender Asset Builder evidence roots. Critic external-directory rules permit those paths while writes/shell and unrelated directories remain denied. Native permission evaluator fixtures passed.
- Native coordinator guard rejects a completed child containing simulated tool-call XML. It retains the existing child, bounds recovery to two returns, and then reports a hard blocker instead of silently declaring completion or creating replacement children. XML is never executed.
- Full test_runner.gd shell commands are fenced out of the 2GiB app control plane. Require the bounded external operator worker and its actual test receipt. Partial results followed by exit137 are failures, not expected acceptance.
- Native guard regression suite passes, including simulated-call reconciliation and app-shell regression fencing. Scoped native-agents and guard playbooks deployed; exact plugin hash and installed agent sources verified. No app rollout, model change or network change.

## Candidate project corrections
The baseline isolated 3GiB CPU worker completed with119 passed/5 failed and36 runtime errors. The four new Shepherd tests plus stuck-recovery test could not load the scene. Fixed invalid TSCN comment markers and removed the problematic temporary imported-scene type inference/dangling AnimationPlayer reference by copying animation resources from the live model. Animation root paths now resolve from each external player to its actual model.

The original mount implementation teleported the dog underneath a flying bird. The bird now approaches and attaches to the dog's mount offset while its normal flight integration is suspended during mount transitions/riding; the dog retains its position/AI ownership. The regression checks that a moved dog carries the bird rather than teleporting to it. The out-of-tree follow test now checks intended horizontal velocity, since move_and_slide does not run on those fixtures and vertical separation does not establish a horizontal leash breach.

Raw purchased assets and delivered GLBs were preserved. Project backups, baseline/follow-up receipts and activation evidence are in /data/ai/helper-scripts/reports/overnight-fixes-20261022. Game changes live in the existing candidate project; infrastructure and agent changes are maintained in this repository. No staging/commit/push performed.

These are code/transport validations, not new pixel-based visual acceptance. Remaining original feature milestones must not be declared complete from these fixes.

## Final validation

Final isolated CPU regression: **124 passed, 0 failed, 0 runtime errors**, exit0, MemoryMax3GiB, peak2772336640 bytes. The source still matched the tested snapshot after execution. Public receipt: `.opencode/validation/operator-godot/godot-final-3g.json` in the candidate project. Additional runtime corrections: TargetSystem is RefCounted with Array-backed entities; detached physics fixtures require local-coordinate fallback; mount time thresholds tolerate floating-point accumulation.

The production job and hourly automation remain paused. No AI session was resumed. Remaining original combat/abilities/environment and visual acceptance milestones are outside these overnight bug repairs; do not infer full project completion from the regression pass.
