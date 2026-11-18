"""Project-neutral declarative terrain/landscape-to-GLB export contract; no caller shell or engine arguments.

Runs an existing, project-staged Unreal .uproject + in-engine Python script (e.g. load a map, find the
landscape actor, export it via AssetExportTask) on the Bazzite worker -- never on the homelab server, which
runs the production LLM and other shared services. uproject_dir is deliberately confined to .opencode/tmp/:
this is a scratch staging area the agent prepared, never the project's live Godot source.
"""
import pathlib, json, hashlib, re


def _relative(s, field):
    if not isinstance(s, str) or not re.fullmatch('[A-Za-z0-9_./-]+', s) or s.startswith('/') or '..' in pathlib.PurePosixPath(s).parts or str(pathlib.PurePosixPath(s)) != s:
        raise ValueError(field + ' ' + json.dumps(s) + ' is not a normalised project-relative path: letters, digits and _ . / - only, no leading or trailing slash, no // and no .. segments')
    return s


def _filename(s, field, suffix):
    if not isinstance(s, str) or '/' in s or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', s) or not s.endswith(suffix):
        raise ValueError(field + ' ' + json.dumps(s) + ' must be a bare ' + suffix + ' filename, no path separators')
    return s


def load(project, job):
    project = pathlib.Path(project)
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', job):
        raise ValueError('Invalid terrain job')
    path = project / '.opencode/terrain-jobs' / job / 'request.json'
    if path.is_symlink() or path.resolve() != path or path.stat().st_size > 32768:
        raise ValueError('Indirect/oversize terrain manifest')
    raw = path.read_bytes()
    v = json.loads(raw)
    if set(v) - {'deadline_sec', 'memory_gib'} != {'schema', 'uproject_dir', 'uproject_file', 'script'} or v['schema'] != 1:
        raise ValueError('Invalid declarative terrain schema')
    deadline = v.get('deadline_sec', 900)
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or deadline != int(deadline) or not 60 <= deadline <= 1800:
        raise ValueError('deadline_sec must be an integer 60-1800')
    deadline = int(deadline)
    memory_gib = v.get('memory_gib', 8)
    if isinstance(memory_gib, bool) or not isinstance(memory_gib, (int, float)) or memory_gib != int(memory_gib) or not 4 <= memory_gib <= 16:
        raise ValueError('memory_gib must be an integer 4-16')
    memory_gib = int(memory_gib)
    uproject_dir = _relative(v['uproject_dir'], 'uproject_dir')
    if not uproject_dir.startswith('.opencode/tmp/'):
        raise ValueError('uproject_dir must be under .opencode/tmp/ (a scratch staging area, never live source)')
    uproject_file = _filename(v['uproject_file'], 'uproject_file', '.uproject')
    script = _filename(v['script'], 'script', '.py')
    directory = project / uproject_dir
    if directory.is_symlink() or directory.resolve() != directory or not directory.is_dir():
        raise ValueError('uproject_dir does not exist or is not a plain directory')
    for name in (uproject_file, script):
        f = directory / name
        if f.is_symlink() or f.resolve() != f or not f.is_file():
            raise ValueError('Missing or unsafe required file: ' + name)
    sha = hashlib.sha256(json.dumps([hashlib.sha256(raw).hexdigest(),
                                      hashlib.sha256((directory / uproject_file).read_bytes()).hexdigest(),
                                      hashlib.sha256((directory / script).read_bytes()).hexdigest()],
                                     separators=(',', ':')).encode()).hexdigest()
    return {**v, 'directory': uproject_dir, 'deadline_sec': deadline, 'memory_gib': memory_gib, 'terrain_spec_sha256': sha}


def revision(project, job):
    # No base project fingerprint, unlike capture_spec: the staged uproject_dir lives entirely under
    # .opencode/tmp/ (outside the live Godot source tree game_worker_bridge.fingerprint() walks), so an
    # unrelated edit to the project's own source must never make this request look stale.
    return hashlib.sha256(json.dumps(['terrain-export', load(project, job)['terrain_spec_sha256']], separators=(',', ':')).encode()).hexdigest()
