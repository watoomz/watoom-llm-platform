#!/usr/bin/env python3
"""MetaHuman package pipeline: inspect, install to Unreal, and (via the Unreal worker) export for Godot.

A Fab MetaHuman `.mhpkg` is a ZIP of Unreal assets plus Manifest.json files that say where each asset belongs under /Game.
  inspect  PACK              what the package holds: editable character vs assembled character, LODs, grooms, clothing, hashes
  unpack   PACK              build PACK/Content (a normal Unreal Content tree, verified file by file) and PACK/metahuman-install.json
  copy-to-project PACK UPROJECT_DIR   copy that Content tree into an Unreal project and enable the MetaHuman plugins
  export-godot PACK CHARACTER [--out DIR] [--texture-size 4096] [--skin-tone R,G,B] [--skin-dir DIR | --rig-skin]
                             run the Unreal stages on the Bazzite worker and build a Godot folder (GLB meshes, DNA, normal maps,
                             scene + setup scripts). CHARACTER is the asset folder name, e.g. Base_Female.
                             --skin-dir DIR uses a collected rig-lane metahuman-skin result (real skin maps); --rig-skin submits that
                             job to the rig, waits for it and uses it. Without either, a flat skin tone + stored normal maps is used.

PACK is a folder directly under /data/ai/assets/fab that holds one .mhpkg. Nothing is ever written outside PACK except
copy-to-project's target. Run as root (the pack folders are root/toolkit owned). Stages that need Unreal (assemble, export for
Godot) live in metahuman_unreal.py and use the Bazzite worker.
"""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, sys, time, zipfile

PACKS = pathlib.Path('/data/ai/assets/fab')
KEEP = {'.uasset', '.uexp', '.ubulk', '.uptnl', '.umap'}
PLUGINS = ['MetaHumanCharacter', 'MetaHumanSDK', 'RigLogic', 'PythonScriptPlugin']
HERE = pathlib.Path(__file__).resolve().parent
EXPORT_PACK = HERE.parents[1] / 'watoom-fab-owned-assets/scripts/unreal-export/export_pack.py'
UE_OUT = pathlib.Path('/data/ai/artifacts/unreal-export')
OUT_ROOT = pathlib.Path('/data/ai/artifacts/metahuman')
GODOT_FILES = HERE.parent / 'godot'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def find_pack(arg):
    pack = pathlib.Path(arg).resolve(strict=True)
    if pack.parent != PACKS or not pack.is_dir():
        raise SystemExit('PACK must be a folder directly under %s' % PACKS)
    files = sorted(pack.glob('*.mhpkg'))
    if len(files) != 1:
        raise SystemExit('expected exactly one .mhpkg in %s, found %d' % (pack, len(files)))
    return pack, files[0]


def characters(z):
    """{member_dir: manifest} for each per-character Manifest.json (the root copy is skipped)."""
    out = {}
    for name in z.namelist():
        parts = name.split('/')
        if len(parts) == 2 and parts[1] == 'Manifest.json':
            out[parts[0]] = json.loads(z.read(name))
    return out


def kind(manifest):
    d = manifest.get('details', {})
    if d.get('bIsEditableCharacter'):
        return 'editable'   # a MetaHuman Creator character: must be assembled in Unreal before it has meshes
    return 'assembled'      # finished skeletal meshes, DNA, grooms, clothing


def safe_member(name):
    p = pathlib.PurePosixPath(name)
    return not p.is_absolute() and '..' not in p.parts and p.suffix.lower() in KEEP | {'.json'}


def inspect(pack, mhpkg):
    with zipfile.ZipFile(mhpkg) as z:
        bad = [n for n in z.namelist() if not n.endswith('/') and not safe_member(n)]
        chars = characters(z)
        rows = []
        for d, m in sorted(chars.items()):
            det = m.get('details', {})
            members = [i for i in z.infolist() if i.filename.startswith(d + '/') and not i.filename.endswith('.json')]
            rows.append({'folder': d, 'name': m.get('name'), 'object_path': m.get('assetData', {}).get('objectPath'),
                         'asset_type': m.get('assetType'), 'kind': kind(m), 'lods': det.get('includedLods'), 'lod0_verts': det.get('lod0VertCount'),
                         'grooms': det.get('numUniqueGrooms'), 'clothing': det.get('numUniqueClothingItems'), 'physics': det.get('bPhysics'),
                         'files': len(members), 'bytes': sum(i.file_size for i in members), 'packages': m.get('dependentPackages', [])})
    acq = pack / 'acquisition.json'
    expect = json.loads(acq.read_text()).get('sha256') if acq.is_file() else None
    actual = sha256(mhpkg)
    return {'pack': pack.name, 'mhpkg': mhpkg.name, 'sha256': actual, 'sha256_matches_acquisition': (actual == expect) if expect else None,
            'unsafe_members': bad, 'characters': rows}


