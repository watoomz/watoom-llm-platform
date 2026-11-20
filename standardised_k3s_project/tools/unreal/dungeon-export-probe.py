"""Bake selected verified pack modules with the real Vulkan GLTFExporter.
Paid sources remain read-only. Generated portable derivatives stay in the private library.
"""

import unreal, pathlib, json, os, traceback, hashlib, struct, time, re

root = pathlib.Path(os.environ["WATOOM_ACCEPTANCE_ROOT"])
request = json.loads((root / "selected-modules.json").read_text())
receipt = {"schema": 1, "status": "RUNNING", "modules": [], "engine": unreal.SystemLibrary.get_engine_version()}
previous = (
    json.loads((root / "dungeon-export-receipt.json").read_text())
    if (root / "dungeon-export-receipt.json").exists()
    else {}
)
receipt["bake_recipe"] = {
    "id": "watoom-native-static-module/v1",
    "pixels": 256,
    "source_model": False,
    "world_space_effects": "frozen_per_module",
}
if previous.get("bake_recipe") != receipt["bake_recipe"] or previous.get("engine") != receipt["engine"]:
    previous = {}


def checkpoint():
    (root / "dungeon-export-receipt.json").write_text(json.dumps(receipt, indent=2))


try:
    if not 1 <= len(request["modules"]) <= 8:
        raise ValueError("Selected module budget")
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    # This is a disposable map created only for the pinned bake task.
    if (root / "Content/GeneratedDungeon/Bake.umap").exists():
        assert levels.load_level("/Game/GeneratedDungeon/Bake")
        for old in actors.get_all_level_actors():
            if "WATOOM_MODULE_BAKE" in [str(tag) for tag in old.tags]:
                actors.destroy_actor(old)
    else:
        assert levels.new_level("/Game/GeneratedDungeon/Bake")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    outputs = root / "baked-modules"
    outputs.mkdir(exist_ok=True)
    options = unreal.GLTFExportOptions()
    size = unreal.GLTFMaterialBakeSize()
    size.set_editor_property("x", 256)
    size.set_editor_property("y", 256)
    size.set_editor_property("auto_detect", False)
    options.set_editor_property("default_material_bake_size", size)
    options.set_editor_property("export_source_model", False)
    for spec in request["modules"]:
        if not re.fullmatch("[a-z0-9-]{1,64}", spec["key"]):
            raise ValueError("Unsafe module key")
        if type(spec["lod"]) is not int or not 0 <= spec["lod"] <= 8:
            raise ValueError("Invalid LOD")
        checkpoint()
        cached = next(
            (old for old in previous.get("modules", []) if all(old.get(key) == value for key, value in spec.items())),
            None,
        )
        if cached:
            target = outputs / (spec["key"] + ".glb")
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == cached.get("sha256"):
                receipt["modules"].append({**cached, "file": str(target)})
                checkpoint()
                continue
        mesh = unreal.load_asset(spec["object_path"])
        assert isinstance(mesh, unreal.StaticMesh)
        actor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
        actor.tags = ["WATOOM_MODULE_BAKE"]
        actor.static_mesh_component.set_static_mesh(mesh)
        actor.static_mesh_component.set_editor_property("forced_lod_model", spec["lod"] + 1)
        options.set_editor_property("default_level_of_detail", spec["lod"])
        output = outputs / (spec["key"] + ".glb")
        messages = unreal.GLTFExporter.export_to_gltf(world, str(output), options, {actor})
        assert isinstance(messages, unreal.GLTFExportMessages)
        errors = list(messages.get_editor_property("errors"))
        assert not errors, str(errors)
        blob = output.read_bytes()
        assert struct.unpack_from("<4sII", blob) == (b"glTF", 2, len(blob))
        sizej = struct.unpack_from("<I", blob, 12)[0]
        document = json.loads(blob[20 : 20 + sizej])
        assert document.get("meshes") and document.get("materials")
        assert document.get("images") and document.get("textures"), "Material bake produced untextured output"
        assert any(
            m.get("pbrMetallicRoughness", {}).get("baseColorTexture") for m in document["materials"]
        ), "Base color texture was lost"
        receipt["modules"].append(
            {
                **spec,
                "file": str(output),
                "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
                "images": len(document["images"]),
                "materials": len(document["materials"]),
                "meshes": len(document["meshes"]),
                "warnings": list(messages.get_editor_property("warnings")),
                "suggestions": list(messages.get_editor_property("suggestions")),
            }
        )
        actors.destroy_actor(actor)
        checkpoint()
    receipt["status"] = "PASS"
    checkpoint()
except Exception:
    receipt.update(status="FAIL", error=traceback.format_exc())
    checkpoint()
finally:
    unreal.EditorPythonScripting.set_keep_python_script_alive(False)
