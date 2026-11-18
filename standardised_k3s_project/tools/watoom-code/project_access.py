#!/usr/bin/env python3
"""Restore explicit editable project paths without changing ownership or asset libraries."""
import argparse
import json
import os
import pathlib
import stat
import tempfile
import subprocess


def targets(project, directories, trees):
    base = pathlib.Path(project).resolve(strict=True)
    if not base.is_relative_to('/data/ai/projects/games') or base == pathlib.Path('/data/ai/projects/games'):
        raise ValueError('An existing game project is required')
    if pathlib.Path(project).is_symlink():
        raise ValueError('Indirect project root refused')
    result = {base}
    for name in directories + trees:
        relative = pathlib.Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Project-relative scope required')
        path = base / relative
        if not path.exists():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(base):
            raise ValueError('Scope escapes the project')
        result.add(path)
        if name in trees:
            for item in path.rglob('*'):
                if item.is_symlink():
                    continue
                if not item.resolve().is_relative_to(base):
                    raise ValueError('Scope escapes the project')
                result.add(item)
    return sorted(result)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', required=True)
    p.add_argument('--directory', action='append', default=[])
    p.add_argument('--tree', action='append', default=[])
    p.add_argument('--evidence', required=True, type=pathlib.Path)
    p.add_argument('--i-approve', action='store_true')
    a = p.parse_args()
    paths = targets(a.project, a.directory, a.tree)
    a.evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    a.evidence = pathlib.Path(tempfile.mkdtemp(prefix="access-", dir=a.evidence))
    before = subprocess.check_output(['getfacl', '-p', '-n', '--', *map(str, paths)])
    (a.evidence / 'acl-before.txt').write_bytes(before)
    (a.evidence / 'plan.json').write_text(json.dumps({'project': a.project, 'paths': list(map(str, paths)), 'uid': 1001}, indent=2))
    print('RISK: restores UID1001 edit access only on the explicit candidate paths; ownership, default ACLs and original asset-library files are preserved.', flush=True)
    if not a.i_approve:
        raise PermissionError('--i-approve required')
    changed = 0
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(pathlib.Path(a.project).resolve()):
            raise ValueError("Concurrent path escape refused")
        mode = path.stat().st_mode
        permission = 'rwx' if stat.S_ISDIR(mode) or mode & 0o111 else 'rw-'
        current = subprocess.check_output(['getfacl', '-cp', '-n', str(path)], text=True)
        lines = set(current.splitlines())
        if 'user:1001:' + permission in lines and 'mask::' + permission in lines:
            continue
        changed += 1
        subprocess.run(['setfacl', '-P', '-n', '-m', 'u:1001:' + permission + ',m::' + permission, '--', str(path)], check=True)
        actual = set(subprocess.check_output(['getfacl', '-cp', '-n', str(path)], text=True).splitlines())
        if 'user:1001:' + permission not in actual or 'mask::' + permission not in actual:
            raise RuntimeError('ACL correction did not take effect: ' + str(path))
    (a.evidence / 'acl-after.txt').write_bytes(subprocess.check_output(['getfacl', '-p', '-n', '--', *map(str, paths)]))
    (a.evidence / 'result.json').write_text(json.dumps({'status': 'PASS', 'paths': len(paths), 'rollback': 'setfacl --restore=' + str(a.evidence / 'acl-before.txt')}))
    print('PASS scoped ACL correction:', len(paths), 'paths; changed_paths=' + str(changed) + '; evidence=' + str(a.evidence))


if __name__ == '__main__':
    main()
