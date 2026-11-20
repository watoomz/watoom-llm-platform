#!/usr/bin/env python3
"""Generate one isolated Breakpad/UE symbol artifact without modifying/rebuilding the engine."""

import argparse, copy, hashlib, json, os, pathlib, re, subprocess, time, tempfile


def semantic_symbol_digest(path):
    """UE encoder: packed uint32 count, then <uint64,uint32,uint32,uint32> records.
    Compare decoded address/line/file/function mappings, ignoring source-root prefixes.
    """
    import mmap, struct, posixpath

    h = hashlib.sha256()
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if len(data) < 4:
            raise ValueError("Invalid UE symbols")
        count = struct.unpack_from("<I", data)[0]
        strings = 4 + 20 * count
        if not count or strings > len(data):
            raise ValueError("Invalid record table")

        def string(offset):
            if offset == 0xFFFFFFFF:
                return b""
            start = strings + offset
            if start >= len(data):
                raise ValueError("Invalid string offset")
            end = data.find(bytes([10]), start)
            if end < 0:
                raise ValueError("Unterminated string")
            return data[start:end]

        last = -1
        group = []

        def flush():
            for value in sorted(group):
                h.update(struct.pack("<I", len(value)))
                h.update(value)

        for i in range(count):
            address, line, fileoff, nameoff = struct.unpack_from("<QIII", data, 4 + 20 * i)
            if address < last:
                raise ValueError("Unsorted symbol records")
            if address != last:
                flush()
                group = []
                last = address
            file = string(fileoff).replace(bytes([92]), b"/")
            if b"/Engine/" in file:
                file = b"Engine/" + file.split(b"/Engine/", 1)[1]
            file = posixpath.normpath(file) if file else b""
            name = string(nameoff)
            group.append(struct.pack("<QIII", address, line, len(file), len(name)) + file + name)
        flush()
    return h.hexdigest(), count


