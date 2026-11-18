"""Executes ONE fixed Unreal operation inside a Windows Job Object. Invoked by unreal_worker.py as: python unreal_runner.py <plan.json>.
The plan comes from the worker (never from the manifest directly): the script is the hash-pinned file shipped with the worker."""
import hashlib, json, pathlib, shutil, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


# Only these MetaHuman plugins are enabled (their dependencies, e.g. RigLogic, follow automatically); the Animator/LiveLink/CoreML plugins are not wanted.
WANTED_PLUGINS = ('MetaHumanCharacter', 'MetaHumanSDK')


def plugins_to_enable(provenance):
    """Names the install-time pinning found on THIS machine, restricted to WANTED_PLUGINS. Raises if none: a project that silently lacks the
    plugin only produces empty results (the first probe did exactly that with Optional entries)."""
    found = {pathlib.PurePosixPath(k).stem for k in provenance.get('metahuman_plugins', {})}
    names = [n for n in WANTED_PLUGINS if n in found]
    if not names:
        raise RuntimeError('no MetaHuman plugin was found when this Unreal install was pinned (found: %s)' % sorted(found))
    return names


def write_project(directory, plugins):
    entries = [{'Name': 'PythonScriptPlugin', 'Enabled': True}] + [{'Name': n, 'Enabled': True} for n in plugins]
    (directory / 'Lane.uproject').write_text(json.dumps({'FileVersion': 3, 'EngineAssociation': '', 'Plugins': entries}, indent=2))
    return directory / 'Lane.uproject'


RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *['COM%d' % n for n in range(1, 10)], *['LPT%d' % n for n in range(1, 10)]}
CONTENT_SUFFIXES = {'.uasset', '.uexp', '.ubulk', '.uptnl'}
MAX_UNPACK_BYTES = 4 * 1024 ** 3
MAX_UNPACK_FILES = 2000


def unpack_package(archive, content_dir):
    """Extracts a character's Content zip into <project>/Content. Refuses anything but Unreal asset files, any path that could escape, Windows reserved
    names, duplicates differing only by case, links, and oversize archives. Returns the list of extracted relative paths."""
    import stat
    import zipfile
    content_dir = pathlib.Path(content_dir)
    content_dir.mkdir(parents=True, exist_ok=True)
    root = content_dir.resolve()
    seen, written, total = set(), [], 0
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename
            parts = pathlib.PurePosixPath(name).parts
            if not parts or name.startswith(('/', chr(92))) or '..' in parts or chr(92) in name or ':' in name or any(ord(ch) < 32 for ch in name) or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('unsafe package member: ' + name)
            if any(x.endswith((' ', '.')) or x.split('.')[0].upper() in RESERVED for x in parts):
                raise ValueError('Windows reserved name in package: ' + name)
            if pathlib.PurePosixPath(name).suffix.lower() not in CONTENT_SUFFIXES:
                raise ValueError('only Unreal asset files are accepted, got: ' + name)
            key = name.casefold()
            if key in seen:
                raise ValueError('duplicate member: ' + name)
            seen.add(key)
            total += info.file_size
            if len(seen) > MAX_UNPACK_FILES or total > MAX_UNPACK_BYTES:
                raise ValueError('package exceeds the expansion budget')
            target = content_dir.joinpath(*parts)
            if not target.resolve().is_relative_to(root):
                raise ValueError('package member escapes Content: ' + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, 'xb') as dst:
                shutil.copyfileobj(src, dst)
            written.append(name)
    if not written:
        raise ValueError('empty package')
    return written


def editor_command(plan, exe_dir, uproject, script, log):
    """The exact Unreal command line for a plan. Full editor (a real renderer, off-screen) or the commandlet; never any argument from the manifest."""
    exe_dir = pathlib.Path(exe_dir)
    common = ['-unattended', '-nosplash', '-nop4', '-nosound', '-stdout', '-FullStdOutLogOutput', '-abslog=' + str(log)]
    if plan.get('full_editor'):
        command = [str(exe_dir / 'UnrealEditor.exe'), str(uproject), '-ExecutePythonScript=' + str(script), '-RenderOffScreen', *common]
    else:
        command = [str(exe_dir / 'UnrealEditor-Cmd.exe'), str(uproject), '-run=PythonScript', '-script=' + str(script), *common]
    if plan.get('null_rhi'):
        command.append('-NullRHI')
    return command


