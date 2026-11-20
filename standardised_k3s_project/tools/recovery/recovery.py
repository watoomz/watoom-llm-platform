#!/usr/bin/env python3
"""Inventory, capture and validate WatooM recovery inputs without changing services.

Default commands are read-only. Capture writes a private backup, never Git. Run
restores into a new empty directory; there is deliberately no live overwrite,
automatic replay of jobs, runtime installer or unfenced GPU mutation here.
"""
import argparse
from contextlib import closing
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tarfile
import time

PROJECT = Path(__file__).resolve().parents[2]
POLICY = PROJECT / 'config/recovery/policy.json'
CAPTURE_PARENT = Path('/data/backups/recovery')
K3S_DATABASE = Path('/var/lib/rancher/k3s/server/db/state.db')
STAMP = re.compile(r'^\d{8}T\d{6}Z$')


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def command(args, timeout=45):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('Probe failed: ' + args[0] + ' ' + args[1])
    return p.stdout


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)


def classify(path, policy):
    """Longest matching prefix wins; unknown storage is an explicit blocker."""
    matches = [x for x in policy['storage'] if path == x['path'] or (x['mode'] != 'boundary' and path.startswith(x['path'].rstrip('/') + '/'))]
    return max(matches, key=lambda x: len(x['path'])) if matches else {'mode': 'unclassified', 'reason': 'No recovery policy for this mount'}


