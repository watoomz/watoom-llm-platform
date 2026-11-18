"""Run inside the accepted editor to reopen a generated map without saving it."""
import unreal,pathlib,json,hashlib
project=pathlib.Path(unreal.Paths.project_dir());output=project/"map-reopen-acceptance.json"
if output.exists():raise ValueError("Existing map-reopen evidence must not be replaced")
mapfile=project/"Content/GeneratedDungeon/Dungeon.umap";before=hashlib.sha256(mapfile.read_bytes()).hexdigest()
if not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level("/Game/GeneratedDungeon/Dungeon"):raise RuntimeError("Native map reopen failed")
actors=[a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors() if isinstance(a,unreal.StaticMeshActor)]
plan=json.loads((project/"dungeon-assembly.json").read_text())
if len(actors)!=len(plan["placements"]):raise RuntimeError("Reopened actor count differs from plan")
for actor in actors:
 component=actor.static_mesh_component
 if component.static_mesh is None or component.get_num_materials()<1 or any(component.get_material(i) is None for i in range(component.get_num_materials())):raise RuntimeError("Reopened module/material reference unresolved")
if hashlib.sha256(mapfile.read_bytes()).hexdigest()!=before:raise RuntimeError("Map changed during reopen")
version=unreal.SystemLibrary.get_engine_version()
if not version.startswith("5.8.3-"):raise RuntimeError("Unexpected editor version")
output.write_text(json.dumps({"status":"PASS","engine_version":version,"actors":len(actors),"map_sha256":before,"plan_sha256":plan["plan_sha256"],"source_map_unchanged":True},indent=2))
