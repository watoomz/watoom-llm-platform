"""Probe actual non-commandlet editor navigation and authored pack blueprints, without GPU."""
import unreal,pathlib,json,time,traceback,hashlib,shutil
root=pathlib.Path(unreal.Paths.project_dir());result={"status":"RUNNING","blueprints":[]}
try:
 levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
 actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
 assert levels and actors,"Editor subsystems unavailable"
 mapfile=root/"Content/NativeProbe.umap"
 if mapfile.exists():
  shutil.copyfile(mapfile,root/"native-probe-before.umap.snapshot")
  result["before_map_sha256"]=hashlib.sha256(mapfile.read_bytes()).hexdigest()
  assert levels.load_level("/Game/NativeProbe")
  for actor in actors.get_all_level_actors():
   if "PROBE_DISPOSABLE" in [str(t) for t in actor.tags]:actors.destroy_actor(actor)
 else:assert levels.new_level("/Game/NativeProbe")
 cube=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(0,0,-5))
 cube.tags=["PROBE_DISPOSABLE"]
 cube.static_mesh_component.set_static_mesh(unreal.load_asset("/Engine/BasicShapes/Cube"))
 cube.set_actor_scale3d(unreal.Vector(50,50,.1))
 world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
 volume=actors.spawn_actor_from_class(unreal.NavMeshBoundsVolume,unreal.Vector(0,0,150))
 volume.tags=["PROBE_DISPOSABLE"]
 origin,extent=volume.get_actor_bounds(False)
 result["default_nav_volume_extent"]=[extent.x,extent.y,extent.z]
 assert min(extent.x,extent.y,extent.z)>0,"Navigation factory created an empty brush"
 volume.set_actor_scale3d(unreal.Vector(30,30,4))
 navsys=unreal.NavigationSystemV1.get_navigation_system(world)
 result["navigation_system"]=str(navsys)
 navsys.on_navigation_bounds_updated(volume)
 unreal.EditorPythonScripting.set_keep_python_script_alive(True)
 started=time.monotonic();built=False
 def tick(_delta):
  global built
  try:
   elapsed=time.monotonic()-started
   if elapsed<3:return
   if not built:
    navdata=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.RecastNavMesh)]
    if not navdata:
     if elapsed>90:raise RuntimeError("Bounds update did not create Recast navigation data")
     return
    unreal.SystemLibrary.execute_console_command(world,"RebuildNavigation");built=True
    return
   if unreal.NavigationSystemV1.is_navigation_being_built(world):
    if elapsed>120:raise RuntimeError("Navigation build exceeded120seconds")
    return
   path=unreal.NavigationSystemV1.find_path_to_location_synchronously(world,unreal.Vector(-500,-500,20),unreal.Vector(500,500,20))
   result["navigation"]={"valid":bool(path and path.is_valid()),"partial":bool(path and path.is_partial()),"points":len(path.path_points) if path else 0}
   if not result["navigation"]["valid"] or result["navigation"]["partial"]:raise RuntimeError("Native Recast navigation path failed")
   for name in ["BPP_dungeon_wall_big_1","BPP_dungeon_floor_test1","BPP_ceiling_staircase"]:
    package="/Game/Dungeon_Forge/Blueprints/"+name
    cls=unreal.load_class(None,package+"."+name+"_C")
    if cls is None:
     result["blueprints"].append({"path":package,"status":"CLASS_UNAVAILABLE"});continue
    actor=actors.spawn_actor_from_class(cls,unreal.Vector(0,0,1000))
    actor.tags=["PROBE_DISPOSABLE"]
    origin,extent=actor.get_actor_bounds(False,True)
    components=actor.get_components_by_class(unreal.StaticMeshComponent)
    result["blueprints"].append({"path":package,"status":"LOADED","origin":[origin.x,origin.y,origin.z],"extent":[extent.x,extent.y,extent.z],
      "components":len(components),"instances":sum(c.get_instance_count() if isinstance(c,unreal.InstancedStaticMeshComponent) else 1 for c in components),
      "meshes":sorted(set(c.static_mesh.get_path_name() for c in components if c.static_mesh))})
    actors.destroy_actor(actor)
   result["status"]="PASS"
  except Exception:result.update(status="FAIL",error=traceback.format_exc())
  (root/"native-api-probe.json").write_text(json.dumps(result,indent=2))
  unreal.unregister_slate_post_tick_callback(handle)
  unreal.EditorPythonScripting.set_keep_python_script_alive(False)
 handle=unreal.register_slate_post_tick_callback(tick)
except Exception:
 result.update(status="FAIL",error=traceback.format_exc());(root/"native-api-probe.json").write_text(json.dumps(result,indent=2))
 unreal.EditorPythonScripting.set_keep_python_script_alive(False)
