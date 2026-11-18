# rig-godot-run: run the latest version of a Godot project on the rig

`Run-GodotProject.bat` (or `Run-GodotProject.ps1`) mirrors a Godot project from its source folder into a local cache and runs it. Run it on the rig (Windows).

```
Run-GodotProject.bat -Source \\server\share\zombie-animal-survival -Name zombie     first time: remembers the source
Run-GodotProject.bat -Name zombie                                                    after that: syncs changes, then runs
```

What it does each run: `robocopy` mirrors the source into `%LOCALAPPDATA%\WatooM\godot-projects\<Name>` (new and changed files only, deleted files removed), keeps the local
Godot import cache, imports if anything changed, then starts Godot. The first run copies everything; later runs take seconds.

It skips folders a player never needs: `.godot`, `.git`, `.opencode`, `.source-backup`. Add more with `-Exclude World,Videos`; use `-Full` to include the usual skips (except `.git` and `.godot`).
If two folders differ only by capital letters (for example `assets` and `Assets`), Windows cannot hold both, and cannot even walk them reliably over the share: the script never scans those folders, decides from the project's other files which one is used (scenes and scripts referring to `res://Assets/`), keeps that one and skips the other, with a warning. `-KeepFolder Assets` forces the choice.

| Option | Effect |
|---|---|
| `-Console` | run the console build in this window so engine messages stay visible |
| `-Editor` | open the editor instead of running the game |
| `-NoSync` | run what is already local |
| `-Check` | show what a sync would copy, change nothing |
| `-KeepFolder` | which of two case-clashing folders to keep, e.g. `-KeepFolder Assets` |
| `-Reset` | delete the local copy and copy everything again |

Godot is found from `WATOOM_GODOT`, the path saved in `%LOCALAPPDATA%\WatooM\godot-run\godot-path.txt`, the pinned rig runtime
`F:\WatooM\rig-async-stage-20261026\runtime\godot-4.7.2\`, or a one-time file picker.

## Where the source comes from
The lab shares `/data/ai/projects` read-only for the rig (`playbooks/projects-share.yml`). After the operator sets the share password, map it once on the rig:

```
net use P: \\10.99.20.225\projects /user:rigshare /persistent:yes
```

then point the script at a project inside it, for example `-Source P:\games\zombie-animal-survival -Name zombie`. Any other folder the rig can read works too.

Status: written and reviewed, not yet run on the rig (no PowerShell on the lab).