def backfill(root, receipt, out, stale_from=None):
    assert (
        receipt["matching_debug_sidecar"]
        and receipt["symbol_records"]["FILE"] > 0
        and receipt["symbol_records"]["FUNC"] > 0
    )

    def sha(path):
        with path.open("rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()

    binary = root / receipt["module"]
    target = binary.with_suffix(".sym")
    assert (
        target.parent.resolve().is_relative_to(root.resolve()) and not target.is_symlink()
    ), "Preserve original/symlinked symbols"
    mount = json.loads(subprocess.check_output(["findmnt", "-J", "-T", str(target.parent)]))
    published = root / "runtime-identity.json"
    if mount["filesystems"][0]["fstype"] != "overlay":
        assert (
            root.is_relative_to(pathlib.Path("/data/ai/toolchains/unreal")) and published.is_file()
        ), "Only a published runtime or accepted overlay may be backfilled"
        identity = json.loads(published.read_text())
        assert (
            sha(root / "Engine/Binaries/Linux/UnrealEditor") == identity["editor_sha256"]
        ), "Published runtime identity changed"
    assert sha(binary) == receipt["binary_sha256"] and sha(out / "module.sym") == receipt["encoded_sha256"]
    if target.exists() and sha(target) == receipt["encoded_sha256"]:
        return
    before = target.read_bytes()
    dummy = 0 < len(before) <= 100 and before.replace(b"DummySyms", b"").strip() == b""
    if not dummy:
        try:
            current_semantic = semantic_symbol_digest(target)
            generated_semantic = semantic_symbol_digest(out / "module.sym")
        except (ValueError, OSError):
            current_semantic = generated_semantic = None
        if current_semantic is not None and current_semantic == generated_semantic:
            (out / "placeholder-backfill.json").write_text(
                json.dumps(
                    {
                        "status": "PASS_EXISTING_SEMANTICALLY_VERIFIED",
                        "target": str(target),
                        "existing_real_symbols_preserved": True,
                        "semantic_sha256": current_semantic[0],
                        "records": current_semantic[1],
                        "source_root_prefixes_normalized": True,
                        "runtime_elf_unchanged": True,
                    },
                    indent=2,
                )
            )
            return
        assert stale_from is not None, "Existing real symbols must not be overwritten without stale provenance"
        old_binary = stale_from / receipt["module"]
        old_sym = old_binary.with_suffix(".sym")
        assert old_sym.is_file() and not old_sym.is_symlink(), "Preserved baseline symbols required"
        baseline_proven = sha(old_sym) == sha(target)
        if not baseline_proven and current_semantic is not None:
            try:
                baseline_proven = current_semantic == semantic_symbol_digest(old_sym)
            except (ValueError, OSError):
                pass
        assert baseline_proven, "Symbols differ semantically from the preserved baseline"

        def buildid(path):
            match = re.search(
                r"Build ID: ([a-fA-F0-9]+)", subprocess.check_output(["readelf", "-n", str(path)], text=True)
            )
            assert match
            return match[1].lower()

        assert buildid(old_binary) != buildid(binary), "Existing symbols belong to the same build; preserve them"
    original = pathlib.Path("/data/ai/assets/unreal-engine") / target.relative_to(root)
    old = sha(original) if original.is_file() else None
    (out / ("placeholder.before" if dummy else "stale-symbol.before")).write_bytes(before)
    fd, temp = tempfile.mkstemp(prefix=".verified-symbol-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchown(f.fileno(), 1009, 1009)
            os.fchmod(f.fileno(), 0o644)
            f.write((out / "module.sym").read_bytes())
            f.flush()
            os.fsync(f.fileno())
        assert target.read_bytes() == before, "Concurrent symbol change"
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    assert sha(target) == receipt["encoded_sha256"] and sha(binary) == receipt["binary_sha256"]
    assert (sha(original) if original.is_file() else None) == old
    (out / "placeholder-backfill.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "target": str(target),
                "original_installation_unchanged": True,
                "runtime_elf_unchanged": True,
                "prior_symbol_bytes": len(before),
                "replaced_stale_baseline": not dummy,
            },
            indent=2,
        )
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True, type=pathlib.Path)
    ap.add_argument("--module", default="Engine/Binaries/Linux/UnrealEditor")
    ap.add_argument("--memory-gib", type=int, choices=[1, 4, 6], default=1)
    ap.add_argument("--seconds", type=int, choices=[90, 300], default=90)
    ap.add_argument("--install-placeholder", "--install-verified", dest="install_placeholder", action="store_true")
    ap.add_argument(
        "--engine-root",
        type=pathlib.Path,
        default=pathlib.Path("/data/ai/builds/unreal-recovery-20261016T213935Z/source"),
    )
    ap.add_argument("--replace-stale-from", type=pathlib.Path)
    a = ap.parse_args()
    root = a.engine_root.resolve()
    assert root.is_relative_to(pathlib.Path("/data/ai"))
    relative = pathlib.PurePosixPath(a.module)
    assert not relative.is_absolute() and ".." not in relative.parts and relative.parts[0] == "Engine"
    binary = root / a.module
    assert binary.is_file() and binary.resolve().is_relative_to(root)
    debug = binary.with_suffix(".debug")
    source = debug if debug.is_file() else binary
    if source != binary:

        def buildid(path):
            value = subprocess.run(["readelf", "-n", str(path)], capture_output=True, text=True, check=True).stdout
            match = re.search(r"Build ID: ([a-fA-F0-9]+)", value)
            assert match, "Missing ELF build ID"
            return match[1].lower()

        assert buildid(binary) == buildid(debug), "Debug sidecar belongs to another binary"

    available = (
        int(
            next(
                x.split()[1]
                for x in pathlib.Path("/proc/meminfo").read_text().splitlines()
                if x.startswith("MemAvailable:")
            )
        )
        * 1024
    )
    assert available > (a.memory_gib + 2) * 1024**3, "Wait for actual host headroom; never evict user work"
    out = a.evidence.resolve()
    assert out.is_relative_to(pathlib.Path("/data/ai/helper-scripts/reports"))
    out.mkdir(mode=0o770, exist_ok=False)
    os.chown(out, 1009, 1009)
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "watoom-toolkit"))
    from kube_worker import job_spec

    image = "127.0.0.1:5000/watoom-toolkit@sha256:3b2368f5c45c8ebced2644ac6f316ef499512de912afa4c6be85a3e37212ef39"
    skeleton = job_spec(
        hashlib.sha256(str(out).encode()).hexdigest()[:16],
        ["true"],
        min(a.seconds, 180),
        str(out),
        image,
        task="symbol-extract",
    )
    spec = skeleton["spec"]["template"]["spec"]
    spec["securityContext"]["runAsUser"] = 1009
    spec["volumes"].append({"name": "engine", "hostPath": {"path": str(root), "type": "Directory"}})
    spec["containers"][0]["volumeMounts"].append({"name": "engine", "mountPath": "/unreal-engine", "readOnly": True})
    spec["activeDeadlineSeconds"] = a.seconds + 45
    c = spec["containers"][0]
    c["image"] = "127.0.0.1:5000/watoom-toolkit@sha256:3b2368f5c45c8ebced2644ac6f316ef499512de912afa4c6be85a3e37212ef39"
    c["resources"] = {
        "requests": {"cpu": "1", "memory": str(a.memory_gib) + "Gi"},
        "limits": {"cpu": "2", "memory": str(a.memory_gib) + "Gi"},
    }
    c["volumeMounts"] = [x for x in c["volumeMounts"] if x["name"] in ("engine", "tmp", "job")]
    spec["volumes"] = [x for x in spec["volumes"] if x["name"] in ("engine", "tmp", "job")]
    next(x for x in spec["volumes"] if x["name"] == "job")["hostPath"]["path"] = str(out)
    code = """import pathlib,subprocess,hashlib,json,sys,resource
binary=pathlib.Path("/unreal-engine")/sys.argv[1];source=pathlib.Path("/unreal-engine")/sys.argv[3];out=pathlib.Path("/job")
def sha(p):
 with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
before=sha(binary);tools=pathlib.Path("/unreal-engine/Engine/Binaries/Linux")
with (out/"dump.private.log").open("w") as log:
 p=subprocess.run([str(tools/"dump_syms"),"-n",binary.name,str(source),str(out/"module.psym")],stdout=log,stderr=subprocess.STDOUT,timeout=int(sys.argv[2]))
assert p.returncode==0,"dump_syms failed; inspect retained private log"
raw=out/"module.psym"
with raw.open() as f:header=f.readline().strip()
assert header.startswith("MODULE Linux ") and binary.name in header,"Symbol identity header invalid"
with raw.open() as f:
 counts={"FILE":0,"FUNC":0,"PUBLIC":0}
 for line in f:
  tag=line.split(" ",1)[0]
  if tag in counts:counts[tag]+=1
if source!=binary:assert counts["FILE"]>0 and counts["FUNC"]>0,"Debug sidecar produced no line/function symbols"
subprocess.run([str(tools/"BreakpadSymbolEncoder"),str(raw),str(out/"module.sym")],check=True,timeout=20,stdout=subprocess.DEVNULL)
assert (out/"module.sym").stat().st_size>0 and before==sha(binary)
(out/"symbol-acceptance.json").write_text(json.dumps({"status":"PASS","module":sys.argv[1],"binary_sha256":before,"breakpad_header":header,"raw_bytes":raw.stat().st_size,"ue_encoded_bytes":(out/"module.sym").stat().st_size,"raw_sha256":sha(raw),"encoded_sha256":sha(out/"module.sym"),"source_unchanged":True,"debug_input":sys.argv[3],"symbol_records":counts,"matching_debug_sidecar":source!=binary,"maximum_child_rss_kib":resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,"scope":"One module only; separate private symbol store, no engine rebuild or symbol-file replacement"},indent=2))
"""
    c["command"] = ["python3", "-c", code, a.module, str(a.seconds), str(source.relative_to(root))]
    name = "watoom-symbol-" + hashlib.sha256(str(out).encode()).hexdigest()[:16]
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": "watoom-code", "labels": {"watoom-test-owner": out.name}},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 3600,
            "activeDeadlineSeconds": a.seconds + 45,
            "template": {"metadata": {"labels": {"watoom-test-owner": out.name}}, "spec": spec},
        },
    }
    manifest = out / "job.json"
    manifest.write_text(json.dumps(job, indent=2))
    os.chown(manifest, 1009, 1009)
    subprocess.run(["kubectl", "-n", "watoom-code", "create", "-f", str(manifest)], capture_output=True, check=True)
    begin = time.monotonic()
    while time.monotonic() - begin < a.seconds + 90:
        value = json.loads(subprocess.check_output(["kubectl", "-n", "watoom-code", "get", "job", name, "-o", "json"]))
        if value.get("status", {}).get("succeeded") or value.get("status", {}).get("failed"):
            break
        time.sleep(3)
    logs = subprocess.run(["kubectl", "-n", "watoom-code", "logs", "job/" + name], capture_output=True, text=True)
    (out / "worker.private.log").write_text(logs.stdout + logs.stderr)
    if not (out / "symbol-acceptance.json").exists():
        raise RuntimeError(
            "Bounded isolated symbol generation failed; original engine unchanged, inspect owned job/evidence"
        )
    result = json.loads((out / "symbol-acceptance.json").read_text())
    assert result["status"] == "PASS"
    if a.install_placeholder:
        backfill(root, result, out, a.replace_stale_from.resolve() if a.replace_stale_from else None)
    print("PASS isolated Breakpad extraction and UE encoding; original module unchanged")


if __name__ == "__main__":
    main()
