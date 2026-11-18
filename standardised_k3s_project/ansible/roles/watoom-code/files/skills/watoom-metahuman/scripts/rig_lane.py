#!/usr/bin/env python3
"""Homelab side of the rig's Unreal lane (operator, root). Talks only to the transfer jail's directories; never to the rig.
  submit probe                    queue the read-only Unreal API probe
  submit-skin PACK CHARACTER [--bake-makeup]   queue the GPU MetaHuman skin/DCC export (PACK must have been unpacked by metahuman_pipeline.py)
  list                            jobs in the jail and their state
  status JOB                      queued | running-or-waiting | complete (PASS/FAIL)
  collect JOB [--out DIR]         verify and copy a finished job's artifacts (default /data/ai/artifacts/rig-lane/JOB)
  cancel JOB                      remove a job that the rig has not started
Results are untrusted data written by the rig: names, sizes and SHA-256 are verified before anything is copied."""
import argparse, json, os, pathlib, secrets, shutil, sys, time

# The lane contract lives in the canonical checkout (a deployed skill has no repo next to it); the repo-relative path is the fallback for tests.
_REL = 'tools/rig-async-stage/unreal-lane/worker-source'
for _c in (os.environ.get('RIG_LANE_SOURCE'), '/data/github/watoom-standardised-homelab/standardised_k3s_project/' + _REL,
           str(pathlib.Path(__file__).resolve().parents[7] / _REL) if len(pathlib.Path(__file__).resolve().parents) > 7 else None):
    if _c and (pathlib.Path(_c) / 'unreal_lane.py').is_file():
        sys.path.insert(0, _c)
        break
import unreal_lane as lane

TRANSFER = pathlib.Path(os.environ.get('RIG_LANE_TRANSFER', '/data/ai/helper-scripts/workstation-transfer'))
OUT_ROOT = pathlib.Path(os.environ.get('RIG_LANE_OUT', '/data/ai/artifacts/rig-lane'))


def new_job_id(prefix):
    return '%s-%s-%s' % (prefix, time.strftime('%Y%m%d%H%M%S'), secrets.token_hex(2))


def submit(op, params=None, package=None, transfer=TRANSFER):
    job = new_job_id(op)
    pkg = None
    if lane.OPS[op]['package']:
        raise SystemExit('this operation needs a package; use its dedicated command')
    manifest = lane.validate_manifest({'schema': 1, 'job': job, 'op': op, 'created': time.time(), 'package': pkg, 'params': params or {}}, expected_job=job)
    inputs = pathlib.Path(transfer) / 'inputs'
    target = inputs / lane.manifest_name(job)
    tmp = inputs / ('.' + lane.manifest_name(job) + '.tmp')
    tmp.write_text(json.dumps(manifest, indent=2))
    os.chmod(tmp, 0o644)
    os.replace(tmp, target)       # atomic: the rig never sees a partial manifest
    return job


def submit_skin(pack, character, bake_makeup=False, transfer=TRANSFER):
    """Zips the character's verified Content files (exactly the ones metahuman_pipeline.py unpacked) and queues a metahuman-skin job."""
    import zipfile
    pack = pathlib.Path(pack)
    state = json.loads((pack / 'metahuman-install.json').read_text())
    row = next((c for c in state['characters'] if c.get('object_path') and ('/' + character + '/') in c['object_path']), None)
    if row is None:
        raise SystemExit('no character %s in %s' % (character, pack.name))
    items = [i for i in state['installed'] if i['character'] == row['name']]
    if not items:
        raise SystemExit('nothing installed for ' + str(row['name']))
    job = new_job_id('skin')
    inputs = pathlib.Path(transfer) / 'inputs'
    zip_tmp = inputs / ('.' + lane.package_name(job) + '.tmp')
    with zipfile.ZipFile(zip_tmp, 'w', zipfile.ZIP_STORED) as z:
        for item in items:
            f = pack / item['file']
            if f.is_symlink() or not f.is_file() or lane.sha256_file(f) != item['sha256']:
                zip_tmp.unlink()
                raise SystemExit('pack file changed since unpack: ' + item['file'])
            z.write(f, pathlib.PurePosixPath(item['file']).relative_to('Content').as_posix())
    os.chmod(zip_tmp, 0o644)
    package = {'sha256': lane.sha256_file(zip_tmp), 'bytes': zip_tmp.stat().st_size}
    params = {'asset': row['object_path'].rsplit('.', 1)[0], 'name': row['name'], 'bake_makeup': bool(bake_makeup)}
    manifest = lane.validate_manifest({'schema': 1, 'job': job, 'op': 'metahuman-skin', 'created': time.time(), 'package': package, 'params': params}, expected_job=job)
    os.replace(zip_tmp, inputs / lane.package_name(job))      # the package first, then the manifest that announces it
    tmp = inputs / ('.' + lane.manifest_name(job) + '.tmp')
    tmp.write_text(json.dumps(manifest, indent=2))
    os.chmod(tmp, 0o644)
    os.replace(tmp, inputs / lane.manifest_name(job))
    return job


