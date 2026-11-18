"""Dev-only preparation through the maintained Ansible role and native idle guard."""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dev-workspace-only', action='store_true')
    p.add_argument('--iac-root', required=True, type=pathlib.Path)
    p.add_argument('--baseline', required=True)
    p.add_argument('--host', required=True)
    p.add_argument('--evidence', required=True, type=pathlib.Path)
    p.add_argument('--i-approve', action='store_true')
    p.add_argument('--prepare-only', action='store_true')
    a = p.parse_args()
    print('RISK: prepares only dedicated dev identities, constrained SSH, a dev clone and receipt recovery; then adds a native dev agent under an idle fence with independent rollback. No production rollout, inference restart or network changes.', flush=True)
    if not a.i_approve:
        raise PermissionError('--i-approve required')
    if not re.fullmatch('[a-f0-9]{40}', a.baseline) or not re.fullmatch('[0-9.]+', a.host):
        raise ValueError('Verified baseline SHA and existing numeric host required')
    root = a.iac_root.resolve(strict=True)
    source = root / 'tools/watoom-code/dev_workspace'
    package_sha = hashlib.sha256(b''.join((source / x).read_bytes() for x in ['index.js', 'package.json', 'agent.md'])).hexdigest()
    remote = subprocess.check_output(['git', '-C', str(root), 'remote', 'get-url', 'origin'], text=True).strip()
    if remote != 'git@github.com:YOUR_GITHUB_USER/watoom-standardised-homelab.git':
        raise PermissionError('Unexpected authoritative production repository')
    current = pathlib.Path('/data/ai/helper-scripts/dev-workspace/config.json')
    if current.exists() and json.loads(current.read_text()).get('enabled'):
        raise RuntimeError('Development is already enabled; inspect owned state instead of reinstalling it')
    a.evidence.mkdir(parents=True, exist_ok=False, mode=0o700)
    variables = {
        'watoom_code_dev_approved': True, 'watoom_code_dev_baseline': a.baseline,
        'watoom_code_dev_remote': remote, 'watoom_code_dev_host': a.host,
        'watoom_code_dev_package_sha': package_sha,
    }
    varfile = a.evidence / 'ansible-vars.json'
    varfile.write_text(json.dumps(variables, indent=2))
    command = ['ansible-playbook', '-i', 'inventories/homelab/hosts.yml', 'playbooks/watoom-code-dev.yml', '-e', '@' + str(varfile)]
    with (a.evidence / 'ansible.log').open('w') as log:
        subprocess.run(command, cwd=root / 'ansible', stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    if a.prepare_only:
        print('PREPARED: backend remains disabled; validate restricted transport before guarded activation')
        return
    subprocess.run(['/usr/bin/python3', '-I', '/data/ai/helper-scripts/dev-workspace/activation.py', '--prepare', '--package-sha', package_sha,
                    '--host', a.host, '--evidence', str(a.evidence / 'activation'), '--i-approve'], check=True, timeout=180)
    (a.evidence / 'result.json').write_text(json.dumps({'status': 'PASS', 'baseline': a.baseline, 'package_sha': package_sha, 'workspace': '/data/github/watoom-homelab-dev'}))


if __name__ == '__main__':
    main()
