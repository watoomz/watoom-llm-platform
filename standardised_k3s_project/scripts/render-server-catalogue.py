#!/usr/bin/env python3
"""Build the server source catalogue from tracked files; --check detects drift.

Uses stdlib only. Reads source, never executes inventoried programs. Descriptions
are declarations from docstrings/Purpose comments or explicitly labelled filename
summaries. Inventory is not proof that a helper is installed, safe, or supported.
"""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = 'https://github.com/YOUR_GITHUB_USER/watoom-standardised-homelab/blob/main/standardised_k3s_project/'
try:
    remote = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    if remote in {'git@github.com:YOUR_GITHUB_USER/watoom-llm-platform.git', 'https://github.com/YOUR_GITHUB_USER/watoom-llm-platform.git'}:
        SOURCE_URL = 'https://github.com/YOUR_GITHUB_USER/watoom-llm-platform/blob/main/standardised_k3s_project/'
except subprocess.CalledProcessError:
    pass
SCOPES = ('scripts', 'ansible/playbooks', 'ansible/roles', 'tools')
CODE = {'.py', '.sh', '.bash', '.js', '.mjs', '.cjs', '.ts', '.gd', '.ps1'}


def tracked():
    result = subprocess.run(['git', 'ls-files', '-z', '--', *SCOPES], cwd=ROOT,
                            capture_output=True, check=True)
    paths = set(result.stdout.decode().split('\0')) - {''}
    # The generator itself becomes part of the inventory before its first commit.
    paths.add('scripts/render-server-catalogue.py')
    candidates = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z', '--', *SCOPES], cwd=ROOT).decode().split('\0')
    paths.update(p for p in candidates if Path(p).suffix in CODE and '.bak' not in p and '__pycache__' not in p)
    return sorted(p for p in paths if (ROOT / p).is_file())


def clean(value, limit=240):
    value = re.sub(r'\s+', ' ', value).strip().replace('|', '/')
    # Never lift credential assignments or PEM/token material into a description.
    if re.search(r'BEGIN .*PRIVATE KEY|gh[pousr]_|github_pat_|password\s*[:=]|token\s*[:=]', value, re.I):
        return 'See source contract; credential-bearing description omitted.'
    return re.sub(r'([`*_{}\[\]()<>#+!])', r'\\\1', value[:limit])


def describe(path, text):
    if path.endswith('.py'):
        try:
            doc = ast.get_docstring(ast.parse(text))
            if doc:
                return clean(doc.split('\n\n')[0]), 'module docstring'
        except (SyntaxError, ValueError):
            pass
    purpose = re.search(r'^\s*#\s*-?\s*Purpose:\s*(.+)', text, re.M)
    if purpose:
        return clean(purpose[1]), 'Purpose comment'
    if Path(path).suffix in {'.yml', '.yaml'}:
        name = re.search(r'^\s*-\s*name:\s*(.+)', text, re.M)
        if name:
            return clean(name[1].strip('\"\'')), 'first named play/task'
    if Path(path).suffix in {'.js', '.mjs', '.cjs', '.ts'}:
        comment = re.search(r'/\*\*?\s*(.*?)\*/', text[:5000], re.S)
        if comment:
            return clean(re.sub(r'^\s*\* ?', '', comment[1], flags=re.M)), 'source comment'
    stem = Path(path).stem.replace('_', ' ').replace('-', ' ')
    kind = 'Test fixture/check' if re.search(r'(^|/)(test[^/]*|tests)/|(^|/)test[-_]', path) else 'Source component'
    return f'{kind}: {stem}. Inspect the source before use.', 'filename summary'


def ref(path):
    return f'[`{path}`]({SOURCE_URL + quote(path, safe="/")})'


def page(title, nav, summary, body):
    return f'---\ntitle: {title}\nnav: {nav}\nsummary: {summary}\n---\n\n' + body


RETIRED_PATHS = {
    'ansible/playbooks/host-ollama.yml', 'ansible/playbooks/opencode-agent.yml', 'ansible/playbooks/opencode-agent-v2-canary.yml', 'ansible/playbooks/rebuild-homelab.yml',
    'ansible/playbooks/watoom-code-retire-legacy.yml', 'scripts/verify-opencode-v2-canary.sh', 'tools/watoom-code/suspend-canary.py',
    'ansible/roles/opencode-agent/tasks/suspended.yml', 'ansible/roles/opencode-agent/tasks/v2_canary.yml',
}
RETIRED_PREFIXES = ('ansible/roles/host_ollama/', 'tools/blender-asset-builder/canary-', 'tools/blender-asset-builder/fix-canary', 'tools/blender-asset-builder/install-canary')


