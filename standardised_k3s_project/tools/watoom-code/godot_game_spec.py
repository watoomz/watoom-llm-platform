"""Typed watoom-godot-game job: a fixed list of skill commands run against a staged game project; no shell, no paths, no engine flags.

The agent writes .opencode/godot-game-jobs/<job>/request.json and requests it through the native game worker tool (operation "godot-game").
The root dispatcher validates it here; game_godot_game.py runs the steps on the Bazzite worker (never the homelab server). The skill scripts
(ansible/roles/watoom-code/files/skills/watoom-godot-game/scripts) are the installed IaC copy, never project files. Steps are (script, subcommand)
pairs from STEPS below; the worker adds --project itself, so a step can carry only plain option tokens.
"""
import hashlib, json, pathlib, re

BASE = 'godot-game-job-v1'
SKILL = pathlib.Path(__file__).resolve().parents[2] / 'ansible/roles/watoom-code/files/skills/watoom-godot-game'
GL_STYLES = {'low-poly', 'pixel-art'}   # the Bazzite container has no GPU: only gl_compatibility styles (software GL) can run
FIELDS = {'schema', 'project_dir', 'steps', 'deadline_sec', 'memory_gib', 'from_project'}
COPY_MAX_MB = 30
INIT_STEPS = {('gg_ui.py', 'init'), ('gg_project.py', 'init')}
# every (script, subcommand) a job may run. Not allowed on purpose: calibrate/matrix (write presets), verify (paths), style probe (needs --out).
STEPS = {
    'gg_project.py': {'init', 'validate', 'sync-runtime', 'show', 'doctor'},
    'gg_style.py': {'apply', 'validate', 'show', 'resolve', 'list'},
    'gg_terrain.py': {'heights', 'layers', 'build'},
    'gg_water.py': {'creek', 'analyse', 'build'},
    'gg_light.py': {'shoot', 'tune'},
    'gg_catalog.py': {'init', 'list', 'validate', 'inspect'},
    'gg_scatter.py': {'plan', 'run'},
    'gg_census.py': {'audit'},
    'gg_player.py': {'init', 'build', 'smoke', 'status'},
    'gg_export.py': {'build', 'status'},
    'gg_ui.py': {'init', 'test', 'shot', 'overlay-check'},
    'gg_assets.py': {'check'},   # find/use read the asset library, which the worker container does not mount: the model runs those in its own session   # UI / overlay games: project start, GDScript tests, transparent UI screenshots, overlay read-back
    'gg_combat.py': {'init', 'check', 'slice', 'pickups', 'mp'},   # combat core, vertical slice, pickups, 2-process multiplayer authority (T-0065/67-72); no args need paths
    'gg_vfx.py': {'check'},   # --spec (if passed) is a path and is not allowed as a token; the built-in demo recipes cover a worker job
    # gg_anim.py is not registered: --mesh/--states carry res:// asset paths outside RES_FLAGS, so it stays a model-run-direct script like gg_assets.py find/use
    'gg_dungeon.py': {'catalog-init', 'catalog-list', 'catalog-validate', 'layout', 'verify'},   # dungeon kit catalog + procedural grid layout (T-0059); pure logic, no engine
}
NO_PROJECT_FLAG = {('gg_project.py', 'doctor')}   # doctor takes no --project
TOKEN = re.compile(r'[A-Za-z0-9_.,:+=-][A-Za-z0-9_.,:+= -]{0,127}')   # no slash, quote, $, ; | & ( ) < > or backtick: a token is never a path or shell syntax
FORBIDDEN = ('--project', '--out', '--work', '--godot', '--report', '--targets', '--against', '--keep')
MAX_STEPS, MAX_ARGS = 12, 24
# the one place a token may hold slashes: a res:// project path, only as the value of --scene or --dir of a gg_ui.py step (it can never leave the project)
RES_PATH = re.compile(r'res://[A-Za-z0-9_][A-Za-z0-9_/.-]{0,120}')
RES_FLAGS = {('gg_ui.py', '--scene'), ('gg_ui.py', '--dir'), ('gg_dungeon.py', '--pieces-dir')}


def path(project, job):
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', job): raise ValueError('job must be 1-64 letters, digits, _ or -')
    return pathlib.Path(project) / '.opencode/godot-game-jobs' / job / 'request.json'


def relative(value, field):
    if not isinstance(value, str) or not re.fullmatch('[A-Za-z0-9_./-]+', value) or value.startswith('/') or value.endswith('/') or '//' in value or '..' in value.split('/'):
        raise ValueError(field + ' ' + json.dumps(value) + ' must be a normalised project-relative path: letters, digits and _ . / - only, no leading or trailing slash, no // and no .. segments')
    return value