def unpack(pack, mhpkg, force=False):
    info = inspect(pack, mhpkg)
    if info['unsafe_members']:
        raise SystemExit('refusing: unexpected members %s' % info['unsafe_members'][:5])
    if info['sha256_matches_acquisition'] is False:
        raise SystemExit('refusing: package hash differs from acquisition.json')
    content = pack / 'Content'
    if content.exists() and not force:
        raise SystemExit('%s exists; pass --force to rebuild it' % content)
    if content.exists():
        import shutil
        shutil.rmtree(content)
    installed = []
    with zipfile.ZipFile(mhpkg) as z:
        names = {i.filename for i in z.infolist()}
        for row in info['characters']:
            for package in row['packages']:
                if not package.startswith('/Game/') or '..' in package:
                    raise SystemExit('unexpected package path ' + package)
                stem = package.rsplit('/', 1)[1]
                for ext in sorted(KEEP):
                    member = '%s/%s' % (row['folder'], stem)
                    candidates = [n for n in names if n.startswith(row['folder'] + '/') and n.endswith('/' + stem + ext) or n == member + ext]
                    for n in candidates:
                        dest = content / (package[len('/Game/'):] + ext)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        h = hashlib.sha256()
                        with z.open(n) as src, open(dest, 'wb') as out:
                            for block in iter(lambda: src.read(1 << 20), b''):
                                h.update(block)
                                out.write(block)
                        installed.append({'character': row['name'], 'package': package, 'file': str(dest.relative_to(pack)), 'bytes': dest.stat().st_size, 'sha256': h.hexdigest()})
    for row in info['characters']:
        if not any(i['character'] == row['name'] for i in installed):
            raise SystemExit('no assets installed for ' + str(row['name']))
    state = {'schema': 1, 'pack': pack.name, 'mhpkg_sha256': info['sha256'], 'characters': info['characters'], 'installed': installed,
             'engine_import': 'CONTENT_READY', 'note': 'Content/ is a normal Unreal Content tree; open the project with the MetaHuman plugins enabled'}
    (pack / 'metahuman-install.json').write_text(json.dumps(state, indent=2))
    return state


def copy_to_project(pack, project_dir):
    import shutil
    state = json.loads((pack / 'metahuman-install.json').read_text())
    project_dir = pathlib.Path(project_dir).resolve(strict=True)
    uprojects = list(project_dir.glob('*.uproject'))
    if len(uprojects) != 1 or not (project_dir / 'Content').is_dir():
        raise SystemExit('UPROJECT_DIR must hold exactly one .uproject and a Content folder')
    for item in state['installed']:
        src = pack / item['file']
        if sha256(src) != item['sha256']:
            raise SystemExit('pack file changed since unpack: ' + item['file'])
        dest = project_dir / 'Content' / pathlib.Path(item['file']).relative_to('Content')
        if dest.exists() and sha256(dest) != item['sha256']:
            raise SystemExit('refusing to overwrite a different file: %s' % dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    doc = json.loads(uprojects[0].read_text(encoding='utf-8-sig'))
    have = {p['Name'] for p in doc.get('Plugins', [])}
    doc.setdefault('Plugins', []).extend({'Name': n, 'Enabled': True} for n in PLUGINS if n not in have)
    uprojects[0].write_text(json.dumps(doc, indent='\t'))
    return {'project': str(uprojects[0]), 'files': len(state['installed']), 'plugins_enabled': PLUGINS}


def run_export_pack(pack, tag, extra):
    """One Unreal stage on the Bazzite worker; returns the output folder. Refuses to continue unless the stage reported success."""
    out = UE_OUT / tag
    cmd = [sys.executable, str(EXPORT_PACK), '--pack', str(pack), '--root', '/Game/EditableCharacters', '--out', str(out),
           '--memory-gib', '8', '--reserve-gib', '0', '--backend', 'bazzite', '--deadline', '2400', *extra]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3000)
    result = json.loads((out / 'result.json').read_text()) if (out / 'result.json').is_file() else {}
    if r.returncode or result.get('status') not in ('METAHUMAN_PASS', 'PORTABLE_EXPORT_PASS'):
        raise SystemExit('Unreal stage %s failed: %s' % (tag, result.get('reason') or result.get('status') or r.stdout[-400:]))
    return out


