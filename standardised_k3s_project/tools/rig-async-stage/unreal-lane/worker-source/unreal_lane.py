"""Shared contract of the rig's Unreal lane (used unchanged by the homelab CLI and the Windows worker).

The lane moves work to the rig over the existing transfer-only SFTP jail: the homelab (root) writes a job manifest and an optional
input package into /payloads/inputs; the rig pulls them, runs ONE fixed operation under a Windows Job Object and uploads the results
into /payloads/uploads/ue-<job>/. Operations are a fixed allow-list: a manifest can never carry code or a command line.
"""
import hashlib, json, re

PREFIX = 'ue-job-'
JOB_ID = re.compile(r'[a-z0-9][a-z0-9-]{7,47}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
# op -> fixed script shipped (hash-pinned) with the worker, whether it needs an input package, deadline, and params it accepts
ASSET_PATH = re.compile(r'/Game/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+){0,6}')
OPS = {
    'probe': {'script': 'ue_probe_api.py', 'package': False, 'timeout': 900, 'params': {}},
    # MetaHuman skin/DCC export on the GPU: the package is a zip of the character's Content (EditableCharacters/<Name>/...). The full editor is used
    # (not the commandlet) with a real renderer, because Epic's TextureGraph - which bakes the skin maps - needs one.
    'metahuman-skin': {'script': 'ue_metahuman.py', 'package': True, 'timeout': 2400, 'full_editor': True, 'null_rhi': False, 'request_op': 'export_dcc',
                       'params': {'asset': lambda v: isinstance(v, str) and bool(ASSET_PATH.fullmatch(v)),
                                  'name': lambda v: isinstance(v, str) and bool(re.fullmatch(r'[A-Za-z0-9_]{1,64}', v)),
                                  'bake_makeup': lambda v: isinstance(v, bool)}},
}
# the only artifact types the rig may return (data formats the DCC export can produce; nothing executable)
UPLOAD_SUFFIXES = ('.json', '.log', '.png', '.txt', '.tga', '.exr', '.jpg', '.dna', '.fbx')
MAX_PACKAGE_BYTES = 4 * 1024 ** 3
MAX_RESULT_BYTES = 2 * 1024 ** 3
MAX_RESULT_FILES = 400


def manifest_name(job): return PREFIX + job + '.json'
def package_name(job): return PREFIX + job + '.zip'
def upload_dir(job): return 'ue-' + job


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def validate_manifest(m, expected_job=None):
    """Returns the manifest if it is acceptable; raises ValueError otherwise. Strict: unknown keys are rejected."""
    if not isinstance(m, dict) or set(m) != {'schema', 'job', 'op', 'created', 'package', 'params'}:
        raise ValueError('manifest keys must be exactly schema, job, op, created, package, params')
    if m['schema'] != 1:
        raise ValueError('unsupported schema')
    if not isinstance(m['job'], str) or not JOB_ID.fullmatch(m['job']):
        raise ValueError('invalid job id')
    if expected_job is not None and m['job'] != expected_job:
        raise ValueError('job id does not match the file name')
    op = OPS.get(m['op'])
    if op is None:
        raise ValueError('operation not allowed: %r' % (m['op'],))
    if not isinstance(m['created'], (int, float)) or isinstance(m['created'], bool):
        raise ValueError('invalid created time')
    params = m['params']
    if not isinstance(params, dict) or set(params) - set(op['params']) or len(json.dumps(params)) > 8192:
        raise ValueError('parameters not allowed for this operation')
    for key, check in op['params'].items():
        if key in params and not check(params[key]):
            raise ValueError('invalid parameter ' + key)
    if m['op'] == 'metahuman-skin' and not {'asset', 'name'} <= set(params):
        raise ValueError('metahuman-skin needs the parameters asset and name')
    pkg = m['package']
    if op['package']:
        if not isinstance(pkg, dict) or set(pkg) != {'sha256', 'bytes'} or not isinstance(pkg['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', pkg['sha256']) \
                or not isinstance(pkg['bytes'], int) or isinstance(pkg['bytes'], bool) or not 0 < pkg['bytes'] <= MAX_PACKAGE_BYTES:
            raise ValueError('this operation needs a package {sha256, bytes}')
    elif pkg is not None:
        raise ValueError('this operation takes no package')
    return m


def validate_result(result, manifest):
    """Checks the rig's result.json (untrusted data). Returns it; raises ValueError."""
    if not isinstance(result, dict) or result.get('schema') != 1 or result.get('job') != manifest['job'] or result.get('op') != manifest['op']:
        raise ValueError('result does not belong to this job')
    if result.get('status') not in ('PASS', 'FAIL'):
        raise ValueError('invalid status')
    files = result.get('files')
    if not isinstance(files, dict) or len(files) > MAX_RESULT_FILES:
        raise ValueError('invalid file table')
    total = 0
    for name, info in files.items():
        if not NAME.fullmatch(name) or not name.endswith(UPLOAD_SUFFIXES) or name == 'result.json':
            raise ValueError('unexpected artifact name ' + name)
        if not isinstance(info, dict) or not re.fullmatch(r'[a-f0-9]{64}', str(info.get('sha256', ''))) or not isinstance(info.get('bytes'), int) or info['bytes'] < 0:
            raise ValueError('invalid artifact entry ' + name)
        total += info['bytes']
    if total > MAX_RESULT_BYTES:
        raise ValueError('result exceeds the size budget')
    return result
