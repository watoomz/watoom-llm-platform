"""Probe native source materials/Blueprint transforms and CPU export; no originals are saved."""

import unreal, pathlib, json, traceback, itertools

root = pathlib.Path(unreal.Paths.project_dir())
result = {"status": "RUNNING", "blueprints": [], "materials": []}


def checkpoint(phase):
    result["phase"] = phase
    (root / "material-api-progress.json").write_text(json.dumps(result, indent=2))


def vec(v):
    return [v.x, v.y, v.z]


try:
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if (root / "Content/MaterialProbe.umap").exists():
        assert levels.load_level("/Game/MaterialProbe")
        for old in actors.get_all_level_actors():
            if "PROBE_DISPOSABLE" in [str(t) for t in old.tags]:
                actors.destroy_actor(old)
    else:
        assert levels.new_level("/Game/MaterialProbe")
    checkpoint("LOADED_DISPOSABLE_MAP")
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous(["/Game"], True)
    dependencies = unreal.AssetRegistryDependencyOptions()
    for name in ["BPP_dungeon_wall_big_1", "BPP_dungeon_floor_test1", "BPP_ceiling_staircase"]:
        package = "/Game/Dungeon_Forge/Blueprints/" + name
        checkpoint("INSPECTING_" + name)
        cls = unreal.load_class(None, package + "." + name + "_C")
        assert cls
        actor = actors.spawn_actor_from_class(cls, unreal.Vector(0, 0, 0))
        actor.tags = ["PROBE_DISPOSABLE"]
        low = [float("inf")] * 3
        high = [-float("inf")] * 3
        entries = []
        meshes = {}
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            mesh = component.static_mesh
            if not mesh:
                continue
            meshname = mesh.get_path_name()
            box = mesh.get_bounding_box()
            transforms = (
                [component.get_instance_transform(i, world_space=True) for i in range(component.get_instance_count())]
                if isinstance(component, unreal.InstancedStaticMeshComponent)
                else [component.get_world_transform()]
            )
            if len(transforms) > 512:
                raise RuntimeError("Blueprint component instance budget exceeded")
            for transform in transforms:
                assert isinstance(transform, unreal.Transform)
                points = [
                    unreal.MathLibrary.transform_location(transform, unreal.Vector(*xyz))
                    for xyz in itertools.product([box.min.x, box.max.x], [box.min.y, box.max.y], [box.min.z, box.max.z])
                ]
                lo = [min(vec(x)[i] for x in points) for i in range(3)]
                hi = [max(vec(x)[i] for x in points) for i in range(3)]
                low = [min(low[i], lo[i]) for i in range(3)]
                high = [max(high[i], hi[i]) for i in range(3)]
                entries.append({"mesh": meshname, "min_cm": lo, "max_cm": hi})
            meshes[meshname] = {
                "lod_triangles": [mesh.get_num_triangles(i) for i in range(mesh.get_num_lods())],
                "collision": str(component.get_collision_enabled()),
            }
        pending = [package]
        visited = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            if len(visited) > 512:
                raise RuntimeError("Blueprint dependency budget exceeded512")
            pending += [
                str(x)
                for x in registry.get_dependencies(current, dependencies)
                if str(x).startswith("/Game/") and str(x) not in visited
            ]
        result["blueprints"].append(
            {
                "path": package,
                "min_cm": low,
                "max_cm": high,
                "meshes": meshes,
                "instances": len(entries),
                "instance_bounds": entries,
                "dependencies": sorted(visited),
            }
        )
        checkpoint("INSPECTED_" + name)
        actors.destroy_actor(actor)
    mesh = unreal.load_asset(
        "/Game/MysticDungeon/Meshes/Floor/SM_Floor_Stone_Square_Tiles_A.SM_Floor_Stone_Square_Tiles_A"
    )
    assert isinstance(mesh, unreal.StaticMesh)
    actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
    actor.tags = ["PROBE_DISPOSABLE"]
    actor.static_mesh_component.set_static_mesh(mesh)
    checkpoint("EXTRACTING_ORIGINAL_MATERIAL_TEXTURES")
    exports = root / "texture-probe"
    exports.mkdir(exist_ok=True)
    seen = set()
    for slot in mesh.get_editor_property("static_materials"):
        material = slot.material_interface
        count = 0
        row = {"material": material.get_path_name(), "chain": []}
        result["materials"].append(row)
        while isinstance(material, unreal.MaterialInstanceConstant) and count < 8:
            count += 1
            values = []
            for entry in material.get_editor_property("texture_parameter_values"):
                texture = entry.parameter_value
                if texture is None:
                    continue
                output = exports / (texture.get_name() + ".png")
                if texture.get_path_name() not in seen:
                    task = unreal.AssetExportTask()
                    task.object = texture
                    task.filename = str(output)
                    task.automated = True
                    task.prompt = False
                    task.replace_identical = True
                    task.exporter = unreal.TextureExporterPNG()
                    success = unreal.Exporter.run_asset_export_task(task)
                    seen.add(texture.get_path_name())
                else:
                    success = output.is_file()
                values.append(
                    {
                        "parameter": str(entry.parameter_info.name),
                        "texture": texture.get_path_name(),
                        "exported": bool(success and output.is_file()),
                        "file": str(output),
                        "bytes": output.stat().st_size if output.exists() else 0,
                    }
                )
            row["chain"].append({"material": material.get_path_name(), "textures": values})
            material = material.get_editor_property("parent")
    checkpoint("EXPORTING_NATIVE_GLB_WITHOUT_SHADER_BAKE")
    options = unreal.GLTFExportOptions()
    options.set_editor_property("bake_material_inputs", unreal.GLTFMaterialBakeMode.DISABLED)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    messages = unreal.GLTFExporter.export_to_gltf(world, str(root / "material-probe.glb"), options, set())
    assert isinstance(messages, unreal.GLTFExportMessages)
    result["export"] = {key: list(messages.get_editor_property(key)) for key in ("errors", "warnings", "suggestions")}
    result["glb_bytes"] = (root / "material-probe.glb").stat().st_size
    result["status"] = "PASS"
except Exception:
    result.update(status="FAIL", error=traceback.format_exc())
finally:
    (root / "material-api-probe.json").write_text(json.dumps(result, indent=2))
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
