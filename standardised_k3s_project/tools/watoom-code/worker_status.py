#!/usr/bin/env python3
"""Worker status snapshot for the command center (Bazzite worker, RIG worker, server worker).

Runs as root on the homelab every ~30 s (systemd timer) and writes ONE small sanitised JSON file that the helper-api container mounts read-only:
what each worker is doing right now, and the outcome of recent jobs. Nothing here starts, stops or changes a job; every source is read-only.

Sources
  game-worker receipts  /data/ai/private/game-worker/<request>.json  (root-only: status, operation, job, project, short failure reason) + the evidence
                        report /data/ai/helper-scripts/reports/game-worker/<evidence>/prepared.json (which worker ran it, unit, limits)
  RIG Unreal lane       jail inputs/ue-job-<job>.json (a submitted job) and uploads/ue-<job>/result.json (its outcome)
  Bazzite, live         one SSH call over the existing worker access (bazzite.py): reachable?, free RAM, running watoom-* units and their start times
  RIG, live             the last SFTP login of the rig's transfer account in the SSH journal (the lane polls every ~15 s, so contact means it is up).
                        The rig reports its phase (FETCHING/RUNNING/UPLOADING) via progress.json; a job with no phase yet is "queued or running".
Free text from receipts is clipped; no paths beyond the project folder name, no manifests, no credentials are written.
RUNNING jobs are labelled STALE_RUNNING in this display after prepared.json's deadline_seconds (default 1800) plus
180 seconds if prepared.json is missing or its declared unit is not active. This never changes receipt status or retries work.
The snapshot also reports collector source health, Bazzite/RIG contact history and atomically writes node-exporter textfile metrics.
Optional RIG uploads/progress.json reports FETCHING, RUNNING or UPLOADING; absence remains compatible with old workers.
"""
import datetime
import argparse, json, math, os, pathlib, re, shutil, subprocess, sys, time

RECEIPTS = pathlib.Path('/data/ai/private/game-worker')
REPORTS = pathlib.Path('/data/ai/helper-scripts/reports/game-worker')
LANE_RESULTS = pathlib.Path('/data/ai/artifacts/rig-lane')
JAIL = pathlib.Path('/var/lib/watoom-workstation-transfer/payloads')
OUT = pathlib.Path('/data/ai/helper-scripts/state/worker-status/workers.json')
MEDIA_SUBDIR = 'media'
# Output files are only read from these places (resolved, no symlinks); everything shown is a re-encoded copy.
ALLOWED_ROOTS = (pathlib.Path('/data/ai/projects'), pathlib.Path('/data/ai/helper-scripts/reports/game-worker'), pathlib.Path('/data/ai/artifacts'),
                 pathlib.Path('/data/ai/assets/generated/opencode-mesh'))
IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
VIDEO_EXT = {'.mp4', '.webm'}
MAX_MEDIA_PER_JOB = 8
MEDIA_JOBS = 30            # only the newest jobs get media; older media folders are pruned
THUMB_PX, VIEW_PX = 360, 1600
MAX_SOURCE_BYTES = 80 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024
MODEL_EXT = {'.glb'}                 # self-contained glTF only: the viewer cannot follow external files
MAX_MODELS_PER_JOB = 3
MAX_MODEL_BYTES = 40 * 1024 * 1024
RIG_HOST = '10.99.1.44'
RIG_ACCOUNT = 'watoom-render-transfer'
BAZZITE_BACKOFF = 120
RECENT = 40
REASON_MAX = 220
STALE_GRACE_SECONDS = 1800  # staging a large project over Wi-Fi can take far longer than the Godot/Blender deadline
DEFAULT_DEADLINE_SECONDS = 1800
MOSS_OUTPUTS = pathlib.Path('/data/ai/projects/images/moss-image/output')
MESH_JOBS = pathlib.Path('/data/ai/llama-mesh/jobs')  # LLaMA-Mesh generation jobs, shown as the 'meshy' worker

STATE_FOR_STATUS = {'RUNNING': 'running', 'COMPLETED': 'completed', 'FAILED': 'failed', 'STALE_RESULT': 'stale',
                    'STALE_REQUEST': 'stale', 'RECONCILIATION_REQUIRED': 'needs_review'}
UNIT_LABELS = (('watoom-godot-import', 'godot import'), ('watoom-godot-capture', 'godot capture'), ('watoom-godot', 'godot'),
               ('watoom-blender', 'blender'), ('watoom-ue-export', 'unreal export'), ('watoom-unreal', 'unreal'),
               ('watoom-asset-capture', 'asset capture'), ('watoom-capture', 'capture'))


def clip(text, n=REASON_MAX):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text if len(text) <= n else text[:n - 1] + '…'


