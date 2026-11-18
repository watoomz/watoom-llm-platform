#!/usr/bin/env python3
"""Build the self-contained bundle to copy to the rig: python3 build_lane.py <output dir>
Gathers the lane's sources, the in-engine scripts (single source of truth: the watoom-metahuman skill) and the two helpers it reuses from the
existing RIG worker, and writes unreal-lane-provenance.json (SHA-256 of every file). The worker refuses to start if any file differs."""
import hashlib, json, pathlib, shutil, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCES = [
    (HERE / 'worker-source', ['unreal_lane.py', 'unreal_worker.py', 'unreal_runner.py', 'unreal_job.py', 'pin_unreal.py']),
    (HERE.parent / 'worker-source', ['windows_job.py', 'pause_control.py']),
    (REPO / 'ansible/roles/watoom-code/files/skills/watoom-metahuman/scripts', ['ue_probe_api.py']),
    (REPO / 'ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts/unreal-export', ['ue_metahuman.py']),
]


def build(out):
    out = pathlib.Path(out)
    if out.exists():
        raise SystemExit('%s exists; choose a new directory' % out)
    out.mkdir(parents=True)
    files = {}
    for src, names in SOURCES:
        for n in names:
            shutil.copy2(src / n, out / n)
            files[n] = hashlib.sha256((out / n).read_bytes()).hexdigest()
    (out / 'unreal-lane-provenance.json').write_text(json.dumps({'schema': 1, 'files': dict(sorted(files.items()))}, indent=2))
    shutil.copy2(HERE / 'Install-UnrealWorker.ps1', out / 'Install-UnrealWorker.ps1')
    return files


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    for name, digest in build(sys.argv[1]).items():
        print(digest[:16], name)
