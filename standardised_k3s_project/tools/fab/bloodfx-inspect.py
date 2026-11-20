import unreal, pathlib, json, collections, hashlib

root = pathlib.Path(unreal.Paths.project_dir())
reg = unreal.AssetRegistryHelpers.get_asset_registry()
reg.scan_paths_synchronous(["/Game"], True)
assets = sorted(
    [
        a
        for a in reg.get_assets_by_path("/Game", recursive=True)
        if str(a.asset_class_path.asset_name) == "GeometryCache"
    ],
    key=lambda a: str(a.package_name),
)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
out = {"engine": unreal.SystemLibrary.get_engine_version(), "assets": [], "api": {}}
for cls in [unreal.GeometryCacheComponent, unreal.SceneCaptureComponent2D, unreal.RenderingLibrary]:
    out["api"][cls.__name__] = [
        x
        for x in dir(cls)
        if any(k in x for k in ["render_target", "capture", "tick_at", "duration", "frame", "bounds"])
    ]
for a in assets:
    obj = unreal.load_asset(str(a.package_name))
    actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
        unreal.GeometryCacheActor, unreal.Vector()
    )
    c = actor.get_geometry_cache_component()
    assert c.set_geometry_cache(obj)
    c.set_editor_property("manual_tick", True)
    c.play()
    duration = c.get_duration()
    assert duration > 0
    sample = []
    for frac in [0.1, 0.5, 0.9]:
        c.tick_at_this_time(duration * frac, True, False, False)
        origin, extent = actor.get_actor_bounds(False)
        sample.append(
            {
                "time": duration * frac,
                "origin": [origin.x, origin.y, origin.z],
                "extent": [extent.x, extent.y, extent.z],
            }
        )
    out["assets"].append(
        {
            "asset": str(a.package_name),
            "duration": duration,
            "frames": c.get_number_of_frames(),
            "tracks": c.get_number_of_tracks(),
            "materials": [str(c.get_material(i).get_path_name()) for i in range(c.get_num_materials())],
            "samples": sample,
        }
    )
    unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(actor)
out["status"] = "PASS_NATIVE_TIMELINE_INSPECTION"
(root / "bloodfx-inspection.json").write_text(json.dumps(out, indent=2))