def check_step(i, s):
    if not isinstance(s, dict) or set(s) - {'script', 'sub', 'args'} or 'script' not in s or 'sub' not in s:
        raise ValueError('steps[%d] must be {"script": ..., "sub": ..., "args": [...]}' % i)
    script, sub = s['script'], s['sub']
    if script not in STEPS: raise ValueError('steps[%d].script %s is not allowed; allowed: %s' % (i, json.dumps(script), ', '.join(sorted(STEPS))))
    if sub not in STEPS[script]: raise ValueError('steps[%d].sub %s is not allowed for %s; allowed: %s' % (i, json.dumps(sub), script, ', '.join(sorted(STEPS[script]))))
    args = s.get('args', [])
    if not isinstance(args, list) or len(args) > MAX_ARGS: raise ValueError('steps[%d].args must be a list of at most %d strings' % (i, MAX_ARGS))
    for k, a in enumerate(args):
        if isinstance(a, str) and k and (script, args[k - 1]) in RES_FLAGS and RES_PATH.fullmatch(a) and '..' not in a.split('/'): continue
        if isinstance(a, str) and '=' in a and (script, a.split('=')[0]) in RES_FLAGS and RES_PATH.fullmatch(a.split('=', 1)[1]) and '..' not in a.split('/'): continue
        if not isinstance(a, str) or not TOKEN.fullmatch(a): raise ValueError('steps[%d].args %s is not a plain token: letters, digits and _ . , : + = - space only (no paths, quotes or shell characters)' % (i, json.dumps(a)))
        flag = a.split()[0].split('=')[0]
        # argparse accepts unambiguous prefixes, so --ou or --pro would reach --out / --project
        if flag in FORBIDDEN or (flag.startswith('--') and len(flag) >= 3 and any(f.startswith(flag) for f in FORBIDDEN)): raise ValueError('steps[%d].args %s is set by the worker and cannot be passed' % (i, json.dumps(a)))
    return {'script': script, 'sub': sub, 'args': list(args)}


def init_style(args):
    """The --style value of a gg_project.py init step (either `--style X` or `--style=X`), or None."""
    for i, a in enumerate(args):
        if a.startswith('--style='): return a[8:]
        if a == '--style' and i + 1 < len(args): return args[i + 1]
    return None


def real_ancestor(project, directory):
    """True when the nearest existing ancestor of a not-yet-created folder is a real (non-link) directory inside the project's .opencode."""
    base = (pathlib.Path(project) / '.opencode').resolve()
    p = directory.parent
    while not p.exists() and not p.is_symlink() and p != p.parent: p = p.parent
    return p.is_dir() and not p.is_symlink() and p.resolve() == p and (p == base or base in p.parents)