def tga_to_png(src, dst, size, invert_green=False, keep_alpha=False):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(src) as im:
        im = im.convert('RGBA' if keep_alpha else 'RGB')
        if invert_green:  # Unreal normal maps are DirectX (green down); Godot expects OpenGL (green up)
            from PIL import ImageChops
            r, g, b, *alpha = im.split()
            im = Image.merge(im.mode, (r, ImageChops.invert(g), b, *alpha))
        if max(im.size) > size:
            scale = size / max(im.size)
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
        im.save(dst, 'PNG', optimize=True)
    return dst.stat().st_size


def clean_glb(data):
    """Removes accessors with count 0 that nothing references (Unreal's exporter leaves a couple in the head mesh; Godot logs an import ERROR
    for each). Returns (bytes, removed_count). A file where anything references an empty accessor, or that is not a plain GLB, is returned unchanged."""
    import struct
    if len(data) < 28 or data[:4] != b'glTF' or struct.unpack('<I', data[16:20])[0] != 0x4E4F534A:
        return data, 0
    jlen = struct.unpack('<I', data[12:16])[0]
    doc = json.loads(data[20:20 + jlen])
    acc = doc.get('accessors', [])
    empty = {i for i, a in enumerate(acc) if a.get('count', 0) == 0}
    if not empty:
        return data, 0
    refs = []
    for m in doc.get('meshes', []):
        for p in m.get('primitives', []):
            refs += list(p.get('attributes', {}).values()) + ([p['indices']] if 'indices' in p else [])
            for t in p.get('targets', []):
                refs += list(t.values())
    for k in doc.get('skins', []):
        if 'inverseBindMatrices' in k:
            refs.append(k['inverseBindMatrices'])
    for a in doc.get('animations', []):
        for sm in a.get('samplers', []):
            refs += [sm.get('input'), sm.get('output')]
    if empty & set(r for r in refs if r is not None):
        return data, 0
    remap, new = {}, []
    for i, a in enumerate(acc):
        if i not in empty:
            remap[i] = len(new)
            new.append(a)
    for m in doc.get('meshes', []):
        for p in m.get('primitives', []):
            p['attributes'] = {k: remap[v] for k, v in p['attributes'].items()}
            if 'indices' in p:
                p['indices'] = remap[p['indices']]
            p['targets'] = [{k: remap[v] for k, v in t.items()} for t in p.get('targets', [])] if 'targets' in p else None
            if p['targets'] is None:
                del p['targets']
    for k in doc.get('skins', []):
        if 'inverseBindMatrices' in k:
            k['inverseBindMatrices'] = remap[k['inverseBindMatrices']]
    for a in doc.get('animations', []):
        for sm in a.get('samplers', []):
            sm['input'], sm['output'] = remap[sm['input']], remap[sm['output']]
    doc['accessors'] = new
    blob = json.dumps(doc, separators=(',', ':')).encode()
    blob += b' ' * (-len(blob) % 4)
    rest = data[20 + jlen:]
    total = 12 + 8 + len(blob) + len(rest)
    return data[:8] + struct.pack('<I', total) + struct.pack('<I', len(blob)) + data[16:20] + blob + rest, len(empty)


