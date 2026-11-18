extends RefCounted
## Builds res://levels/<level>/player.tscn: CharacterBody3D (origin = feet) with a capsule collider and a camera rig. All values from the profile.
## args: {level, player:{height_m, radius_m, speed_mps, accel_mps2, jump_height_m, gravity_mps2, max_slope_deg}, camera:{mode, eye_height_m, fov_deg, distance_m,
##        pitch_deg, ortho_size_m, near_m, far_m, mouse_sens_deg_per_px}}
## Data: scene, nodes, capsule [r, h], camera_local [x,y,z], reload_ok.
const Save := preload("res://addons/gg/lib/save.gd")
const PlayerScript := preload("res://addons/gg/game/player_3d.gd")
const RigScript := preload("res://addons/gg/game/camera_rig.gd")

func run(_tree: SceneTree, args: Dictionary) -> Dictionary:
	var p: Dictionary = args["player"]
	var c: Dictionary = args["camera"]
	var body := CharacterBody3D.new()
	body.name = "Player"
	body.set_script(PlayerScript)
	var jump_v := 0.0
	if float(p["jump_height_m"]) > 0.0:
		jump_v = sqrt(2.0 * float(p["gravity_mps2"]) * float(p["jump_height_m"]))
	body.set("speed", float(p["speed_mps"]))
	body.set("accel", float(p["accel_mps2"]))
	body.set("jump_velocity", jump_v)
	body.set("gravity", float(p["gravity_mps2"]))
	body.set("floor_angle_deg", float(p["max_slope_deg"]))
	body.set("mouse_sens", float(c["mouse_sens_deg_per_px"]))
	body.set("world_relative", str(c["mode"]) in ["top_down", "isometric"])
	var shape := CollisionShape3D.new()
	shape.name = "Capsule"
	var cap := CapsuleShape3D.new()
	cap.radius = float(p["radius_m"])
	cap.height = float(p["height_m"])
	shape.shape = cap
	shape.position = Vector3(0, float(p["height_m"]) * 0.5, 0)
	body.add_child(shape)
	var rig := Node3D.new()
	rig.name = "CameraRig"
	rig.set_script(RigScript)
	rig.set("mode", str(c["mode"]))
	rig.set("eye_height", float(c["eye_height_m"]))
	rig.set("fov", float(c["fov_deg"]))
	rig.set("distance", float(c["distance_m"]))
	rig.set("pitch_deg", float(c["pitch_deg"]))
	rig.set("ortho_size", float(c.get("ortho_size_m", 20.0)))
	rig.set("near", float(c["near_m"]))
	rig.set("far", float(c["far_m"]))
	body.add_child(rig)
	var out := "res://levels/%s/player.tscn" % args["level"]
	var saved := Save.save_scene(body, out)
	if not saved["ok"]:
		return saved
	var back: Node = (ResourceLoader.load(out, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene).instantiate()
	var ok: bool = absf(float(back.get("speed")) - float(p["speed_mps"])) < 1e-6 and absf(float(back.get("jump_velocity")) - jump_v) < 1e-6 \
		and str(back.get_node("CameraRig").get("mode")) == str(c["mode"]) and (back.get_node("Capsule") as CollisionShape3D).shape is CapsuleShape3D
	back.free()
	if not ok:
		return {"ok": false, "error": "the reloaded player scene does not hold the values that were set (scripts or exports were not saved)"}
	var eye := Vector3(0, float(c["eye_height_m"]), 0)
	return {"ok": true, "data": {"scene": out, "nodes": saved["nodes"], "capsule": [cap.radius, cap.height], "camera_local": [eye.x, eye.y, eye.z], "reload_ok": true}}
