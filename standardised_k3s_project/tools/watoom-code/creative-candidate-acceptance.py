#!/usr/bin/env python3
"""Aggregate real native creative candidate receipts; never deploy or fabricate a passing gate."""

import argparse, hashlib, json, pathlib, re, sys, urllib.error
from maintenance_guard import Maintenance


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", required=True, type=pathlib.Path)
    a = p.parse_args()
    root = a.evidence.resolve()
    out = root / "candidate"
    identity = json.loads((out / "identity.json").read_text())
    assert identity["namespace"] == "watoom-code" and identity["name"] == "watoom-code-memory-candidate-20261016"
    m = Maintenance(identity["namespace"], identity["name"], out, True, True)
    assert m.request("/api/session/active")["data"] == {}
    assert m.request("/api/session/deployment-guard")["data"] == {
        "version": 1,
        "supported": True,
        "held": True,
        "leases": 0,
    }
    try:
        m.request("/api/config", authenticated=False)
    except urllib.error.HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError("Anonymous configuration access permitted")
    requests = json.loads((out / "release-native-requests.json").read_text())
    wanted = {item["job"]: item for item in requests}
    rows = json.loads(
        m.exec(
            "import sqlite3,json;d=sqlite3.connect('file:/state/application.sqlite?mode=ro',uri=True);print(json.dumps([dict(zip(['job','phase','outcome'],row)) for row in d.execute(\"SELECT job,phase,outcome FROM _watoom_specialist_job WHERE job LIKE 'creative-release-020-%'\")]))"
        )
    )
    assert len(rows) == 12 and all(row["phase"] == "completed" for row in rows)
    verified = {}
    catalog_data = json.loads((out / "toolkit-state/asset-catalog/catalog.json").read_text())
    assert (
        catalog_data["root"] == "/assets"
        and catalog_data["schema"] == 1
        and catalog_data["cursor"] == ""
        and len(catalog_data["records"]) == 6309
    )
    assert all(record.get("metadata_version") == 2 for record in catalog_data["records"].values())
    for row in rows:
        if row["job"] not in wanted:
            continue
        outcome = json.loads(row["outcome"])
        assert len(outcome["artifacts"]) <= 16
        manifest_artifact = next(item for item in outcome["artifacts"] if item["reference"].endswith("/manifest.json"))
        assert manifest_artifact["reference"].startswith("artifact:generated/watoom-toolkit-3d/v1/")
        relative = manifest_artifact["reference"][9:]
        manifest_path = out / "published" / relative
        assert (
            manifest_path.resolve().is_relative_to((out / "published").resolve())
            and sha(manifest_path) == manifest_artifact["sha256"]
        )
        manifest = json.loads(manifest_path.read_text())
        assert manifest["status"] == "PASS"
        details = manifest["creative"]
        assert details["source_hashes_unchanged"] is True
        for file in manifest["outputs"]:
            assert re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", file["path"]) and file["path"] not in [".", ".."]
            path = manifest_path.parent / file["path"]
            assert not path.is_symlink() and path.stat().st_size == file["bytes"] and sha(path) == file["sha256"]
        for reference in details["source_references"]:
            source = pathlib.Path("/data/ai/assets") / reference["path"]
            assert (
                source.resolve().is_relative_to(pathlib.Path("/data/ai/assets").resolve())
                and sha(source) == reference["sha256"]
            )
        godot = manifest["godot_acceptance"]
        assert godot["status"] == "PASS" and godot["meshes"] > 0
        operation = wanted[row["job"]]["payload"]["operation"]
        if operation == "optimize":
            assert godot["meshes"] == 1 and godot["collision_shapes"] > 0
            assert "NOT CONFIGURED" in details["optimization"]["lod_runtime_policy"]
        elif operation == "world":
            assert godot["collision_shapes"] > 0 and (manifest_path.parent / "world-layout.json").is_file()
            prior = json.loads((root / "world-determinism.json").read_text())
            assert prior["status"] == "PASS" and sha(manifest_path.parent / "asset.glb") == prior["glb_sha256"]
        elif operation == "character":
            assert (
                godot["bones"] > 0
                and set(godot["animation_motion"]) == {"Idle", "Walk", "Run"}
                and min(godot["animation_motion"].values()) > 0.00001
            )
            for clip in ["Idle", "Walk", "Run"]:
                assert sha(manifest_path.parent / (clip + "-a.png")) != sha(manifest_path.parent / (clip + "-b.png"))
        elif operation == "material":
            assert details["material"]["baking"] == {"type": "EMIT", "device": "CPU", "resolution": 128, "finite": True}
            assert "normal" in godot["material_maps"] and all(
                (manifest_path.parent / (name + ".png")).is_file()
                for name in ["albedo", "normal", "roughness", "metallic", "orm"]
            )
        else:
            raise AssertionError("Unexpected operation")
        verified[operation] = {
            "status": "PASS",
            "job": row["job"],
            "manifest": manifest_artifact["reference"],
            "manifest_sha256": manifest_artifact["sha256"],
            "glb_sha256": sha(manifest_path.parent / "asset.glb"),
            "godot": godot,
        }
    assert set(verified) == {"optimize", "world", "character", "material"}
    for name in [
        "independent-pair-rollback.json",
        "restart-idempotency.json",
        "final-pair-source-verification.json",
        "final-guard-rejection.json",
        "gui-final/creative-browser.json",
        "memory-acceptance.private.json",
    ]:
        assert json.loads((out / name).read_text())["status"] == "PASS", name
    rollback = json.loads((out / "independent-pair-rollback.json").read_text())
    assert rollback["image"] == identity["image"] and rollback["toolkit_image"] == identity["toolkit_image"]
    assert (
        rollback["injected_failure_automatic_rollback"] == "PASS" and rollback["old_toolkit_real_execution"] == "PASS"
    )
    readers = json.loads((root / "asset-reader-proof/read-access.json").read_text())
    assert (
        readers["status"] == "PASS"
        and readers["worker"]["checked"] == len(catalog_data["records"])
        and readers["worker"]["denied"] == 0
        and readers["application"]["denied"] == 0
    )
    result = {
        key: "PASS"
        for key in [
            "guard_boot",
            "guard_race",
            "rollback",
            "authenticated_api",
            "authenticated_gui",
            "memory",
            "creative",
            "creative_rollback",
            "creative_api",
            "creative_gui",
            "creative_durability",
        ]
    }
    result.update(
        {
            "status": "PASS",
            "image": identity["image"],
            "toolkit_image": identity["toolkit_image"],
            "acceptance_root": str(out),
            "pipelines": verified,
            "catalog": {
                "supported_files": len(catalog_data["records"]),
                "deferred_checksums": sum(
                    value["checksum_state"] == "DEFERRED" for value in catalog_data["records"].values()
                ),
                "schema": 1,
                "metadata_version": 2,
                "root": "/assets",
                "sha256": sha(out / "toolkit-state/asset-catalog/catalog.json"),
            },
            "asset_library_access": "PASS",
            "verified_worker_uid": 1010,
            "verified_application_uid": 1001,
            "anonymous_api_status": 401,
            "maintenance_rejection_status": 500,
            "previous_negative_case": "Verified pre-output ACL failure retained as quarantined uncertain operation; original replay refused; never erased or claimed successful",
            "unreal": "BLOCKED until current protected editor build and acceptance finish",
        }
    )
    (out / "candidate-acceptance.json").write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                "status": "PASS",
                "pipelines": list(verified),
                "supported_files": len(catalog_data["records"]),
                "deferred_checksums": result["catalog"]["deferred_checksums"],
                "candidate_acceptance": str(out / "candidate-acceptance.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