def friendly(text):
    """Turn a raw subprocess error repr ("Command '[...long argv...]' returned non-zero exit status 255.") into something readable."""
    text = str(text or '')
    if text.startswith("Command '["):
        m = re.search(r'(returned non-zero exit status \d+|timed out after [\d.]+ seconds)', text)
        return 'worker command ' + m.group(1) if m else 'worker command failed'
    return text


def project_name(path):
    return pathlib.PurePosixPath(str(path or '')).name or None


def read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return None


def mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def numeric_time(value, fallback=None):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else fallback


def classify_stale_running(started, now, deadline_seconds, evidence_missing, unit_running, grace=STALE_GRACE_SECONDS):
    """Display-only stale rule: deadline + grace and absent evidence or inactive unit."""
    try:
        deadline = float(deadline_seconds)
    except (TypeError, ValueError):
        deadline = DEFAULT_DEADLINE_SECONDS
    if started is None or deadline < 0:
        return False
    try:
        age = now - float(started)
    except (TypeError, ValueError):
        return False
    return bool(evidence_missing or not unit_running) and age > deadline + grace


def receipt_jobs(receipts=RECEIPTS, reports=REPORTS, limit=RECENT, now=None, active_units=None, unit_status_known=True):
    """Recent game-worker jobs, newest first, in the dashboard's common shape."""
    now = time.time() if now is None else now
    active_units = {str(u).removesuffix('.service') for u in (active_units or ())}
    files = []
    for p in pathlib.Path(receipts).glob('*.json'):
        m = mtime(p)
        if m is not None:
            files.append((m, p))
    jobs = []
    for finished, path in sorted(files, reverse=True)[:limit]:
        doc = read_json(path)
        if not isinstance(doc, dict):
            continue
        status = str(doc.get('status') or '')
        prepared = read_json(pathlib.Path(reports) / str(doc.get('evidence_id') or '-') / 'prepared.json') or {}
        worker = doc.get('worker') or prepared.get('worker') or 'server'
        result = doc.get('worker_result') or {}
        started = mtime(pathlib.Path(reports) / str(doc.get('evidence_id') or '-') / 'prepared.json')
        state = STATE_FOR_STATUS.get(status, 'unknown')
        if state == 'running' and not started:
            started = finished   # still staging: the receipt was written when the job was requested, and prepared.json does not exist yet
        unit = prepared.get('unit')
        prepared_file = pathlib.Path(reports) / str(doc.get('evidence_id') or '-') / 'prepared.json'
        unit_running = (str(unit).removesuffix('.service') in active_units) if unit and worker == 'bazzite' and unit_status_known else True
        if state == 'running' and classify_stale_running(started, now, prepared.get('deadline_seconds'),
                                                         not prepared_file.is_file(), unit_running):
            state = 'stale_running'
        reason = None
        if state == 'failed':
            reason = result.get('failure_reason') or doc.get('reason')
        elif state == 'stale_running':
            reason = 'exceeded deadline plus %ds grace with missing evidence or inactive unit' % STALE_GRACE_SECONDS
        elif state in ('stale', 'needs_review'):
            reason = doc.get('reason') or ('result no longer matches the current project files' if status == 'STALE_RESULT' else None)
        elif state == 'completed':
            reason = result.get('summary')
        is_running = state in ('running', 'stale_running')
        jobs.append({
            'id': str(doc.get('request_id') or path.stem)[:12], 'worker': worker, 'operation': doc.get('operation'), 'name': doc.get('job'),
            'project': project_name(doc.get('project')), 'state': state,
            'detail': clip(friendly(reason)) or None, 'unit': unit,
            'started': started if is_running or started else None,
            'finished': None if is_running else finished,
            'seconds': round(finished - started) if not is_running and started and finished >= started else None,
            'memory_limit': prepared.get('memory_limit') or result.get('memory_limit'),
            'deadline_seconds': prepared.get('deadline_seconds') or DEFAULT_DEADLINE_SECONDS,
            'failure_stage': result.get('failure_stage') or doc.get('failure_stage'),
            'failure_code': result.get('failure_code') or doc.get('failure_code'),
            '_key': str(doc.get('request_id') or path.stem)[:12], '_receipt': doc.get('receipt'), '_project': doc.get('project'),
        })
    return jobs


def lane_outcome(doc, fallback, stamp):
    status = str(doc.get('status') or '')
    job = str(doc.get('job') or fallback)
    state = 'completed' if status == 'PASS' else ('needs_review' if status == 'RECONCILIATION_REQUIRED' else 'failed')
    files = doc.get('files') or []
    detail = doc.get('error') or doc.get('reason') or ('%s; %d files' % (status, len(files)) if files else status)
    finished = numeric_time(doc.get('finished'), stamp)
    return {'id': job[-12:], 'worker': 'rig', 'operation': doc.get('op'), 'name': job, 'project': None, 'state': state, 'detail': clip(detail),
            'failure_stage': doc.get('failure_stage'), 'failure_code': doc.get('failure_code'), 'unit': None,
            'started': None, 'finished': finished, 'seconds': None, 'memory_limit': None, 'deadline_seconds': None, '_key': job, '_lane_job': job}


