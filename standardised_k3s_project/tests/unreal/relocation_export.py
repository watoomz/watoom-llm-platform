"""Run with Unreal Python in an isolated relocation acceptance project."""
import unreal
import pathlib
import json
import hashlib
import os

out = pathlib.Path(os.environ["WATOOM_ACCEPTANCE_OUTPUT"]).resolve()
engine = pathlib.Path(unreal.Paths.engine_dir()).resolve()
for hidden in json.loads(os.environ["WATOOM_ACCEPTANCE_HIDDEN_ROOTS"]):
    assert not (pathlib.Path(hidden) / "Engine").exists(), "old installation must be hidden"
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert levels.new_level("/Game/RelocationProbe")
actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(0, 0, 0))
mesh = unreal.load_asset("/Engine/BasicShapes/Cube")
assert mesh
actor.static_mesh_component.set_static_mesh(mesh)
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
result = unreal.GLTFExporter.export_to_gltf(world, str(out / "probe.glb"), unreal.GLTFExportOptions(), set())
assert isinstance(result, unreal.GLTFExportMessages)
assert not list(result.get_editor_property("errors"))
blob = (out / "probe.glb").read_bytes()
assert blob[:4] == b"glTF"
editor_hash = hashlib.sha256((engine / "Binaries/Linux/UnrealEditor").read_bytes()).hexdigest()
assert editor_hash == os.environ["WATOOM_ACCEPTANCE_EDITOR_SHA256"]
(out / "relocation.json").write_text(json.dumps({
    "status": "PASS_RELOCATED_NATIVE_EXPORT",
    "engine": str(engine),
    "version": unreal.SystemLibrary.get_engine_version(),
    "editor_sha256": editor_hash,
    "old_installations_hidden": True,
    "glb_bytes": len(blob)
}, indent=2))
