"""Convert purchased FBX files to self-contained GLB, relinking textures the FBX points at on the author's machine.

Purchased packs often embed absolute texture paths such as C:/Users/<author>/.../Color2.png. Godot then fails with
"Can't open file from path 'res://../../Users/...'". Never byte-patch the FBX; run this instead, then import the GLB.

Run through the game worker (operation "blender", script "skill:blender-export-pipelines/scripts/fbx_relink_to_glb.py"):
  args: ["--input", "Assets/arena/apocalypse", "--textures", "Assets/arena/apocalypse,Assets/textures",
         "--output", "{out}"]  [--map Color2.png=Assets/arena/apocalypse/T_Color2.tga ...] [--no-recursive]
--input is one .fbx or a folder of them. Each missing image is resolved by file name in the --textures folders:
exact name, then same name with any image extension, then with/without a T_ prefix (case-insensitive). If more than
one file matches, nothing is guessed: the image is reported as ambiguous and you add --map NAME=PATH.
Writes <output>/<relative path>.glb (textures embedded) and prints @@JSON@@ with relinked/missing/ambiguous per file.
"""
import argparse, json, pathlib, sys
import bpy

IMAGE_EXT = ('.png', '.tga', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.exr', '.webp')


def args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser(prog='fbx_relink_to_glb.py')
    p.add_argument('--input', required=True);p.add_argument('--output', required=True)
    p.add_argument('--textures', default='', help='comma-separated folders searched for texture files')
    p.add_argument('--map', action='append', default=[], help='IMAGE_NAME=PATH for an image the search cannot decide')
    p.add_argument('--no-recursive', action='store_true')
    return p.parse_args(argv)


def norm(name):
    stem = pathlib.PurePath(name).stem.lower()
    return stem[2:] if stem.startswith('t_') else stem


def index(folders, recursive):
    files = []
    for folder in folders:
        root = pathlib.Path(folder)
        if not root.is_dir(): raise SystemExit('texture folder not found: ' + folder)
        files += [x for x in (root.rglob('*') if recursive else root.iterdir()) if x.is_file() and x.suffix.lower() in IMAGE_EXT]
    return files


def candidates(raw, files):
    """raw is the path stored in the FBX, possibly a Windows path or garbage bytes."""
    name = raw.replace('\\', '/').rsplit('/', 1)[-1].strip()
    if not name or not name.isprintable(): return name, []
    exact = [x for x in files if x.name.lower() == name.lower()]
    if exact: return name, exact
    same = [x for x in files if x.stem.lower() == pathlib.PurePath(name).stem.lower()]
    if same: return name, same
    return name, [x for x in files if norm(x.name) == norm(name)]


def import_fbx(path):
    for obj in list(bpy.data.objects): bpy.data.objects.remove(obj, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.actions, bpy.data.armatures):
        for item in list(coll): coll.remove(item)
    if hasattr(bpy.ops.wm, 'fbx_import'): bpy.ops.wm.fbx_import(filepath=str(path))
    else: bpy.ops.import_scene.fbx(filepath=str(path))


def convert(fbx, out, files, mapping):
    import_fbx(fbx)
    report = {'input': str(fbx), 'output': str(out), 'relinked': {}, 'missing': [], 'ambiguous': {}, 'already_ok': 0}
    for image in bpy.data.images:
        if image.source != 'FILE' or image.packed_file: continue
        current = pathlib.Path(bpy.path.abspath(image.filepath))
        if image.filepath and current.is_file(): report['already_ok'] += 1;continue
        name, found = candidates(image.filepath or image.name, files)
        if name in mapping or image.name in mapping: found = [pathlib.Path(mapping.get(name) or mapping[image.name])]
        if len(found) == 1:
            image.filepath = str(found[0].resolve());image.reload();report['relinked'][name or image.name] = str(found[0])
        elif found: report['ambiguous'][name or image.name] = [str(x) for x in found[:10]]
        else: report['missing'].append(name or repr(image.filepath))
    report.update(objects=len(bpy.data.objects), meshes=len(bpy.data.meshes), armatures=len(bpy.data.armatures),
                  actions=[a.name for a in bpy.data.actions][:50], materials=len(bpy.data.materials))
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out), export_format='GLB', export_image_format='AUTO', export_animations=True, export_apply=False)
    report['ok'] = out.is_file() and not report['missing'] and not report['ambiguous']
    return report


def main():
    a = args()
    mapping = {}
    for item in a.map:
        if '=' not in item: raise SystemExit('--map needs IMAGE_NAME=PATH, got ' + item)
        k, v = item.split('=', 1)
        if not pathlib.Path(v).is_file(): raise SystemExit('--map target not found: ' + v)
        mapping[k] = v
    source = pathlib.Path(a.input);output = pathlib.Path(a.output)
    if source.is_file(): todo = [(source, output / (source.stem + '.glb') if output.suffix.lower() != '.glb' else output)]
    elif source.is_dir():
        todo = [(x, output / x.relative_to(source).with_suffix('.glb')) for x in sorted(source.rglob('*') if not a.no_recursive else source.iterdir())
                if x.is_file() and x.suffix.lower() == '.fbx']
    else: raise SystemExit('--input not found: ' + a.input)
    if not todo: raise SystemExit('no .fbx files under ' + a.input)
    files = index([x for x in a.textures.split(',') if x] or [str(source if source.is_dir() else source.parent)], not a.no_recursive)
    results = []
    for fbx, out in todo:
        try: results.append(convert(fbx, out, files, mapping))
        except Exception as e: results.append({'input': str(fbx), 'ok': False, 'error': str(e)[:300]})
    summary = {'ok': all(r.get('ok') for r in results), 'converted': sum(1 for r in results if 'error' not in r), 'files': len(results),
               'needs_attention': [r for r in results if not r.get('ok')][:50], 'results': results[:200]}
    print('@@JSON@@' + json.dumps(summary))
    if not summary['converted']: raise SystemExit(1)


main()