def lane_jobs(results=LANE_RESULTS, jail=JAIL, limit=RECENT):
    """RIG Unreal lane jobs: submitted-without-result (queued or running) and recent outcomes (from the jail, then collected artifacts)."""
    jobs = {}
    inputs = pathlib.Path(jail) / 'inputs'
    for manifest in inputs.glob('ue-job-*.json'):
        doc = read_json(manifest) or {}
        job = str(doc.get('job') or manifest.name[len('ue-job-'):-len('.json')])
        result_file = pathlib.Path(jail) / 'uploads' / ('ue-' + job) / 'result.json'
        result = read_json(result_file)
        progress = read_json(result_file.parent / 'progress.json') or {}
        phase = progress.get('phase') if progress.get('phase') in ('FETCHING', 'RUNNING', 'UPLOADING') else None
        phase_at = progress.get('timestamp') if isinstance(progress.get('timestamp'), (int, float)) else None
        created = numeric_time(doc.get('created'), mtime(manifest))
        if result is None:
            detail = 'submitted; the rig has not uploaded a result yet'
            if phase:
                detail = 'rig phase: ' + phase.lower()
            jobs[job] = {'id': job[-12:], 'worker': 'rig', 'operation': doc.get('op'), 'name': job, 'project': (doc.get('params') or {}).get('name'),
                         'state': 'queued_or_running', 'detail': detail, 'phase': phase, 'phase_at': phase_at, 'unit': None,
                         'started': created, 'finished': None, 'seconds': None, 'memory_limit': None, 'deadline_seconds': None, '_key': job, '_lane_job': job}
        elif isinstance(result, dict):
            record = lane_outcome(result, job, mtime(result_file))
            record['project'] = (doc.get('params') or {}).get('name')
            record['started'] = created
            if record['finished'] and created and record['finished'] >= created:
                record['seconds'] = round(record['finished'] - created)
            jobs[job] = record
    for result_file in pathlib.Path(results).glob('*/result.json'):
        doc = read_json(result_file)
        if not isinstance(doc, dict):
            continue
        job = str(doc.get('job') or result_file.parent.name)
        if job not in jobs:
            jobs[job] = lane_outcome(doc, result_file.parent.name, mtime(result_file))
    ordered = sorted(jobs.values(), key=lambda j: (j['finished'] or j['started'] or 0), reverse=True)
    return ordered[:limit]


def moss_jobs(output=MOSS_OUTPUTS, limit=RECENT):
    """Completed MOSS Studio jobs from its JSON sidecars and matching generated PNGs."""
    jobs = []
    output = pathlib.Path(output)
    for record in output.glob('*.json'):
        if not re.fullmatch(r'[a-f0-9]{32}', record.stem):
            continue
        doc = read_json(record)
        if not isinstance(doc, dict) or doc.get('hidden') is True:
            continue  # hidden from the MOSS Recent list by the operator
        image = output / (record.stem + '.png')
        if not image.is_file() or image.is_symlink():
            continue
        created = numeric_time(doc.get('created'), mtime(record))
        finished = mtime(image)
        jobs.append({'id': record.stem[-12:], 'worker': 'moss', 'operation': 'image generation',
                     'name': record.stem, 'project': 'MOSS Image', 'state': 'completed',
                     'detail': None, 'unit': None, 'started': created, 'finished': finished,
                     'seconds': round(finished - created) if created and finished and finished >= created else None,
                     'memory_limit': None, 'deadline_seconds': None, '_key': 'moss-' + record.stem,
                     '_moss_image': str(image)})
    return sorted(jobs, key=lambda j: j['finished'] or j['started'] or 0, reverse=True)[:limit]


def iso_epoch(value):
    try:
        return datetime.datetime.fromisoformat(value).timestamp() if isinstance(value, str) else None
    except ValueError:
        return None