def inventory(policy):
    raw = json.loads(command(['kubectl', 'get', 'deploy,sts,ds,cronjob,pvc', '-A', '-o', 'json']))
    workloads, pvcs, storage, secrets, images = [], [], {}, set(), set()
    for obj in raw['items']:
        meta, spec = obj['metadata'], obj.get('spec', {})
        if obj['kind'] == 'PersistentVolumeClaim':
            pvcs.append({'namespace': meta['namespace'], 'name': meta['name'],
                         'volume': spec.get('volumeName'), 'storageClass': spec.get('storageClassName'),
                         'request': spec.get('resources', {}).get('requests', {}).get('storage')})
            continue
        if obj['kind'] == 'CronJob':
            pod = spec.get('jobTemplate', {}).get('spec', {}).get('template', {}).get('spec', {})
        else:
            pod = spec.get('template', {}).get('spec', {})
        key = meta['namespace'] + '/' + meta['name']
        entry = {'kind': obj['kind'], 'namespace': meta['namespace'], 'name': meta['name'],
                 'replicas': spec.get('replicas'), 'suspend': spec.get('suspend'), 'images': [], 'volumes': []}
        for c in pod.get('containers', []) + pod.get('initContainers', []):
            images.add(c['image']); entry['images'].append(c['image'])
            for v in c.get('env', []):
                ref = v.get('valueFrom', {}).get('secretKeyRef')
                if ref:
                    secrets.add(meta['namespace'] + '/' + ref['name'])
            for v in c.get('envFrom', []):
                if 'secretRef' in v:
                    secrets.add(meta['namespace'] + '/' + v['secretRef']['name'])
        for vol in pod.get('volumes', []):
            if 'hostPath' in vol:
                path = vol['hostPath']['path']; storage.setdefault(path, []).append(key)
                entry['volumes'].append({'hostPath': path})
            if 'persistentVolumeClaim' in vol:
                entry['volumes'].append({'pvc': vol['persistentVolumeClaim']['claimName']})
            if 'secret' in vol:
                secrets.add(meta['namespace'] + '/' + vol['secret']['secretName'])
        workloads.append(entry)
    pods = json.loads(command(['kubectl', 'get', 'pods', '-A', '-o', 'json']))
    running_ids = sorted({c.get('imageID', '') for p in pods['items']
                          for c in p.get('status', {}).get('containerStatuses', []) if c.get('imageID')})
    volumes = json.loads(command(['kubectl', 'get', 'pv', '-o', 'json']))
    for v in volumes['items']:
        path = v.get('spec', {}).get('hostPath', {}).get('path') or v.get('spec', {}).get('local', {}).get('path')
        if path:
            storage.setdefault(path, []).append('PV/' + v['metadata']['name'])
    containers = []
    ids = command(['docker', 'ps', '-aq']).split()
    if ids:
        for c in json.loads(command(['docker', 'inspect', *ids])):
            labels = c.get('Config', {}).get('Labels') or {}
            entry = {'name': c['Name'].lstrip('/'), 'image': c['Config']['Image'], 'imageID': c['Image'],
                     'running': c['State']['Running'], 'mounts': [],
                     'compose_files': labels.get('com.docker.compose.project.config_files'),
                     'compose_directory': labels.get('com.docker.compose.project.working_dir')}
            images.add(entry['image'])
            for m in c.get('Mounts', []):
                path = m.get('Source')
                if path:
                    storage.setdefault(path, []).append('Docker/' + entry['name'])
                    entry['mounts'].append({'source': path, 'destination': m['Destination'], 'type': m['Type']})
            containers.append(entry)
    units = []
    for line in command(['systemctl', 'list-unit-files', 'watoom-*', '--no-legend', '--no-pager']).splitlines():
        words = line.split()
        if not words or not words[0].endswith(('.service', '.timer', '.socket')):
            continue
        name = words[0]
        probe = subprocess.run(['systemctl', 'show', name, '-p', 'ActiveState', '-p', 'FragmentPath'], capture_output=True, text=True, timeout=15)
        state = probe.stdout.splitlines()
        fields = dict(x.split('=', 1) for x in state if '=' in x)
        units.append({'name': name, 'enabled': words[1], 'active': fields.get('ActiveState'),
                      'unit_file': fields.get('FragmentPath')})
    mounts = json.loads(command(['findmnt', '--json', '--output', 'TARGET,SOURCE,FSTYPE']))
    users = []
    for line in command(['getent', 'passwd']).splitlines():
        fields = line.split(':')
        if fields[0].startswith(('watoom', 'codex')) or fields[0] == 'root' or 1000 <= int(fields[2]) < 65534:
            users.append({'name': fields[0], 'uid': int(fields[2]), 'gid': int(fields[3]), 'home': fields[5]})
    secret_list = json.loads(command(['kubectl', 'get', 'secret', '-A', '-o', 'json']))
    # Names/types only: never write Secret data, config content, env values or session bodies to this inventory.
    secret_names = [{'namespace': s['metadata']['namespace'], 'name': s['metadata']['name'], 'type': s.get('type')}
                    for s in secret_list['items']]
    mapped = []
    for path, consumers in sorted(storage.items()):
        rule = classify(path, policy)
        mapped.append({'path': path, 'consumers': sorted(set(consumers)), 'mode': rule['mode'], 'reason': rule['reason'], 'policy_root': rule.get('path')})
    return {'schema_version': 1, 'sampled_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'host': command(['hostname']).strip(), 'kernel': command(['uname', '-r']).strip(),
            'source_machine_id_sha256': hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest(),
            'workloads': workloads, 'pvcs': pvcs, 'docker': containers, 'systemd_units': units,
            'storage': mapped, 'mounts': mounts, 'users': users, 'image_references': sorted(images),
            'running_image_ids': running_ids, 'secret_names': secret_names,
            'secret_references': sorted(secrets), 'policy': policy['name'],
            'limits': ['Snapshot is inventory, not a backup or permission to replay workloads.',
                       'Zero replicas is an intended state, not proof of retirement.',
                       'Local registry images, secrets and persistent data require separate private recovery material.']}


