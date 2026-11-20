#!/usr/bin/env python3
"""Stage a terrain-export job's .opencode/tmp/<dir> + .opencode/terrain-jobs/<job>/request.json pairing that
game_terrain_export.py (the operator) and terrain_spec.py (the declarative contract it validates against)
require. Runs in your own session, not the worker; nothing here touches Unreal or Bazzite.

Before this skill existed there was no model-facing way to produce that pairing: both files have exact
path/filename rules (terrain_spec.py's _relative/_filename checks) and the .uproject must carry the right
plugins (PythonScriptPlugin + GLTFExporter, same convention as the Fab export pipeline's export_pack.py) or
the worker's headless UnrealEditor cannot even load the project or run your script.

  terrain_stage.py init  --project P --job J [--script-name NAME.py] [--plugins NAME,NAME] [--deadline-sec N] [--memory-gib N]
      Creates .opencode/tmp/<job>/ with a minimal Terrain.uproject and a starter script.py (the output
      contract the operator checks: write /job/output/manifest.json with status SUCCESS|PARTIAL and
      output.produced, see references/terrain-output-contract.md), and .opencode/terrain-jobs/<job>/request.json
      pointing at it. Refuses if either already exists -- use `adopt` to iterate on a prior job instead of
      hand-editing paths.

  terrain_stage.py adopt --project P --from-job OLD --new-job NEW [--deadline-sec N] [--memory-gib N]
      Copies OLD's staged .uproject + script (not its output/Saved/Intermediate/DerivedDataCache) into a
      fresh .opencode/tmp/<new-job>/ and writes NEW's request.json pointing at it, inheriting OLD's
      deadline_sec/memory_gib unless overridden. terrain_spec.py refuses to rerun a used job name, so this
      is how you iterate on the same landscape setup: tweak the copied script, submit under a new job name.

Exit codes: 0 ok | 2 refused (bad input or an existing file/dir in the way).
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import sys

PROJECTS_ROOT = pathlib.Path('/data/ai/projects/games')
JOB_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
DEFAULT_PLUGINS = ('PythonScriptPlugin', 'GLTFExporter')
EXCLUDE_DIRS = {'Saved', 'Intermediate', 'DerivedDataCache', 'output', '.git'}  # same set game_terrain_export.py excludes
SCRIPT_TEMPLATE = '''"""Terrain export for job %s: runs unattended inside UnrealEditor on the worker (-ExecutePythonScript).
Load the target map, locate the Landscape actor, export it, and write the output contract below -- the
operator (game_terrain_export.py) only trusts /job/output/manifest.json, nothing printed to stdout.