def mesh_jobs(root=MESH_JOBS, limit=RECENT):
    """LLaMA-Mesh generation jobs (complete/running/failed) with their game-ready GLB; prompts and errors are never copied."""
    states = {'complete': 'completed', 'running': 'running', 'failed': 'failed'}
    jobs = []
    for folder, state in states.items():
        for job in pathlib.Path(root, folder).glob('*'):
            if not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{8}', job.name) or job.is_symlink():
                continue
            status, request = read_json(job / 'status.json'), read_json(job / 'request.json')
            if not isinstance(status, dict) or not isinstance(request, dict):
                continue
            started = iso_epoch(request.get('created_at')) or mtime(job)
            finished = iso_epoch(status.get('finished_at')) if state != 'running' else None
            name = request.get('name') if isinstance(request.get('name'), str) else job.name
            glb = None
            out = status.get('output_dir')
            if state == 'completed' and isinstance(out, str):
                glb = pathlib.Path(out) / 'game-ready' / 'asset.glb'
            jobs.append({'id': job.name[-8:], 'worker': 'meshy', 'operation': 'mesh generation', 'name': name[:80],
                         'project': 'LLaMA-Mesh', 'state': state, 'detail': None, 'unit': None, 'started': started,
                         'finished': finished, 'seconds': round(finished - started) if started and finished and finished >= started else None,
                         'memory_limit': None, 'deadline_seconds': None, '_key': 'meshy-' + job.name, '_mesh_glb': str(glb) if glb else None})
    return sorted(jobs, key=lambda j: j['finished'] or j['started'] or 0, reverse=True)[:limit]


