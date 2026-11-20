#!/usr/bin/env python3
"""Prepare an isolated CoW engine view; never write the original lower tree."""

import argparse, pathlib, json, subprocess, os, tarfile, hashlib, fcntl

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
a = ap.parse_args()
r = a.evidence
plan = json.loads((r / "build-plan.json").read_text())
build = pathlib.Path(plan["isolated_root"]).resolve()
original = pathlib.Path(plan["source"]).resolve()
assert build.is_relative_to(pathlib.Path("/data/ai/builds")) and original == pathlib.Path(
    "/data/ai/assets/unreal-engine"
)
lock = (build / "build.lock").open("w")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def run(args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT, timeout=60)


def mounted(path):
    return any(line.split()[4] == str(path) for line in pathlib.Path("/proc/self/mountinfo").read_text().splitlines())


# Never alter an upper layer while its merged mount may cache old dentries.
if mounted(build / "source"):
    current = json.loads(run(["findmnt", "--json", "-T", str(build / "source"), "-o", "TARGET,FSTYPE,OPTIONS"]))[
        "filesystems"
    ][0]
    assert (
        current["target"] == str(build / "source")
        and current["fstype"] == "overlay"
        and "upperdir=" + str(build / "upper") in current["options"]
    )
    run(["umount", str(build / "source")])
# All original workspace changes are independently restorable, byte for byte.
for name in ["dirty-tracked-raw.private.tar.gz", "untracked-before.private.tar.gz"]:
    with tarfile.open(r / name) as archive:
        for member in archive.getmembers():
            if member.isfile():
                assert archive.extractfile(member).read() == (original / member.name).read_bytes()
for rel, digest in json.loads((r / "source-sentinels.json").read_text()).items():
    assert hashlib.sha256((original / rel).read_bytes()).hexdigest() == digest
for name in [
    "lower",
    "upper",
    "overlay-work",
    "source",
    "cow-proof-lower",
    "cow-proof-upper",
    "cow-proof-work",
    "cow-proof-view",
]:
    p = build / name
    p.mkdir(mode=0o750, exist_ok=True)
    if not mounted(p):
        os.chown(p, 1009, 1009)
# Independent kernel CoW test: writes and metadata changes through the merged view
# must leave the lower bytes and ownership unchanged.
proof = build / "cow-proof-lower/protected"
proof.write_text("original-protected")
args = [
    "mount",
    "-t",
    "overlay",
    "overlay",
    "-o",
    "lowerdir="
    + str(build / "cow-proof-lower")
    + ",upperdir="
    + str(build / "cow-proof-upper")
    + ",workdir="
    + str(build / "cow-proof-work"),
    str(build / "cow-proof-view"),
]
run(args)
try:
    target = build / "cow-proof-view/protected"
    target.write_text("isolated-change")
    os.chown(target, 1009, 1009)
    assert proof.read_text() == "original-protected" and proof.stat().st_uid == 0
finally:
    run(["umount", str(build / "cow-proof-view")])
if not mounted(build / "lower"):
    run(["mount", "--bind", str(original), str(build / "lower")])
    run(["mount", "-o", "remount,bind,ro", str(build / "lower")])
lower = json.loads(run(["findmnt", "--json", "-T", str(build / "lower"), "-o", "TARGET,OPTIONS"]))["filesystems"][0]
assert lower["target"] == str(build / "lower") and "ro" in lower["options"].split(",")
# Hide inherited generated caches with opaque upper directories. All future
# intermediates then have paths in this isolated engine view, not the original.
hidden = []
for directory, dirs, _ in os.walk(original, followlinks=False):
    for name in list(dirs):
        if name == "Source":
            dirs.remove(name)
            continue
        rel = (pathlib.Path(directory) / name).relative_to(original)
        if name not in ["Intermediate", "Saved"]:
            if rel.parts not in [("DerivedDataCache",), ("Engine", "DerivedDataCache")]:
                continue
        upper = build / "upper" / rel
        upper.mkdir(parents=True, exist_ok=True)
        os.chown(upper, 1009, 1009)
        os.setxattr(upper, "trusted.overlay.opaque", b"y")
        hidden.append(str(rel))
        dirs.remove(name)
    if ".git" in dirs:
        dirs.remove(".git")
# Upper-only ancestors must retain the original directory ownership/mode.
for directory, dirs, _ in os.walk(build / "upper"):
    p = pathlib.Path(directory)
    rel = p.relative_to(build / "upper")
    lower_path = original / rel
    if lower_path.is_dir():
        stat = lower_path.stat()
        os.chown(p, stat.st_uid, stat.st_gid)
        os.chmod(p, stat.st_mode & 0o7777)
if not mounted(build / "source"):
    run(
        [
            "mount",
            "-t",
            "overlay",
            "overlay",
            "-o",
            "lowerdir="
            + str(build / "lower")
            + ",upperdir="
            + str(build / "upper")
            + ",workdir="
            + str(build / "overlay-work"),
            str(build / "source"),
        ]
    )
source = build / "source"
# Prevent absolute symlinks from bypassing the read-only lower/CoW view.
links = []
for directory, dirs, files in os.walk(source, followlinks=False):
    if ".git" in dirs:
        dirs.remove(".git")
    for name in dirs + files:
        p = pathlib.Path(directory) / name
        if not p.is_symlink():
            continue
        target = os.readlink(p)
        if target == str(original) or target.startswith(str(original) + "/"):
            replacement = str(source) + target[len(str(original)) :]
            p.unlink()
            p.symlink_to(replacement)
            links.append({"path": str(p), "before": target, "after": replacement})
for rel, digest in json.loads((r / "source-sentinels.json").read_text()).items():
    assert hashlib.sha256((source / rel).read_bytes()).hexdigest() == digest
assert os.getxattr(build / "upper/Engine/Intermediate", "trusted.overlay.opaque") == b"y"
receipt = {
    "status": "PASS",
    "isolation": "kernel overlay with read-only lower bind",
    "cow_write_proof": "PASS",
    "original": str(original),
    "source": str(source),
    "upper": str(build / "upper"),
    "hidden_generated_directories": hidden,
    "redirected_absolute_links": links,
    "backup_raw_changes": "PASS",
}
(r / "isolated-copy-result.json").write_text(json.dumps(receipt, indent=2))
print(
    json.dumps(
        {
            "status": "PASS",
            "isolation": receipt["isolation"],
            "hidden_generated_directories": len(hidden),
            "redirected_links": len(links),
        }
    )
)
