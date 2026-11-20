#!/usr/bin/env python3
"""Queue bounded resource changes for the next isolated Unreal phase; never interrupt an active compiler."""

import argparse, json, os, pathlib, tempfile, shutil, time

p = argparse.ArgumentParser()
p.add_argument("--evidence", required=True, type=pathlib.Path)
p.add_argument("--parallel-actions", type=int, choices=[1, 2, 3, 4, 5, 6, 7, 8], required=True)
p.add_argument("--apply", action="store_true")
a = p.parse_args()
r = a.evidence
path = r / "build-plan.json"
before = path.read_bytes()
plan = json.loads(before)
assert plan["source"] == "/data/ai/assets/unreal-engine"
assert pathlib.Path(plan["isolated_root"]).is_relative_to("/data/ai/builds")
assert (
    plan["original_preserved"] is True and json.loads((r / "isolated-copy-result.json").read_text())["status"] == "PASS"
)
for name in ["dirty-tracked-raw.private.tar.gz", "untracked-before.private.tar.gz", "source-sentinels.json"]:
    assert (r / name).is_file()
mem = {l.split(":")[0]: int(l.split()[1]) * 1024 for l in pathlib.Path("/proc/meminfo").read_text().splitlines()}
hard = min(a.parallel_actions * 3, 12) * 1024**3
soft = min(2.75 * a.parallel_actions, 11) * 1024**3
floor = 2 * 1024**3
# A live owned phase may reuse its already-approved memory envelope.
# Additional parallel jobs remain inside that same cgroup cap; no RAM is added.
group = pathlib.Path(plan.get("cgroup", ""))
reuse = (
    plan.get("memory_max_bytes") == hard
    and group.parent == pathlib.Path("/sys/fs/cgroup")
    and group.name.startswith("watoom-unreal-")
    and (group / "cgroup.procs").is_file()
    and (group / "cgroup.procs").read_text().strip()
    and int((group / "memory.max").read_text()) == hard
)
required = (floor + 1024**3) if reuse else (hard + floor)
assert mem["MemAvailable"] >= required, "Insufficient measured headroom; preserve current build limits"
assert shutil.disk_usage(plan["isolated_root"]).free >= plan["minimum_data_free_bytes"]
after = {
    **plan,
    "parallel_actions": a.parallel_actions,
    "memory_max_bytes": hard,
    "memory_high_bytes": int(soft),
    "cpu_quota": (
        str(
            {1: 150000, 2: 300000, 3: 450000, 4: 600000, 5: 800000, 6: 1000000, 7: 1000000, 8: 1000000}[
                a.parallel_actions
            ]
        )
        + " 100000"
    ),
    "minimum_host_available_bytes": floor,
    "flags": ["-NoUBA", "-NoDumpSyms", "-MaxParallelActions=" + str(a.parallel_actions)],
}
receipt = {
    "status": "PREFLIGHT_PASS",
    "apply": a.apply,
    "effective": "next owned build phase; current compiler unchanged",
    "host_available_bytes": mem["MemAvailable"],
    "parallel_actions": a.parallel_actions,
    "memory_max_bytes": hard,
    "minimum_host_available_bytes": floor,
    "reused_owned_memory_envelope": bool(reuse),
    "required_available_bytes": required,
    "before": plan,
    "after": after,
}
if a.apply:
    assert path.read_bytes() == before, "Build plan changed concurrently"
    descriptor, tmp = tempfile.mkstemp(prefix=".build-plan-", dir=r)
    try:
        with os.fdopen(descriptor, "w") as f:
            json.dump(after, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        fd = os.open(r, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    (r / ("resource-tuning-" + str(time.time_ns()) + ".json")).write_text(json.dumps(receipt, indent=2))
print(json.dumps({k: v for k, v in receipt.items() if k not in ("before", "after")}, indent=2))
