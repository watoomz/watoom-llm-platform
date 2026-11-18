# Project storage and captures

Canonical projects live under /data/ai/projects:
- games/<project> for games and game prototypes.
- development/<project> for application/development work.
- pipelines/<project> for standalone pipeline projects.

Application state, accepted toolchains, shared read-only assets, model data, build caches and private operational reports are infrastructure, not disposable projects. Their existing paths under /data/ai are preserved.

Write project captures to .opencode/captures/<task-id>/. Register a project once:
~~~sh
python3 /data/ai/helper-scripts/register-project-captures.py --project /data/ai/projects/games/PROJECT
~~~
View the same files under /data/ai/captures/games/PROJECT/<task-id>/. The common tree is a filesystem index, not another asset catalog. Registration refuses external roots, path escapes and conflicting existing destinations. Keep credentials, private logs and purchased source files out of captures.

Current HeroQuest home: /data/ai/projects/games/heroquest-quest1-poc.
Use fresh native sessions at canonical paths after project moves; do not preserve old project paths with compatibility symlinks. The application mounts games and development at their canonical paths with write access; shared /data/ai remains read-only and current Magpie remains protected. Do not create more legacy root projects.

Seven obsolete acceptance-test/old Magpie directories were archived, not deleted, under /data/ai/retired-projects/20261019-workspace-cleanup, preserving original relative paths. Exact move/rollback mapping: /data/ai/helper-scripts/reports/project-layout-cleanup-20261019/move-result.json. Restore only while no session/process references that project. Current Magpie, Hyper, paid assets, repositories, PVC/game data and infrastructure were preserved.

Apply layout without application rollout:
~~~sh
ANSIBLE_CONFIG=ansible/ansible.cfg ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts.yml ansible/playbooks/project-layout.yml
~~~

All retained application worktrees now live in development/, pipeline work in pipelines/, and original Moonstone source in games/moonstone-original. Legacy workspace snapshots are archived in /data/ai/retired-projects/20261019-project-layout. No project compatibility links are created. Git worktree backlinks and installed helper path references were repaired during migration; historical evidence is retained unchanged.