def result_path(job, transfer=TRANSFER):
    return pathlib.Path(transfer) / 'uploads' / lane.upload_dir(job) / 'result.json'


def status(job, transfer=TRANSFER):
    inputs = pathlib.Path(transfer) / 'inputs'
    if not (inputs / lane.manifest_name(job)).is_file():
        return 'unknown'
    r = result_path(job, transfer)
    if not r.is_file():
        return 'queued-or-running'
    try:
        return 'complete-' + json.loads(r.read_text())['status']
    except (ValueError, KeyError, OSError):
        return 'result-unreadable'


def collect(job, out=None, transfer=TRANSFER):
    inputs = pathlib.Path(transfer) / 'inputs'
    manifest = lane.validate_manifest(json.loads((inputs / lane.manifest_name(job)).read_text()), expected_job=job)
    src = result_path(job, transfer).parent
    result = lane.validate_result(json.loads((src / 'result.json').read_text()), manifest)
    dest = pathlib.Path(out) if out else OUT_ROOT / job
    if dest.exists():
        raise SystemExit('%s exists; choose a new --out' % dest)
    dest.mkdir(parents=True)
    for name, info in result['files'].items():
        f = src / name
        if f.is_symlink() or not f.is_file() or f.stat().st_size != info['bytes'] or lane.sha256_file(f) != info['sha256']:
            shutil.rmtree(dest)
            raise SystemExit('artifact failed verification: ' + name)
        shutil.copy2(f, dest / name)
    (dest / 'result.json').write_text(json.dumps(result, indent=2))
    return {'job': job, 'status': result['status'], 'dir': str(dest), 'files': sorted(result['files'])}


def cancel(job, transfer=TRANSFER):
    if result_path(job, transfer).exists():
        raise SystemExit('the rig already produced a result; nothing to cancel')
    (pathlib.Path(transfer) / 'inputs' / lane.manifest_name(job)).unlink()
    (pathlib.Path(transfer) / 'inputs' / lane.package_name(job)).unlink(missing_ok=True)
    return {'job': job, 'cancelled': True, 'note': 'if the rig already fetched it, it still runs and the result is ignored'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('submit').add_argument('op', choices=sorted(o for o, v in lane.OPS.items() if not v['package']))
    sk = sub.add_parser('submit-skin')
    sk.add_argument('pack'); sk.add_argument('character'); sk.add_argument('--bake-makeup', action='store_true')
    sub.add_parser('list')
    for c in ('status', 'collect', 'cancel'):
        s = sub.add_parser(c)
        s.add_argument('job')
        if c == 'collect':
            s.add_argument('--out')
    a = ap.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root')
    if a.cmd == 'submit':
        out = {'job': submit(a.op)}
    elif a.cmd == 'submit-skin':
        out = {'job': submit_skin(a.pack, a.character, a.bake_makeup)}
    elif a.cmd == 'list':
        inputs = TRANSFER / 'inputs'
        jobs = sorted(f.name[len(lane.PREFIX):-5] for f in inputs.glob(lane.PREFIX + '*.json'))
        out = {j: status(j) for j in jobs}
    elif a.cmd == 'status':
        out = {'job': a.job, 'status': status(a.job)}
    elif a.cmd == 'collect':
        out = collect(a.job, a.out)
    else:
        out = cancel(a.job)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
