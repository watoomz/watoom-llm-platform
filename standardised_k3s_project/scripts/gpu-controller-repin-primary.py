#!/usr/bin/env python3
"""Re-pin the GPU controller's approved spec digest for the primary model Deployment.

The controller refuses all GPU actions (incl. recovery) when a pinned Deployment's
UID/spec digest differs from live. After a reviewed primary Deployment change, run
--apply (via the llm-model-lab role with gpu_controller_repin_primary=true).
Only deployment_identity[primary].spec_sha256 may change; UID must match; the
controller must be qwen-ready, unowned and certain. A timestamped backup is kept.
Exit 0 = unchanged/updated, 2 = blocked. Same digest formula as g3h_service.py.
"""
import argparse, copy, hashlib, json, os, pathlib, subprocess, sys, time

BASE = pathlib.Path('/data/ai/helper-scripts')
CONFIG = BASE / 'config/gpu-controller.json'
STATE = BASE / 'state/gpu-controller/state.json'

def digest(obj):
    spec = copy.deepcopy(obj['spec']); spec.pop('replicas', None)
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='write; default is read-only check')
    ap.add_argument('--config', default=str(CONFIG))
    ap.add_argument('--state', default=str(STATE))
    a = ap.parse_args()
    cfgp = pathlib.Path(a.config)
    cfg = json.loads(cfgp.read_text())
    name, ns = cfg['primary'], cfg['namespace']
    live = json.loads(subprocess.check_output(['kubectl', '-n', ns, 'get', 'deployment', name, '-o', 'json']))
    pinned = cfg['deployment_identity'][name]
    if live['metadata']['uid'] != pinned['uid']:
        sys.exit('BLOCKED: primary Deployment UID changed; re-enrol, do not re-pin')
    new = digest(live)
    if new == pinned['spec_sha256']:
        print('UNCHANGED'); return
    st = json.loads(pathlib.Path(a.state).read_text())
    if (st.get('phase'), st.get('owner'), st.get('uncertain')) != ('qwen-ready', None, False):
        sys.exit('BLOCKED: controller not qwen-ready/unowned/certain: ' + json.dumps(st))
    if not a.apply:
        print('DRIFT %s -> %s (run with --apply)' % (pinned['spec_sha256'][:12], new[:12])); sys.exit(2)
    backup = cfgp.with_name(cfgp.name + '.bak-' + time.strftime('%Y%m%dT%H%M%S'))
    backup.write_bytes(cfgp.read_bytes()); os.chmod(backup, 0o600)
    cfg['deployment_identity'][name]['spec_sha256'] = new
    raw = cfgp.read_text(); indent = 2 if '\n  "' in raw else None
    tmp = cfgp.with_name(cfgp.name + '.tmp')
    tmp.write_text(json.dumps(cfg, indent=indent) + '\n'); os.chmod(tmp, 0o600); tmp.replace(cfgp)
    print('REPINNED %s -> %s (backup %s)' % (pinned['spec_sha256'][:12], new[:12], backup.name))

if __name__ == '__main__':
    main()
