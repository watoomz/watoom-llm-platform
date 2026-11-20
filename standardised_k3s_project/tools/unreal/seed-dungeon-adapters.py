#!/usr/bin/env python3
"""Merge receipt-backed adapters into a private copy of the existing global Catalog."""

import argparse, copy, hashlib, json, pathlib, sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    for key in ("evidence", "catalog", "subset", "adapters"):
        ap.add_argument("--" + key, required=True, type=pathlib.Path)
    a = ap.parse_args()
    e = a.evidence.resolve()
    work = pathlib.Path("/data/ai/builds") / e.name
    if not e.is_relative_to("/data/ai/helper-scripts/reports"):
        raise ValueError("Private evidence required")
    if any(not p.resolve().is_relative_to(work) for p in (a.subset, a.adapters)):
        raise ValueError("Existing private inspection inputs required")
    original = json.loads(a.catalog.read_text())
    if (
        original.get("schema") != 1
        or original.get("root") != "/assets"
        or original.get("cursor") != ""
        or len(original.get("records", {})) < 6309
    ):
        raise ValueError("Completed global Catalog required")
    proofs = {}
    for style, prefix in (("dungeon-builder", "builder"), ("dungeon-forge", "forge"), ("mixed", "mixed")):
        receipt = e / (prefix + "-vertical-landing-candidate-acceptance.json")
        proof = json.loads(receipt.read_text())
        if (
            proof.get("status") != "PASS"
            or proof["style"] != style
            or proof["levels"] != 2
            or proof["rooms"] != 4
            or proof["cardinal_yaws"] != [0, 90, 180, 270]
        ):
            raise ValueError("Full real worker/rotation/visual acceptance required")
        manifest = pathlib.Path(proof["directory"]) / "artifacts/manifest.json"
        if sha(manifest) != proof["manifest_sha256"]:
            raise ValueError("Accepted worker manifest changed")
        proofs[style] = (proof, sha(receipt))
    subset = json.loads(a.subset.read_text())
    adapters = json.loads(a.adapters.read_text())
    merged = copy.deepcopy(original)
    added = 0
    for key, record in subset["records"].items():
        path = pathlib.Path("/data/ai/assets") / record["path"]
        if not path.resolve().is_relative_to("/data/ai/assets") or path.stat().st_size != record["bytes"]:
            raise ValueError("Selected source identity changed")
        with path.open("rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != record["sha256"]:
                raise ValueError("Selected source hash changed")
        if key in merged["records"]:
            old = merged["records"][key]
            if (
                old["path"] != record["path"]
                or old["bytes"] != record["bytes"]
                or old["mtime_ns"] != record["mtime_ns"]
            ):
                raise ValueError("Refresh changed Catalog entries before seeding")
            # Keep existing license/compatibility/metadata; enrich only proven checksum fields.
            old.update(sha256=record["sha256"], checksum_state="VERIFIED")
        else:
            merged["records"][key] = copy.deepcopy(record)
            added += 1
    for key, adapter in adapters.items():
        style = adapter["style"]
        proof, pin = proofs[style]
        if key not in merged["records"] or style not in ("dungeon-builder", "dungeon-forge"):
            raise ValueError("Unknown inspected anchor")
        verified = copy.deepcopy(adapter)
        verified.update(
            status="VERIFIED",
            candidate_only=False,
            native_qa_receipt_sha256=pin,
            vertical_verified=True,
            vertical_receipt_sha256=pin,
            compatibility_receipt_sha256=proofs["mixed"][1],
        )
        for entries in verified["modules"].values():
            for module in entries:
                module.update(collision_verified=True, materials_verified=True)
        record = merged["records"][key]
        record["dungeon_adapter"] = verified
        metadata = record.setdefault("source_metadata", {})
        metadata["dungeon_generator"] = {
            "style": style,
            "status": "VERIFIED",
            "levels": 2,
            "profile": "300cm tile/900cm room/400cm floors",
            "receipt_sha256": pin,
        }
    # Prove normal public preparation uses these annotations rather than an operator bypass.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "watoom-toolkit"))
    from asset_catalog import Catalog, atomic
    import dungeon_pipeline

    output = e / "verified-dungeon-catalog.json"
    merged["root"] = "/data/ai/assets"
    atomic(output, merged)
    anchors = {v["style"]: k for k, v in adapters.items()}
    plans = {}
    for style in ("dungeon-builder", "dungeon-forge", "mixed"):
        request = {
            "asset_id": anchors["dungeon-builder" if style == "mixed" else style],
            "seed": 42,
            "dungeon": {"style": style, "rooms": 4, "levels": 2},
        }
        if style == "mixed":
            request["asset_ids"] = [anchors["dungeon-forge"]]
        plan = dungeon_pipeline.prepare(request, Catalog("/data/ai/assets", output))
        if plan["plan_sha256"] != proofs[style][0]["plan_sha256"]:
            raise ValueError("Public assembly differs from actual accepted native worker")
        plans[style] = {"plan_sha256": plan["plan_sha256"], "placements": len(plan["placements"])}
    merged["root"] = "/assets"
    atomic(output, merged)
    result = {
        "status": "PASS",
        "catalog": str(output),
        "sha256": sha(output),
        "base_sha256": sha(a.catalog),
        "base_records": len(original["records"]),
        "records": len(merged["records"]),
        "added": added,
        "native_public_preparation": plans,
        "live_state_changed": False,
    }
    atomic(e / "verified-dungeon-catalog-acceptance.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
