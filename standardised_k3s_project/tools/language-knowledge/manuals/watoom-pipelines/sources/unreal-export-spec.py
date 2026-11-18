"""Declarative Unreal pack export request: which purchased pack, folder and asset classes; no paths or engine arguments.

The agent writes .opencode/unreal-export-jobs/<job>/request.json in its game project and requests the job through the
native game worker tool. The root dispatcher validates it here, runs export_pack.py (Bazzite first, local fallback,
never replayed) and copies the exported files into .opencode/unreal-exports/<job>/.
"""
import hashlib, json, pathlib, re

PACKS = pathlib.Path('/data/ai/assets/fab')
CLASSES = ('SkeletalMesh', 'AnimSequence', 'StaticMesh', 'Texture2D')
FIELDS = {'schema', 'pack', 'root', 'classes', 'include', 'exclude', 'max_assets', 'memory_gib'}
REQUIRED = {'schema', 'pack', 'root', 'classes'}


def path(project, job):
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', job): raise ValueError('job must be 1-64 letters, digits, _ or -')
    return pathlib.Path(project) / '.opencode/unreal-export-jobs' / job / 'request.json'


def load(project, job):
    """The validated request plus its sha256. Every error names the field and the rule, so the agent can fix it."""
    file = path(project, job)
    if not file.is_file() or file.is_symlink() or file.resolve() != file: raise ValueError(str(file.relative_to(project)) + ' must be a regular file, not a link')
    if file.stat().st_size > 16384: raise ValueError('request.json must be at most 16 KiB')
    raw = file.read_bytes()
    try: v = json.loads(raw)
    except json.JSONDecodeError as e: raise ValueError('request.json is not valid JSON: ' + str(e)) from None
    if not isinstance(v, dict): raise ValueError('request.json must be a JSON object')
    if set(v) - FIELDS: raise ValueError('unknown fields ' + ', '.join(sorted(set(v) - FIELDS)) + '; allowed: ' + ', '.join(sorted(FIELDS)))
    if REQUIRED - set(v): raise ValueError('missing fields ' + ', '.join(sorted(REQUIRED - set(v))))
    if v['schema'] != 1: raise ValueError('schema must be 1')
    pack = v['pack']
    if not isinstance(pack, str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,127}', pack):
        raise ValueError('pack must be the folder name of a purchased pack under /data/ai/assets/fab, e.g. "animals-free-low-poly-3d-models-pack-e20511e6"')
    folder = PACKS / pack
    if folder.is_symlink() or not (folder / 'Content').is_dir(): raise ValueError('pack ' + json.dumps(pack) + ' is not a downloaded pack with a Content folder under /data/ai/assets/fab')
    root = v['root']
    if not isinstance(root, str) or not re.fullmatch(r'/Game(/[A-Za-z0-9_ .-]+)+', root) or '..' in root.split('/') or root.endswith('/'):
        raise ValueError('root must be an Unreal content folder like "/Game/AnimalsPack" (no trailing slash, no ..)')
    classes = v['classes']
    if not isinstance(classes, list) or not classes or len(set(classes)) != len(classes) or any(c not in CLASSES for c in classes):
        raise ValueError('classes must be a non-empty list of distinct values from ' + ', '.join(CLASSES))
    names = {}
    for field in ('include', 'exclude'):
        values = v.get(field, [])
        if not isinstance(values, list) or len(values) > 64 or any(not isinstance(x, str) or not re.fullmatch('[A-Za-z0-9_ ./-]{1,100}', x) for x in values):
            raise ValueError(field + ' must be a list of at most 64 name fragments: letters, digits, space and _ . / - (no commas)')
        names[field] = values
    max_assets = v.get('max_assets', 400)
    if isinstance(max_assets, bool) or not isinstance(max_assets, int) or not 1 <= max_assets <= 2000: raise ValueError('max_assets must be an integer 1-2000')
    memory = v.get('memory_gib', 4)
    if isinstance(memory, bool) or not isinstance(memory, int) or not 2 <= memory <= 12: raise ValueError('memory_gib must be an integer 2-12')
    return {'pack': folder, 'root': root, 'classes': classes, 'include': names['include'], 'exclude': names['exclude'] or None,
            'max_assets': max_assets, 'memory_gib': memory, 'spec_sha256': hashlib.sha256(raw).hexdigest()}


BASE = 'unreal-export-v1'


def revision(project, job):
    """Binds a request to the exact manifest bytes only: an export reads the purchased pack, not the game source, so
    the agent may keep editing the project while it runs. The coordinator-guard tool computes the same value."""
    return hashlib.sha256(json.dumps([BASE, load(project, job)['spec_sha256']], separators=(',', ':')).encode()).hexdigest()
