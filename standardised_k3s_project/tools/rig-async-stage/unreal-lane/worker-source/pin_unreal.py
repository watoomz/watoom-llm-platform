"""Run ON THE RIG once after installing Unreal (and again after any engine/plugin update): records what the lane is allowed to run.
Writes unreal-runtime-provenance.json next to this file: engine version + SHA-256 of the editor executables + the MetaHuman plugin descriptors.
The worker refuses to start, and refuses each job, if any of these hashes later differs."""
import argparse, hashlib, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
EXES = ('UnrealEditor-Cmd.exe', 'UnrealEditor.exe')


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def collect(root):
    root = pathlib.Path(root).resolve(strict=True)
    version = json.loads((root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    binaries = root / 'Engine/Binaries/Win64'
    files = {}
    for name in EXES:
        if not (binaries / name).is_file():
            raise SystemExit('missing ' + str(binaries / name))
        files[name] = sha(binaries / name)
    plugins = {}
    for f in sorted((root / 'Engine/Plugins').rglob('*.uplugin')):
        if 'metahuman' in f.name.lower() or 'MetaHuman' in f.parts:
            d = json.loads(f.read_text(encoding='utf-8-sig'))
            plugins[str(f.relative_to(root)).replace('\\', '/')] = {'name': d.get('FriendlyName'), 'version': d.get('VersionName'), 'sha256': sha(f)}
    return {'schema': 1, 'root': str(root), 'version': '%s.%s.%s' % (version['MajorVersion'], version['MinorVersion'], version['PatchVersion']),
            'branch': version.get('BranchName'), 'executable_dir': str(binaries), 'files': files, 'metahuman_plugins': plugins}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--ue-root', required=True, help=r'e.g. C:\Program Files\Epic Games\UE_5.8')
    a = ap.parse_args()
    doc = collect(a.ue_root)
    (HERE / 'unreal-runtime-provenance.json').write_text(json.dumps(doc, indent=2))
    print(json.dumps({k: doc[k] for k in ('version', 'files')}, indent=1))
    print('MetaHuman plugin descriptors found: %d' % len(doc['metahuman_plugins']))
    if not doc['metahuman_plugins']:
        print('WARNING: no MetaHuman plugin found under Engine/Plugins; install/enable it before running MetaHuman operations', file=sys.stderr)
