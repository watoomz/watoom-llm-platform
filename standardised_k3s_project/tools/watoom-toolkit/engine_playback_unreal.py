"""Reload saved assets in the real editor and prove component animation playback."""

import unreal, pathlib, json, traceback, time

r = pathlib.Path(__file__).resolve().parent
source = json.loads((r / "source.json").read_text())
prior = json.loads((r / "unreal-result.json").read_text())
result = {"status": "FAIL", "scope": "fresh editor reload, actual skeletal component playback, LOD generation"}
callback_handle = None


def finish(error=None):
    global callback_handle
    if error:
        result["exception"] = str(error)
    if callback_handle is not None:
        unreal.unregister_slate_post_tick_callback(callback_handle)
        callback_handle = None
    (r / "unreal-playback.json").write_text(json.dumps(result, indent=2))
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)


try:
    mesh = unreal.load_asset(prior["mesh"])
    assert mesh is not None
    if source["skeletal"]:
        sub = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
        assert sub
        assert sub.regenerate_lod(mesh, 2, False, False), "Skeletal LOD generation unavailable"
        result["lod_count"] = sub.get_lod_count(mesh)
        assert result["lod_count"] >= 2
        result["lod_vertices"] = [sub.get_num_verts(mesh, i) for i in range(result["lod_count"])]
        assert result["lod_vertices"][1] < result["lod_vertices"][0], "LOD did not reduce vertices"
        unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
        world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
        assert world is not None, "No isolated editor world"
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        actor = actors.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0))
        component = actor.skeletal_mesh_component
        component.set_skeletal_mesh_asset(mesh)
        component.set_update_animation_in_editor(True)
        animations = [unreal.load_asset(path) for path, cls in prior["classes"].items() if cls == "AnimSequence"]
        assert animations
        state = {"index": 0, "began": None, "first": None}
        result["clips"] = []

        def pose():
            return [
                str(component.get_socket_transform(n, unreal.RelativeTransformSpace.RTS_COMPONENT))
                for n in source["bones"]
            ]

        def tick(delta):
            try:
                now = time.monotonic()
                if state["began"] is None:
                    component.play_animation(animations[state["index"]], True)
                    state["began"] = now
                    return
                age = now - state["began"]
                if state["first"] is None and age > 0.08:
                    state["first"] = pose()
                    return
                if age > 0.35 and state["first"] is not None:
                    second = pose()
                    changed = state["first"] != second
                    result["clips"].append(
                        {
                            "name": animations[state["index"]].get_name(),
                            "changed": changed,
                            "sample_interval_seconds": age - 0.08,
                        }
                    )
                    if not changed:
                        raise RuntimeError("Actual component playback is stationary")
                    state.update(index=state["index"] + 1, began=None, first=None)
                    if state["index"] == len(animations):
                        result["status"] = "PASS"
                        finish()
            except Exception:
                finish(traceback.format_exc())

        unreal.EditorPythonScripting.set_keep_python_script_alive(True)
        callback_handle = unreal.register_slate_post_tick_callback(tick)
    else:
        sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        assert sub
        options = unreal.StaticMeshReductionOptions()
        settings = []
        for ratio, size in [(1.0, 1.0), (0.5, 0.5)]:
            setting = unreal.StaticMeshReductionSettings()
            setting.set_editor_property("percent_triangles", ratio)
            setting.set_editor_property("screen_size", size)
            settings.append(setting)
        options.set_editor_property("reduction_settings", settings)
        assert sub.set_lods(mesh, options) >= 2
        result["lod_count"] = mesh.get_num_lods()
        assert result["lod_count"] >= 2
        unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
        result["status"] = "PASS"
        finish()
except Exception:
    finish(traceback.format_exc())
