extends RefCounted
## T-0066: build res://levels/<level>/<level>.tscn, a playable first-person shooting range: sky + sun, a 60 m floor,
## the first-person player (player_3d + capsule + Combat + CameraRig + fps_weapon.gd under the rig) at the origin
## facing -Z, and args.walls destructible props (game/destructible.gd) in a row at args.distances metres ahead.
## Every runtime part builds its children in _ready, so the saved scene stays small and has no generated nodes.
## args: {level: "fps_range", wall: "res://...glb", gun: "res://...glb" | "", gun_rotation: [x, y, z] deg, gun_scale: 1,
##        distances: [6, 10, 14], wall_health: 100}
## data: {scene, nodes, walls}
const Save := preload("res://addons/gg/lib/save.gd")
const Player := preload("res://addons/gg/game/player_3d.gd")
const Rig := preload("res://addons/gg/game/camera_rig.gd")
const FpsWeapon := preload("res://addons/gg/game/fps_weapon.gd")
const Destructible := preload("res://addons/gg/game/destructible.gd")
const CombatComponent := preload("res://addons/gg/game/combat_component.gd")


func run(_tree: SceneTree, args: Dictionary) -> Dictionary:
	var level: String = args.get("level", "fps_range")
	var wall_path: String = args.get("wall", "")
	if not ResourceLoader.exists(wall_path):
		return {"ok": false, "error": "args.wall %s is not a resource" % wall_path}
	var root := Node3D.new()
	root.name = "FpsRange"

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = Sky.new()
	env.sky.sky_material = ProceduralSkyMaterial.new()
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var we := WorldEnvironment.new()
	we.name = "WorldEnvironment"
	we.environment = env
	root.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	sun.shadow_enabled = true
	sun.rotation_degrees = Vector3(-50, 35, 0)
	root.add_child(sun)

	var floor := StaticBody3D.new()
	floor.name = "Floor"
	var fs := CollisionShape3D.new()
	fs.name = "Shape"
	fs.shape = BoxShape3D.new()
	fs.shape.size = Vector3(60, 1, 60)
	floor.add_child(fs)
	var fm := MeshInstance3D.new()
	fm.name = "Mesh"
	fm.mesh = BoxMesh.new()
	fm.mesh.size = Vector3(60, 1, 60)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.35, 0.37, 0.33)
	fm.mesh.material = mat
	floor.add_child(fm)
	floor.position = Vector3(0, -0.5, 0)
	root.add_child(floor)

	var player := Player.new()
	player.name = "Player"
	var cs := CollisionShape3D.new()
	cs.name = "Capsule"
	cs.shape = CapsuleShape3D.new()
	cs.shape.radius = 0.35
	cs.shape.height = 1.8
	cs.position.y = 0.9
	player.add_child(cs)
	var pc := CombatComponent.new()
	pc.name = "Combat"
	player.add_child(pc)
	var rig := Rig.new()
	rig.name = "CameraRig"
	rig.mode = "first_person"
	player.add_child(rig)
	var gun := FpsWeapon.new()
	gun.name = "Rifle"
	var gun_path: String = args.get("gun", "")
	if gun_path != "" and ResourceLoader.exists(gun_path):
		gun.model = load(gun_path)
		var r: Array = args.get("gun_rotation", [0, 0, 0])
		gun.model_rotation_deg = Vector3(r[0], r[1], r[2])   # packs point their barrels along different axes
		gun.model_scale = float(args.get("gun_scale", 1.0))
		if args.has("gun_offset"):
			var o: Array = args["gun_offset"]
			gun.model_offset = Vector3(o[0], o[1], o[2])   # the model's pivot is rarely its grip
	rig.add_child(gun)
	root.add_child(player)

	var walls := []
	for i in (args.get("distances", [6, 10, 14]) as Array).size():
		var d: float = float(args["distances"][i])
		var w := Destructible.new()
		w.name = "Wall_%d" % i
		w.model = load(wall_path)
		w.max_health = float(args.get("wall_health", 100.0))
		w.position = Vector3((i - 1) * 3.0, 0, -d)
		root.add_child(w)
		walls.append(w.name)

	var out := "res://levels/%s/%s.tscn" % [level, level]
	var saved := Save.save_scene(root, out, true)
	if not saved["ok"]:
		return saved
	return {"ok": true, "data": {"scene": out, "nodes": saved["nodes"], "walls": walls}}