def collect_outputs(project_dir, out):
    """Copies the DCC export (and the in-engine result) into the job folder with flat names; only allowed data types leave the project."""
    sys.path.insert(0, str(HERE))
    import unreal_lane as lane
    names = []
    dcc = project_dir / 'dcc'
    for f in sorted(dcc.rglob('*')) if dcc.is_dir() else []:
        if f.is_file() and not f.is_symlink() and f.suffix.lower() in lane.UPLOAD_SUFFIXES:
            flat = '__'.join(f.relative_to(dcc).parts)
            if lane.NAME.fullmatch(flat) and flat != 'result.json':
                shutil.copy2(f, out / flat)
                names.append(flat)
    native = project_dir / 'native-result.json'
    if native.is_file():
        shutil.copy2(native, out / 'native-result.json')
        names.append('native-result.json')
    return names


def execute(plan_path):
    import os
    from unreal_job import run_limited
    plan_path = pathlib.Path(plan_path)
    out = plan_path.parent
    plan = json.loads(plan_path.read_text())
    prov = json.loads((HERE / 'unreal-runtime-provenance.json').read_text())
    exe_dir = pathlib.Path(prov['executable_dir'])
    for name, digest in prov['files'].items():
        if sha(exe_dir / name) != digest:
            raise RuntimeError('Unreal executable changed since pinning: ' + name)
    script = HERE / plan['script']
    project_dir = out / 'project'
    project_dir.mkdir()
    uproject = write_project(project_dir, plugins_to_enable(prov))
    if plan.get('package'):
        unpack_package(out / 'package.zip', project_dir / 'Content')
    if plan.get('request'):                     # fixed keys chosen by the worker from the validated manifest, read by the in-engine script
        (project_dir / 'request.json').write_text(json.dumps(plan['request']))
    os.environ['WLK_JOB_DIR'] = str(project_dir)
    log = out / 'unreal.log'
    command = editor_command(plan, exe_dir, uproject, script, log)
    started = time.monotonic()
    code = run_limited(command, project_dir, plan['timeout'], plan['memory_bytes'])
    elapsed = round(time.monotonic() - started, 1)
    if log.is_file() and log.stat().st_size > 4 * 1024 ** 2:
        data = log.read_bytes()
        log.write_bytes(data[:1024 ** 2] + b'\n...[truncated]...\n' + data[-3 * 1024 ** 2:])
    files = []
    saved = project_dir / 'Saved'
    for candidate in sorted(saved.glob('*.json')) if saved.is_dir() else []:
        shutil.copy2(candidate, out / candidate.name)
        files.append(candidate.name)
    files += collect_outputs(project_dir, out)
    native_pass = False
    if (project_dir / 'native-result.json').is_file():
        try:
            native = json.loads((project_dir / 'native-result.json').read_text())
            native_pass = native.get('status') in ('METAHUMAN_PASS', 'PROBE_DONE') and not native.get('error')
        except ValueError:
            pass
    # a full editor can crash while shutting down after it already wrote a good result (seen on the Linux runs): accept that, and record it
    ok = bool(files) and (code == 0 or (plan.get('full_editor') and native_pass))
    receipt = {'schema': 1, 'op': plan['op'], 'engine_version': prov['version'], 'executable_sha256': prov['files'], 'script': plan['script'],
               'script_sha256': sha(script), 'memory_limit_bytes': plan['memory_bytes'], 'exit_code': code, 'elapsed_sec': elapsed,
               'shutdown_crash_accepted': bool(code != 0 and ok), 'status': 'PASS' if ok else 'FAIL', 'collected': files}
    (out / 'worker.json').write_text(json.dumps(receipt, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        sys.exit(execute(sys.argv[1]))
    except SystemExit as error:                      # a normal exit code is not an error
        if error.code not in (0, None):
            pathlib.Path(sys.argv[1]).parent.joinpath('runner-error.log').write_text(repr(error))
        raise
    except BaseException as error:
        pathlib.Path(sys.argv[1]).parent.joinpath('runner-error.log').write_text(repr(error))
        raise
