#!/usr/bin/env python3
"""Export a fresh LLM platform source snapshot; never commit, push or deploy.

Tracked platform working-tree bytes plus explicitly selected new source files are
copied alongside a clean, pinned application snapshot. No source Git history is
imported. High-confidence secret findings quarantine entire files and are reported
by path/rule only. Review the report before any commit or upload.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

PROJECT = Path(__file__).resolve().parents[2]
BLOCK_PARTS = {'.git', '.private', '.kube', 'node_modules', '__pycache__', '.venv',
               'secrets-vault', 'apk-web'}
BLOCK_SUFFIX = ('.bundle', '.db', '.sqlite', '.sqlite3', '.tar', '.tar.gz', '.tgz', '.zip',
                '.7z', '.key', '.pem', '.pfx', '.p12', '.token', '.log', '.hprof',
                '.pub')  # SSH public keys identify the owner's accounts
RULES = {
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'aws-key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'slack-token': re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'openai-key': re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b'),
    'credential-url': re.compile(rb'https?://[^\s/@:\"\']{2,}:[^\s/@\"\']{8,}@'),
}


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--application', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path, help='new empty export directory')
    ap.add_argument('--include-new', action='append', default=[], help='exact project-relative new source path')
    a = ap.parse_args()
    app = a.application.resolve()
    out = a.output.resolve()
    if out.exists() or not out.is_relative_to(Path('/data/ai/projects/llm')):
        raise ValueError('Output must be a new directory under /data/ai/projects/llm')
    if git(app, 'status', '--porcelain').strip():
        raise ValueError('Application snapshot must be clean')
    app_head = git(app, 'rev-parse', 'HEAD').decode().strip()
    # Read only public pin values; never load runtime credentials/configuration.
    pins = (PROJECT / 'ansible/vars/watoom-code.yml').read_text()
    expected = re.search(r'^watoom_code_application_commit:\s*(\w+)', pins, re.M)[1]
    if app_head != expected:
        raise ValueError('Application source does not match current deployment pin')
    out.mkdir(mode=0o700, parents=True)
    excluded = set(json.loads((PROJECT / 'tools/git/private-publication-excludes.json').read_text())['paths'])
    rows, skips, findings, links = [], [], [], []
    policy = json.loads((PROJECT / 'tools/git/llm-platform-publication-policy.json').read_text())
    reviewed = policy['reviewed_nonsecret_files']
    scope = policy.get('scope', {})
    scope_prefixes = tuple(scope.get('exclude_prefixes', []))
    sanitised = []
    roots = [('standardised_k3s_project', PROJECT), ('application', app)]
    for prefix, root in roots:
        files = set(git(root, 'ls-files', '-z').decode().split('\0')) - {''}
        if root == PROJECT:
            for p in a.include_new:
                relative = Path(p)
                if relative.is_absolute() or '..' in relative.parts or not (root / relative).is_file():
                    raise ValueError('Invalid explicit new source path')
                files.add(p)
        for relative in sorted(files):
            path = root / relative
            name = prefix + '/' + relative
            parts = set(Path(relative).parts)
            reason = None
            if name in excluded:
                reason = 'private-source-policy'
            elif prefix == 'standardised_k3s_project' and scope_prefixes and relative.startswith(scope_prefixes):
                reason = 'out-of-scope'
            elif parts & BLOCK_PARTS or ('secrets' in parts and not path.name.endswith('.example')) or any(v in relative for v in ['.opencode/work/', '.opencode/captures/', '.opencode/worker-requests/']) or relative.startswith('manifests/05-secrets/') and '/templates/' not in relative:
                reason = 'runtime-or-secret-directory'
            elif path.name == '.env' or path.name.endswith('.env') or path.name in {'kubeconfig', 'k3s.yaml'}:
                reason = 'credential-file'
            elif path.name.endswith(BLOCK_SUFFIX) or '.bak' in path.name or '.sensitive.' in path.name:
                reason = 'archive-binary-or-backup'
            elif not path.exists():
                reason = 'missing-source'
            if reason:
                skips.append({'path': name, 'reason': reason})
                continue
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                link = os.readlink(path)
                resolved = (target.parent / link).resolve()
                if Path(link).is_absolute() or not resolved.is_relative_to(out / prefix):
                    skips.append({'path': name, 'reason': 'escaping-symlink'})
                    continue
                target.symlink_to(link)
                links.append({'path': name, 'target': link})
                continue
            if not path.is_file():
                skips.append({'path': name, 'reason': 'not-regular-source'})
                continue
            if path.stat().st_size > 20_000_000:
                skips.append({'path': name, 'reason': 'large-binary-external-prerequisite'})
                continue
            raw = path.read_bytes()
            hits = [{'path': name, 'rule': rule, 'line': raw[:m.start()].count(b'\n') + 1}
                    for rule, pattern in RULES.items() for m in pattern.finditer(raw)]
            if hits and reviewed.get(name) != hashlib.sha256(raw).hexdigest():
                findings.extend(hits)
                skips.append({'path': name, 'reason': 'quarantined-secret-pattern'})
                continue
            if name == 'standardised_k3s_project/manifests/10-infrastructure/llm/searxng.yml' and policy.get('sanitise_searxng_secret'):
                raw = re.sub(rb'(?m)^(\s*secret_key:)\s*.+$', rb'\1 REPLACE_WITH_DEPLOYMENT_SECRET', raw)
                sanitised.append({'path': name, 'field': 'secret_key', 'reason': 'embedded deployment secret replaced in export only'})
            target.write_bytes(raw)
            target.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
            rows.append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    # Scope overlays replace or add files whose full private form references excluded components.
    overlay = PROJECT / scope['overlay_dir'] if scope.get('overlay_dir') else None
    if overlay and overlay.is_dir():
        by_path = {r['path']: r for r in rows}
        for src in sorted(p for p in overlay.rglob('*') if p.is_file()):
            name = 'standardised_k3s_project/' + src.relative_to(overlay).as_posix()
            raw = src.read_bytes()
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o755 if src.stat().st_mode & 0o111 else 0o644)
            row = {'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            if name in by_path:
                by_path[name].update(row)
            else:
                rows.append(row)
    # Repository-root documents (README, LICENSE, ...) are maintained beside the exporter, not in the project tree.
    root_overlay = PROJECT / 'tools/git/llm-root-overlay'
    if root_overlay.is_dir():
        for src in sorted(p for p in root_overlay.iterdir() if p.is_file()):
            raw = src.read_bytes()
            (out / src.name).write_bytes(raw)
            rows.append({'path': src.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    # Links in kept documents that point at out-of-scope files become plain text, so the export has no dead local links.
    gone = {s['path'] for s in skips if s['reason'] == 'out-of-scope'}
    link_md = re.compile(r'\[([^\]]+)\]\((?!https?:|#|mailto:)([^)#\s]+)(#[^)]*)?\)')
    link_html = re.compile(r'<a\s+[^>]*?href="(?!https?:|#|mailto:)([^"#]+)(?:#[^"]*)?"[^>]*>(.*?)</a>', re.S)
    for row in rows:
        if not row['path'].endswith(('.md', '.html')) or not row['path'].startswith('standardised_k3s_project/'):
            continue
        file = out / row['path']
        text = file.read_text(errors='ignore')
        base = Path(row['path']).parent

        def gone_target(t):
            if t.startswith('/'):
                return False
            return os.path.normpath(str(base / t)) in gone or any(g.startswith(os.path.normpath(str(base / t)) + '/') for g in gone)
        new = link_md.sub(lambda m: m[1] if gone_target(m[2]) else m[0], text)
        new = link_html.sub(lambda m: m[2] if gone_target(m[1]) else m[0], new)
        if new != text:
            raw = new.encode()
            file.write_bytes(raw)
            row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    # List entries that point at files the scope left out would dangle; drop exactly those lines.
    for relative in policy.get('prune_missing_paths', []):
        target = out / 'standardised_k3s_project' / relative
        if not target.is_file():
            continue
        ref = re.compile(r'^\s*-\s+["\']?((?:manifests|ansible|scripts|tools|config|docs)/[^\s"\']+)["\']?\s*$')
        kept, dropped = [], 0
        for line in target.read_text().splitlines(keepends=True):
            m = ref.match(line)
            if m and not (out / 'standardised_k3s_project' / m[1]).exists():
                dropped += 1
                continue
            kept.append(line)
        if dropped:
            raw = ''.join(kept).encode()
            target.write_bytes(raw)
            for row in rows:
                if row['path'] == 'standardised_k3s_project/' + relative:
                    row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            sanitised.append({'path': 'standardised_k3s_project/' + relative, 'field': 'dangling-path-list', 'reason': '%d entries for out-of-scope files removed' % dropped})
    # The Glance dashboard source lists every service of the original homelab; keep only the AI platform.
    if policy.get('prune_glance'):
        subprocess.run(['python3', str(PROJECT / 'tools/git/prune-glance.py'), str(out / 'standardised_k3s_project')], check=True)
    if policy.get('prune_manifests'):
        subprocess.run(['python3', str(PROJECT / 'tools/git/prune-manifests.py'), str(out / 'standardised_k3s_project')], check=True)
    # Generated catalogue and guide pages describe the whole homelab; rebuild them from the scoped tree.
    regen = policy.get('regenerate') or {}
    if regen:
        project_out = out / 'standardised_k3s_project'
        run = lambda *c, **k: subprocess.run(list(c), cwd=project_out, check=True, capture_output=True, **k)
        run('git', 'init', '-q')
        run('git', '-c', 'user.name=export', '-c', 'user.email=export@example.invalid', 'add', '-A')
        try:
            for script, interpreter in regen['commands']:
                run(interpreter, script)
            check = subprocess.run([regen['verifier'][1], regen['verifier'][0]], cwd=project_out, capture_output=True, text=True)
            (out / 'publication').mkdir(exist_ok=True)
            (out / 'publication' / 'documentation-check.txt').write_text(check.stdout[-4000:] + check.stderr[-2000:])
            if 'RESULT=PASS' not in check.stdout:
                raise ValueError('Documentation verification failed on the scoped export; see publication/documentation-check.txt')
        finally:
            subprocess.run(['rm', '-rf', str(project_out / '.git')], check=True)
        # Refresh the file manifest for the regenerated tree.
        by_path = {r['path']: r for r in rows}
        seen = set()
        for file in sorted(project_out.rglob('*')):
            if file.is_symlink() or not file.is_file():
                continue
            name = 'standardised_k3s_project/' + file.relative_to(project_out).as_posix()
            raw = file.read_bytes()
            seen.add(name)
            row = {'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            if name in by_path:
                by_path[name].update(row)
            else:
                rows.append(row)
        rows[:] = [r for r in rows if not r['path'].startswith('standardised_k3s_project/') or r['path'] in seen or (out / r['path']).is_symlink()]
    # Environment-identifying values (domain, LAN addressing, GitHub owner) become placeholders in the export only.
    placeholders = policy.get('placeholders') or {}
    placed = []
    if placeholders:
        rules = [(r['name'], re.compile(r['pattern'].encode()), r['replace'].encode()) for r in placeholders['rules']]
        prefixes = tuple(placeholders['apply_to_prefixes'])
        for row in rows:
            if not row['path'].startswith(prefixes):
                continue
            file = out / row['path']
            if file.is_symlink():
                continue
            raw = file.read_bytes()
            if b'\0' in raw:
                continue
            new = raw
            for name, pattern, replacement in rules:
                new, count = pattern.subn(replacement, new)
                if count:
                    placed.append({'path': row['path'], 'rule': name, 'count': count})
            if new != raw:
                file.write_bytes(new)
                row.update(bytes=len(new), sha256=hashlib.sha256(new).hexdigest())
        # Fail closed: no forbidden value may survive anywhere in the export (application included).
        forbidden = [(f, re.compile(f.encode())) for f in placeholders['forbidden_after']]
        leaks = []
        for row in rows:
            file = out / row['path']
            if file.is_symlink():
                continue
            raw = file.read_bytes()
            if b'\0' in raw:
                continue
            for label, pattern in forbidden:
                if pattern.search(raw):
                    leaks.append({'path': row['path'], 'rule': label})
        if leaks:
            (out / 'publication').mkdir(exist_ok=True)
            (out / 'publication' / 'placeholder-leaks.json').write_text(json.dumps(leaks, indent=2) + '\n')
            raise ValueError('Forbidden environment values remain in %d file(s); see publication/placeholder-leaks.json' % len(leaks))
    # Hard-coded plaintext assignments need a human review; values never leave the host report.
    candidates = []
    assignment = re.compile(rb'(?im)^\s*(?:[\w.-]*(?:password|api_key|access_token|secret)[\w.-]*)\s*[:=]\s*[\"\']?([A-Za-z0-9_+/=-]{12,})')
    for row in rows:
        raw = (out / row['path']).read_bytes()
        if b'\0' in raw:
            continue
        for hit in assignment.finditer(raw):
            value = hit[1].lower()
            if any(x in value for x in [b'example', b'placeholder', b'changeme', b'your_', b'password', b'test', b'none', b'undefined']):
                continue
            candidates.append({'path': row['path'], 'rule': 'literal-credential-review', 'line': raw[:hit.start()].count(b'\n') + 1})
    meta = out / 'publication'
    meta.mkdir(exist_ok=True)
    provenance = {'platform_head': git(PROJECT, 'rev-parse', 'HEAD').decode().strip(),
                  'platform_dirty_paths': git(PROJECT, 'diff', '--name-only').decode().splitlines(),
                  'application_commit': app_head, 'application_origin': git(app, 'remote', 'get-url', 'origin').decode().strip(),
                  'history_imported': False, 'excluded_private_source': sorted(excluded),
                  'file_count': len(rows), 'symlinks': links,
                  'sanitised': sanitised, 'placeholder_substitutions': {'files': len({x['path'] for x in placed}), 'replacements': sum(x['count'] for x in placed)}, 'review_policy': 'standardised_k3s_project/tools/git/llm-platform-publication-policy.json',
                  'limits': ['Heuristic source scan; not a formal secret audit', 'Not a qualified clean-room installer',
                             'Independent Toolkit/AgentMemory/model runtime pins require matching external sources/build inputs']}
    (meta / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    (meta / 'files.json').write_text(json.dumps(rows, indent=2) + '\n')
    (meta / 'exclusions.json').write_text(json.dumps(skips, indent=2) + '\n')
    report = {'status': 'REVIEW_REQUIRED', 'files': len(rows), 'excluded': len(skips),
              'quarantined_findings': findings, 'review_candidates': candidates}
    (meta / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output': str(out), 'files': len(rows), 'excluded': len(skips),
                      'quarantined': len(findings), 'review_candidates': len(candidates)}))


if __name__ == '__main__':
    main()