def fix_normals(data, threshold=0.05):
    """Unreal's head export carries vertex normals that point against the mesh on a large share of the skin triangles (about 30 percent
    on the base characters): under any lighting that renders as dark and white blocks across the face, while an unlit view looks fine.
    For every primitive where more than `threshold` of the triangles disagree with their own normals, recompute smooth normals from the
    geometry (area weighted, welded by position) in place and drop the now stale tangents so Godot regenerates them. Returns
    (bytes, fixed_primitive_count); anything that is not a plain GLB, or a machine without numpy, is returned unchanged."""
    import struct
    try:
        import numpy as np
    except ImportError:
        return data, 0
    if len(data) < 28 or data[:4] != b'glTF' or struct.unpack('<I', data[16:20])[0] != 0x4E4F534A:
        return data, 0
    jlen = struct.unpack('<I', data[12:16])[0]
    doc = json.loads(data[20:20 + jlen])
    base = 20 + jlen + 8
    buf = bytearray(data)
    kinds = {5126: np.float32, 5123: np.uint16, 5125: np.uint32}
    widths = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3}

    def locate(index):
        a = doc['accessors'][index]
        view = doc['bufferViews'][a['bufferView']]
        dt = kinds[a['componentType']]
        nc = widths[a['type']]
        stride = view.get('byteStride') or np.dtype(dt).itemsize * nc
        return a, dt, nc, base + view.get('byteOffset', 0) + a.get('byteOffset', 0), stride

    def read(index):
        a, dt, nc, off, stride = locate(index)
        raw = np.frombuffer(bytes(buf), dtype=np.uint8, count=a['count'] * stride, offset=off).reshape(a['count'], stride)
        return raw[:, :np.dtype(dt).itemsize * nc].copy().view(dt).reshape(a['count'], nc)

    fixed = 0
    for mesh in doc.get('meshes', []):
        for prim in mesh.get('primitives', []):
            attrs = prim.get('attributes', {})
            if 'indices' not in prim or 'POSITION' not in attrs or 'NORMAL' not in attrs or prim.get('mode', 4) != 4:
                continue
            pos = read(attrs['POSITION']).astype(np.float64)
            nor = read(attrs['NORMAL']).astype(np.float64)
            tri = read(prim['indices']).reshape(-1, 3).astype(np.int64)
            if not len(tri):
                continue
            face = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
            if (np.einsum('ij,ij->i', face, nor[tri].sum(axis=1)) < 0).mean() < threshold:
                continue
            weld = np.unique(np.round(pos * 1e5).astype(np.int64), axis=0, return_inverse=True)[1].reshape(-1)
            acc = np.zeros((weld.max() + 1, 3))
            for corner in range(3):
                np.add.at(acc, weld[tri[:, corner]], face)
            new = acc[weld]
            length = np.linalg.norm(new, axis=1, keepdims=True)
            new = np.where(length > 1e-12, new / np.maximum(length, 1e-12), nor)
            a, dt, nc, off, stride = locate(attrs['NORMAL'])
            rows = new.astype(np.float32)
            for i in range(a['count']):
                buf[off + i * stride:off + i * stride + 12] = rows[i].tobytes()
            attrs.pop('TANGENT', None)
            fixed += 1
    if not fixed:
        return data, 0
    blob = json.dumps(doc, separators=(',', ':')).encode()
    blob += b' ' * (-len(blob) % 4)
    rest = bytes(buf[20 + jlen:])
    total = 12 + 8 + len(blob) + len(rest)
    return data[:8] + struct.pack('<I', total) + struct.pack('<I', len(blob)) + data[16:20] + blob + rest, fixed


def primitive_stats(data):
    """Vertex count, bounds centre and size of every primitive of the first mesh of a GLB (in order), or None if it is not a plain GLB."""
    import struct
    if len(data) < 28 or data[:4] != b'glTF' or struct.unpack('<I', data[16:20])[0] != 0x4E4F534A:
        return None
    doc = json.loads(data[20:20 + struct.unpack('<I', data[12:16])[0]])
    rows = []
    for i, p in enumerate(doc['meshes'][0]['primitives']):
        a = doc['accessors'][p['attributes']['POSITION']]
        lo, hi = a['min'], a['max']
        rows.append({'index': i, 'verts': a['count'], 'material': p.get('material'),
                     'center': [(x + y) / 2 for x, y in zip(lo, hi)], 'size': [y - x for x, y in zip(lo, hi)]})
    return rows


