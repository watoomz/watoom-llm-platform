#!/usr/bin/env python3
"""Index every model file a Godot project can use without Unreal: .glb/.gltf/.fbx under the owned packs and the loose files in humble_assets.

  build_model_index.py [--fab /data/ai/assets/fab] [--humble /data/ai/assets/humble_assets] [--out /data/ai/assets/catalog/model-index.json]

One entry per file: id, pack, path, ext, bytes and, for .glb, what the file really holds (meshes, skins, animation names, materials) read from the glTF JSON chunk
(no engine, no textures loaded), so a model can pick an asset with `gg_assets.py find` instead of reading the 970-line asset-index.md. Read only: nothing is
copied or converted. Zip archives are listed (kind "archive") but not opened.
"""
import argparse, json, os, re, struct, sys, time

EXTS = {'.glb': 'glb', '.gltf': 'gltf', '.fbx': 'fbx'}
SKIP_DIRS = {'__MACOSX', 'Intermediate', 'Saved', 'DerivedDataCache', '.git'}
MAX_DEPTH = 6


def glb_facts(path):
    """-> dict of counts from the glTF JSON chunk of a .glb, or None when it is not a readable glb."""
    try:
        with open(path, 'rb') as f:
            head = f.read(20)
            if len(head) < 20: return None
            magic, version, _ = struct.unpack('<4sII', head[:12])
            clen, ctype = struct.unpack('<II', head[12:20])
            if magic != b'glTF' or ctype != 0x4E4F534A or clen > 64 * 1024 * 1024: return None
            j = json.loads(f.read(clen))
    except (OSError, ValueError, struct.error):
        return None
    anims = [str(a.get('name', ''))[:40] for a in j.get('animations', [])]
    return {'meshes': len(j.get('meshes', [])), 'skins': len(j.get('skins', [])), 'animations': len(anims), 'animation_names': anims[:8],
            'materials': len(j.get('materials', [])), 'generator': str(j.get('asset', {}).get('generator', ''))[:40]}


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def walk(root, base_depth, pack_of):
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not os.path.islink(os.path.join(d, x)))
        if d[len(root):].count(os.sep) >= MAX_DEPTH: dirs[:] = []
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            p = os.path.join(d, f)
            if ext in EXTS and not os.path.islink(p):
                yield pack_of(p), p, EXTS[ext]


def build(fab, humble):
    models, seen = [], set()

    def add(pack, p, kind):
        base = slug(pack + '-' + os.path.splitext(os.path.basename(p))[0])[:90]
        mid, n = base, 2
        while mid in seen:
            mid = '%s-%d' % (base, n); n += 1
        seen.add(mid)
        e = {'id': mid, 'pack': pack, 'path': p, 'ext': kind, 'bytes': os.path.getsize(p), 'converted': '/glb/converted/' in p}
        if kind == 'glb':
            e['glb'] = glb_facts(p)
        models.append(e)
    if os.path.isdir(fab):
        for pack in sorted(os.listdir(fab)):
            pdir = os.path.join(fab, pack)
            if os.path.isdir(pdir) and not os.path.islink(pdir) and pack not in ('zips', 'chars'):
                for _, p, kind in walk(pdir, 0, lambda x, pack=pack: pack): add(pack, p, kind)
    if os.path.isdir(humble):
        for f in sorted(os.listdir(humble)):
            p = os.path.join(humble, f)
            ext = os.path.splitext(f)[1].lower()
            if os.path.isfile(p) and not os.path.islink(p) and ext in EXTS: add('humble_assets', p, EXTS[ext])
    return models


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--fab', default='/data/ai/assets/fab'); ap.add_argument('--humble', default='/data/ai/assets/humble_assets')
    ap.add_argument('--out', default='/data/ai/assets/catalog/model-index.json')
    a = ap.parse_args(argv)
    models = build(a.fab, a.humble)
    doc = {'schema': 1, 'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'count': len(models), 'models': models}
    tmp = a.out + '.tmp'
    with open(tmp, 'w') as f: json.dump(doc, f, indent=1)
    os.replace(tmp, a.out); os.chmod(a.out, 0o644)
    kinds = {}
    for m in models: kinds[m['ext']] = kinds.get(m['ext'], 0) + 1
    print('indexed %d model files (%s) -> %s' % (len(models), ', '.join('%s %d' % kv for kv in sorted(kinds.items())), a.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
