"""Read-only: run INSIDE the Unreal Editor on the rig (Tools > Execute Python Script, or Output Log in Python mode).
Lists which MetaHuman export/build functions this engine + plugin version exposes. Changes nothing; loads no assets.
Writes <project>/Saved/metahuman_api_probe.json and logs the same JSON after the marker WLK_PROBE."""
import json
import os

import unreal

r = {"engine": unreal.SystemLibrary.get_engine_version()}
names = [n for n in dir(unreal) if "metahuman" in n.lower()]
r["metahuman_class_count"] = len(names)
want = {
    "MetaHumanCharacterExportBlueprintLibrary": ("",),
    "MetaHumanCharacterEditorSubsystem": ("build", "assemble", "rig", "export", "can_", "edit"),
    "MetaHumanDCCExportParams": ("",),
    "MetaHumanCharacterEditorBuildParameters": ("",),
    "MetaHumanDefaultPipelineType": ("",),
    "MetaHumanQualityLevel": ("",),
}
for cls, keys in want.items():
    c = getattr(unreal, cls, None)
    r[cls] = None if c is None else [m for m in dir(c) if not m.startswith("_") and any(k in m for k in keys)]
r["export_or_dcc_named_classes"] = [n for n in names if "export" in n.lower() or "dcc" in n.lower()]
path = os.path.join(unreal.Paths.project_saved_dir(), "metahuman_api_probe.json")
with open(path, "w") as f:
    f.write(json.dumps(r, indent=1))
unreal.log("WLK_PROBE file: " + path)
unreal.log("WLK_PROBE " + json.dumps(r))
