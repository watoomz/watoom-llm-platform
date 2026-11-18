"""Content-only assembly, saved-map verification and actual Vulkan capture."""
import os,pathlib,json,time,traceback,hashlib,importlib.util
import unreal
root=pathlib.Path(os.environ["WATOOM_ACCEPTANCE_ROOT"]).resolve()
out=root/"dungeon-export-receipt.json";receipt={"status":"RUNNING","navigation":"NOT TESTED","gameplay":"OUT OF SCOPE"}
def save():out.write_text(json.dumps(receipt,indent=2)+"\n")
def fail():
 receipt.update(status="FAIL",error=traceback.format_exc());save()
 unreal.EditorPythonScripting.set_keep_python_script_alive(False)
try:
 spec=importlib.util.spec_from_file_location("grid_layout",root/"grid_layout.py");grid=importlib.util.module_from_spec(spec);spec.loader.exec_module(grid)
 plan=grid.prepare(json.loads((root/"layout.json").read_text()))
 assert not (root/"Content/Levels/Quest1.umap").exists(),"New map destination required"
 actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem);levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
 levels.new_level("/Game/Levels/Quest1")
 cube=unreal.load_asset("/Engine/BasicShapes/Cube");assert cube
 asset_tools=unreal.AssetToolsHelpers.get_asset_tools();materials={}
 for name,rgb in {"floor":(.34,.27,.18),"wall":(.18,.055,.045),"rock":(.10,.10,.115)}.items():
  mat=asset_tools.create_asset("M_"+name,"/Game/PoC/Materials",unreal.Material,unreal.MaterialFactoryNew())
  colour=unreal.MaterialEditingLibrary.create_material_expression(mat,unreal.MaterialExpressionConstant3Vector,-200,0)
  colour.set_editor_property("constant",unreal.LinearColor(*rgb,1))
  unreal.MaterialEditingLibrary.connect_material_property(colour,"",unreal.MaterialProperty.MP_BASE_COLOR)
  unreal.MaterialEditingLibrary.recompile_material(mat);unreal.EditorAssetLibrary.save_loaded_asset(mat);materials[name]=mat
 manifest=[]
 for i,item in enumerate(plan["placements"]):
  actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*item["position"]))
  actor.set_actor_label("Q1_%04d_%s"%(i,item["role"]));actor.tags=["Quest1PoC",item["role"]]
  actor.static_mesh_component.set_static_mesh(cube);actor.static_mesh_component.set_material(0,materials[item["role"]])
  actor.static_mesh_component.set_collision_profile_name("BlockAll");actor.set_actor_scale3d(unreal.Vector(*item["scale"]))
  manifest.append({"actor":actor.get_actor_label(),**item})
 size=plan["grid"]["cell_cm"];cx=(plan["grid"]["cols"]-1)*size/2;cy=(plan["grid"]["rows"]-1)*size/2
 light=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(cx,cy,1800),unreal.Rotator(-55,-35,0))
 light.light_component.set_mobility(unreal.ComponentMobility.MOVABLE);light.light_component.set_editor_property("intensity",3.0)
 sky=actors.spawn_actor_from_class(unreal.SkyLight,unreal.Vector(cx,cy,1800));sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
 cameras=[]
 for name,pos in [("overhead",(cx,cy,10000)),("perspective",(cx-3800,cy-4300,5000))]:
  camera=actors.spawn_actor_from_class(unreal.CameraActor,unreal.Vector(*pos));camera.set_actor_label("Q1Camera_"+name)
  camera.set_actor_rotation(unreal.Rotator(-90,-90,0) if name=="overhead" else unreal.MathLibrary.find_look_at_rotation(camera.get_actor_location(),unreal.Vector(cx,cy,0)),False)
  camera.camera_component.set_editor_property("aspect_ratio",4/3);camera.camera_component.set_editor_property("field_of_view",58)
  if name=="overhead":
   camera.camera_component.set_editor_property("projection_mode",unreal.CameraProjectionMode.ORTHOGRAPHIC)
   camera.camera_component.set_editor_property("ortho_width",max(plan["grid"]["cols"]*size,plan["grid"]["rows"]*size*4/3)*1.12)
  cameras.append(name)
 assert levels.save_current_level();assert levels.load_level("/Game/Levels/Quest1")
 placed=[a for a in actors.get_all_level_actors() if "Quest1PoC" in map(str,a.tags)];assert len(placed)==len(manifest)
 world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
 for c,r in plan["floor_cells"]:
  assert unreal.SystemLibrary.line_trace_single(world,unreal.Vector(c*size,r*size,100),unreal.Vector(c*size,r*size,-30),unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True) is not None
 for a,b in plan["door_edges"]:
  assert unreal.SystemLibrary.capsule_trace_single(world,unreal.Vector(a[0]*size,a[1]*size,100),unreal.Vector(b[0]*size,b[1]*size,100),30,88,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True) is None
 (root/"actor-manifest.json").write_text(json.dumps({"schema":plan["schema"],"layout_sha256":plan["layout_sha256"],"grid":plan["grid"],"actors":manifest},indent=2))
 receipt.update(status="MAP_REOPENED_CAPTURE_PENDING",engine=unreal.SystemLibrary.get_engine_version(),layout_sha256=plan["layout_sha256"],actors=len(placed),floor_checks=len(plan["floor_cells"]),door_capsule_checks=len(plan["door_edges"]),editable_map="/Game/Levels/Quest1",map_sha256=hashlib.sha256((root/"Content/Levels/Quest1.umap").read_bytes()).hexdigest());save()
 unreal.EditorPythonScripting.set_keep_python_script_alive(True)
 started=time.monotonic();phase=0;ready=0;index=0;task=None
 def tick(delta):
  global phase,ready,index,task
  try:
   if phase==0 and time.monotonic()-started>5:
    phase=1;unreal.AutomationLibrary.finish_loading_before_screenshot();ready=time.monotonic();phase=2
   elif phase==2 and time.monotonic()-ready>10:
    name=cameras[index];camera=next(a for a in actors.get_all_level_actors() if a.get_actor_label()=="Q1Camera_"+name)
    task=unreal.AutomationLibrary.take_high_res_screenshot(1600,1200,str(root/(name+".png")),camera=camera);assert task and task.is_valid_task();phase=3
   elif phase==3 and task.is_task_done() and (root/(cameras[index]+".png")).exists():
    index+=1
    if index==len(cameras):
     receipt.update(status="PASS",captures=[x+".png" for x in cameras]);save();unreal.unregister_slate_post_tick_callback(handle);unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    else:ready=time.monotonic();phase=2
   elif phase not in (1,) and time.monotonic()-started>900:raise TimeoutError("Capture deadline")
  except Exception:unreal.unregister_slate_post_tick_callback(handle);fail()
 handle=unreal.register_slate_post_tick_callback(tick)
except Exception:fail()
