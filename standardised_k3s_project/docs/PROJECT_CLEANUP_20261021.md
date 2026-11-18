# Project cleanup and operational relocation — 2026-10-21

Owner-approved policy: retain HeroQuest PoC, latest Magpie candidate, Moonstone remake and image projects. Relocate operational infrastructure using real directories, without symlinks. Preserve purchased assets and unrelated repository edits.

## Applied

- Isolated dev clone: `/data/github/watoom-homelab-dev`. HEAD and dirty status preserved; dedicated account can read the clone; all three isolation tests pass. Backend remains disabled, as found before migration. Maintained dev plugin, setup, activation, test and SELinux paths updated; no integration was enabled implicitly.
- Purchased staging assets: `/data/ai/assets/humble-staging`; atomic rename preserved directory inode and contents.
- Blender output history: `/data/ai/assets/generated/blender-asset-builder`; maintained and installed pipeline defaults updated.
- Deleted confirmed game tests: backups, hyper-combat-offline, moonstone-original, voxel-fps-v2-test, wombat-australia. Checked process cwd/executable and explicit workload hostPath references first. Kept all three requested game projects.
- Removed six obsolete top-level probes/test archive/cache items.
- Prepared protected `/data/ai/projects/images/generated` and copied existing immutable PNG/receipt runs with rsync checksum comparison. Existing publication root is still authoritative until fenced cutover.

## Prepared, not yet live

Planned host roots (defaults remain at current live locations until fenced cutover): development `/data/ai/workspaces/development`, pipeline workspace `/data/ai/workspaces/pipelines`, original Magpie asset source `/data/ai/assets/legacy-magpie-source`. Container compatibility mount paths remain unchanged, using real hostPath volumes rather than symlinks. Production build checkout Git worktree metadata must be repaired when moving development. Full rendered Kubernetes JSON and changed YAML parse successfully.

Model Manager output default and app nested read-only publication mount target `/data/ai/projects/images/generated`. Final checksum sync, broker root change and application rollout require idle image queue and native admission guard. Do not interrupt active generation/model restoration or steal its guard.

Shared hidden tool/state folders still require relocation and matching mounts before removal from projects. No claim that cleanup/cutover is complete.

Evidence: `/data/ai/helper-scripts/reports/projects-cleanup-20261021`.

Temporary queue maintenance marker was removed after verifying ownership; active operation was never interrupted.
