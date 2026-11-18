"""Render source GeometryCache samples to RGBA frames; no static-GLTF animation claim."""
import unreal,pathlib,json,time,math,traceback
try:
 ROOT=pathlib.Path(unreal.Paths.project_dir());OUT=ROOT/"raw-frames";OUT.mkdir(exist_ok=True)
 PLAN=json.loads((ROOT/"bloodfx-inspection.json").read_text())
 receipt={"status":"RUNNING","engine":unreal.SystemLibrary.get_engine_version(),"renderer":"software Vulkan (runner must verify actual device)","assets":[],"scope":"Fixed-view 256px effect bake; original native materials, not editable 3D cache conversion"}
 def save(): (ROOT/"bloodfx-render.json").write_text(json.dumps(receipt,indent=2))
 save()
 world=unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
 actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
 actor=actors.spawn_actor_from_class(unreal.GeometryCacheActor,unreal.Vector())
 comp=actor.get_geometry_cache_component();comp.set_editor_property("manual_tick",True)
 camera=actors.spawn_actor_from_class(unreal.SceneCapture2D,unreal.Vector())
 capture=camera.get_editor_property("capture_component2d")
 capture.set_editor_property("capture_every_frame",False)
 capture.set_editor_property("capture_on_movement",False)
 capture.set_editor_property("capture_source",unreal.SceneCaptureSource.SCS_SCENE_COLOR_HDR)
 capture.set_editor_property("primitive_render_mode",unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST)
 capture.set_editor_property("show_only_actors",[actor])
 capture.set_editor_property("projection_type",unreal.CameraProjectionMode.ORTHOGRAPHIC)
 rt=unreal.RenderingLibrary.create_render_target2d(world,256,256,unreal.TextureRenderTargetFormat.RTF_RGBA8,unreal.LinearColor(0,0,0,1),False)
 capture.set_editor_property("texture_target",rt)
 for rotation,intensity in [(unreal.Rotator(-45,-45,0),5.0),(unreal.Rotator(-30,135,0),2.0)]:
  light=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(),rotation)
  lc=light.get_component_by_class(unreal.DirectionalLightComponent);lc.set_editor_property("intensity",intensity);lc.set_editor_property("cast_shadows",False)
 state={"asset":-1,"frame":0,"phase":"next","after":0.0}
 def finish(error=None):
  receipt["status"]="FAIL" if error else "PASS_NATIVE_SAMPLED_RENDER"
  if error:receipt["error"]=error
  save();unreal.unregister_slate_post_tick_callback(HANDLE);unreal.SystemLibrary.quit_editor()
 def tick(delta):
  try:
   if time.monotonic()<state["after"]:return
   if state["phase"]=="next":
    state["asset"]+=1
    if state["asset"]>=len(PLAN["assets"]):finish();return
    a=PLAN["assets"][state["asset"]];obj=unreal.load_asset(a["asset"]);assert obj is not None
    comp.set_geometry_cache(obj);comp.set_editor_property("manual_tick",True);comp.play()
    # Stable framing encompasses native decoded sample bounds.
    mn=[min(x["origin"][i]-x["extent"][i] for x in a["samples"]) for i in range(3)]
    mx=[max(x["origin"][i]+x["extent"][i] for x in a["samples"]) for i in range(3)]
    center=unreal.Vector(*[(mn[i]+mx[i])/2 for i in range(3)]);radius=max(1.0,math.sqrt(sum((mx[i]-mn[i])**2 for i in range(3))))
    location=center+unreal.Vector(radius,-radius,radius)
    camera.set_actor_location(location,False,False);camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(location,center),False)
    capture.set_editor_property("ortho_width",radius*1.3)
    folder=OUT/a["asset"].split("/")[-1];folder.mkdir(exist_ok=True)
    receipt["assets"].append({"asset":a["asset"],"duration":a["duration"],"frames":[],"camera_center":[center.x,center.y,center.z],"ortho_width":radius*1.3})
    state.update(phase="warming",frame=0,folder=folder,count=min(96,max(8,math.ceil(a["duration"]*12)+1)))
    comp.tick_at_this_time(a["duration"]*.02,True,False,False)
    save();return
   if state["phase"]=="warming":
    # Advance phase before flushing: the supported flush may re-enter Slate.
    state["phase"]="wait_repaint";state["after"]=float("inf")
    unreal.AutomationLibrary.finish_loading_before_screenshot()
    state["after"]=time.monotonic()+2.0
    return
   if state["phase"] in ("wait_repaint","sample"):
    a=PLAN["assets"][state["asset"]];t=a["duration"]*(.00001+.99998*state["frame"]/(state["count"]-1))
    comp.tick_at_this_time(t,True,False,False)
    assert abs(comp.get_animation_time()-t)<.01,"Native cache did not advance"
    state.update(phase="capture",after=time.monotonic()+.15,time=t);return
   if state["phase"]=="capture":
    capture.capture_scene();state.update(phase="export",after=time.monotonic()+.15);return
   if state["phase"]=="export":
    name=f"frame_{state['frame']:03d}.png"
    unreal.RenderingLibrary.export_render_target(world,rt,str(state["folder"]),name)
    path=state["folder"]/name;assert path.is_file() and path.stat().st_size>100
    receipt["assets"][-1]["frames"].append({"time":state["time"],"path":str(path.relative_to(ROOT))})
    state["frame"]+=1;state["phase"]="next" if state["frame"]==state["count"] else "sample";save()
  except Exception:finish(traceback.format_exc())
 HANDLE=unreal.register_slate_post_tick_callback(tick)
except Exception:
 pathlib.Path(unreal.Paths.project_dir(),"bloodfx-render.json").write_text(json.dumps({"status":"FAIL","error":traceback.format_exc()},indent=2))
 unreal.SystemLibrary.quit_editor()
