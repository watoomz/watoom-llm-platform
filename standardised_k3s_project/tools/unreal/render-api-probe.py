import unreal,pathlib,json
assert hasattr(unreal,"GLTFExporter") and hasattr(unreal.GLTFExporter,"export_to_gltf")
assert hasattr(unreal,"AutomationLibrary") and hasattr(unreal.AutomationLibrary,"take_high_res_screenshot")
assert hasattr(unreal,"LevelEditorSubsystem")
root=pathlib.Path(unreal.Paths.project_dir())
(root/"render-api-probe.json").write_text(json.dumps({"status":"PASS","version":unreal.SystemLibrary.get_engine_version()}))
print("WATOOM_RENDER_API_PROBE_PASS")
