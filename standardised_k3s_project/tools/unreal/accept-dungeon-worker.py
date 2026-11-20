#!/usr/bin/env python3
"""Verify one completed isolated native worker's receipts and published artifacts."""

import argparse, hashlib, json, pathlib, re


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(evidence, name, catalog, visual):
    if not re.fullmatch("[a-z0-9-]{1,60}", name):
        raise ValueError("Safe worker name required")
    work = pathlib.Path("/data/ai/builds") / evidence.name / name
    launch = json.loads((evidence / (name + "-launch.json")).read_text())
    if launch["directory"] != str(work):
        raise ValueError("Worker identity mismatch")
    plan = json.loads((work / "dungeon-project/dungeon-assembly.json").read_text())
    manifest_path = work / "artifacts/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    validation = json.loads((work / "artifacts/validation.json").read_text())
    native = validation["native"]
    if (
        manifest["status"] != "PASS"
        or manifest["plan_sha256"] != plan["plan_sha256"]
        or native["plan_sha256"] != plan["plan_sha256"]
    ):
        raise ValueError("Positive matching worker receipts required")
    if (
        native["status"] != "NATIVE_QA_PASS_EXPORT_RENDER_PENDING"
        or native["native_collision"] != "PASS"
        or native["native_navigation"] != "PASS"
    ):
        raise ValueError("Real native collision/navigation required")
    if native["actors"] != len(plan["placements"]) or len(native["placements"]) != len(plan["placements"]):
        raise ValueError("Native actor count mismatch")
    yaws = set()
    for actual, expected in zip(native["placements"], plan["placements"]):
        if actual["module"] != expected["asset"] or actual["role"] != expected["role"]:
            raise ValueError("Native module identity mismatch")
        rotation = actual["rotation_pitch_yaw_roll"]
        wanted = expected["rotation"]
        if any(abs((a - b + 180) % 360 - 180) > 1e-5 for a, b in zip(rotation, wanted)):
            raise ValueError("Native rotation differs from plan")
        yaws.add(wanted[1] % 360)
    if len(native["ground_checks"]) != len(plan["layout"]["rooms"]) or not all(
        r["blocking"] for r in native["ground_checks"] + native["wall_checks"]
    ):
        raise ValueError("Positive physics controls required")
    if len(native["paths"]) != len(plan["layout"]["connections"]) or not all(r["complete"] for r in native["paths"]):
        raise ValueError("All native routes must complete")
    if len(native["capsule_checks"]) != len(plan["layout"]["connections"]) or any(
        r["blocked"] for r in native["capsule_checks"]
    ):
        raise ValueError("Actual capsule traversal required")
    if sha(work / "artifacts/dungeon.umap") != native["map_sha256"]:
        raise ValueError("Map changed after physical acceptance")
    for row in manifest["outputs"]:
        if not re.fullmatch("[a-zA-Z0-9_.-]+", row["path"]) or row["path"] in (".", ".."):
            raise ValueError("Unsafe artifact path")
        path = work / "artifacts" / row["path"]
        if path.is_symlink() or path.stat().st_size != row["bytes"] or sha(path) != row["sha256"]:
            raise ValueError("Published artifact changed")
    godot = manifest["godot_acceptance"]
    if (
        godot["status"] != "PASS"
        or godot["meshes"] < len(plan["placements"])
        or godot["collision_shapes"] < godot["meshes"]
        or godot["textured_surfaces"] != godot["surfaces"]
    ):
        raise ValueError("Actual textured Godot import/collision required")
    records = json.loads(catalog.read_text())["records"]
    provenance = json.loads((work / "artifacts/provenance.json").read_text())
    for row in provenance["source_files"]:
        record = records[row["id"]]
        path = pathlib.Path("/data/ai/assets") / record["path"]
        if not path.resolve().is_relative_to("/data/ai/assets") or sha(path) != row["sha256"]:
            raise ValueError("Original source hash changed")
    image = work / "artifacts/perspective.png"
    if not image.read_bytes().startswith(bytes.fromhex("89504e470d0a1a0a")):
        raise ValueError("Render artifact missing")
    if not visual:
        raise ValueError("Inspect actual perspective.png pixels before recording visual acceptance")
    result = {
        "status": "PASS",
        "job": launch["job"],
        "job_uid": launch["job_uid"],
        "directory": str(work),
        "source_sha256": launch["source_sha256"],
        "manifest_sha256": sha(manifest_path),
        "plan_sha256": plan["plan_sha256"],
        "style": json.loads((evidence / (name + "-request.json")).read_text())["dungeon"]["style"],
        "rooms": len(plan["layout"]["rooms"]),
        "levels": len({r["position"][2] for r in plan["layout"]["rooms"]}),
        "native_actors": native["actors"],
        "cardinal_yaws": sorted(yaws),
        "native_paths": native["paths"],
        "godot": godot,
        "source_integrity": "PASS",
        "visual_review": "PASS actual pixels reviewed",
        "renderer": "Blender CPU using pinned native Vulkan material bakes; editable map validated separately in Unreal",
    }
    (evidence / (name + "-acceptance.json")).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


def main():
    ap = argparse.ArgumentParser()
    for name in ("evidence", "catalog"):
        ap.add_argument("--" + name, required=True, type=pathlib.Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--visual-reviewed", action="store_true")
    a = ap.parse_args()
    verify(a.evidence.resolve(), a.name, a.catalog.resolve(), a.visual_reviewed)


if __name__ == "__main__":
    main()
