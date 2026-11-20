# Project storage and captures

Projects live under /data/ai/projects, one directory per space; the WatooM Code new-session picker groups them the same way (see `/data/ai/projects/AGENTS.md` and `watoom_code_project_spaces`):
- games/ for games and game prototypes.
- work/ and development/ for application and development work.
- writing/ for Writing Studio and creative-writer projects.
- images/ for image work.
- homelab/ for homelab tasks.
- llm/ for LLM tooling and pipeline projects.
- devices/ for hardware such as ESP32 boards.

Application state, accepted toolchains, shared read-only assets, model data, build caches and private operational reports are infrastructure, not disposable projects. Their existing paths under /data/ai are preserved.

Write project captures to .opencode/captures/<task-id>/. Register a project once:
~~~sh
python3 /data/ai/helper-scripts/register-project-captures.py --project /data/ai/projects/games/PROJECT
~~~
View the same files under /data/ai/captures/games/PROJECT/<task-id>/. The common tree is a filesystem index, not another asset catalog. Registration refuses external roots, path escapes and conflicting existing destinations. Keep credentials, private logs and purchased source files out of captures.

Start fresh native sessions at the new path after moving a project; no compatibility symlinks are kept. The application mounts the project spaces with write access; shared /data/ai stays read-only.

Apply layout without application rollout:
~~~sh
ANSIBLE_CONFIG=ansible/ansible.cfg ANSIBLE_ROLES_PATH=ansible/roles ansible-playbook -i ansible/inventories/homelab/hosts.yml ansible/playbooks/project-layout.yml
~~~
