"""Load a source snapshot with explicitly transferred and remapped dependencies."""
import json, pathlib, posixpath, urllib.parse
import bpy

def owner_path(library, original_source, reverse, depth=0):
    if library is None:return original_source
    if depth>12:raise ValueError('Library dependency depth')
    value=library.filepath.replace('\\','/')
    if value in reverse:return reverse[value]
    if value.startswith('//') or not value.startswith('/') and not (len(value)>1 and value[1]==':'):
        base=owner_path(library.parent,original_source,reverse,depth+1)
        return posixpath.normpath(posixpath.join(posixpath.dirname(base),value[2:] if value.startswith('//') else value))
    return posixpath.normpath(value)

def original_path(value, original_source, library=None, reverse=None):
    value=value.replace('\\','/');reverse=reverse or {}
    if value in reverse:return reverse[value]
    if value.startswith('//') or not value.startswith('/') and not (len(value)>1 and value[1]==':'):
        base=owner_path(library,original_source,reverse)
        return posixpath.normpath(posixpath.join(posixpath.dirname(base),value[2:] if value.startswith('//') else value))
    return posixpath.normpath(value)

def open_source(request):
    source=pathlib.Path(request['manifest']['source']);mapping=request.get('dependency_map',{})
    if source.suffix.lower()=='.blend':
        bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
        # Libraries must be relocated before images and scene inventory are evaluated.
        for _ in range(12):
            changed=False
            reverse={v.replace('\\','/'):k for k,v in mapping.items()}
            for library in list(bpy.data.libraries):
                origin=original_path(library.filepath,request['original_source'],library.parent,reverse)
                target=mapping.get(origin)
                if target and pathlib.Path(bpy.path.abspath(library.filepath,library=library.parent))!=pathlib.Path(target):
                    p=pathlib.Path(target)
                    bpy.ops.wm.lib_relocate(library=library.name,directory=str(p.parent),filename=p.name)
                    changed=True
            if not changed:break
        reverse={v.replace('\\','/'):k for k,v in mapping.items()}
        for image in bpy.data.images:
            if image.packed_file or image.source not in ('FILE','TILED','SEQUENCE'):continue
            origin=original_path(image.filepath,request['original_source'],image.library,reverse)
            target=mapping.get(origin)
            if target:image.filepath=target;image.reload()
    else:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
        bpy.ops.import_scene.gltf(filepath=str(source))

def dependencies(request):
    open_source(request);items=[];mapping=request.get('dependency_map',{});reverse={v.replace('\\','/'):k for k,v in mapping.items()}
    for library in bpy.data.libraries:
        if not library.packed_file:
            name=original_path(library.filepath,request['original_source'],library.parent,reverse)
            items.append({'path':name,'kind':'library'})
    for image in bpy.data.images:
        if image.packed_file or image.source not in ('FILE','TILED','SEQUENCE'):continue
        name=original_path(image.filepath,request['original_source'],image.library,reverse)
        # A mapped sequence/UDIM stem remains mapped as a stem in the next probe.
        if name in mapping:continue
        items.append({'path':name,'kind':image.source.lower()})
    return items

if __name__=='__main__':
    import sys
    plan=pathlib.Path(sys.argv[sys.argv.index('--')+1]);request=json.loads(plan.read_text())
    (plan.parent/'dependencies.json').write_text(json.dumps(dependencies(request),indent=2))
