# gg-export: ship a smoke-tested level (3D)

```bash
python3 scripts/gg_export.py status --project /abs/path/game
python3 scripts/gg_export.py build  --project /abs/path/game [--preset pck|linux|windows] [--out DIR]
```
Output goes to `<project>/gg_data/export/<preset>/` (`game.pck`, `game.x86_64` or `game.exe`, `export.log`, `export_ok.json`).

## Rules

- Refuses (exit 2) unless `smoke_ok.json` is valid. If you synced the runtime or changed the level, run `gg_player.py build` and `gg_player.py smoke` again.
- Refuses a preset that is not in `gg_project.json` `export.presets` (default `["pck"]`).
- `linux` and `windows` need the Godot export templates for the exact engine version in `~/.local/share/godot/export_templates/<version>` (download `Godot_v4.7.2-stable_export_templates.tpz` from the godot GitHub release; the zip's `templates/` files go in that folder). On this host (2026-11-17) only `linux_debug.x86_64`, `linux_release.x86_64` and `version.txt` are installed, so `linux` is verified and `windows` still refuses. Add the preset name to `export.presets` first.
- The project is never changed. A copy without `gg_data`, `.godot`, `.git` and `.opencode` is staged in `gg_data/export/stage`, its `run/main_scene` is set to the level (the project's own main scene is the boot scene), and the export runs from the copy.
- For `linux` the binary is also run like a player would run it (xvfb, forward_plus, 90 frames with `--write-movie`): the log must be clean, the process must exit 0 with the frames recorded, and the last frame must not be flat (std >= 0.03, >= 500 colours) and must match the smoke test's start shot (mean abs diff <= 0.05, measured 0.010). Release templates ignore `-s`, so `pack_check` cannot run inside the binary; it runs on the `game.pck` beside it with the editor binary instead. A binary without its `game.pck` fails (exit 4).
- The result is proven, not assumed: the pack is loaded by the engine (`--main-pack`) and the `pack_check` op instances the level, then confirms a `Player` and a `Camera3D` exist and that `gg_data` is not inside. Exit 3/4/5 as everywhere.

## Verified by running (Godot 4.7.2)

256 m low-poly third-person island with creek, trees and boulders: `build` exported a 572 KB `game.pck`; the pack loaded with 326 nodes, a player and a camera, main scene the level, no `gg_data`. `linux` preset: 73.5 MB `game.x86_64` + `game.pck`; the binary ran 90 frames on the GPU with a clean log, std 0.126, 5588 colours, start diff 0.010. Not verified: the windows binary, 2D levels, driving the exported game with input (the smoke test covers gameplay on the source project), a headless-only host.