def is_retired(path):
    """Retired and legacy source stays in Git but is not part of the current-state reference."""
    return path in RETIRED_PATHS or path.startswith(RETIRED_PREFIXES)


def build():
    rows = []
    committed = set(subprocess.check_output(['git', 'ls-files', '-z', '--', *SCOPES], cwd=ROOT).decode().split('\0'))
    excluded = json.loads((ROOT / 'tools/git/private-publication-excludes.json').read_text())['paths']
    excluded = {p.removeprefix('standardised_k3s_project/') for p in excluded}
    for path in tracked():
        if is_retired(path):
            continue
        p = ROOT / path
        raw = p.read_bytes()
        row = {'path': path, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
               'scope': next(s for s in SCOPES if path.startswith(s + '/'))}
        if path in excluded:
            row.update(description='Private instruction source; excluded from publication.', basis='exclusion policy', private=True)
        else:
            text = raw.decode('utf-8', errors='replace') if len(raw) < 2_000_000 else ''
            row['description'], row['basis'] = describe(path, text)
            row['code'] = p.suffix in CODE or (row['scope'] == 'scripts' and not p.suffix)
            row['vendored'] = '/pi-mcp-bridge-runtime/' in path
            if row['code']:
                row['options'] = sorted(set(re.findall(r'add_argument\([\"\'](--[\w-]+)', text)))
            if row['scope'] == 'ansible/playbooks' or ('/tasks/' in path and p.suffix == '.yml'):
                row['task_names'] = [clean(v) for v in re.findall(r'^\s*-\s*name:\s*(.+)', text, re.M)]
                row['role_references'] = sorted(set(re.findall(r'(?:include_role|import_role):\s*\n\s+name:\s*[\"\']?([\w-]+)', text)))
        rows.append(row)
    common = ('This catalogue is generated from tracked source and untracked code candidates by `scripts/render-server-catalogue.py`. '
              'It does not run programs or certify their deployment. Source links use the configured WatooM source repository; '
              'the separate LLM repository retains the same `standardised_k3s_project/` paths. '
              'Descriptions name their evidence basis; a filename summary is not a verified operational contract.\n\n'
              'Read [Operations](operations.md), [installation and configuration](llm-project.md), '
              'and [the software design](software-design.md) before executing deployment or recovery helpers. '
              'Run no bulk scripts from this list.\n\n')
    counts = Counter(r['scope'] for r in rows)
    outputs = {}
    overview = ('## Coverage\n\n| Area | Source files | Reference |\n|---|---:|---|\n' +
                ''.join(f'| `{scope}/` | {counts[scope]} | [{label}]({target}.md) |\n' for scope, label, target in [
                    ('scripts', 'Operator scripts', 'server-scripts'), ('ansible/playbooks', 'Playbooks', 'server-playbooks'),
                    ('ansible/roles', 'Roles and deployed payloads', 'server-roles'), ('tools', 'Tools and checks', 'server-tools')]) +
                '\nThe [machine-readable inventory](/guide/assets/server-catalogue.json) records every tracked file in these four areas, '
                'including non-executable templates, fixtures, bundled dependency files, and private-source placeholders. '
                'It contains paths, file hashes and descriptions, not private instruction bodies or secret values. '
                'Untracked code candidates are included for completeness; inclusion does not claim they are committed. Runtime helper copies and external application source are outside this catalogue.\n\n'
                '## How to use the reference\n\n'
                '1. Start with the task in Operations or the LLM project guide.\n'
                '2. Locate its playbook and the role/tasks it imports.\n'
                '3. Inspect defaults, required variables, templates, and the exact helper in Git.\n'
                '4. Validate the change using the documented tier; apply only the owning playbook.\n'
                '5. Verify runtime behaviour and record rollback evidence.\n\n'
                '## Source and runtime boundaries\n\n'
                'The operator checkout is desired state. `/data/ai/helper-scripts` contains installed runtime copies and state; '
                'fix their owner source rather than editing an installed copy. `archive/`, `retired/` and historical acceptance notes '
                'are references, not installation instructions. Test/acceptance/cutover names never imply permission to run on production. '
                'Use the [custom extensions map](llm-extensions.md) for plugins, agents, skills and workers, and '
                '[GitHub publication](llm-publication.md) for external source and distribution boundaries.\n')
    outputs['docs/guide/server-catalogue.md'] = page('Server automation reference', 'Server reference',
        'Complete tracked-source coverage for operator scripts, Ansible playbooks and roles, tools, checks and deployed payloads.', common + overview)
    for scope, name, title, nav in [('scripts', 'server-scripts', 'Operator script reference', 'Scripts'),
                                   ('ansible/playbooks', 'server-playbooks', 'Ansible playbook reference', 'Playbooks'),
                                   ('tools', 'server-tools', 'Tool and validation reference', 'Tools')]:
        selected = [r for r in rows if r['scope'] == scope and (scope != 'tools' or r.get('code'))]
        body = common
        if scope == 'ansible/playbooks':
            body += ('## Invocation and inputs\n\nFrom the project root, use `./ansible-run playbooks/<name>.yml` '
                     'only after reading that playbook and its role defaults. The wrapper sets inventory/vault/execution environment. '
                     'Play-level variables, vars files, includes and gates remain authoritative; there is no universal safe apply command. '
                     'Use `scripts/watoom-ansible-validate.sh standard` for production-bound Ansible source.\n\n')
        elif scope == 'scripts':
            body += ('## Invocation and inputs\n\nPython helpers use `python3 scripts/<name>.py`; Bash helpers use `bash scripts/<name>.sh`. '
                     'Documentation rendering uses `/data/ai/toolchains/docs-render/bin/python`. Extensionless wrappers must be inspected for their shebang. '
                     'Even `--help` is not assumed safe for an arbitrary operational script. Listed options are static argparse declarations, not defaults or permission to mutate.\n\n')
        for r in selected:
            body += f'## {r["path"]}\n\n{r["description"]}\n\nSource: {ref(r["path"])}. Description basis: {r["basis"]}.\n\n'
            if r.get('lifecycle'):
                body += '**Lifecycle: ' + r['lifecycle'] + '**\n\n'
            if r.get('options'):
                body += 'Declared CLI options: ' + ', '.join('`' + v + '`' for v in r['options']) + '.\n\n'
            if r.get('task_names'):
                body += 'Named steps: ' + '; '.join(r['task_names'][:10]) + ('. Further steps are in source.' if len(r['task_names']) > 10 else '.') + '\n\n'
        outputs[f'docs/guide/{name}.md'] = page(title, nav, 'Source-backed purpose and interfaces for each tracked component; inspect gates and configuration before running.', body)
    body = common
    roles = sorted({r['path'].split('/')[2] for r in rows if r['scope'] == 'ansible/roles'})
    for role in roles:
        members = [r for r in rows if r['path'].startswith('ansible/roles/' + role + '/')]
        body += f'## {role}\n\n'
        main = next((r for r in members if r['path'].endswith('/tasks/main.yml')), None)
        if main and main.get('lifecycle'):
            body += '**Lifecycle: ' + main['lifecycle'] + '**\n\n'
        body += (main['description'] if main else 'Role payload; inspect owning playbook before use.') + '\n\n'
        for part in ['tasks/main.yml', 'defaults/main.yml', 'handlers/main.yml', 'meta/main.yml']:
            p = f'ansible/roles/{role}/{part}'
            if (ROOT / p).exists():
                body += '- ' + ref(p) + '\n'
        body += f'\nSource files: {len(members)}. All paths and hashes are in the downloadable inventory.\n\n'
        tasks = [r for r in members if '/tasks/' in r['path']]
        body += '| Task file | Purpose declared in source |\n|---|---|\n'
        for r in tasks:
            body += f'| {ref(r["path"])} | {r["description"]} |\n'
        payloads = [r for r in members if r.get('code') and not r.get('vendored')]
        if payloads:
            body += '\n### Deployed code and helpers\n\n| Source | Purpose |\n|---|---|\n'
            for r in payloads:
                body += f'| {ref(r["path"])} | {r["description"]} ({r["basis"]}) |\n'
        vendor = sum(bool(r.get('vendored')) for r in members)
        if vendor:
            body += f'\nBundled `pi-mcp-bridge-runtime` dependency payload: {vendor} files, indexed individually in JSON; retain its upstream notices.\n'
        body += '\n'
    outputs['docs/guide/server-roles.md'] = page('Ansible role reference', 'Roles',
        'Each role, its task entrypoints, defaults, handlers and deployed helper payloads.', body)
    outputs['docs/server-catalogue.json'] = json.dumps({'schema_version': 1, 'scope': list(SCOPES),
        'coverage': 'tracked source plus untracked code candidates; not runtime deployment proof', 'counts': dict(counts),
        'roles': len(roles), 'files': rows}, indent=2, ensure_ascii=False) + '\n'
    return outputs


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true', help='fail on catalogue drift without writing')
    args = ap.parse_args()
    drift = []
    for name, value in build().items():
        path = ROOT / name
        if not path.exists() or path.read_text() != value:
            drift.append(name)
            if not args.check:
                path.write_text(value)
    print(json.dumps({'result': 'FAIL' if args.check and drift else 'PASS', 'changed': drift}))
    return int(args.check and bool(drift))


if __name__ == '__main__':
    raise SystemExit(main())
