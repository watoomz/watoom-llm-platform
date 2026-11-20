#!/usr/bin/env python3
"""Refresh the single live Catalog through its supported bounded Toolkit job API."""

import argparse, fcntl, hashlib, json, pathlib, re, sys, time, urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "watoom-code"))
from maintenance_guard import Maintenance


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True, type=pathlib.Path)
    ap.add_argument(
        "--acquisition-evidence",
        type=pathlib.Path,
        help="Explicit completed receipt-backed queue; defaults to original dungeon acquisition",
    )
    ap.add_argument(
        "--verify-only", action="store_true", help="Revalidate an existing completed scan without new index jobs"
    )
    a = ap.parse_args()
    out = a.evidence.resolve()
    assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports")) and out.is_dir()
    lock = (out / "catalog-reconcile.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fab = (
        a.acquisition_evidence
        or pathlib.Path(pathlib.Path("/data/ai/helper-scripts/reports/dungeon-fab-current.txt").read_text().strip())
    ).resolve()
    assert (
        fab.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports")) and fab.is_dir()
    ), "Invalid acquisition evidence scope"
    downloads = json.loads((fab / "download-status.json").read_text())
    assert (
        downloads["status"] == "PASS" and len(downloads["completed"]) == downloads["total"]
    ), "Finish verified acquisition first; never index an incomplete pack as complete"
    result = out / "catalog-reconciliation.json"
    assert not result.exists(), "Inspect completed reconciliation rather than replaying it"
    state = pathlib.Path("/data/ai/watoom-code/toolkit-state")
    assert (
        out / "catalog-before.private.json"
    ).exists() == a.verify_only, "Use fresh scan evidence or verify-only with preserved snapshot"
    before = (
        (out / "catalog-before.private.json").read_bytes()
        if a.verify_only
        else (state / "asset-catalog/catalog.json").read_bytes()
    )
    if not a.verify_only:
        (out / "catalog-before.private.json").write_bytes(before)
    original = json.loads(before)
    adapters = {k: v["dungeon_adapter"] for k, v in original["records"].items() if "dungeon_adapter" in v}
    m = Maintenance("watoom-code", "watoom-code", out, True, True)
    # Read actual controller limits and conservative projected metadata size before
    # using its local index subprocess. Larger libraries need an isolated metadata job.
    quantity = m.kub("get", "deploy", "watoom-toolkit")["spec"]["template"]["spec"]["containers"][0]["resources"][
        "limits"
    ]["memory"]
    match = re.fullmatch(r"([0-9]+)(Mi|Gi)", quantity)
    assert match, "Inspect unrecognised memory quantity"
    memory_limit = int(match[1]) * (1024**2 if match[2] == "Mi" else 1024**3)
    all_paths = {v["path"] for v in original["records"].values()}
    for item in downloads["completed"]:
        receipt = json.loads(pathlib.Path(item["receipt"]).read_text())
        all_paths.update(str(pathlib.Path(file).relative_to("/data/ai/assets")) for file in receipt["files"])
    projected = int(len(before) / max(1, len(original["records"])) * len(all_paths))
    assert (
        projected * 8 + 128 * 1024**2 < memory_limit * 0.9
    ), "Use an isolated bounded Catalog worker: projected metadata exceeds the live controller headroom"
    layers = m.request("/api/config")
    entries = next(
        x["info"]["watoom_specialists"]["entries"]
        for x in reversed(layers)
        if x.get("type") == "document" and "watoom_specialists" in x.get("info", {})
    )
    url = next(x["url"] for x in entries if x["descriptor"]["id"] == "local-toolkit")
    code = """import os,sys,json,urllib.request
r=urllib.request.Request(sys.argv[1]+"/api/jobs",headers={"Authorization":"Bearer "+os.environ["WATOOM_TOKEN"],"Content-Type":"application/json"},data=json.dumps({"task":"asset-index","limit":1024,"timeout":30}).encode())
print(urllib.request.urlopen(r,timeout=45).read().decode())
"""
    batches = json.loads((out / "catalog-batches.json").read_text()) if a.verify_only else []
    cursor = original.get("cursor", "")
    stalled = 0
    started = time.monotonic()
    for index in range(0 if a.verify_only else 100):
        assert time.monotonic() - started < 1800, "Catalog reconciliation time bound"
        value = json.loads(m.exec(code, url))
        assert value["status"] == "PASS" and value["verification"]["status"] == "PASS"
        ident = value["id"]
        assert re.fullmatch("[a-f0-9]{16}", ident)
        evidence = state / "jobs" / ident / "worker/artifacts/result.json"
        data = json.loads(evidence.read_text())
        assert data["status"] == "PASS", data.get("errors")
        current = json.loads((state / "asset-catalog/catalog.json").read_text())
        assert all(
            current["records"].get(k, {}).get("dungeon_adapter") == v for k, v in adapters.items()
        ), "Verified native adapter annotation changed"
        batches.append(
            {
                "job": ident,
                "processed": data["processed"],
                "indexed": data["indexed"],
                "scan_complete": data["scan_complete"],
                "errors": data["errors"],
            }
        )
        (out / "catalog-batches.json").write_text(json.dumps(batches, indent=2))
        if data["scan_complete"]:
            break
        stalled = stalled + 1 if cursor == current.get("cursor", "") else 0
        assert stalled < 2, "Catalog scan made no progress; inspect before repeated attempts"
        cursor = current.get("cursor", "")
        time.sleep(1)
    else:
        if not a.verify_only:
            raise ValueError("Catalog batch count boundary")
    current = json.loads((state / "asset-catalog/catalog.json").read_text())
    assert set(original["records"]) <= set(
        current["records"]
    ), "Existing entries disappeared; inspect actual source changes"
    paths = {v["path"]: v for v in current["records"].values()}
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "watoom-toolkit"))
    from asset_catalog import FORMATS, EXCLUDE

    checked = 0
    unsupported = 0
    excluded = 0
    for item in downloads["completed"]:
        receipt = json.loads(pathlib.Path(item["receipt"]).read_text())
        assert receipt["asset"]["id"] == item["id"]
        for file in receipt["files"]:
            path = pathlib.Path(file)
            assert path.resolve().is_relative_to("/data/ai/assets")
            if any(part in EXCLUDE for part in path.relative_to("/data/ai/assets").parts):
                excluded += 1
                continue
            if path.suffix.lower() not in FORMATS:
                unsupported += 1
                continue
            relative = str(path.relative_to("/data/ai/assets"))
            record = paths[relative]
            stat = path.stat()
            assert record["bytes"] == stat.st_size and record["mtime_ns"] == stat.st_mtime_ns
            checked += 1
    result.write_text(
        json.dumps(
            {
                "status": "PASS",
                "records": len(paths),
                "prior_records_preserved": len(original["records"]),
                "verified_adapters_preserved": len(adapters),
                "receipt_backed_supported_files": checked,
                "unsupported_source_files": unsupported,
                "excluded_source_files": excluded,
                "batches": len(batches),
                "catalog_sha256": hashlib.sha256((state / "asset-catalog/catalog.json").read_bytes()).hexdigest(),
                "access": "Existing global /assets read-only mounts inherited by current/future project workers; no per-project catalog or pack duplication",
                "license_or_engine_compatibility": "Catalog discovery does not grant redistribution or certify unsupported formats",
            },
            indent=2,
        )
    )
    print("PASS single global Catalog reconciled through supported Toolkit API")


if __name__ == "__main__":
    main()
