"""Declarative headless Blender job for a game project: which script, its arguments and limits; no paths outside the project.

The agent writes .opencode/blender-jobs/<job>/request.json and requests it through the native game worker tool
(operation "blender"). The root dispatcher validates it here and game_blender.py runs the pinned Blender in a
bounded unit with no network: the project is read-only, .opencode/blender-out/<job>/ is the only writable folder.
"""
import hashlib, json, pathlib, re

SKILLS = pathlib.Path(__file__).resolve().parents[2] / 'ansible/roles/watoom-code/files/skills'
FIELDS = {'schema', 'script', 'blend', 'args', 'deadline_sec', 'memory_gib'}
REL = re.compile(r'[A-Za-z0-9_.][A-Za-z0-9_ ./-]*')
BASE = 'blender-job-v1'


def path(project, job):
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', job): raise ValueError('job must be 1-64 letters, digits, _ or -')
    return pathlib.Path(project) / '.opencode/blender-jobs' / job / 'request.json'


def relative(value, field):
    if not isinstance(value, str) or not REL.fullmatch(value) or value.endswith('/') or '//' in value or '..' in value.split('/'):
        raise ValueError(field + ' ' + json.dumps(value) + ' must be a project-relative path: letters, digits, space and _ . / -, no leading or trailing slash, no //, no ..')
    return value


def script_path(project, script):
    """A project script, or skill:<skill>/<path> for an installed skill script (read-only, the IaC source)."""
    if isinstance(script, str) and script.startswith('skill:'):
        rel = relative(script[6:], 'script')
        file = SKILLS / rel
        if not rel.endswith('.py') or rel.count('/') < 1 or file.is_symlink() or not file.is_file() or file.resolve() != file:
            raise ValueError('script ' + json.dumps(script) + ' is not an installed skill script; use skill:<skill-name>/scripts/<file>.py')
        return file
    rel = relative(script, 'script')
    file = pathlib.Path(project) / rel
    if not rel.endswith('.py') or file.is_symlink() or not file.is_file() or file.resolve() != file:
        raise ValueError('script ' + json.dumps(script) + ' must be a regular .py file in the project (or skill:<skill>/scripts/<file>.py)')
    return file


def load(project, job):
    file = path(project, job)
    if not file.is_file() or file.is_symlink() or file.resolve() != file: raise ValueError(str(file.relative_to(project)) + ' must be a regular file, not a link')
    if file.stat().st_size > 16384: raise ValueError('request.json must be at most 16 KiB')
    raw = file.read_bytes()
    try: v = json.loads(raw)
    except json.JSONDecodeError as e: raise ValueError('request.json is not valid JSON: ' + str(e)) from None
    if not isinstance(v, dict): raise ValueError('request.json must be a JSON object')
    if set(v) - FIELDS: raise ValueError('unknown fields ' + ', '.join(sorted(set(v) - FIELDS)) + '; allowed: ' + ', '.join(sorted(FIELDS)))
    if v.get('schema') != 1: raise ValueError('schema must be 1')
    if 'script' not in v: raise ValueError('missing field script')
    script = script_path(project, v['script'])
    blend = None
    if v.get('blend') is not None:
        rel = relative(v['blend'], 'blend');blend = pathlib.Path(project) / rel
        if not rel.endswith('.blend') or blend.is_symlink() or not blend.is_file() or blend.resolve() != blend:
            raise ValueError('blend ' + json.dumps(v['blend']) + ' must be a regular .blend file in the project; it is opened before the script runs')
    args = v.get('args', [])
    if not isinstance(args, list) or len(args) > 64 or any(not isinstance(x, str) or len(x) > 1024 or '\x00' in x for x in args):
        raise ValueError('args must be a list of at most 64 strings (each up to 1024 characters); {out} is replaced by the output folder')
    deadline = v.get('deadline_sec', 300)
    if isinstance(deadline, bool) or not isinstance(deadline, int) or not 60 <= deadline <= 900: raise ValueError('deadline_sec must be an integer 60-900')
    memory = v.get('memory_gib', 4)
    if isinstance(memory, bool) or not isinstance(memory, int) or not 2 <= memory <= 6: raise ValueError('memory_gib must be an integer 2-6')
    # installed skill scripts verify the qualified server profile: exactly a 4 GiB cgroup (worker_profile.verify_external)
    if v['script'].startswith('skill:') and memory != 4: raise ValueError('memory_gib must be 4 (or omitted) for skill: scripts; they verify the qualified 4 GiB worker profile')
    return {'script': script, 'script_name': v['script'], 'blend': blend, 'args': args, 'deadline_sec': deadline, 'memory_gib': memory,
            'spec_sha256': hashlib.sha256(raw).hexdigest(), 'script_sha256': hashlib.sha256(script.read_bytes()).hexdigest()}


def revision(project, job):
    """Bound to the manifest bytes only (the coordinator-guard tool computes the same); the script hash is recorded in the receipt."""
    return hashlib.sha256(json.dumps([BASE, load(project, job)['spec_sha256']], separators=(',', ':')).encode()).hexdigest()
