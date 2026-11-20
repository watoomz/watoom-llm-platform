#!/usr/bin/env python3
"""Verify/apply the exact JSON SHA1 repair to the existing server downloader; no auth changes."""

import argparse, hashlib, json, pathlib, subprocess, os

p = argparse.ArgumentParser()
p.add_argument("--apply", action="store_true")
a = p.parse_args()
here = pathlib.Path(__file__).resolve().parent
info = json.loads((here / "epic-fab-source.json").read_text())
source = pathlib.Path(info["source"])
patch = here / info["patch"]
target = source / "src/manifestParser.ts"
assert hashlib.sha256(patch.read_bytes()).hexdigest() == info["patch_sha256"]
current = hashlib.sha256(target.read_bytes()).hexdigest()
if current != info["patched_file_sha256"]:
    assert current == info["original_file_sha256"], "Unknown local source; inspect rather than overwrite"
    if not a.apply:
        raise SystemExit("BLOCKED: exact known source needs --apply")
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
assert hashlib.sha256(target.read_bytes()).hexdigest() == info["patched_file_sha256"]
env = {**os.environ, "EPIC_FAB_SOURCE": str(source)}
subprocess.run(["/root/.bun/bin/bun", str(here / "test-manifest-hash.ts")], env=env, check=True, timeout=30)
print("PASS existing downloader exact repair; file checksum enforcement unchanged")
