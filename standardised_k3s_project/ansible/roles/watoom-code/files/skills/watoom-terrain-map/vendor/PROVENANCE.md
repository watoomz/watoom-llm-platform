# Vendored: Terrain3D

- Upstream: https://github.com/TokisanGames/Terrain3D
- Version: v1.1.0-stable (release id 428774085, published 2026-10-30)
- Upstream archive: `Terrain3D_v1.1.0-stable.zip`, sha256
  `51b78bc758f5759cbc8eaaab14e5cf4e8661717e265fdd760f5abf945f15b243`,
  45,665,295 bytes, from
  https://github.com/TokisanGames/Terrain3D/releases/download/v1.1.0-stable/Terrain3D_v1.1.0-stable.zip
- License: MIT. Copyright (c) 2023-2026 Cory Petkovsek, Roope Palmroos, and
  Contributors. Full text: `addons/terrain_3d/LICENSE.txt` (copied verbatim
  from the upstream archive).
- Compatibility: `compatibility_minimum = 4.5` (from the upstream
  `.gdextension` file). The homelab's pinned Godot is 4.7.2.

## What was trimmed from the upstream archive

The upstream zip is 86 MB extracted (every platform/arch/debug combination
plus the demo project). We keep only what this homelab actually targets:

- `addons/terrain_3d/bin/`: kept `libterrain.{linux,windows}.{debug,release}.x86_64.*`
  (4 files, ~16 MB). Dropped android/ios/macos/web and all non-x86_64 arches.
  `terrain.gdextension` was edited to list only those 4 library entries (the
  upstream file lists every platform; ours is honest about what's actually
  here). To restore a dropped platform: re-download the upstream zip at the
  pinned version above, copy the needed `bin/libterrain.*` file in, and add
  its line back to `terrain.gdextension` from the upstream copy.
- Dropped `demo/` entirely (the Terrain3D example project, not needed to use
  the addon in our own projects).
- Kept `brushes/`, `icons/`, `src/` (the editor-plugin GDScript, needed by
  `plugin.cfg`'s `script="src/editor_plugin.gd"`), `plugin.cfg`,
  `terrain.gdextension`, `LICENSE.txt`, `README.md` unmodified.

## Verified (2026-11-13, this session, against the actually-installed godot-4.7.2-1.fc44 Fedora package)

- The trimmed `linux.release.x86_64`/`linux.debug.x86_64` libraries load:
  `ClassDB.class_exists("Terrain3D")` is true, the class instantiates, and
  `region_size` reads its documented default (256).
- `Terrain3DData.import_images([height_image, null, null], global_position,
  offset, scale)` successfully imported this project's own real DEM heightmap
  (`zombie-animal-survival/World/terrain/heightmap.exr`, 513x513) into 9
  regions, and `terrain.data.get_height(...)` returned a plausible real
  elevation (86.6 m, inside the source DEM's actual 36.78-184.42 m range).
  `Terrain3DData.save_directory(...)` wrote 9 real `.res` region files.
- **Known limitation, confirmed by test, not by documentation**: the editor
  plugin (`--headless --editor` with the plugin enabled in
  `[editor_plugins]`) segfaults in pure headless mode on Linux with no
  display (`timeout: the monitored command dumped core`, no further
  diagnostic) -- but only AFTER the asset reimport/extension-discovery pass
  it exists for has already finished and been written to `.godot/`, so a
  project that is primed this way once still ends up correctly usable;
  `install_terrain3d.py`'s `prime_import()` runs this crashing pass
  deliberately and ignores its exit code, exactly once per project (skipped
  on later runs once `.godot/imported/` exists). Direct `Terrain3D`-node/
  `Terrain3DData` usage via
  `godot --headless --rendering-driver dummy --script <file>.gd <project>`
  (a plain `SceneTree` script, NOT going through the editor plugin) does not
  hit this and is fully reliable -- this is exactly how `install_terrain3d.py`
  bakes height data, and it is the only Linux-headless path this vendoring
  relies on. Opening the real Godot EDITOR with this addon (to paint textures,
  place foliage, etc.) needs an actual display/GPU -- i.e. the Windows rig,
  which is the addon's normal supported environment and was not itself
  re-tested this session.