def classify_head_surfaces(stats):
    """Roles for the head mesh's surfaces from geometry alone (Unreal's glTF export loses the names): skin, teeth, eye, eyelashes, clear.
    skin = the biggest surface; eye = two equal, small, mirrored surfaces; teeth = the densest remaining surface below the eyes; eyelashes = the densest thin
    surface at eye height; every other thin shell (saliva, eye shell, eye edge, cartilage) is 'clear' so it cannot hide the eyes. Returns None when the
    pattern is not recognised (the Godot script then falls back to the largest-surface rule)."""
    if not stats or len(stats) < 4:
        return None
    face = max(stats, key=lambda r: r['verts'])
    eyes = [r for r in stats if r is not face and max(r['size']) < 0.045]
    pairs = [(a, b) for i, a in enumerate(eyes) for b in eyes[i + 1:] if a['verts'] == b['verts'] and abs(a['center'][0] + b['center'][0]) < 0.01
             and abs(a['center'][0]) > 0.01 and abs(a['center'][1] - b['center'][1]) < 0.01]
    if len(pairs) != 1:
        return None
    left, right = pairs[0]
    eye_y = (left['center'][1] + right['center'][1]) / 2
    rest = [r for r in stats if r is not face and r is not left and r is not right]
    low = [r for r in rest if r['center'][1] < eye_y - 0.03]
    teeth = max(low, key=lambda r: r['verts']) if low else None
    lashes_pool = [r for r in rest if abs(r['center'][1] - eye_y) < 0.02 and r is not teeth]
    lashes = max(lashes_pool, key=lambda r: r['verts']) if lashes_pool else None
    if teeth is None or lashes is None:
        return None
    roles = {}
    for r in stats:
        roles[r['index']] = ('skin' if r is face else 'eye' if r in (left, right) else 'teeth' if r is teeth else 'eyelashes' if r is lashes else 'clear')
    return [{'index': r['index'], 'verts': r['verts'], 'role': roles[r['index']]} for r in stats]


SKIN_MAPS = {   # slot -> DCC map file; (invert_green) : Unreal normals are DirectX, Godot expects OpenGL
    'albedo_head': ('Head_Basecolor.png', False), 'normal_head': ('Head_Normal.png', True), 'roughness_head': ('Head_SRMF.png', False),
    'albedo_body': ('Body_Basecolor.png', False), 'normal_body': ('Body_Normal.png', True), 'roughness_body': ('Body_SRMF.png', False),
}


DETAIL_MAPS = {   # slot -> (DCC map file, invert_green, keep_alpha)
    'eye_color': ('Eyes_Color.png', False, False), 'eye_normal': ('Eyes_Normal.png', True, False),
    'teeth_color': ('Teeth_Color.png', False, False), 'teeth_normal': ('Teeth_Normal.png', True, False),
    'lashes_color': ('Eyelashes_Color.png', False, True),   # the alpha channel is the strand cut-out
}


def merge_skin(skin_dir, dest, texture_size):
    """Uses a collected rig-lane metahuman-skin result: the six maps Godot can use become materials; everything else is kept for reference."""
    skin_dir = pathlib.Path(skin_dir)
    prefix = next((f.name.split('__Maps__')[0] for f in skin_dir.glob('*__Maps__*.png')), None)
    if prefix is None:
        raise SystemExit('%s has no DCC maps (expected <name>__Maps__*.png); is it a metahuman-skin result?' % skin_dir)
    if json.loads((skin_dir / 'result.json').read_text()).get('status') != 'PASS':
        raise SystemExit('the skin job did not pass')
    (dest / 'textures/skin').mkdir(parents=True)
    (dest / 'textures/reference').mkdir(parents=True)
    slots, used = {}, set()
    for slot, (name, invert) in SKIN_MAPS.items():
        src = skin_dir / ('%s__Maps__%s' % (prefix, name))
        if not src.is_file():
            continue
        tga_to_png(src, dest / 'textures/skin' / name, texture_size, invert_green=invert)
        slots[slot] = 'skin/' + name
        used.add(src.name)
    if not {'albedo_head', 'albedo_body'} <= set(slots):
        raise SystemExit('the skin result lacks Head_Basecolor/Body_Basecolor')
    for slot, (name, invert, alpha) in DETAIL_MAPS.items():
        src = skin_dir / ('%s__Maps__%s' % (prefix, name))
        if src.is_file():
            tga_to_png(src, dest / 'textures/skin' / name, texture_size, invert_green=invert, keep_alpha=alpha)
            slots[slot] = 'skin/' + name
            used.add(src.name)
    for f in sorted(skin_dir.iterdir()):      # eye/teeth/lash maps, the expression-driven maps and masks: not used by the static Godot scene
        if f.name not in used and f.suffix.lower() in ('.png', '.tga'):
            shutil.copy2(f, dest / 'textures/reference' / f.name.split('__', 1)[-1].replace('Maps__', '').replace('Masks__', 'mask_'))
    return slots


