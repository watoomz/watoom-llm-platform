#!/usr/bin/env python3
"""Point this checkout at your own disks.

The platform expects three roots, written literally in manifests, playbooks and scripts:
  /data/ai   models, agent memory, projects, worker state       (--data-root)
  /app       small service state (Grafana, Prometheus, Loki...) (--app-root)
  /data/github/watoom-standardised-homelab/standardised_k3s_project   this checkout (--repo-root)

Examples:
  python3 tools/set-paths.py --data-root /srv/ai --app-root /srv/app --repo-root "$(pwd)" --dry-run
  python3 tools/set-paths.py --data-root /srv/ai --app-root /srv/app --repo-root "$(pwd)"

It rewrites text files in place (skips .git and binaries) and prints every file it changed. Run it once, review
`git diff`, and commit. Use --dry-run first.
"""
import argparse, pathlib, re, sys

DEFAULT_DATA, DEFAULT_APP = '/data/ai', '/app'
DEFAULT_REPO = '/data/github/watoom-standardised-homelab/standardised_k3s_project'
SKIP_DIRS = {'.git', 'node_modules', '__pycache__'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data-root', default=DEFAULT_DATA)
    ap.add_argument('--app-root', default=DEFAULT_APP)
    ap.add_argument('--repo-root', default=DEFAULT_REPO)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    here = pathlib.Path(__file__).resolve().parents[1]
    for label, value in (('data-root', a.data_root), ('app-root', a.app_root), ('repo-root', a.repo_root)):
        if not value.startswith('/') or value.endswith('/') and value != '/':
            sys.exit('--%s must be an absolute path without a trailing slash: %r' % (label, value))
    # Order matters: the repo root is the longest and contains /data/, so it is replaced first via a placeholder.
    pairs = [(DEFAULT_REPO, '\0REPO\0'), (DEFAULT_DATA, '\0DATA\0')]
    # /app is also a common path INSIDE containers (/app/helper.py), so only host-side uses are rewritten:
    # hostPath `path:` values, `- /app/...` list items and Ansible path/src/dest values.
    app_re = re.compile(r'(?m)^(\s*(?:-\s+)?(?:path|src|dest|[\w]*_(?:dir|path|root)):?\s*["\']?)' + re.escape(DEFAULT_APP) + r'(?=/)')
    list_re = re.compile(r'(?m)^(\s*-\s+["\']?)' + re.escape(DEFAULT_APP) + r'(?=/)')
    changed = 0
    for path in sorted(here.rglob('*')):
        if not path.is_file() or SKIP_DIRS & set(path.parts) or path.is_symlink() or path.resolve() == pathlib.Path(__file__).resolve():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for old, token in pairs:
            new = new.replace(old, token)
        new = new.replace('\0REPO\0', a.repo_root).replace('\0DATA\0', a.data_root)
        if a.app_root != DEFAULT_APP:
            new = app_re.sub(lambda m: m[1] + a.app_root, new)
            new = list_re.sub(lambda m: m[1] + a.app_root, new)
        if new != text:
            changed += 1
            print(('would change ' if a.dry_run else 'changed ') + str(path.relative_to(here)))
            if not a.dry_run:
                path.write_text(new)
    print('%d file(s) %s' % (changed, 'would change' if a.dry_run else 'changed'))
    if a.app_root != DEFAULT_APP:
        print('Container-internal /app paths were left alone on purpose. Check `grep -rn "/app/" ansible` for host paths set another way.')


if __name__ == '__main__':
    main()
