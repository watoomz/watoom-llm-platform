extends RefCounted
## Dock the game window as a strip along the bottom of the screen, borderless, always on top, with a transparent background.
## Use from the main scene's _ready():
##   const Overlay := preload("res://addons/gg/game/overlay_window.gd")
##   func _ready() -> void:
##       Overlay.dock_bottom(get_window(), 240, Overlay.windowed_requested())
##       Overlay.set_passthrough(get_window(), [Rect2(0, 0, get_window().size.x, 240)])   # clicks elsewhere fall through
## The project must also set display/window/per_pixel_transparency/allowed=true and rendering/viewport/transparent_background=true
## (`gg_ui.py init` does); gg_ui.py overlay-check reads all of it back.

## `--windowed` (a user argument after `--`) shows the same strip as a normal framed window for testing.
static func windowed_requested() -> bool:
	return "--windowed" in OS.get_cmdline_user_args() or "--windowed" in OS.get_cmdline_args()

## Pure geometry: the strip rectangle at the bottom of `usable` (the screen minus taskbars), full width.
static func strip_rect(usable: Rect2i, height_px: int) -> Rect2i:
	var h := clampi(height_px, 1, usable.size.y)
	return Rect2i(usable.position.x, usable.end.y - h, usable.size.x, h)

static func dock_bottom(window: Window, height_px: int, windowed: bool = false, screen: int = -1) -> Rect2i:
	var s := DisplayServer.window_get_current_screen() if screen < 0 else screen
	var r := strip_rect(DisplayServer.screen_get_usable_rect(s), height_px)
	window.borderless = not windowed
	window.always_on_top = not windowed
	window.transparent = not windowed
	window.transparent_bg = not windowed
	window.unresizable = true
	window.size = r.size
	window.position = r.position
	return r

## Only the union bounding box can be one polygon in the engine: pass every clickable rectangle; the rest of the window lets clicks through.
static func set_passthrough(window: Window, rects: Array) -> void:
	if rects.is_empty():
		window.mouse_passthrough_polygon = PackedVector2Array()
		return
	var u: Rect2 = rects[0]
	for r in rects:
		u = u.merge(r)
	window.mouse_passthrough_polygon = PackedVector2Array([u.position, Vector2(u.end.x, u.position.y), u.end, Vector2(u.position.x, u.end.y)])
