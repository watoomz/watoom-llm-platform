extends SceneTree
var receipt = {"status":"RUNNING","effects":[]}
func _initialize():
 call_deferred("run")
func run():
 var manifest = JSON.parse_string(FileAccess.get_file_as_string("res://manifest.json"))
 var root = Node3D.new()
 get_root().add_child(root)
 var environment = WorldEnvironment.new()
 environment.environment = Environment.new()
 environment.environment.background_mode = Environment.BG_COLOR
 environment.environment.background_color = Color(0.6,0.6,0.6)
 root.add_child(environment)
 var camera = Camera3D.new()
 camera.projection = Camera3D.PROJECTION_ORTHOGONAL
 camera.current = true
 root.add_child(camera)
 var sprite = AnimatedSprite3D.new()
 sprite.shaded = false
 sprite.double_sided = true
 root.add_child(sprite)
 DirAccess.make_dir_recursive_absolute("res://captures")
 for effect in manifest.assets:
  var frames = load("res://"+effect.resource) as SpriteFrames
  assert(frames != null and frames.get_frame_count("default")==effect.frames)
  sprite.sprite_frames=frames
  sprite.pixel_size=effect.pixel_size
  camera.size=effect.pixel_size*256*1.1
  camera.position=Vector3(0,0,camera.size*2)
  sprite.play("default")
  await create_timer(maxf(0.08,effect.duration*0.2)).timeout
  await RenderingServer.frame_post_draw
  var first=sprite.frame
  var a=get_root().get_texture().get_image()
  a.save_png("res://captures/"+effect.name+"-a.png")
  await create_timer(maxf(0.12,effect.duration*0.45)).timeout
  await RenderingServer.frame_post_draw
  var second=sprite.frame
  var b=get_root().get_texture().get_image()
  b.save_png("res://captures/"+effect.name+"-b.png")
  assert(second>first and a.get_data()!=b.get_data(),"Godot effect failed actual playback/render: "+effect.name)
  receipt.effects.append({"name":effect.name,"frames":[first,second],"image_a":effect.name+"-a.png","image_b":effect.name+"-b.png","actual_render_changed":true})
 receipt.status="PASS_GODOT_SPRITE3D_PLAYBACK_RENDER"
 var f=FileAccess.open("res://godot.json",FileAccess.WRITE)
 f.store_string(JSON.stringify(receipt,"  "));f.close()
 quit(0)