def rig_contact(run=subprocess.run, now=None, diagnostic=None):
    """Epoch of the rig's most recent SFTP login in the last seven days; report journal command failures separately."""
    try:
        r = run(['journalctl', '-u', 'sshd', '--since', '-7 days', '--no-pager', '-o', 'short-unix', '-g',
                 'Accepted publickey for %s from %s' % (RIG_ACCOUNT, RIG_HOST), '-n', '1'], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        if diagnostic is not None: diagnostic['error'] = 'journalctl command failed'
        return None
    if r.returncode:
        if diagnostic is not None: diagnostic['error'] = 'journalctl returned exit status %s' % r.returncode
        return None
    for line in reversed((r.stdout or '').splitlines()):
        m = re.match(r'^(\d+)\.\d+\s', line)
        if m:
            return float(m.group(1))
    return None


PROBE = ("echo UP; awk '/MemAvailable/{print $2*1024}' /proc/meminfo; "
         "for u in $(systemctl --user list-units 'watoom-*' --state=running --no-legend --plain 2>/dev/null | awk '{print $1}'); do "
         "echo \"UNIT $u $(date -d \"$(systemctl --user show -p ActiveEnterTimestamp --value $u)\" +%s 2>/dev/null)\"; done")


def unit_label(unit):
    for prefix, label in UNIT_LABELS:
        if unit.startswith(prefix):
            return label
    return unit.split('.')[0]


def bazzite_state(sh, previous, now):
    """One SSH round trip; backs off after a failure so an offline worker is not hammered."""
    last = previous or {}
    if last.get('reachable') is False and now - (last.get('checked') or 0) < BAZZITE_BACKOFF:
        return dict(last)
    try:
        r = sh(PROBE, timeout=40)
        if r.returncode == 255 or 'UP' not in (r.stdout or '').split():
            err = ([l for l in (r.stderr or '').strip().splitlines() if l.strip()] or ['no answer'])[-1]
            failed = {'reachable': False, 'checked': now, 'error': clip(err, 160), 'units': [], 'failure_code': 'unreachable' if r.returncode == 255 else 'worker_error'}
        else:
            lines = r.stdout.splitlines()
            mem = next((int(l) for l in lines if l.strip().isdigit()), None)
            units = []
            for line in lines:
                m = re.match(r'^UNIT (\S+) (\d+)?', line)
                if m:
                    units.append({'unit': m.group(1), 'label': unit_label(m.group(1)), 'started': float(m.group(2)) if m.group(2) else None})
            return {'reachable': True, 'checked': now, 'last_ok': now, 'consecutive_failures': 0, 'first_failure': None,
                    'failure_code': None, 'free_ram_bytes': mem, 'units': units}
    except Exception as exc:  # noqa: BLE001 - any failure means "could not ask"
        failed = {'reachable': False, 'checked': now, 'error': clip(exc, 160), 'units': [], 'failure_code': 'unreachable'}
    failed['last_ok'] = last.get('last_ok')
    failed['consecutive_failures'] = int(last.get('consecutive_failures') or 0) + 1
    failed['first_failure'] = last.get('first_failure') or now
    return failed



def rig_note(waiting):
    """Only explain the gap when a rig job has not reported a phase yet (not picked up, or a lane installed before phase progress existed)."""
    silent = [j for j in waiting if not j.get('phase')]
    if not silent:
        return ''
    return 'No phase reported yet for %d job%s: the rig has not picked %s up, or its lane predates phase progress (reinstall the lane bundle).' % (
        len(silent), '' if len(silent) == 1 else 's', 'it' if len(silent) == 1 else 'them')

def build(now, previous=None, receipts=RECEIPTS, reports=REPORTS, lane_results=LANE_RESULTS, jail=JAIL, sh=None, journal=rig_contact, media_root=None, roots=None, moss_output=MOSS_OUTPUTS, mesh_root=MESH_JOBS):
    prev = previous or {}
    if sh:
        bz = bazzite_state(sh, (prev.get('bazzite') or {}), now)
    else:
        bz = dict(prev.get('bazzite') or {})
        bz.setdefault('reachable', None); bz.setdefault('units', []); bz.setdefault('checked', now)
        bz['error'] = 'not probed'
    source_info = {}
    def source(name, fn, fallback):
        try:
            value = fn()
            source_info[name] = {'ok': True, 'count': len(value) if hasattr(value, '__len__') else int(value is not None), 'error': None}
            return value
        except Exception as exc:
            source_info[name] = {'ok': False, 'count': 0, 'error': clip(exc, 180)}
            return fallback
    games = source('receipts', lambda: receipt_jobs(receipts, reports, limit=100000, now=now,
        active_units=[u['unit'].removesuffix('.service') for u in bz.get('units', [])], unit_status_known=bz.get('reachable') is True), [])
    lane = source('lane_results', lambda: lane_jobs(lane_results, jail, limit=100000), [])
    moss = source('moss_outputs', lambda: moss_jobs(moss_output, limit=100000), [])
    mesh = source('mesh_jobs', lambda: mesh_jobs(mesh_root, limit=100000), [])
    jail_inputs = source('jail', lambda: list((pathlib.Path(jail) / 'inputs').glob('ue-job-*.json')), [])
    journal_error = {}
    def get_contact():
        try:
            return journal(now=now, diagnostic=journal_error) if journal is rig_contact else journal(now=now)
        except Exception as exc:
            journal_error['error'] = clip(exc, 180)
            raise
    contact = source('journal', get_contact, None)
    if journal_error.get('error'):
        source_info['journal'] = {'ok': False, 'count': 0, 'error': journal_error['error']}
    elif 'journal' in source_info:
        source_info['journal']['count'] = int(contact is not None)
    source_info['bazzite_probe'] = {'ok': bz.get('reachable') is True,
                                    'count': len(bz.get('units', [])), 'error': bz.get('error') or ('not probed' if sh is None else None)}
    for key, directory, pattern in (('receipts', receipts, '*.json'), ('lane_results', lane_results, '*/result.json'), ('jail', jail, '**/*.json')):
        try:
            count, error = scan_json_health(directory, pattern)
            source_info[key] = {'ok': error is None, 'count': count, 'error': error}
        except Exception as exc:
            source_info[key] = {'ok': False, 'count': 0, 'error': clip(exc, 180)}
    # attach running units to the receipt that owns them
    for unit in bz.get('units', []):
        active_name = str(unit['unit']).removesuffix('.service')
        owner = next((j for j in games if j['unit'] and str(j['unit']).removesuffix('.service') == active_name), None)
        if owner:
            unit['name'], unit['operation'], unit['project'] = owner['name'], owner['operation'], owner['project']
            unit['memory_limit'], unit['deadline_seconds'] = owner['memory_limit'], owner['deadline_seconds']
    running_bz = [j for j in games if j['worker'] == 'bazzite' and j['state'] == 'running']
    rig_waiting = [j for j in lane if j['state'] == 'queued_or_running'] + [j for j in games if j['worker'] == 'rig' and j['state'] == 'running']
    rig_online = contact is not None and now - contact < 180
    bz_failures = int(bz.get('consecutive_failures') or 0)
    bz_health = 'ok' if bz.get('reachable') is True else ('down' if bz_failures >= 3 else 'degraded' if bz_failures else 'unknown')
    bazzite = {'reachable': bz.get('reachable'), 'checked': bz.get('checked'), 'error': bz.get('error'), 'free_ram_bytes': bz.get('free_ram_bytes'),
               'last_ok': bz.get('last_ok'), 'consecutive_failures': bz_failures, 'first_failure': bz.get('first_failure'),
               'failure_code': bz.get('failure_code'), 'health': bz_health,
               'busy': bool(bz.get('units')) or bool(running_bz), 'units': bz.get('units', []), 'running_jobs': running_bz}
    quiet = max(0, round(now - contact)) if contact is not None else None
    rig_health = 'ok' if quiet is not None and quiet < 180 else ('degraded' if quiet is not None and quiet < 600 else 'down')
    rig = {'online': rig_online, 'last_contact': contact, 'quiet_for_seconds': quiet, 'health': rig_health,
           'busy': bool(rig_waiting), 'waiting_or_running': rig_waiting,
           'note': rig_note(rig_waiting)}
    metric_jobs = games + lane + moss + mesh
    jobs = sorted(metric_jobs, key=lambda j: (j['finished'] or j['started'] or 0), reverse=True)[:RECENT * 2]
    attach_outputs(jobs, media_root or (OUT.parent / MEDIA_SUBDIR), lane_results, jail, roots)
    for j in games + lane + moss + mesh:
        for k in [k for k in j if k.startswith('_')]:
            del j[k]
    return {'schema': 1, 'generated': now, 'bazzite': bazzite, 'rig': rig, 'jobs': jobs,
            'collector': {'version': '3', 'duration_ms': 0, 'sources': source_info}, '_metric_jobs': metric_jobs}


# ---- produced outputs (images, captures) -----------------------------------------------------------------------------------
def safe_source(path, roots=None):
    """A regular file inside an allowed root, reached without symlinks; None otherwise."""
    try:
        p = pathlib.Path(path)
        if not p.is_absolute() or p.is_symlink():
            return None
        resolved = p.resolve(strict=True)
        if str(resolved) != str(p) and any(part.is_symlink() for part in p.parents if str(part) not in ('/', '')):
            return None
        if not any(resolved.is_relative_to(r) for r in (roots or ALLOWED_ROOTS)) or not resolved.is_file():
            return None
        return resolved
    except (OSError, ValueError, RuntimeError):
        return None


def game_outputs(job, roots=None):
    """(media sources, other outputs) a game-worker receipt points to: its captured images and the files its script produced."""
    sources, other = [], []
    receipt_path = job.get('_receipt')
    doc = read_json(receipt_path) if receipt_path and str(receipt_path).endswith('.json') else None
    if not isinstance(doc, dict):
        return sources, other
    for image in doc.get('images') or []:
        src = safe_source((image or {}).get('path'), roots) if isinstance(image, dict) else None
        if src and src.suffix.lower() in IMAGE_EXT | VIDEO_EXT | MODEL_EXT:
            sources.append(src)
    project = job.get('_project')
    for out in doc.get('outputs') or []:
        if not isinstance(out, dict) or not out.get('file') or not project:
            continue
        src = safe_source(pathlib.Path(project) / str(out['file']), roots)
        if not src:
            continue
        if src.suffix.lower() in IMAGE_EXT | VIDEO_EXT | MODEL_EXT:
            sources.append(src)
        else:
            other.append({'kind': 'file', 'name': src.name, 'bytes': src.stat().st_size})
    return sources, other


def lane_outputs(job, results=LANE_RESULTS, jail=JAIL, roots=None):
    sources, other = [], []
    name = job.get('_lane_job')
    for base in (pathlib.Path(results) / str(name), pathlib.Path(jail) / 'uploads' / ('ue-' + str(name))):
        if not base.is_dir():
            continue
        for f in sorted(base.iterdir()):
            src = safe_source(f, roots)
            if not src:
                continue
            if src.suffix.lower() in IMAGE_EXT | MODEL_EXT:
                sources.append(src)
            elif src.suffix.lower() in ('.fbx', '.dna', '.zip') or src.name == 'result.json':
                if src.name != 'result.json':
                    other.append({'kind': 'file', 'name': src.name, 'bytes': src.stat().st_size})
        if sources or other:
            break
    return sources[:MAX_MEDIA_PER_JOB * 4 + MAX_MODELS_PER_JOB], other[:12]


def _encode(src, dest, px, quality):
    from PIL import Image  # imported late: the collector still works (without thumbnails) where Pillow is missing
    Image.MAX_IMAGE_PIXELS = 150_000_000
    with Image.open(src) as im:
        im.load()
        w, h = im.size
        if im.mode in ('RGBA', 'LA', 'P'):
            base = Image.new('RGB', im.size, (26, 26, 25))
            rgba = im.convert('RGBA')
            base.paste(rgba, mask=rgba.split()[3])
            im = base
        else:
            im = im.convert('RGB')
        im.thumbnail((px, px))
        im.save(dest, 'JPEG', quality=quality, optimize=True)
    return w, h


def make_media(key, sources, media_root):
    """Re-encode up to MAX_MEDIA_PER_JOB images (thumbnail + viewable size), copy up to MAX_MODELS_PER_JOB GLB models, into <media_root>/<key>/; reuse what is there."""
    d = pathlib.Path(media_root) / key
    index = read_json(d / 'index.json') or {}
    models = [x for x in sources if x.suffix.lower() in MODEL_EXT][:MAX_MODELS_PER_JOB]
    media = [x for x in sources if x.suffix.lower() not in MODEL_EXT][:MAX_MEDIA_PER_JOB]
    out, new_index = [], {}
    for tag, items in (('i', media), ('g', models)):
        for n, src in enumerate(items):
            slot = '%s%d' % (tag, n)
            try:
                st = src.stat()
            except OSError:
                continue
            sig = [str(src), st.st_size, int(st.st_mtime)]
            prev = index.get(slot)
            cached = (prev or {}).get('public', {})
            if prev and prev.get('sig') == sig and (pathlib.Path(media_root) / (cached.get('view') or cached.get('video') or cached.get('model') or '-')).is_file():
                new_index[slot] = prev
                out.append(cached)
                continue
            if st.st_size > MAX_SOURCE_BYTES:
                continue
            entry = {'kind': 'image', 'name': src.name, 'bytes': st.st_size}
            try:
                if tag == 'g':
                    if st.st_size > MAX_MODEL_BYTES:
                        continue
                    d.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, d / ('g%d.glb' % n))
                    os.chmod(d / ('g%d.glb' % n), 0o644)
                    entry.update(kind='model', model='%s/g%d.glb' % (key, n))
                elif src.suffix.lower() in VIDEO_EXT:
                    if st.st_size > MAX_VIDEO_BYTES:
                        continue
                    d.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, d / ('m%d%s' % (n, src.suffix.lower())))
                    os.chmod(d / ('m%d%s' % (n, src.suffix.lower())), 0o644)
                    entry.update(kind='video', video='%s/m%d%s' % (key, n, src.suffix.lower()))
                else:
                    d.mkdir(parents=True, exist_ok=True)
                    w, h = _encode(src, d / ('t%d.jpg' % n), THUMB_PX, 78)
                    _encode(src, d / ('v%d.jpg' % n), VIEW_PX, 85)
                    for suffix in ('t%d.jpg' % n, 'v%d.jpg' % n):
                        os.chmod(d / suffix, 0o644)
                    entry.update(thumb='%s/t%d.jpg' % (key, n), view='%s/v%d.jpg' % (key, n), width=w, height=h)
            except Exception:  # noqa: BLE001 - an unreadable file must not break the snapshot
                continue
            new_index[slot] = {'sig': sig, 'public': entry}
            out.append(entry)
    if d.is_dir():
        d.chmod(0o755)
        (d / 'index.json').write_text(json.dumps(new_index), encoding='utf-8')
    return out