def load(project, job, fresh=True):
    """fresh=True is the start-of-job check (the staging folder must be new or empty for init/from_project jobs). Re-reading a request after its
    job ran (the fingerprint, reconciliation) passes fresh=False: the folder is full by then and that must not turn a PASS into a failure."""
    file = path(project, job)
    if not file.is_file() or file.is_symlink() or file.resolve() != file: raise ValueError(str(file.relative_to(project)) + ' must be a regular file, not a link')
    if file.stat().st_size > 16384: raise ValueError('request.json must be at most 16 KiB')
    raw = file.read_bytes()
    try: v = json.loads(raw)
    except json.JSONDecodeError as e: raise ValueError('request.json is not valid JSON: ' + str(e)) from None
    if not isinstance(v, dict): raise ValueError('request.json must be a JSON object')
    if set(v) - FIELDS: raise ValueError('unknown fields ' + ', '.join(sorted(set(v) - FIELDS)) + '; allowed: ' + ', '.join(sorted(FIELDS)))
    if v.get('schema') != 1: raise ValueError('schema must be 1')
    for f in ('project_dir', 'steps'):
        if f not in v: raise ValueError('missing field ' + f)
    pdir = relative(v['project_dir'], 'project_dir')
    if not pdir.startswith('.opencode/tmp/'): raise ValueError('project_dir must be under .opencode/tmp/ (a scratch copy of the game project, never the live source)')
    directory = pathlib.Path(project) / pdir
    steps = v['steps']
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS: raise ValueError('steps must be a list of 1-%d steps' % MAX_STEPS)
    steps = [check_step(i, s) for i, s in enumerate(steps)]
    first = steps[0]
    from_project = v.get('from_project', False)
    if not isinstance(from_project, bool): raise ValueError('from_project must be true or false')
    if from_project and (first['script'], first['sub']) in INIT_STEPS: raise ValueError('from_project copies the live project, so the first step cannot be an init step')
    deadline = v.get('deadline_sec', 900)
    if isinstance(deadline, bool) or not isinstance(deadline, int) or not 120 <= deadline <= 1800: raise ValueError('deadline_sec must be an integer 120-1800')
    memory = v.get('memory_gib', 4)
    if isinstance(memory, bool) or not isinstance(memory, int) or not 3 <= memory <= 8: raise ValueError('memory_gib must be an integer 3-8')
    if not fresh:
        # Re-read after the run (fingerprint / reconcile): only the manifest itself is bound. The live project and the staging folder change while
        # the job runs (the model keeps editing), so none of their state may turn a finished PASS into a failure.
        return {'directory': pdir, 'create_directory': False, 'from_project': from_project, 'steps': steps, 'deadline_sec': deadline, 'memory_gib': memory, 'spec_sha256': hashlib.sha256(raw).hexdigest()}
    if fresh and from_project and directory.exists() and (directory.is_symlink() or not directory.is_dir() or any(directory.iterdir())): raise ValueError('with from_project the project_dir must not exist yet or be empty: it already holds files from an earlier job. Pick a NEW project_dir for every job, e.g. .opencode/tmp/<job-name> (the worker fills it with a copy of the live project; files over %d MB, .git, .godot, .opencode, gg_data/jobs, gg_data/export/stage and gg_data/selftest* are left out; the rest of gg_data, e.g. style.resolved.json/world/census.json/scatter, IS copied, so if you adopt a finished job\'s output/project back onto the live project, the next from_project job keeps that continuity instead of losing it)' % COPY_MAX_MB)
    # The model's tools cannot create an empty folder, so an init job may name one that does not exist yet: the operator creates it (INIT_STEPS).
    missing = (first['script'], first['sub']) in INIT_STEPS and not directory.exists() and not directory.is_symlink() and real_ancestor(project, directory)
    if from_project:
        missing = not directory.exists() and not directory.is_symlink() and real_ancestor(project, directory)
        if not missing and not (directory.is_dir() and not directory.is_symlink()): raise ValueError('project_dir does not exist and cannot be created')
    if not missing and not from_project and (directory.is_symlink() or directory.resolve() != directory or not directory.is_dir()): raise ValueError('project_dir does not exist or is not a plain directory (only a job whose first step is gg_ui.py init or gg_project.py init may name a folder that is not there yet)')
    root = pathlib.Path(project) if from_project else directory   # what the checks below look at: the live project when it is to be copied
    if (first['script'], first['sub']) == ('gg_ui.py', 'init'):
        if fresh and not missing and any(directory.iterdir()): raise ValueError('project_dir must be empty when the first step is gg_ui.py init')
    elif (root / 'gg_ui.json').is_file() and not (root / 'gg_project.json').exists():
        f = root / 'project.godot'   # a UI project (gg_ui.py init) runs on software GL by construction: no style preset to check
        if f.is_symlink() or f.resolve() != f or not f.is_file() or (root / 'gg_ui.json').is_symlink(): raise ValueError('project_dir needs a regular project.godot and gg_ui.json')
    elif (first['script'], first['sub']) == ('gg_project.py', 'init'):
        if fresh and not missing and any(directory.iterdir()): raise ValueError('project_dir must be empty when the first step is gg_project.py init')
        style = init_style(first['args'])
        if style not in GL_STYLES: raise ValueError('gg_project.py init needs --style ' + ' or '.join(sorted(GL_STYLES)) + ' on the Bazzite worker (no GPU there, so the Vulkan styles cannot run); got ' + json.dumps(style))
    else:
        for name in ('project.godot', 'gg_project.json'):
            f = root / name
            if f.is_symlink() or f.resolve() != f or not f.is_file(): raise ValueError('project_dir needs a regular ' + name + ' (start the job with a gg_project.py init step, or stage a project that has one)')
        try: cfg = json.loads((root / 'gg_project.json').read_text())
        except (ValueError, UnicodeDecodeError): raise ValueError('gg_project.json is not valid JSON') from None
        if not isinstance(cfg, dict) or not isinstance(cfg.get('style'), dict): raise ValueError('gg_project.json needs a "style" object (gg_project.py init writes it)')
        preset = cfg['style'].get('preset')
        if preset not in GL_STYLES: raise ValueError('the project style ' + json.dumps(preset) + ' needs a GPU; the Bazzite worker runs only ' + ' or '.join(sorted(GL_STYLES)))
    return {'directory': pdir, 'create_directory': missing, 'from_project': from_project, 'steps': steps, 'deadline_sec': deadline, 'memory_gib': memory, 'spec_sha256': hashlib.sha256(raw).hexdigest()}


def revision(project, job):
    """Bound to the manifest bytes only (the coordinator-guard tool computes the same); the staged copy is hashed by the operator and in the receipt."""
    return hashlib.sha256(json.dumps([BASE, load(project, job, fresh=False)['spec_sha256']], separators=(',', ':')).encode()).hexdigest()
