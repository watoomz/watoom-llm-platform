# Setting up the worker machines

The LLM platform runs on one Linux host (k3s). The game/creative agents can also hand heavy jobs (Godot, Blender, Unreal)
to extra machines. This page says what the repo sets up for you and what you do by hand. **Network access and file
permissions between the machines are yours to arrange** (SSH keys, firewall, shares).

Honest status: the lab (server) side is infrastructure-as-code. The worker machines are only **partly** scripted, and
none of it has been run from a blank machine, so expect to follow these steps by hand the first time.

## Lab side (this repo, automated)
- k3s manifests for the workers' queues and bridges (`manifests/10-infrastructure/opencode`, `platform-workers`).
- `ansible/roles/workstation-render-stage` creates the restricted SFTP area a Windows worker uses (`sftp.conf.j2`).
- `ansible/playbooks/worker-status.yml` installs the status collector behind the command-center Workers panel.
- `tools/watoom-code/` holds the game-worker bridge, receipts and Bazzite/rig wrappers (`game_worker_bridge.py`, `game_bazzite.py`, ...).

## Linux worker (the "Bazzite" role: rootless podman + SSH, runs Godot/Blender headless)
Automated or scripted here:
- `tools/bazzite-render-worker/install-blender.py` installs a SHA-verified portable Blender.
- `tools/bazzite-render-worker/qualify-*.py` check GPU and memory limits before you route work to it.
- `tools/watoom-toolkit/Containerfile*` build the toolkit images the jobs run in.
- The lab-side helper stages runtimes and launches resource-limited systemd units per job.

You do by hand:
1. Install a Linux distribution with podman and systemd; create a normal user for jobs (the code assumes `watoom`; change it in the wrappers if you prefer another).
2. Authorise the lab's SSH key for that user; keep the connection details out of git (the code reads them from a root-only file on the lab).
3. Make sure systemd user lingering and cgroup memory/CPU limits work for that user.
4. Run the qualify scripts; only then enable routing (`tools/bazzite-render-worker/routing-policy.json`).

## Windows worker (the "RIG" role: Godot, Blender, Unreal, outbound SFTP only)
Scripted here:
- `tools/rig-async-stage/worker-source/Install-StageWorker.ps1` and `Rig-Jobs.ps1` install the polling worker and the pause/resume controls.
- `tools/rig-async-stage/unreal-lane/` (`build_lane.py` on the lab, then `Install-UnrealWorker.ps1` on the worker) installs the Unreal lane.
- `tools/rig-godot-run/` and `tools/rig-godot-viewer/` are helpers for opening and running projects.

You do by hand:
1. Install Godot (the version pinned in the docs), Blender and, for the Unreal lane, Unreal Engine plus the MetaHuman plugin.
2. Create the Windows user, install the OpenSSH client, and add the key for the lab's SFTP jail user.
3. Open outbound access to the lab's SFTP port; the worker polls, so nothing listens on the Windows machine.
4. Run the installers above from a copy of the built bundle.

## Not covered yet
There is no single role or playbook that builds either worker end to end. Writing a Linux worker role (user, podman,
limits, Blender, toolkit image) would be the natural next step.