def verify_backup(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8-sig'))
    if not isinstance(manifest.get('files'), dict) or not manifest['files']:
        raise ValueError('Empty or invalid backup file manifest')
    for name, expected in manifest['files'].items():
        relative = Path(name)
        target = root / relative
        if relative.is_absolute() or '..' in relative.parts or target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ValueError('Unsafe backup manifest path')
        if not target.is_file() or digest(target) != expected:
            raise ValueError('Backup content does not match manifest: ' + name)
    return manifest


def restore_test(backup, target):
    manifest = verify_backup(backup)
    root, target = Path(backup).resolve(), Path(target).resolve()
    if target.exists() or target == root or target.is_relative_to(root):
        raise ValueError('Restore test needs a NEW directory outside the backup')
    target.mkdir(mode=0o700, parents=True)
    checks = []
    for name in manifest['files']:
        if not name.endswith(('.sqlite.gz', '.db.gz')):
            continue
        dest = target / name.removesuffix('.gz'); dest.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(root / name, 'rb') as src, dest.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        with closing(sqlite3.connect('file:' + str(dest) + '?mode=ro', uri=True)) as db:
            result = db.execute('pragma integrity_check').fetchone()[0]
            if result != 'ok':
                raise ValueError('Restored SQLite integrity check failed')
        checks.append({'file': name, 'integrity': 'ok'})
    if not checks:
        raise ValueError('No SQLite snapshots available to test')
    for name in manifest['files']:
        if name.endswith('.tar.gz'):
            # Validate archive readability and safe member names without extracting credentials.
            with tarfile.open(root / name, 'r:gz') as archive:
                for member in archive:
                    if Path(member.name).is_absolute() or '..' in Path(member.name).parts:
                        raise ValueError('Unsafe archive member')
                    if member.isfile():
                        with archive.extractfile(member) as f:
                            while f.read(1 << 20):
                                pass
    result = {'result': 'PASS', 'scope': 'off-host backup checksums, isolated SQLite restoration, archive readability',
              'sqlite': checks, 'limits': ['No service was started or overwritten.',
              'AgentMemory live-file archive is not an application-consistency qualification.',
              'This is not a full replacement-host recovery drill.']}
    atomic_json(target / 'result.json', result)
    return result


def coverage(inv, policy, evidence=None):
    blockers = []
    for p in inv['storage']:
        if p['mode'] == 'unclassified':
            blockers.append({'component': p['path'], 'reason': 'Unclassified persistent storage'})
    if not evidence:
        blockers += [{'component': x, 'reason': 'No verified private recovery evidence supplied'} for x in policy['required_evidence']]
    else:
        for key in policy['required_evidence']:
            record = evidence.get(key, {})
            if not record.get('verified') or not record.get('location') or not record.get('sha256'):
                blockers.append({'component': key, 'reason': 'Missing verified location and checksum'})
                continue
            location = Path(record['location'])
            if not location.is_file() or location.is_symlink() or digest(location) != record['sha256']:
                blockers.append({'component': key, 'reason': 'Evidence file unavailable or checksum mismatch on this recovery host'})
    return {'result': 'BLOCKED' if blockers else 'READY_FOR_ISOLATED_DRILL', 'blockers': blockers,
            'limits': ['Evidence attestations must refer to real tested material; this check is not a full restore test.']}


def capture(policy, output, include_projects=False):
    """Create a private, portable recovery bundle. No services are stopped or restarted."""
    if os.geteuid() != 0:
        raise ValueError('Private recovery capture requires the operator/root account')
    out = Path(output).resolve()
    if out.exists() or out.parent != CAPTURE_PARENT or not STAMP.fullmatch(out.name):
        raise ValueError('Capture output must be a new /data/backups/recovery/YYYYmmddTHHMMSSZ directory')
    os.umask(0o077); out.mkdir(mode=0o700, parents=True)
    inv = inventory(policy); atomic_json(out / 'environment.json', inv)
    # Reuse the existing consistent online SQLite/config backup implementation.
    helper = PROJECT / 'tools/watoom-code/backup.py'
    subprocess.run(['python3', str(helper), '--dest', str(out / 'application-snapshots'), '--keep', '1',
                    '--textfile-dir', str(out / 'metrics')], check=True, stdout=subprocess.DEVNULL)
    private = out / 'private'; private.mkdir(mode=0o700)
    cluster_db = K3S_DATABASE
    if cluster_db.is_file():
        target = private / 'k3s-state.sqlite'
        with closing(sqlite3.connect('file:' + str(cluster_db) + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            dst.execute('pragma journal_mode=delete')
            if dst.execute('pragma integrity_check').fetchone()[0] != 'ok':
                raise ValueError('K3s database snapshot integrity failed')
        with target.open('rb') as src, gzip.open(str(target) + '.gz', 'wb') as dst:
            shutil.copyfileobj(src, dst)
        target.unlink()
    for resource in ['secrets', 'configmaps', 'deploy,sts,ds,cronjob,svc,pv,pvc']:
        raw = command(['kubectl', 'get', resource, '-A', '-o', 'json'], timeout=90)
        (private / (resource.replace(',', '-') + '.json')).write_text(raw)
    excluded, missing, links = [], [], []
    roots = list(policy['capture_roots'])
    roots += [p['path'] for p in inv['storage'] if p['mode'] == 'capture']
    if include_projects:
        roots += policy['project_roots']
    else:
        roots = [p for p in roots if not any(p == q or p.startswith(q + '/') for q in policy['project_roots'])]
    roots = sorted(set(roots), key=lambda p: (len(Path(p).parts), p))
    roots = [p for p in roots if not any(p != q and p.startswith(q.rstrip('/') + '/') for q in roots)]
    written_bytes = 0
    sqlite_map = []
    def filtered(member):
        nonlocal written_bytes
        parts = set(Path(member.name).parts)
        if parts & set(policy['exclude_directory_names']):
            excluded.append(member.name); return None
        if member.issym() or member.islnk():
            links.append({'path': member.name, 'target': member.linkname}); return None
        if not (member.isfile() or member.isdir()):
            excluded.append(member.name); return None
        absolute = '/' + member.name
        if not include_projects and any(absolute == q or absolute.startswith(q + '/') for q in policy['project_roots']):
            excluded.append(member.name); return None
        rule = classify(absolute, policy)
        if rule['mode'] in {'reacquire', 'exclude-media', 'transient'}:
            excluded.append(member.name); return None
        if member.isfile():
            written_bytes += member.size
            free = shutil.disk_usage(out).free
            if written_bytes > policy['capture_max_source_bytes'] or free < policy['minimum_free_bytes'] + 2 * member.size:
                raise ValueError('Capture storage budget reached; partial evidence preserved, no success manifest written')
        if member.isfile() and member.name.endswith(('.db', '.sqlite', '.sqlite3')):
            source = Path(absolute)
            with source.open('rb') as probe:
                is_sqlite = probe.read(16) == b'SQLite format 3\x00'
            if is_sqlite:
                target = private / 'sqlite-snapshots' / (member.name + '.sqlite')
                target.parent.mkdir(parents=True, exist_ok=True)
                deadline = time.monotonic() + 120
                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        raise ValueError('SQLite snapshot deadline reached; no complete recovery bundle published')
                with closing(sqlite3.connect('file:' + str(source) + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(target)) as dst:
                    src.backup(dst, pages=256, progress=progress)
                    dst.execute('pragma journal_mode=delete')
                    if dst.execute('pragma integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('Recovery SQLite snapshot integrity failed')
                with target.open('rb') as src, gzip.open(str(target) + '.gz', 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                target.unlink()
                sqlite_map.append({'original': absolute, 'snapshot': str(Path(str(target) + '.gz').relative_to(out))})
                return None
        if member.isfile() and member.name.endswith(('-wal', '-shm')):
            source = Path(absolute[:-4])
            if source.is_file():
                with source.open('rb') as probe:
                    if probe.read(16) == b'SQLite format 3\x00':
                        return None
        return member
    # Low-priority operator invocation is recommended; no parallel filesystem walks.
    with tarfile.open(out / 'private-state.tar.gz', 'w:gz', compresslevel=1) as archive:
        for name in roots:
            source = Path(name)
            if not source.exists():
                missing.append(name); continue
            archive.add(source, arcname=name.lstrip('/'), recursive=True, filter=filtered)
    # Preserve custom running Docker images that cannot be fetched from a public registry.
    running = [c for c in inv.get('docker', []) if c.get('running')]
    refs = sorted({c['image'] for c in running})
    if refs:
        image_bytes = 0
        image_records = []
        for ref in refs:
            meta = json.loads(command(['docker', 'image', 'inspect', ref]))[0]
            expected = {c['imageID'] for c in running if c['image'] == ref}
            if expected != {meta['Id']}:
                raise ValueError('A Docker tag no longer identifies the running image; reconcile source/image identity before capture')
            image_bytes += meta['Size']
            image_records.append({'reference': ref, 'imageID': meta['Id'], 'bytes': meta['Size']})
        if written_bytes + image_bytes > policy['capture_max_source_bytes'] or shutil.disk_usage(out).free < 2 * image_bytes + policy['minimum_free_bytes']:
            raise ValueError('Insufficient recovery budget for Docker image archives; partial evidence preserved')
        raw_images = private / 'docker-images.tar'
        with (private / 'docker-image-export.log').open('w') as log:
            subprocess.run(['docker', 'image', 'save', '--output', str(raw_images), *refs], check=True, timeout=3600, stdout=log, stderr=log)
        packed_images = private / 'docker-images.tar.gz'
        with raw_images.open('rb') as src, gzip.open(packed_images, 'wb', compresslevel=1) as dst:
            shutil.copyfileobj(src, dst)
        assert raw_images.is_relative_to(out) and raw_images.name == 'docker-images.tar'
        raw_images.unlink()  # only this successful capture's generated intermediate
        atomic_json(private / 'docker-images.json', image_records)
    atomic_json(private / 'sqlite-map.json', sqlite_map)
    atomic_json(private / 'capture-notes.json', {'missing_roots': missing, 'excluded_entries': excluded,
                'symlinks_to_recreate': links, 'projects_included': include_projects,
                'consistency': 'SQLite snapshots consistent; other live files best effort. Reconcile every in-flight job after recovery.'})
    files = {str(p.relative_to(out)): digest(p) for p in out.rglob('*') if p.is_file()}
    atomic_json(out / 'manifest.json', {'schema_version': 1, 'created': dt.datetime.now(dt.timezone.utc).isoformat(),
                'files': files, 'projects_included': include_projects,
                'scope': 'private environment capture; not a whole-server or off-host restore qualification'})
    return {'result': 'CAPTURED_NOT_OFFHOST_VERIFIED', 'backup': str(out), 'files': len(files),
            'missing_roots': missing, 'projects_included': include_projects}




def restore_bundle(backup, target):
    root, target = Path(backup).resolve(), Path(target).resolve()
    verify_backup(root)
    if target.exists() or target == root or target.is_relative_to(root):
        raise ValueError('Bundle restore requires a NEW isolated target directory outside the backup')
    archive_path = root / 'private-state.tar.gz'
    if not archive_path.is_file():
        raise ValueError('This is not a full environment bundle; use restore-test for the legacy app backup')
    target.mkdir(mode=0o700, parents=True)
    with tarfile.open(archive_path, 'r:gz') as archive:
        for member in archive:
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError('Unexpected link or special file in environment bundle')
            archive.extract(member, target, filter='data')
    for record in json.loads((root / 'private/sqlite-map.json').read_text()):
        original = Path(record['original'])
        relative = Path(str(original).lstrip('/'))
        snapshot = root / record['snapshot']
        if not original.is_absolute() or '..' in relative.parts or not snapshot.resolve().is_relative_to(root):
            raise ValueError('Unsafe SQLite restore map')
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(snapshot, 'rb') as src, dest.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        with closing(sqlite3.connect('file:' + str(dest) + '?mode=ro', uri=True)) as db:
            if db.execute('pragma integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Restored bundle database integrity failed')
    metadata = target / '_recovery'
    metadata.mkdir(mode=0o700)
    for name in ['environment.json', 'private/secrets.json', 'private/configmaps.json', 'private/capture-notes.json']:
        source = root / name
        if source.exists():
            shutil.copyfile(source, metadata / source.name)
    return {'result': 'RESTORED_ISOLATED_NOT_ACTIVATED', 'target': str(target),
            'limits': ['No file was copied onto the live root; no workload was started.',
                       'Recreate reviewed symlinks and ownership/SELinux labels through existing owners.',
                       'Non-SQLite service databases still require an application-consistent restore drill.']}


def run_phase(policy, source_inventory, evidence_path, phase_id, vars_file, output):
    inv = json.loads(Path(source_inventory).read_text())
    current = hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest()
    if current == inv['source_machine_id_sha256']:
        raise ValueError('Recovery apply is refused on the inventoried production machine; use an isolated replacement host')
    report = coverage(inv, policy, json.loads(Path(evidence_path).read_text()))
    if report['blockers']:
        raise ValueError('Recovery prerequisites are incomplete; run audit and resolve every blocker first')
    phase = next((x for x in policy['stages'] if x['id'] == phase_id), None)
    if not phase or not phase.get('playbooks'):
        raise ValueError('This is a manual restore/bootstrap prerequisite, not an executable Ansible phase')
    if not vars_file or not Path(vars_file).is_file():
        raise ValueError('A reviewed private recovery vars file is required; no gate booleans are fabricated')
    out = Path(output).resolve()
    if out.exists():
        raise ValueError('Phase evidence directory must be new')
    for path in ['/app', '/data']:
        if not os.path.ismount(path):
            raise ValueError('Required storage is not mounted: ' + path)
    for unit in ['k3s', 'docker']:
        command(['systemctl', 'is-active', unit])
    os.umask(0o077); out.mkdir(mode=0o700, parents=True)
    results = []
    for name in phase['playbooks']:
        # An entry is 'file.yml' or 'file.yml:tag1,tag2' (tagged parts of a combined playbook).
        file_name, _, tags = name.partition(':')
        playbook = PROJECT / 'ansible/playbooks' / file_name
        if not playbook.is_file():
            raise ValueError('Owning playbook missing: ' + file_name)
        args = [str(PROJECT / 'ansible-run'), 'playbooks/' + file_name, '-e', '@' + str(Path(vars_file).resolve())]
        if tags:
            args += ['--tags', tags]
        with (out / (name.replace(':', '--').replace(',', '_') + '.log')).open('w') as log:
            env = dict(os.environ, ROOT=str(PROJECT))
            result = subprocess.run(args, cwd=PROJECT, env=env, stdout=log, stderr=subprocess.STDOUT)
        results.append({'playbook': name, 'exit': result.returncode})
        atomic_json(out / 'phase.json', {'phase': phase_id, 'results': results, 'scope': 'Ansible execution only, runtime acceptance still required'})
        if result.returncode:
            raise ValueError('Recovery phase stopped; inspect its private log and reconcile before retrying')
    return {'result': 'RECONCILED_NOT_ACCEPTED', 'phase': phase_id, 'evidence': str(out)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, default=POLICY)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('inventory'); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('plan'); p.add_argument('--inventory', required=True, type=Path)
    p = sub.add_parser('audit'); p.add_argument('--inventory', required=True, type=Path); p.add_argument('--evidence', type=Path)
    p = sub.add_parser('verify-backup'); p.add_argument('--backup', required=True, type=Path)
    p = sub.add_parser('restore-test'); p.add_argument('--backup', required=True, type=Path); p.add_argument('--target', required=True, type=Path)
    p = sub.add_parser('restore-bundle'); p.add_argument('--backup', required=True, type=Path); p.add_argument('--target', required=True, type=Path)
    p = sub.add_parser('run-phase'); p.add_argument('--inventory', required=True, type=Path); p.add_argument('--evidence', required=True, type=Path); p.add_argument('--phase', required=True); p.add_argument('--vars-file', required=True, type=Path); p.add_argument('--output', required=True, type=Path)
    p = sub.add_parser('capture'); p.add_argument('--output', required=True, type=Path); p.add_argument('--scope', choices=['environment-projects', 'environment-only'], default='environment-projects')
    args = parser.parse_args(); policy = json.loads(args.policy.read_text())
    if args.action == 'inventory':
        value = inventory(policy); atomic_json(args.output, value)
        print(json.dumps({'result': 'INVENTORIED', 'output': str(args.output), 'workloads': len(value['workloads']), 'storage_paths': len(value['storage'])}))
    elif args.action == 'plan':
        inv = json.loads(args.inventory.read_text()); print(json.dumps({'stages': policy['stages'], 'coverage': coverage(inv, policy)}, indent=2))
    elif args.action == 'audit':
        value = coverage(json.loads(args.inventory.read_text()), policy, json.loads(args.evidence.read_text()) if args.evidence else None)
        print(json.dumps(value, indent=2)); return 2 if value['blockers'] else 0
    elif args.action == 'restore-bundle':
        print(json.dumps(restore_bundle(args.backup, args.target)))
    elif args.action == 'run-phase':
        print(json.dumps(run_phase(policy, args.inventory, args.evidence, args.phase, args.vars_file, args.output)))
    elif args.action == 'verify-backup':
        value = verify_backup(args.backup); print(json.dumps({'result': 'PASS', 'files': len(value['files'])}))
    elif args.action == 'restore-test':
        print(json.dumps(restore_test(args.backup, args.target)))
    else:
        print(json.dumps(capture(policy, args.output, args.scope == 'environment-projects')))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, tarfile.TarError, sqlite3.Error) as error:
        # Do not print command stderr, private configuration or response bodies.
        raise SystemExit('FAIL recovery check: ' + str(error))
