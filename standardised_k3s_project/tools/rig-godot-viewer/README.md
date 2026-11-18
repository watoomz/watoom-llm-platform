# rig-godot-viewer: open an asset in Godot on the rig

Run on the rig (Windows). Drag a `.glb` / `.gltf` / `.tscn` file, or a whole Godot-ready folder such as a converted MetaHuman, onto
`Open-InGodot.bat`, or double-click it and pick a file. A viewer window opens on the rig's own GPU:

| Input | Action |
|---|---|
| left-drag / right-drag / wheel | orbit / pan / zoom |
| `F` / `R` | frame the asset / reset the view |
| `1` `2` `3` `4` | shaded / unshaded / wireframe / normals (use `2` to separate texture problems from lighting problems) |
| `L` / `G` / `B` | cycle lighting / toggle grid / cycle background |
| `A` | play the first animation, if any |
| `Tab` | hide the info text (mesh, surface, vertex, bone counts; size in metres) |

`Open-InGodot-Editor.bat` opens the Godot editor on the same staged project instead.

How it works: the script copies the asset's folder into `%LOCALAPPDATA%\WatooM\godot-viewer\project`, lets Godot import it (a large asset takes a
few minutes the first time; unchanged assets reopen immediately), and opens `viewer/viewer.tscn`. A converted scene names its textures as
`res://metahuman/<Name>/...`, so the folder is staged exactly where those paths expect (found by checking which prefix makes every referenced
file exist); a bare glb goes to `res://asset/`. Folders over 3 GB stage only the chosen file. Nothing outside the cache folder is written.

Godot is found, in order, from `WATOOM_GODOT`, the path saved in `%LOCALAPPDATA%\WatooM\godot-viewer\godot-path.txt`, the pinned rig runtime
`F:\WatooM\rig-async-stage-20261026\runtime\godot-4.7.2\Godot_v4.7.2-stable_win64.exe`, then a search of `F:\WatooM` and `F:\AI`; if none exists it asks once.

Get the asset to the rig however you normally move files (the MetaHuman Godot output is a plain folder: `.../Base_Female/godot-skin2`). The viewer
itself was verified on Bazzite with the Base_Female MetaHuman (the `viewer/` project, framing, orbit, wireframe); the PowerShell launcher has not been
run on the rig yet, and the prefix detection was checked against the real MetaHuman folder only.
