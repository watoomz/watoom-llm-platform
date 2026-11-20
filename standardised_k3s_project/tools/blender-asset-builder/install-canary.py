#!/usr/bin/env python3
"""Reproduce the additive canary project from authoritative source and pinned vendor."""

import argparse, pathlib, json, shutil, hashlib, sys, datetime

p = argparse.ArgumentParser()
p.add_argument("--target", required=True)
p.add_argument("--vendor", default="/data/ai/helper-scripts/watoom-blender-package/upstream/EL4CTEO__blender-skills")
p.add_argument("--dry-run", action="store_true")
a = p.parse_args()
source = pathlib.Path(__file__).resolve().parent
r = pathlib.Path(a.target).resolve()
v = pathlib.Path(a.vendor).resolve()
if not r.is_relative_to(pathlib.Path("/data/ai/assets/generated/blender-asset-builder")):
    p.error("target must be a new version under /data/ai/assets/generated/blender-asset-builder")
if r.exists():
    p.error("target exists; preserving it; use a new version")
if not (v / "skills/blender-asset-qa/scripts/qa_check.py").is_file():
    p.error("pinned upstream is missing")
manifest = json.loads((source / "upstream-manifest.json").read_text())
pin = next(x for x in manifest if x["repo"] == "EL4CTEO__blender-skills")
for name, sha in pin["files"].items():
    f = v / name
    if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != sha:
        p.error("vendor integrity mismatch: " + name)
if a.dry_run:
    print(
        json.dumps(
            {
                "target": str(r),
                "vendor_commit": pin["commit"],
                "action": "new project-local canary, CPU only",
                "production_changes": False,
            }
        )
    )
    sys.exit(0)
try:
    for d in ["scripts", "references", "source", "textures", "renders", "game-ready", "reports", "engine-validation"]:
        (r / d).mkdir(parents=True, exist_ok=False)
    for n in ["pipeline.py", "validate.py", "contact.py", "import.gd", "magpie.py", "memory.py", "canary-smoke.py"]:
        shutil.copy2(source / n, r / "scripts" / n)
    shutil.copytree(v, r / "upstream/EL4CTEO", ignore=shutil.ignore_patterns(".git", "__pycache__"))
    shutil.copytree(source / "skill", r / ".opencode/skills/watoom-blender-asset-builder")
    (r / "opencode.json").write_text(json.dumps({"skills": ["./.opencode/skills"]}, indent=2))
    (r / "references/sources.json").write_text(
        json.dumps(
            {
                "source": "local procedural anatomy recipe",
                "photographic_reference": "NOT TESTED",
                "input_review_required": True,
            }
        )
    )
    shutil.copy2(source / "upstream-manifest.json", r / "upstream-manifest.json")
    print(
        json.dumps(
            {
                "status": "PASS",
                "project": str(r),
                "next": "adjust ownership to the verified canary UID/GID for this new directory only, then execute scripts/pipeline.py --root <container path> --build",
            }
        )
    )
except Exception:
    # Rollback preserves partial output for diagnosis instead of deleting it.
    if r.exists():
        r.rename(
            r.with_name(r.name + "-failed-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        )
    raise
