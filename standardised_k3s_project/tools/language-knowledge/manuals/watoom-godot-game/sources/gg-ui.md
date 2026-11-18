# gg-ui: UI and overlay games (a strip along the bottom of the screen, menus, idle games, HUDs)

`gg_ui.py` is for games whose product is a user interface, not a 3D level: it starts an empty UI project, runs your GDScript tests, renders a scene to a PNG that keeps its transparency and measures it, and reads back what the engine says about the overlay window. It never replaces looking at the PNG.

## Commands

```bash
python3 scripts/gg_ui.py init          --project /abs/path/game --name my_strip --width 1920 --height 240   # empty folder (a brief, assets/ and .opencode/ may already be there)
python3 scripts/gg_ui.py test          --project /abs/path/game                                              # runs res://tests/test_*.gd
python3 scripts/gg_ui.py shot          --project /abs/path/game --scene res://scenes/main.tscn --size 1920x240 --dock bottom --min-model-views 1 --name strip
python3 scripts/gg_ui.py overlay-check --project /abs/path/game                                              # the project's main scene
```
Exit codes: 0 pass, 1 a check failed (the FAIL lines say which), 2 refused (the message names the bad value), 3 fatal engine log line (a script parse error is exit 3 with the engine's message), 4 no verdict, 5 runner failure.

## What `init` gives you

`project.godot` for a transparent, borderless, always-on-top window on `gl_compatibility` (the worker has no GPU), `scenes/main.tscn` and `scripts/main.gd` (docks the window and nothing else: replace the body of `_ready`), `tests/test_overlay.gd`, `gg_ui.json`, and the runtime in `addons/gg/`. Do not edit `addons/gg/` or the window settings by hand; `gg_project.py sync-runtime` repairs the runtime.

`addons/gg/game/overlay_window.gd` is the tested docking helper: `dock_bottom(window, height_px, windowed)` makes the window full width, `height_px` tall, at the bottom of the usable screen (above the taskbar), borderless, always on top and transparent; `windowed_requested()` is true when the game was started with `-- --windowed`, which shows the same strip as a normal framed window for testing; `set_passthrough(window, rects)` lets clicks outside the union of `rects` fall through to the desktop; `strip_rect(usable, height)` is the pure geometry.

## Tests

```gdscript
extends "res://addons/gg/lib/gg_test.gd"
const Combat := preload("res://scripts/combat.gd")
func test_crit_doubles_damage() -> void:
	eq(Combat.damage(10, true), 20, "crit")
```
Every `test_*` method of every `tests/test_*.gd` is one test (it may `await`); `before_each()` runs before each. Assertions: `ok(cond)`, `eq(got, want)`, `near(got, want, tol)`, `between(got, lo, hi)`, `fail(msg)`; a failed assertion is recorded and the test goes on, so one run lists every broken check. A test with no assertions FAILS, and zero tests is a refusal (exit 2), never a pass. Keep game rules in plain scripts with no scene dependencies so tests can call them without a window. Seed random numbers (`RandomNumberGenerator.seed`) when you test a probability, and test it over many rolls with a tolerance.

## `shot`: what the numbers mean

The scene is drawn into a transparent viewport, so the PNG has alpha: empty (alpha under 16) means the desktop shows through there. The checks: `drawn` (share of drawn pixels), with `--dock bottom --screen WxH`: the window is the screen's width (+-2 px), at most `--max-height-frac` (0.4) of its height, and its bottom row is drawn; with `--expect-see-through`: some fully transparent pixels exist in the image; `nothing clipped` (no visible Control reaches outside the image); `buttons big enough` (each at least 24 px); `text size` (labels at least `--min-font`, default 11); each `SubViewportContainer` (a 3D model view) must be drawn and not flat (luma spread at least 4), and `--min-model-views N` demands at least N of them. The census is read back from the engine, not guessed from pixels. The report is `<project>/gg_data/ui_shot/<name>.report.json`. Open the PNG and look: layout, overlap and "does that look like an orc" are yours to judge.

## `overlay-check`: what it proves and what it cannot

It runs the main scene and reads back from the engine: borderless, always-on-top and transparent (the window flag OR the project setting), per-pixel transparency allowed, the window rectangle against the usable screen (full width, at most 40% high, bottom edge on the screen's bottom edge), and with `--require-passthrough` the passthrough polygon. It does NOT prove always-on-top stacking or per-pixel alpha against a real desktop: the worker has Xvfb and no compositor. Put "overlay behaviour on a real desktop: NOT VERIFIED" in your report and tell the owner how to try it (`godot --path <project>` and `-- --windowed` for the framed version).

## Models and icons from the asset library

Use only owned assets that are already converted or go through the documented conversion route (`watoom-fab-owned-assets`: `asset_advisor.py advise`, then the native unreal-export job). Put a model behind a `SubViewportContainer` + `SubViewport` (own camera and light, `transparent_bg = true`) so it shows in `shot`'s model-view check; classify each model with `gg_catalog.py` first. Never download anything: a new Fab download needs the owner's per-asset approval.

## Godot 4 syntax (the engine is 4.x: Godot 3 spellings fail the whole project import)
`@onready var x = $Node` (not `onready var`), `@export var`, `signal.connect(callable)` (not `connect("sig", obj, "method")`), `await` (not `yield`), `super()` (not `.method()`), `PackedStringArray`/`Array[T]` typing, `str(x)`/`String(x)`, `randf_range()`, `preload()` constants, `Callable(self, "m")`. One parse error in any script makes `gg_ui.py test` exit 3 ("project import failed"): read the SCRIPT ERROR line in the log tail, fix that file, and resubmit as a NEW job name.
