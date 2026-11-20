#!/usr/bin/env python3
"""Keep helper files that are shipped in several places identical to one source (T-0115).

Source of truth: ansible/roles/watoom-code/files/skill-shared/<group>/<relpath>
A skill receives a group's file when it already carries that relpath (skills opt in by having the file).

Usage:
    sync-skill-shared.py           rewrite every skill copy from the shared source
    sync-skill-shared.py --check   exit 1 and list copies that differ (CI / make check)
"""
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "ansible/roles/watoom-code/files"
SHARED, SKILLS = ROOT / "skill-shared", ROOT / "skills"
# Tool modules bundled twice: (canonical source, bundled copy). The rig worker bundle carries copies because it is
# shipped as a self-contained, hash-pinned tree; after a sync, refresh tools/rig-async-stage/source-manifest.json.
MIRRORS = [
    ("tools/watoom-code/asset_capture_blender.py", "tools/rig-async-stage/worker-source/shared_capture.py"),
    ("tools/ts4-animation/verify_retarget_constraints_blender.py",
     "tools/rig-async-stage/worker-source/runtime_helpers/tools/ts4-animation/verify_retarget_constraints_blender.py"),
]


def main() -> int:
    check = "--check" in sys.argv[1:]
    drift, synced = [], 0
    for source in sorted(p for p in SHARED.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        rel = source.relative_to(SHARED).parts[1:]  # drop the group name
        if len(rel) < 2:  # group-level files (README.md) document the group; they are not shipped
            continue
        data = source.read_bytes()
        for copy in sorted(SKILLS.glob("*/" + "/".join(rel))):
            if copy.read_bytes() != data:
                drift.append(copy.relative_to(ROOT))
                if not check:
                    copy.write_bytes(data)
            synced += 1
    for source, copy in MIRRORS:
        data, target = (PROJECT / source).read_bytes(), PROJECT / copy
        if target.read_bytes() != data:
            drift.append(Path(copy))
            if not check:
                target.write_bytes(data)
        synced += 1
    if check:
        for path in drift:
            print(f"DRIFT: {path}")
        print(f"{'FAIL' if drift else 'OK'}: {synced} shared skill copies checked")
        return 1 if drift else 0
    print(f"synced {len(drift)} of {synced} shared skill copies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
