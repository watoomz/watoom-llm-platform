"""Execute inside Unreal's Python plugin in the disposable acceptance project."""
import unreal, pathlib, json, time, traceback, os, struct, subprocess
root=pathlib.Path(os.environ["WATOOM_ACCEPTANCE_ROOT"])
try:
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if (root/"Content/RecoveryProbe.umap").exists():
        assert levels.load_level("/Game/RecoveryProbe")
        existing=actors.get_all_level_actors()
        assert {"Floor","BackWall","SideWall","Pillar","Step"} <= {a.get_actor_label() for a in existing}
        camera=next(a for a in existing if isinstance(a,unreal.CameraActor))
    else:
        assert levels.new_level("/Game/RecoveryProbe")
        cube=unreal.load_asset("/Engine/BasicShapes/Cube")
        assert cube
        fixtures=[
          ("Floor",(0,0,-25),(8,8,0.5)),
          ("BackWall",(0,400,125),(8,0.3,3)),
          ("SideWall",(400,0,125),(0.3,8,3)),
          ("Pillar",(-200,100,125),(0.8,0.8,3)),
          ("Step",(-100,-100,25),(2,2,0.5))]
        for name,location,scale in fixtures:
            actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,unreal.Vector(*location))
            actor.set_actor_label(name)
            actor.static_mesh_component.set_static_mesh(cube)
            actor.set_actor_scale3d(unreal.Vector(*scale))
        light=actors.spawn_actor_from_class(unreal.DirectionalLight,unreal.Vector(0,0,500),unreal.Rotator(-45,-30,0))
        light.light_component.set_editor_property("intensity",8.0)
        actors.spawn_actor_from_class(unreal.SkyLight,unreal.Vector(0,0,300))
        camera=actors.spawn_actor_from_class(unreal.CameraActor,unreal.Vector(-950,-950,850),unreal.Rotator(-30,45,0))
        unreal.EditorLevelLibrary.set_level_viewport_camera_info(camera.get_actor_location(),camera.get_actor_rotation())
        assert levels.save_current_level()
    # Existing saved fixtures also need an explicitly positioned viewport and dynamic light.
    camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(camera.get_actor_location(),unreal.Vector(0,0,75)),False)
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    editor.set_level_viewport_camera_info(camera.get_actor_location(),camera.get_actor_rotation())
    for actor in actors.get_all_level_actors():
        if isinstance(actor,(unreal.DirectionalLight,unreal.SkyLight)):
            actor.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    (root/"scene-diagnostics.json").write_text(json.dumps({
        "camera_location":str(camera.get_actor_location()),"camera_rotation":str(camera.get_actor_rotation()),
        "actors":[{"name":a.get_actor_label(),"location":str(a.get_actor_location())} for a in actors.get_all_level_actors()]},indent=2))
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    result=unreal.GLTFExporter.export_to_gltf(world,str(root/"recovery-room.glb"),unreal.GLTFExportOptions(),set())
    # UE Python consumes the bool return as success and returns the output struct.
    assert isinstance(result,unreal.GLTFExportMessages), "GLTF export failed: "+repr(result)
    errors=list(result.get_editor_property("errors"))
    assert not errors, str(errors)
    glb=(root/"recovery-room.glb").read_bytes()
    assert len(glb)>20 and struct.unpack_from("<4sII",glb)==(b"glTF",2,len(glb))
    (root/"export-messages.json").write_text(json.dumps({
        "errors":errors,"warnings":list(result.get_editor_property("warnings")),
        "suggestions":list(result.get_editor_property("suggestions"))},indent=2))
    receipt={"status":"EXPORTED_RENDER_PENDING","version":unreal.SystemLibrary.get_engine_version(),"map":"/Game/RecoveryProbe","glb":str(root/"recovery-room.glb"),"actors":len(actors.get_all_level_actors())}
    (root/"render-probe.json").write_text(json.dumps(receipt,indent=2))
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    assert unreal.EditorPythonScripting.get_keep_python_script_alive()
    started=time.monotonic();task=None
    def tick(_delta):
        global task
        try:
            elapsed=time.monotonic()-started
            if task is None and elapsed>45:
                subprocess.run(["/usr/sbin/import","-window","root",str(root/"editor-desktop.png")],timeout=20,check=True)
                task=unreal.AutomationLibrary.take_high_res_screenshot(1280,720,str(root/"editor-viewport.png"),camera=camera)
                assert task and task.is_valid_task()
            elif task is not None and task.is_task_done() and (root/"editor-viewport.png").exists():
                receipt["status"]="PASS"
                (root/"render-probe.json").write_text(json.dumps(receipt,indent=2))
                unreal.unregister_slate_post_tick_callback(handle)
                unreal.EditorPythonScripting.set_keep_python_script_alive(False)
            elif elapsed>300:
                raise RuntimeError("Rendered screenshot timeout")
        except Exception:
            (root/"render-probe-error.txt").write_text(traceback.format_exc())
            unreal.unregister_slate_post_tick_callback(handle)
            unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    handle=unreal.register_slate_post_tick_callback(tick)
except Exception:
    (root/"render-probe-error.txt").write_text(traceback.format_exc())
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
