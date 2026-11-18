#!/usr/bin/env python3
"""Operator-side Unreal pack export for a native game-worker request; the root dispatcher is the only caller.

Reads the declarative request (unreal_export_spec), runs the maintained export_pack.py (Bazzite first, local k8s Job
fallback, never replayed), then copies the portable files into the project's .opencode/unreal-exports/<job>/ so the
agent can use them without access to the artifact store. Writes <evidence>/result.json; exit 0 on PASS or PARTIAL.
"""
import argparse, json, os, pathlib, shutil, subprocess, sys
import unreal_export_spec

HERE = pathlib.Path(__file__).resolve().parent
EXPORT = HERE.parent.parent / 'ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts/unreal-export/export_pack.py'
OUTS = pathlib.Path('/data/ai/artifacts/unreal-export')
DEADLINE = 720  # past exports took 1-6 min; export_pack waits deadline+180 s, inside the dispatcher's 20 min unit limit
MAX_COPY = 4 * 1024**3


def atomic(path, value):
    tmp = path.with_suffix('.tmp');tmp.write_text(json.dumps(value, indent=2));os.chmod(tmp, 0o644);os.replace(tmp, path)


def copy_tree(source, target, owner):
    """Regular files only (no links), into a new folder owned like the project's .opencode."""
    files = [x for x in sorted(source.rglob('*')) if x.is_file() and not x.is_symlink()]
    if sum(x.stat().st_size for x in files) > MAX_COPY: raise ValueError('export is larger than 4 GiB; use the artifact folder')
    target.mkdir(parents=True, mode=0o2770)
    for d in [target, target.parent]: os.chown(d, *owner)
    for x in files:
        dest = target / x.relative_to(source)
        for d in reversed(dest.parents):
            if d.is_relative_to(target) and not d.exists(): d.mkdir(mode=0o2770);os.chown(d, *owner)
        shutil.copyfile(x, dest);os.chmod(dest, 0o660);os.chown(dest, *owner)
    return files


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', type=pathlib.Path, required=True);p.add_argument('--evidence', type=pathlib.Path, required=True)
    p.add_argument('--i-approve', action='store_true');p.add_argument('--export-job', required=True)
    a = p.parse_args()
    if os.geteuid() != 0: raise PermissionError('Operator only')
    project = a.project.resolve(strict=True)
    if not a.i_approve or a.project.is_symlink() or project.parent != pathlib.Path('/data/ai/projects/games'): raise ValueError('Approved existing game project required')
    a.evidence.mkdir(parents=True, exist_ok=False);os.chmod(a.evidence, 0o750)
    receipt = {'status': 'FAIL', 'scope': 'Portable export of purchased Unreal pack content; visual and gameplay acceptance stay separate.', 'job': a.export_job}
    try:
        spec = unreal_export_spec.load(project, a.export_job)
        dot = project / '.opencode';st = dot.stat();owner = (st.st_uid, st.st_gid)
        target = dot / 'unreal-exports' / a.export_job
        if target.exists() or target.is_symlink(): raise ValueError('.opencode/unreal-exports/' + a.export_job + ' already exists; use a new job name')
        out = OUTS / (project.name + '-' + a.export_job + '-' + a.evidence.name[:12])
        cmd = [sys.executable, str(EXPORT), '--pack', str(spec['pack']), '--root', spec['root'], '--out', str(out), '--classes', ','.join(spec['classes']),
               '--include', ','.join(spec['include']), '--max-assets', str(spec['max_assets']), '--memory-gib', str(spec['memory_gib']),
               '--deadline', str(DEADLINE), '--backend', 'auto']
        if spec['exclude'] is not None: cmd += ['--exclude', ','.join(spec['exclude'])]
        receipt.update(spec_sha256=spec['spec_sha256'], artifact_directory=str(out))
        with (a.evidence / 'export.log').open('w') as log: r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, text=True, timeout=DEADLINE + 380)
        tail = (a.evidence / 'export.log').read_text(errors='replace').splitlines()
        result = json.loads((out / 'result.json').read_text()) if (out / 'result.json').is_file() else None
        if result is None:
            receipt['failure_reason'] = 'export did not start: ' + (([x for x in tail if x.strip()] or ['no output'])[-1])[:300]
        else:
            receipt.update({k: result[k] for k in ['engine', 'root', 'counts', 'source_unchanged', 'backend', 'backend_fallback_reason', 'memory_limit_gib'] if k in result})
            receipt['export_status'] = result.get('status')
            receipt['errors'] = [str(x)[:300] for x in result.get('failed', [])][:20]
            if result.get('status') in ('PORTABLE_EXPORT_PASS', 'PARTIAL_EXPORT') and r.returncode == 0:
                copy_tree(out / 'exported', target, owner)
                receipt['exported'] = [{'class': x.get('class'), 'unreal_path': x.get('path'), 'file': '.opencode/unreal-exports/' + a.export_job + '/' + str(x['file']).removeprefix('exported/')}
                                       for x in result.get('exported', []) if isinstance(x, dict) and x.get('file')][:200]
                receipt['export_directory'] = str(target)
                receipt['status'] = 'PASS' if result['status'] == 'PORTABLE_EXPORT_PASS' else 'PARTIAL'
                if result['status'] == 'PARTIAL_EXPORT': receipt['failure_reason'] = 'some assets failed to export; see errors'
            else:
                receipt['failure_reason'] = str(result.get('reason') or 'export failed')[:500]
    except (ValueError, OSError, subprocess.TimeoutExpired) as e:
        receipt['failure_reason'] = str(e)[:500]
    atomic(a.evidence / 'result.json', receipt);print(json.dumps({k: receipt.get(k) for k in ('status', 'failure_reason', 'counts', 'export_directory')}))
    raise SystemExit(0 if receipt['status'] in ('PASS', 'PARTIAL') else 1)


if __name__ == '__main__': main()