TODO fill in your actual landscape lookup/export for this job (see unreal.EditorLevelLibrary / AssetExportTask;
check references/terrain-output-contract.md in this skill for the manifest shape and a worked example).
"""
import json
import pathlib
import unreal

OUT = pathlib.Path('/job/output')
OUT.mkdir(parents=True, exist_ok=True)
manifest = {"status": "FAIL", "output": {"produced": False}}
try:
    # TODO: load your level, find the Landscape actor, export it under OUT.
    raise NotImplementedError("fill in the export for job %s before running this")
except Exception as e:
    manifest["failure_reason"] = str(e)[:500]
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
'''


def job_name(s, field):
    if not isinstance(s, str) or not JOB_RE.fullmatch(s):
        raise SystemExit('refused: %s %r must match %s' % (field, s, JOB_RE.pattern))
    return s


def safe_project(p):
    project = pathlib.Path(p).resolve(strict=True)
    if project.parent != PROJECTS_ROOT or pathlib.Path(p).is_symlink():
        raise SystemExit('refused: %s is not an approved project directory' % p)
    return project


def write_request(project, job, uproject_dir, uproject_file, script_name, deadline_sec, memory_gib):
    if not 60 <= deadline_sec <= 1800:
        raise SystemExit('refused: deadline_sec must be 60-1800, got %s' % deadline_sec)
    if not 4 <= memory_gib <= 16:
        raise SystemExit('refused: memory_gib must be 4-16, got %s' % memory_gib)
    jobs_dir = project / '.opencode/terrain-jobs' / job
    if jobs_dir.exists():
        raise SystemExit('refused: terrain job %s already has a request; use adopt with a new job name' % job)
    jobs_dir.mkdir(parents=True)
    body = {'schema': 1, 'uproject_dir': uproject_dir, 'uproject_file': uproject_file, 'script': script_name,
            'deadline_sec': deadline_sec, 'memory_gib': memory_gib}
    (jobs_dir / 'request.json').write_text(json.dumps(body, indent=2))
    print('terrain_stage.py: wrote %s' % (jobs_dir / 'request.json'))


def do_init(a):
    project = safe_project(a.project)
    job = job_name(a.job, '--job')
    script_name = a.script_name
    if '/' in script_name or not script_name.endswith('.py'):
        raise SystemExit('refused: --script-name must be a bare *.py filename')
    staging = project / '.opencode/tmp' / job
    if staging.exists():
        raise SystemExit('refused: %s already exists; use adopt to start from an existing job, or pick a new --job' % staging)
    staging.mkdir(parents=True)
    plugins = [x for x in (a.plugins.split(',') if a.plugins else DEFAULT_PLUGINS) if x]
    (staging / 'Terrain.uproject').write_text(json.dumps(
        {'FileVersion': 3, 'EngineAssociation': '', 'Plugins': [{'Name': n, 'Enabled': True} for n in plugins]}, indent=2))
    (staging / script_name).write_text(SCRIPT_TEMPLATE % (job, job))
    write_request(project, job, '.opencode/tmp/' + job, 'Terrain.uproject', script_name, a.deadline_sec, a.memory_gib)
    print('terrain_stage.py init: staged %s (edit %s before submitting the job)' % (staging, staging / script_name))
    return 0


def do_adopt(a):
    project = safe_project(a.project)
    old_job, new_job = job_name(a.from_job, '--from-job'), job_name(a.new_job, '--new-job')
    old_request_path = project / '.opencode/terrain-jobs' / old_job / 'request.json'
    if not old_request_path.is_file():
        raise SystemExit('refused: no request.json for --from-job %s' % old_job)
    old = json.loads(old_request_path.read_text())
    old_dir = project / old['uproject_dir']
    if old_dir.is_symlink() or not old_dir.is_dir():
        raise SystemExit('refused: %s (from-job %s) is missing or unsafe' % (old_dir, old_job))
    new_dir = project / '.opencode/tmp' / new_job
    if new_dir.exists():
        raise SystemExit('refused: %s already exists' % new_dir)
    new_dir.mkdir(parents=True)
    for entry in sorted(old_dir.iterdir()):
        if entry.name in EXCLUDE_DIRS or entry.is_symlink():
            continue
        if entry.is_dir():
            shutil.copytree(entry, new_dir / entry.name, symlinks=False)
        elif entry.is_file():
            shutil.copyfile(entry, new_dir / entry.name)
    write_request(project, new_job, '.opencode/tmp/' + new_job, old['uproject_file'], old['script'],
                   a.deadline_sec if a.deadline_sec is not None else old.get('deadline_sec', 900),
                   a.memory_gib if a.memory_gib is not None else old.get('memory_gib', 8))
    print('terrain_stage.py adopt: %s -> %s (edit %s before submitting)' % (old_dir, new_dir, new_dir / old['script']))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init')
    p.add_argument('--project', required=True); p.add_argument('--job', required=True)
    p.add_argument('--script-name', default='export.py'); p.add_argument('--plugins', default=None)
    p.add_argument('--deadline-sec', type=int, default=900); p.add_argument('--memory-gib', type=int, default=8)
    p = sub.add_parser('adopt')
    p.add_argument('--project', required=True); p.add_argument('--from-job', required=True); p.add_argument('--new-job', required=True)
    p.add_argument('--deadline-sec', type=int, default=None); p.add_argument('--memory-gib', type=int, default=None)
    a = ap.parse_args(argv)
    try:
        return {'init': do_init, 'adopt': do_adopt}[a.cmd](a)
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 2
        raise


if __name__ == '__main__':
    sys.exit(main())