def rig_skin(pack, character):
    """Submit a metahuman-skin job to the rig, wait (up to 45 min) and return the collected result folder."""
    import rig_lane
    job = rig_lane.submit_skin(pack, character)
    deadline = time.time() + 45 * 60
    while time.time() < deadline:
        state = rig_lane.status(job)
        if state.startswith('complete'):
            out = rig_lane.collect(job)
            if out['status'] != 'PASS':
                raise SystemExit('rig skin job %s failed; see %s' % (job, out['dir']))
            return pathlib.Path(out['dir'])
        time.sleep(15)
    raise SystemExit('rig skin job %s did not finish within 45 minutes (it keeps running; collect it later with rig_lane.py)' % job)


def export_godot(pack, mhpkg, character, out_dir=None, texture_size=4096, skin_tone='0.78,0.60,0.50', skin_dir=None, use_rig=False):
    state_file = pack / 'metahuman-install.json'
    if not (pack / 'Content').is_dir() or not state_file.is_file():
        unpack(pack, mhpkg)
    state = json.loads(state_file.read_text())
    row = next((c for c in state['characters'] if c['object_path'] and ('/' + character + '/') in c['object_path']), None)
    if row is None:
        raise SystemExit('no character %s; have %s' % (character, [c['object_path'] for c in state['characters']]))
    asset = row['object_path'].rsplit('.', 1)[0]
    name = row['name']
    stamp = time.strftime('%Y%m%dT%H%M%S')
    plugins = 'MetaHumanCharacter,MetaHumanSDK,RigLogic'
    inputs = run_export_pack(pack, 'mh-%s-%s-godot' % (pack.name[:24], stamp),
                             ['--script', 'ue_metahuman.py', '--full-editor', '--accept-shutdown-crash', '--plugins', plugins,
                              '--request-extra', json.dumps({'op': 'export_godot_inputs', 'asset': asset})])
    if use_rig and not skin_dir:
        skin_dir = rig_skin(pack, character)
    textures = None if skin_dir else run_export_pack(pack, 'mh-%s-%s-tex' % (pack.name[:24], stamp), ['--classes', 'Texture2D', '--include', character])
    dest = pathlib.Path(out_dir) if out_dir else OUT_ROOT / pack.name / character / 'godot'
    if dest.exists():
        raise SystemExit('%s exists; choose a new --out or remove it' % dest)
    for sub in ('meshes', 'dna', 'textures'):
        (dest / sub).mkdir(parents=True)
    parts = inputs / 'parts'
    meshes = sorted((parts / 'meshes').glob('*.glb'))
    if len(meshes) < 3:
        raise SystemExit('expected head, body and full-body meshes, found %d' % len(meshes))
    for f in meshes:
        cleaned, removed = clean_glb(f.read_bytes())
        cleaned, renormalised = fix_normals(cleaned)
        if renormalised:
            print('  %s: recomputed vertex normals on %d surface(s) (the export\'s normals disagreed with the mesh)' % (f.name, renormalised))
        (dest / 'meshes' / f.name).write_bytes(cleaned)
    for f in sorted((parts / 'dna').rglob('*.dna')):
        shutil.copy2(f, dest / 'dna' / f.name)
    head_glb = next(f.name for f in meshes if f.name.endswith('_Head.glb'))
    # The neck-cut body, not the full-body mesh: FullBody carries its own head, which would sit inside the separate head mesh and z-fight with it.
    body_glb = next((f.name for f in meshes if f.name.endswith('_Body.glb') and not f.name.endswith('_FullBody.glb')), None) \
        or next(f.name for f in meshes if f.name.endswith('_FullBody.glb'))
    converted, slots = {}, {}
    if skin_dir:
        slots = merge_skin(skin_dir, dest, texture_size)
        converted = {v: (dest / 'textures' / v).stat().st_size for v in slots.values()}
    else:
        for f in sorted((textures / 'exported').rglob('*.tga')):
            png = dest / 'textures' / (f.stem + '.png')
            converted[png.name] = tga_to_png(f, png, texture_size, invert_green='Normal' in f.stem)
        for slot, suffix in (('normal_head', '_Normal_Head.png'), ('normal_body', '_Normal_Body.png')):
            found = next((n for n in converted if n.endswith(suffix)), None)
            if found:
                slots[slot] = found
    order = ['albedo_head', 'normal_head', 'roughness_head', 'albedo_body', 'normal_body', 'roughness_body', 'eye_color', 'eye_normal', 'teeth_color', 'teeth_normal', 'lashes_color']
    resources = ['[ext_resource type="Texture2D" path="res://metahuman/%s/textures/%s" id="tex_%s"]' % (name, slots[k], k) for k in order if k in slots]
    properties = ['%s = ExtResource("tex_%s")' % (k, k) for k in order if k in slots]
    roles = classify_head_surfaces(primitive_stats((dest / 'meshes' / head_glb).read_bytes()))
    if roles and skin_dir:
        properties += ['head_surface_roles = PackedStringArray(%s)' % ', '.join('"%s"' % r['role'] for r in roles),
                       'head_surface_verts = PackedInt32Array(%s)' % ', '.join(str(r['verts']) for r in roles)]
    r, g, b = [float(x) for x in skin_tone.split(',')]
    for src in sorted(GODOT_FILES.iterdir()):
        text = src.read_text()
        for k, v in {'@NAME@': name, '@HEAD_GLB@': head_glb, '@BODY_GLB@': body_glb, '@STEPS@': str(4 + len(resources)),
                     '@TEXTURE_RESOURCES@': '\n'.join(resources), '@TEXTURE_PROPERTIES@': '\n'.join(properties),
                     '@SKIN@': 'Color(%g, %g, %g, 1)' % (r, g, b)}.items():
            text = text.replace(k, v)
        (dest / src.name.replace('character.tscn', name + '.tscn')).write_text(text)
    limitations = ['Facial animation is joint + corrective-driven by RigLogic (the .dna files); Godot has no RigLogic, so the face is a static neutral pose that follows the body skeleton.',
                   'Hair strands (grooms) are not exported; this editable character has none.']
    if skin_dir:
        limitations = ['Skin, eye, teeth and lash maps come from the rig\'s GPU export (Epic TextureGraph). Roughness is read from the green channel of the SRMF map and normals are green-flipped for Godot: both are assumptions to confirm visually.',
                       'Head surfaces are identified from their geometry (the glTF has no names): skin, teeth, two eyes, eyelashes, and the remaining thin shells (saliva, eye shell, eye edge, cartilage) are made nearly transparent so they cannot hide the eyes. %s' % ('Roles: ' + ', '.join('%d=%s' % (r['index'], r['role']) for r in roles) + '.' if roles else 'The roles could not be identified for this mesh, so only the largest surface is skinned.'),
                       'The expression-driven maps (CM1-3, WM1-3) and masks are kept under textures/reference only: Godot has no RigLogic.'] + limitations
    else:
        limitations.insert(0, 'No skin job was used: the scene has a flat skin_tone plus the stored normal maps. Re-run with --skin-dir/--rig-skin for real skin textures.')
    manifest = {'schema': 1, 'pack': pack.name, 'mhpkg_sha256': state['mhpkg_sha256'], 'character': name, 'source_asset': asset,
                'unreal_stages': [inputs.name] + ([textures.name] if textures else []), 'skin_source': str(skin_dir) if skin_dir else None,
                'meshes': [f.name for f in meshes], 'textures': converted, 'texture_slots': slots,
                'dna': sorted(p.name for p in (dest / 'dna').iterdir()), 'texture_size': texture_size, 'limitations': limitations,
                'godot_use': 'Copy this folder into your project (e.g. res://metahuman/%s/) and instance %s.tscn.' % (name, name)}
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return {'godot_folder': str(dest), **{k: manifest[k] for k in ('meshes', 'textures', 'dna', 'limitations')}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for c in ('inspect', 'unpack'):
        s = sub.add_parser(c)
        s.add_argument('pack')
        if c == 'unpack':
            s.add_argument('--force', action='store_true')
    s = sub.add_parser('export-godot')
    s.add_argument('pack')
    s.add_argument('character')
    s.add_argument('--out')
    s.add_argument('--texture-size', type=int, default=4096)
    s.add_argument('--skin-tone', default='0.78,0.60,0.50')
    sk = s.add_mutually_exclusive_group()
    sk.add_argument('--skin-dir')
    sk.add_argument('--rig-skin', action='store_true')
    s = sub.add_parser('copy-to-project')
    s.add_argument('pack')
    s.add_argument('project_dir')
    a = ap.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root')
    pack, mhpkg = find_pack(a.pack)
    if a.cmd == 'inspect':
        out = inspect(pack, mhpkg)
    elif a.cmd == 'unpack':
        out = unpack(pack, mhpkg, a.force)
    elif a.cmd == 'export-godot':
        out = export_godot(pack, mhpkg, a.character, a.out, a.texture_size, a.skin_tone, a.skin_dir, a.rig_skin)
    else:
        out = copy_to_project(pack, a.project_dir)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
