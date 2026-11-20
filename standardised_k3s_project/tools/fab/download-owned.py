#!/usr/bin/env python3
"""Bounded sequential acquisition using the existing authenticated epic-fab CLI."""

import argparse, datetime, fcntl, json, os, pathlib, re, shutil, signal, subprocess, time

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
ap.add_argument("--concurrency", type=int, choices=range(1, 5), default=4)
ap.add_argument("--asset-hours", type=int, choices=range(1, 5), default=3)
ap.add_argument("--continue-on-error", action="store_true")
ap.add_argument("--engine", default="UE_5.8")
a = ap.parse_args()
assert re.fullmatch(r"UE_[0-9]+\.[0-9]+", a.engine)
r = a.evidence.resolve()
assert r.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports"))
root = pathlib.Path("/data/ai/assets/fab").resolve()
lock = (r / "download.lock").open("w")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
items = json.loads((r / "server-download-selection.json").read_text())
assert items and len({x["id"] for x in items}) == len(items)
assert all(re.fullmatch("[a-f0-9]{32}", x["id"]) for x in items)


def save(v):
    p = r / "download-status.json"
    t = p.with_suffix(".new")
    t.write_text(json.dumps(v, indent=2))
    os.replace(t, p)


def available():
    return (
        int(
            next(
                x.split()[1]
                for x in pathlib.Path("/proc/meminfo").read_text().splitlines()
                if x.startswith("MemAvailable:")
            )
        )
        * 1024
    )


child = None
group = None
results = []
failures = []
started = time.monotonic()
initial = shutil.disk_usage(root).free


def stop():
    if child and child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
    if group and (group / "cgroup.procs").read_text().strip():
        (group / "cgroup.kill").write_text("1")


def interrupt(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, interrupt)
signal.signal(signal.SIGINT, interrupt)
try:
    for index, item in enumerate(items):
        slug = re.sub("[^a-z0-9]+", "-", item["title"].lower()).strip("-")[:64]
        target = root / (slug + "-" + item["id"][:8])
        assert target.resolve().parent == root and not target.is_symlink()
        receipt = r / ("download-" + item["id"] + ".json")
        if receipt.exists():
            result = json.loads(receipt.read_text())
            assert result["asset"]["id"] == item["id"]
            results.append({"id": item["id"], "status": "PASS", "path": str(target), "receipt": str(receipt)})
            continue
        if available() < 4 * 1024**3:
            raise RuntimeError("Host headroom below4GiB before acquisition; Unreal preserved")
        group = pathlib.Path("/sys/fs/cgroup") / ("watoom-fab-" + str(os.getpid()) + "-" + str(index))
        group.mkdir()
        for n, v in [
            ("memory.high", str(1024**3)),
            ("memory.max", str(1536 * 1024**2)),
            ("memory.swap.max", "0"),
            ("cpu.max", "100000 100000"),
            ("pids.max", "64"),
        ]:
            (group / n).write_text(v)

        def own():
            (group / "cgroup.procs").write_text(str(os.getpid()))

        out = r / ("download-" + item["id"] + ".private.stdout")
        err = r / ("download-" + item["id"] + ".private.stderr")
        with out.open("wb") as stdout, err.open("wb") as stderr:
            os.chmod(out, 0o600)
            os.chmod(err, 0o600)
            child = subprocess.Popen(
                [
                    "nice",
                    "-n",
                    "15",
                    "ionice",
                    "-c",
                    "3",
                    "/data/ai/bin/epic-fab",
                    "download",
                    item["id"],
                    "--engine",
                    a.engine,
                    "--concurrency",
                    str(a.concurrency),
                    "--into",
                    str(target),
                ],
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
                preexec_fn=own,
            )
            begin = time.monotonic()
            while child.poll() is None:
                reason = None
                free = shutil.disk_usage(root).free
                if available() < 3 * 1024**3:
                    reason = "host_memory_reserve"
                elif free < 300 * 1024**3:
                    reason = "data_disk_floor"
                elif initial - free > 200 * 1024**3:
                    reason = "200GiB_transfer_budget"
                elif time.monotonic() - begin > a.asset_hours * 3600:
                    reason = "per_asset_time_budget"
                elif time.monotonic() - started > 24 * 3600:
                    reason = "24_hour_total_budget"
                save(
                    {
                        "status": "RUNNING",
                        "pid": os.getpid(),
                        "current": item["title"],
                        "asset_id": item["id"],
                        "target": str(target),
                        "completed": results,
                        "total": len(items),
                        "memory_current": int((group / "memory.current").read_text()),
                        "failures": failures,
                        "reason": reason,
                    }
                )
                if reason:
                    stop()
                    raise RuntimeError(reason)
                time.sleep(3)
        if child.returncode != 0:
            reason = "epic-fab download failed exit" + str(child.returncode) + "; private stderr retained for diagnosis"
            failures.append({"id": item["id"], "title": item["title"], "reason": reason, "stderr": str(err)})
            if not a.continue_on_error:
                raise RuntimeError(reason)
            assert not (group / "cgroup.procs").read_text().strip()
            group.rmdir()
            group = None
            child = None
            save(
                {
                    "status": "RUNNING",
                    "completed": results,
                    "failures": failures,
                    "total": len(items),
                    "reason": "Continuing independent owned assets after verified failure; no hash bypass",
                }
            )
            continue
        result = json.loads(out.read_text())
        assert result["asset"]["id"] == item["id"] and result["files"] and result["bytesTotal"] > 0
        receipt.write_text(json.dumps(result, indent=2))
        for directory, dirs, files in os.walk(target, followlinks=False):
            for p in [pathlib.Path(directory), *[pathlib.Path(directory) / f for f in files]]:
                assert not p.is_symlink() and p.resolve().is_relative_to(target.resolve())
                os.chown(p, 1009, 1009)
        results.append(
            {
                "id": item["id"],
                "status": "PASS",
                "path": str(target),
                "bytes": result["bytesTotal"],
                "files": len(result["files"]),
                "receipt": str(receipt),
            }
        )
        (r / ("cgroup-" + item["id"] + ".json")).write_text(
            json.dumps({n: (group / n).read_text() for n in ["memory.events", "memory.peak"]}, indent=2)
        )
        assert not (group / "cgroup.procs").read_text().strip()
        group.rmdir()
        group = None
        child = None
    save(
        {
            "status": "BLOCKED" if failures else "PASS",
            "failures": failures,
            "completed": results,
            "total": len(items),
            "checksums": "Existing epic-fab manifest SHA1 and length verification per downloaded file",
            "source_assets_preserved": True,
            "pipeline_integration": "PENDING_ENGINE_AND_PACK_ACCEPTANCE",
        }
    )
except BaseException as e:
    stop()
    save(
        {
            "status": "BLOCKED",
            "reason": str(e),
            "completed": results,
            "total": len(items),
            "partial_files_retained": True,
            "failures": failures,
            "unreal_untouched": True,
        }
    )
    raise
