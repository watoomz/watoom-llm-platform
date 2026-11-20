#!/usr/bin/env python3
"""Receipt-gated, read-only Unreal project integration inspection; never executes plugins."""

import argparse, hashlib, json, pathlib, configparser

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
ap.add_argument("--asset-id", required=True)
a = ap.parse_args()
out = a.evidence.resolve()
assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports"))
status = json.loads((out / "download-status.json").read_text())
item = next(x for x in status.get("completed", []) if x["id"] == a.asset_id and x["status"] == "PASS")
receipt = json.loads(pathlib.Path(item["receipt"]).read_text())
assert receipt["asset"]["id"] == a.asset_id
source = pathlib.Path(item["path"]).resolve()
assert source.parent == pathlib.Path("/data/ai/assets/fab")
projects = list(source.glob("*.uproject"))
assert len(projects) == 1, "Inspect actual complete-project layout"
project = projects[0]
descriptor = json.loads(project.read_text())
ini = configparser.ConfigParser(strict=False, interpolation=None)
ini.read(source / "Config/DefaultEngine.ini")
section = "/Script/EngineSettings.GameMapsSettings"
maps = {k: ini.get(section, k, fallback="") for k in ["EditorStartupMap", "GameDefaultMap", "GameInstanceClass"]}
required = [x["Name"] for x in descriptor.get("Plugins", []) if x.get("Enabled")]
result = {
    "status": "SOURCE_INSPECTED_RUNTIME_PENDING",
    "asset_id": a.asset_id,
    "source": str(source),
    "project": project.name,
    "descriptor_sha256": hashlib.sha256(project.read_bytes()).hexdigest(),
    "source_engine": descriptor.get("EngineAssociation"),
    "required_plugins": required,
    "maps": maps,
    "project_modules": descriptor.get("Modules", []),
    "integration_route": "Existing global Catalog .uproject record -> isolated project-local staging preserving Content namespaces and Config -> actual accepted Unreal load/Blueprint compile/play test -> opt-in game project integration",
    "unreal_5_8_3": "NOT TESTED",
    "gameplay": "NOT TESTED",
    "godot_logic_port": "NOT PROVIDED; Unreal Blueprints/input/game instance are not portable via static GLB",
    "source_policy": "Read-only shared source. Never overwrite a game project Config wholesale. Never auto-enable downloaded code plugins/MCP servers.",
    "required_acceptance": [
        "Receipt-backed source",
        "Required plugin/modules available and real BuildIds match",
        "Isolated project load and Blueprint compilation",
        "Input mapping/game instance/GameMode ownership review",
        "Actual movement/combat/damage/health behavior and rendered playtest",
        "Project-scoped opt-in with restart/idempotency and existing game regression",
    ],
}
target = out / ("framework-" + a.asset_id + ".json")
target.write_text(json.dumps(result, indent=2))
print(json.dumps(result))