def attach_outputs(jobs, media_root, results=LANE_RESULTS, jail=JAIL, roots=None, limit=MEDIA_JOBS):
    """Give each of the newest jobs an `outputs` list; prune media folders of jobs that dropped out of the window."""
    keep = set()
    for job in jobs[:limit]:
        key = re.sub(r'[^A-Za-z0-9._-]', '_', str(job.get('_key') or job.get('id') or ''))[:60]
        if not key or job.get('state') in ('running', 'stale_running', 'queued_or_running'):
            job['outputs'] = []
            continue
        sources, other = game_outputs(job, roots) if job.get('_receipt') or job.get('_project') else ([], [])
        if job.get('_lane_job'):
            sources, other = lane_outputs(job, results, jail, roots)
        elif job.get('_mesh_glb'):
            src = safe_source(job['_mesh_glb'], roots)
            sources = [src] if src and src.suffix.lower() in MODEL_EXT else []
        elif job.get('_moss_image'):
            src = safe_source(job['_moss_image'], roots)
            sources = [src] if src and src.suffix.lower() in IMAGE_EXT else []
        keep.add(key)
        job['outputs'] = make_media(key, sources, media_root) + other
    for job in jobs[limit:]:
        job['outputs'] = []
    root = pathlib.Path(media_root)
    if root.is_dir():
        for d in root.iterdir():
            if d.is_dir() and d.name not in keep:
                shutil.rmtree(d, ignore_errors=True)
    for job in jobs:
        for k in [k for k in job if k.startswith('_')]:
            del job[k]
    return jobs


