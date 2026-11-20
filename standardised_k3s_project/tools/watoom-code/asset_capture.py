#!/usr/bin/env python3
"""Fixed external 4GiB capture runner; accepts declarative manifests only."""

import argparse, json, pathlib, os, subprocess, time, sys, hashlib, re, fcntl, struct
from asset_capture_contract import manifest, sha, contained

CONFIG = pathlib.Path("/etc/watoom-asset-capture.json")


def check_outputs(v, out, result, returncode):
    """Validate a finished worker's receipt and outputs (shared by the server and Bazzite runners); mutates result."""
    result["exit_code"] = returncode
    receipt = out / "worker.json"
    if receipt.is_file():
        result.update(json.loads(receipt.read_text()))
    for filename in result.get("files", []):
        target = contained(out / filename, [out])
        if target.parent != out:
            raise ValueError("Unexpected nested worker artifact")
    images = result.get("images", [])
    if v["mode"] not in ("inspect", "pose-inspect", "pose-prepare") and len(images) != (
        1 if v["mode"] == "still" else v.get("frames", [1, 1])[1] - v.get("frames", [1, 1])[0] + 1
    ):
        raise ValueError("Missing actual rendered frames")
    for filename in images:
        target = contained(out / filename, [out])
        with target.open("rb") as image:
            header = image.read(24)
        if header[:8] != bytes([137, 80, 78, 71, 13, 10, 26, 10]) or list(struct.unpack(">II", header[16:24])) != v.get(
            "resolution", [768, 1024]
        ):
            raise ValueError("Invalid or incorrectly sized PNG")
    result["source_unchanged"] = sha(v["source"]) == v["source_sha256"]
    result["cgroup_limit_verified"] = result.get("cgroup_memory_max") == 4294967296
    result["outputs"] = [
        {"path": str(x), "sha256": sha(x), "bytes": x.stat().st_size}
        for x in out.iterdir()
        if x.is_file() and not x.is_symlink()
    ]
    if (
        returncode != 0
        or not result["source_unchanged"]
        or not result["cgroup_limit_verified"]
        or not receipt.is_file()
    ):
        result["status"] = "FAIL"


def run(project, job, evidence, config=CONFIG, expected_manifest_sha256=None):
    if os.geteuid() != 0:
        raise PermissionError("Operator only")
    private = pathlib.Path("/data/ai/private/asset-capture")
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (private / "operator.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.check_output(
        [
            "systemctl",
            "list-units",
            "--state=running",
            "--no-legend",
            "--plain",
            "watoom-godot-*",
            "watoom-blender-capture-*",
        ],
        text=True,
    ).strip():
        raise RuntimeError("External engine worker already active; reconcile before launch")
    cfg = json.loads(config.read_text())
    p = pathlib.Path(project)
    if str(p) not in cfg["projects"] or not p.is_dir() or p.resolve() != p:
        raise ValueError("Unapproved project")
    if not re.fullmatch("[A-Za-z0-9][A-Za-z0-9_-]{0,63}", job):
        raise ValueError("Invalid job")
    roots = cfg["source_roots"] + [str(p)]
    mf = contained(p / ".opencode/capture-jobs" / job / "request.json", [str(p)])
    if mf.stat().st_size > 65536:
        raise ValueError("Oversize manifest")
    raw = mf.read_bytes()
    if expected_manifest_sha256 and hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
        raise ValueError("Manifest changed after native authorization")
    v = manifest(json.loads(raw), roots)
    if sha(v["source"]) != v["source_sha256"]:
        raise ValueError("Source revision mismatch")
    blender = pathlib.Path(cfg["blender"])
    if sha(blender) != cfg["blender_sha256"]:
        raise ValueError("Unqualified Blender binary")
    mem = (
        int(
            next(
                x.split()[1]
                for x in pathlib.Path("/proc/meminfo").read_text().splitlines()
                if x.startswith("MemAvailable:")
            )
        )
        * 1024
    )
    if mem < 6 * 1024**3:
        raise RuntimeError("WAITING_FOR_HEADROOM: 4GiB worker plus2GiB reserve")
    ev = pathlib.Path(evidence)
    ev.mkdir(parents=True, exist_ok=False)
    out = p / ".opencode/captures" / job
    if out.exists():
        raise ValueError("Output already exists; inspect it, never replay")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.parent.resolve() != out.parent:
        raise ValueError("Indirect output")
    out.mkdir()
    os.chown(out, 1001, 1001)
    plan = out / "plan.json"
    plan.write_text(json.dumps({"manifest": v, "source_roots": roots, "ffmpeg": cfg.get("ffmpeg")}, indent=2))
    plan.chmod(0o644)
    unit = "watoom-blender-capture-" + hashlib.sha256((str(out) + str(time.time_ns())).encode()).hexdigest()[:16]
    props = {
        "User": "1001",
        "Group": "1001",
        "MemoryMax": "4G",
        "MemorySwapMax": "0",
        "CPUQuota": "200%",
        "TasksMax": "128",
        "RuntimeMaxSec": "900",
        "TimeoutStopSec": "10",
        "KillMode": "control-group",
        "PrivateNetwork": "yes",
        "PrivateDevices": "yes",
        "PrivateTmp": "yes",
        "ProtectSystem": "strict",
        "ProtectHome": "yes",
        "NoNewPrivileges": "yes",
        "ReadWritePaths": str(out),
        "InaccessiblePaths": "/data/ai/private /data/ai/watoom-code",
    }
    cmd = ["systemd-run", "--wait", "--collect", "--unit=" + unit]
    for k, val in props.items():
        cmd += ["--property=" + k + "=" + val]
    cmd += [
        "--setenv=HOME=/tmp",
        "--setenv=XDG_CACHE_HOME=/tmp",
        "--setenv=OMP_NUM_THREADS=2",
        "--setenv=OPENBLAS_NUM_THREADS=2",
        str(blender),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "--python-exit-code",
        "1",
        "--python",
        str(pathlib.Path(__file__).with_name("asset_capture_blender.py")),
        "--",
        str(plan),
    ]
    result = {
        "status": "FAIL",
        "unit": unit,
        "memory_limit": 4294967296,
        "source": v["source"],
        "source_sha256": v["source_sha256"],
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "runner_sha256": sha(__file__),
        "worker_sha256": sha(pathlib.Path(__file__).with_name("asset_capture_blender.py")),
        "output": str(out),
    }
    try:
        with (ev / "worker.log").open("w") as log:
            r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=950)
        with (ev / "blender-journal.log").open("w") as journal:
            subprocess.run(
                ["journalctl", "--no-pager", "-u", unit], stdout=journal, stderr=subprocess.STDOUT, timeout=15
            )
        check_outputs(v, out, result, r.returncode)
    except Exception as e:
        subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=20)
        result.update(status="FAIL", error=str(e)[:500])
    (ev / "result.json").write_text(json.dumps(result, indent=2))
    os.chmod(ev / "result.json", 0o644)
    print(json.dumps(result))
    return 0 if result["status"] in ("PASS", "CAPTURED_VISUAL_REVIEW_PENDING", "PREPARED_REVIEW_PENDING") else 1


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--project", required=True)
    a.add_argument("--job", required=True)
    a.add_argument("--evidence", required=True)
    a.add_argument("--i-approve", action="store_true")
    a.add_argument("--config", type=pathlib.Path, default=CONFIG)
    a.add_argument("--expected-manifest-sha256")
    v = a.parse_args()
    if not v.i_approve:
        a.error("Explicit operator approval required")
    sys.exit(run(v.project, v.job, v.evidence, v.config, v.expected_manifest_sha256))
