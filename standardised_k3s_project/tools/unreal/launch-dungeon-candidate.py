#!/usr/bin/env python3
"""Launch one bounded operator-only dungeon acceptance worker from frozen source.

Private candidate annotations never modify the authoritative Catalog or enable
the public pipeline. This intentionally does not build or promote an image.
"""

import argparse, pathlib, json, sys, hashlib, os, shutil, secrets, subprocess


def main():
    ap = argparse.ArgumentParser()
    for name in ("evidence", "catalog", "adapters"):
        ap.add_argument("--" + name, required=True, type=pathlib.Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--style", required=True, choices=["dungeon-builder", "dungeon-forge", "mixed"])
    ap.add_argument("--rooms", type=int, default=2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--levels", type=int, default=1)
    ap.add_argument("--anchor", required=True)
    ap.add_argument("--second-anchor")
    a = ap.parse_args()
    import re

    if not re.fullmatch("[a-z0-9-]{1,60}", a.name):
        raise ValueError("Safe candidate name required")
    evidence = a.evidence.resolve()
    if not evidence.is_relative_to("/data/ai/helper-scripts/reports"):
        raise ValueError("Private evidence required")
    work = pathlib.Path("/data/ai/builds") / evidence.name
    for path in (a.catalog.resolve(), a.adapters.resolve()):
        if not path.is_relative_to(work):
            raise ValueError("Existing private candidate files required")
    root = pathlib.Path(__file__).resolve().parents[1] / "watoom-toolkit"
    sys.path.insert(0, str(root))
    from asset_catalog import Catalog, atomic, checksum
    import dungeon_pipeline, kube_worker

    namespace = "watoom-code"

    def kub(*args, body=None):
        p = subprocess.run(
            ["kubectl", "-n", namespace, *args],
            input=json.dumps(body) if body is not None else None,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if p.returncode:
            raise RuntimeError(p.stderr[-700:])
        return json.loads(p.stdout) if p.stdout.strip().startswith(("{", "[")) else p.stdout

    pods = kub("get", "pods", "-l", "app=watoom-toolkit-worker", "-o", "json")["items"]
    if any(p.get("status", {}).get("phase") not in ("Succeeded", "Failed") for p in pods):
        raise RuntimeError("Existing worker must finish before serial acceptance")
    available = (
        int(
            next(
                l.split()[1]
                for l in pathlib.Path("/proc/meminfo").read_text().splitlines()
                if l.startswith("MemAvailable:")
            )
        )
        * 1024
    )
    if available < 8 * 1024**3:
        raise RuntimeError("6GiB worker plus2GiB reserve unavailable")
    base = work / a.name
    base.mkdir(mode=0o770)
    os.chown(base, 1009, 1009)
    data = json.loads(a.catalog.read_text())
    data["root"] = "/data/ai/assets"
    catalog = work / (a.name + "-catalog.json")
    atomic(catalog, data)
    adapters = json.loads(a.adapters.read_text())
    jobid = secrets.token_hex(8)
    engine = pathlib.Path("/data/ai/builds/unreal-recovery-20261016T213935Z/source")
    expected = "213806629a4cfb3c70d3d8ab264ce78ebaabf76f32206efed7b4009a70e3cc15"
    if checksum(engine / "Engine/Binaries/Linux/UnrealEditor") != expected:
        raise RuntimeError("Accepted editor changed")
    request = {
        "task": "3d-creative",
        "operation": "world",
        "asset_id": a.anchor,
        "seed": a.seed,
        "dungeon": {"style": a.style, "rooms": a.rooms, **({"levels": a.levels} if a.levels != 1 else {})},
        "timeout": 840,
        "output": "/job/artifacts",
        "job_id": jobid,
        "expected_engine_sha256": expected,
    }
    if a.second_anchor:
        request["asset_ids"] = [a.second_anchor]
    plan = dungeon_pipeline.prepare(request, Catalog("/data/ai/assets", catalog), candidate_adapters=adapters)
    request["expected_plan_sha256"] = plan["plan_sha256"]
    data["root"] = "/assets"
    atomic(catalog, data)
    os.chown(catalog, 1009, 1009)
    os.chmod(catalog, 0o600)
    selected = sorted(p for p in root.iterdir() if p.is_file() and p.suffix in (".py", ".gd", ".json"))
    sha = hashlib.sha256(b"".join(p.name.encode() + b"\0" + p.read_bytes() + b"\0" for p in selected)).hexdigest()
    source = work / (a.name + "-source-" + sha[:12])
    source.mkdir()
    for p in selected:
        shutil.copyfile(p, source / p.name)
    (source / "candidate-adapters.json").write_text(json.dumps(adapters))
    (source / "candidate_accept.py").write_text(
        'import json,sys\nfrom pathlib import Path\nfrom dungeon_worker import run\nrun(json.loads(sys.argv[1]),candidate_adapters=json.loads(Path("/opt/watoom/candidate-adapters.json").read_text()))\n'
    )
    deployment = kub("get", "deploy", "watoom-toolkit", "-o", "json")
    image = next(c["image"] for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "toolkit")
    argv = ["python3", "-B", "/opt/watoom/dungeon_worker.py", json.dumps(request, separators=(",", ":"))]
    spec = kube_worker.job_spec(
        jobid,
        argv,
        840,
        str(base),
        image,
        None,
        "3d-creative",
        None,
        False,
        "/data/ai/assets",
        str(engine),
        str(catalog),
    )
    spec["metadata"]["namespace"] = namespace
    spec["metadata"]["labels"]["watoom-test-owner"] = evidence.name
    pod = spec["spec"]["template"]["spec"]
    pod["containers"][0]["command"][2] = "/opt/watoom/candidate_accept.py"
    pod["containers"][0]["volumeMounts"].append({"name": "source", "mountPath": "/opt/watoom", "readOnly": True})
    pod["volumes"].append({"name": "source", "hostPath": {"path": str(source), "type": "Directory"}})
    atomic(evidence / (a.name + "-job.json"), spec)
    atomic(evidence / (a.name + "-request.json"), request)
    result = kub("create", "-f", "-", "-o", "json", body=spec)
    atomic(
        evidence / (a.name + "-launch.json"),
        {
            "status": "RUNNING",
            "fixture_only": True,
            "job": result["metadata"]["name"],
            "job_uid": result["metadata"]["uid"],
            "source_sha256": sha,
            "source": str(source),
            "placements": len(plan["placements"]),
            "directory": str(base),
        },
    )
    print(json.dumps({"job": result["metadata"]["name"], "source_sha256": sha, "placements": len(plan["placements"])}))


if __name__ == "__main__":
    main()