def write_atomic(path, doc):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.tmp')
    tmp.write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def render_metrics(doc, now=None, jobs=None):
    """Prometheus textfile metrics from this snapshot and the collector's complete recent job set."""
    now = doc.get('generated', time.time()) if now is None else now
    cutoff = now - 86400
    jobs = doc.get('jobs', []) if jobs is None else jobs
    lines = []
    def metric(name, value, labels=None):
        label_text = '' if not labels else '{' + ','.join('%s="%s"' % (k, str(v).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')) for k, v in labels.items()) + '}'
        lines.append('%s%s %s' % (name, label_text, value))
    states = {}
    oldest = {}
    for job in jobs:
        stamp = job.get('finished') or job.get('started') or 0
        worker = job.get('worker') or 'server'
        state = job.get('state') or 'unknown'
        if stamp >= cutoff:
            states[(worker, state)] = states.get((worker, state), 0) + 1
        if state in ('running', 'stale_running') and job.get('started'):
            oldest[worker] = max(oldest.get(worker, 0), max(0, now - job['started']))
            job_id = str(job.get('id') or job.get('name') or 'unknown')[:80]
            metric('watoom_worker_running_job_seconds', round(max(0, now - job['started']), 3), {'worker': worker, 'job': job_id})
            try:
                deadline = float(job.get('deadline_seconds') or DEFAULT_DEADLINE_SECONDS)
            except (TypeError, ValueError):
                deadline = DEFAULT_DEADLINE_SECONDS
            metric('watoom_worker_running_job_deadline_seconds', deadline, {'worker': worker, 'job': job_id})
    for worker in ('bazzite', 'rig', 'server'):
        if worker == 'bazzite':
            up = 1 if doc.get('bazzite', {}).get('reachable') is True else 0
            busy = doc.get('bazzite', {}).get('busy')
            failures = doc.get('bazzite', {}).get('consecutive_failures', 0)
        elif worker == 'rig':
            up = 1 if doc.get('rig', {}).get('online') else 0
            busy = doc.get('rig', {}).get('busy')
            failures = 0 if up else 1
        else:
            up = 1
            busy = any(j.get('worker') == 'server' and j.get('state') in ('running', 'stale_running') for j in jobs)
            failures = 0
        metric('watoom_worker_up', up, {'worker': worker})
        metric('watoom_worker_busy', int(bool(busy)), {'worker': worker})
        metric('watoom_worker_oldest_running_job_seconds', round(oldest.get(worker, 0), 3), {'worker': worker})
        metric('watoom_worker_consecutive_failures', failures, {'worker': worker})
        for (w, state), count in sorted(states.items()):
            if w == worker:
                metric('watoom_worker_jobs', count, {'worker': worker, 'state': state})
    metric('watoom_worker_snapshot_timestamp_seconds', int(doc.get('generated') or now))
    return '\n'.join(lines) + '\n'


def scan_json_health(directory, pattern):
    directory = pathlib.Path(directory)
    if not directory.is_dir():
        return 0, 'source directory missing or unreadable'
    paths = list(directory.glob(pattern))
    bad = [p.name for p in paths if not isinstance(read_json(p), dict)]
    return len(paths) - len(bad), ('%d unreadable or invalid JSON file(s)' % len(bad) if bad else None)


def write_metrics_atomic(path, body):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.tmp')
    tmp.write_text(body, encoding='utf-8')
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def bazzite_sh():
    here = pathlib.Path(__file__).resolve().parent
    for candidate in (here, pathlib.Path('/data/ai/watoom-code/config/skills/watoom-fab-owned-assets/scripts/unreal-export')):
        if (candidate / 'bazzite.py').is_file():
            sys.path.insert(0, str(candidate))
            break
    import bazzite  # the existing worker-access helper (copied beside this script when installed)
    return bazzite.sh


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=pathlib.Path, default=OUT)
    ap.add_argument('--prom', type=pathlib.Path, default=pathlib.Path('/var/lib/node_exporter/textfile/watoom-workers.prom'))
    ap.add_argument('--no-bazzite', action='store_true', help='skip the SSH probe')
    a = ap.parse_args(argv)
    started = time.monotonic()
    now = time.time()
    previous = read_json(a.out) or {}
    sh = None
    if not a.no_bazzite:
        try:
            sh = bazzite_sh()
        except Exception as exc:  # noqa: BLE001
            print('bazzite access unavailable: %s' % exc, file=sys.stderr)
    try:
        doc = build(now, previous, sh=sh, media_root=a.out.parent / MEDIA_SUBDIR)
    except Exception as exc:  # a broken source must not prevent a diagnostic snapshot
        error = clip(exc, 180)
        doc = {'schema': 1, 'generated': now, 'bazzite': {'reachable': None, 'busy': False, 'consecutive_failures': 0},
               'rig': {'online': False, 'busy': False, 'quiet_for_seconds': None}, 'jobs': [],
               'collector': {'version': '2', 'duration_ms': 0, 'sources': {name: {'ok': False, 'count': 0, 'error': error}
                for name in ('receipts', 'lane_results', 'jail', 'journal', 'bazzite_probe')}}}
        doc['_metric_jobs'] = []
    metric_jobs = doc.pop('_metric_jobs', doc.get('jobs', []))
    prom_error = None
    try:
        write_metrics_atomic(a.prom, render_metrics(doc, now=now, jobs=metric_jobs))
    except OSError as exc:
        prom_error = clip(exc, 180)
    doc['collector']['duration_ms'] = round((time.monotonic() - started) * 1000)
    if prom_error:
        doc['collector']['sources']['metrics_output'] = {'ok': False, 'count': 0, 'error': prom_error}
    write_atomic(a.out, doc)
    print('worker status written: %d jobs, bazzite %s, rig %s' % (len(doc['jobs']), {True: 'up', False: 'down', None: 'unknown'}[doc['bazzite']['reachable']],
                                                                  'online' if doc['rig']['online'] else 'quiet'))


if __name__ == '__main__':
    main()
