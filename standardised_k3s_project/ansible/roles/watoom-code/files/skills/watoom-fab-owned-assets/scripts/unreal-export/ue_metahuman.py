"""Unreal-side MetaHuman stages (runs under UnrealEditor-Cmd -run=PythonScript, same sandbox as ue_export_assets.py).

Reads /job/request.json: {"op": "probe"|"assemble"|"export", "asset": "/Game/.../MHC_X" (probe/assemble), "root": "/Game/<Folder>", ...}.
Writes /job/native-result.json. The mounted pack Content is read-only; everything written goes under /job.
  probe    - what the headless MetaHuman API exposes, and what the character asset is (no changes)
"""
import os, unreal, json, pathlib, traceback, hashlib

JOB = pathlib.Path(os.environ.get('WLK_JOB_DIR', '/job'))  # the Linux sandbox mounts /job; the rig lane sets WLK_JOB_DIR
r = {'status': 'FAIL', 'scope': 'MetaHuman stage; pack content is read-only.'}


def mark(msg):
    """Stage marker: engine log plus a flushed file, so a native crash still shows how far we got."""
    unreal.log('WLK_STAGE ' + msg)
    with open(JOB / 'progress.log', 'a') as f:
        f.write(msg + '\n')


def names(obj, needle=None, limit=400):
    out = [n for n in dir(obj) if not n.startswith('_') and (needle is None or needle in n.lower())]
    return out[:limit]


def props(asset):
    out = {}
    for n in names(asset):
        try:
            v = asset.get_editor_property(n)
        except Exception:
            continue
        out[n] = repr(v)[:160]
    return out


def probe(req):
    r['engine'] = unreal.SystemLibrary.get_engine_version()
    r['metahuman_api'] = [n for n in dir(unreal) if 'metahuman' in n.lower()]
    asset = unreal.load_asset(req['asset'])
    if asset is None:
        raise ValueError('load failed: ' + req['asset'])
    r['asset_class'] = asset.get_class().get_path_name()
    r['asset_properties'] = props(asset)
    r['asset_methods'] = [n for n in names(asset) if callable(getattr(asset, n, None))][:200]
    subs = {}
    for n in r['metahuman_api']:
        cls = getattr(unreal, n)
        if 'subsystem' in n.lower() or 'library' in n.lower():
            subs[n] = names(cls)[:120]
    r['subsystems'] = subs
    r['status'] = 'PROBE_DONE'


def docs(req):
    """Signatures/docs of named symbols ("Class" or "Class.method") plus whether the character can be built here."""
    out = {}
    for sym in req['symbols']:
        obj = unreal
        try:
            for part in sym.split('.'):
                obj = getattr(obj, part)
            out[sym] = {'doc': (obj.__doc__ or '')[:1800], 'members': [n for n in dir(obj) if not n.startswith('_')][:80] if isinstance(obj, type) else None}
        except Exception as e:
            out[sym] = {'error': str(e)[:200]}
    r['docs'] = out
    asset = unreal.load_asset(req['asset'])
    sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
    checks = {}
    for fn in ('can_build_meta_human', 'is_requesting_auto_rigging', 'is_auto_rigging_in_progress', 'get_face_state', 'has_face_dna', 'is_rigged'):
        f = getattr(sub, fn, None)
        if f is None:
            continue
        try:
            checks[fn] = repr(f(asset))[:200]
        except Exception as e:
            checks[fn] = 'ERR ' + str(e)[:200]
    r['subsystem_checks'] = checks
    r['subsystem_methods'] = [n for n in dir(sub) if not n.startswith('_')]
    r['status'] = 'PROBE_DONE'


def why(req):
    """Why can this character not be built here? Opens it for edit (in memory only) and asks the engine to log the reason."""
    asset = unreal.load_asset(req['asset'])
    sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
    out = {}
    for fn in ('try_add_object_to_edit', 'is_object_added_for_editing', 'is_character_valid'):
        f = getattr(sub, fn, None)
        if f is None:
            out[fn] = 'absent'
            continue
        try:
            out[fn] = repr(f(asset))[:200]
        except Exception as e:
            out[fn] = 'ERR ' + str(e)[:200]
    unreal.log('WLK_WHY begin')
    try:
        out['can_build'] = sub.can_build_meta_human(asset, True)
    except Exception as e:
        out['can_build'] = 'ERR ' + str(e)[:300]
    unreal.log('WLK_WHY end')
    for fn in ('has_face_dna', 'has_body_dna', 'get_rig_type', 'is_rigged', 'get_character_rig_type'):
        f = getattr(sub, fn, None)
        if f is not None:
            try:
                out[fn] = repr(f(asset))[:200]
            except Exception as e:
                out[fn] = 'ERR ' + str(e)[:200]
    out['rig_methods'] = [n for n in dir(sub) if any(w in n for w in ('rig', 'dna', 'edit', 'valid', 'state'))]
    r['why'] = out
    r['status'] = 'PROBE_DONE'


def open_for_edit(req):
    """Load the character and register it for editing (in memory; the mounted pack is never written). Returns (asset, subsystem)."""
    asset = unreal.load_asset(req['asset'])
    if asset is None:
        raise ValueError('load failed: ' + req['asset'])
    sub = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
    if not sub.try_add_object_to_edit(asset):
        raise ValueError('character could not be opened for editing')
    if not sub.can_build_meta_human(asset, True):
        raise ValueError('character is not ready for assembly (rig missing?); see the log')
    return asset, sub


def files_under(folder):
    rows = []
    for f in sorted(pathlib.Path(folder).rglob('*')):
        if f.is_file():
            rows.append({'file': str(f.relative_to(JOB)), 'bytes': f.stat().st_size, 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()})
    return rows


def export_dcc(req):
    """Epic's DCC package (meshes, textures, DNA for Maya/Blender): the source for the Godot route."""
    asset, sub = open_for_edit(req)
    out = JOB / 'dcc'
    out.mkdir(exist_ok=True)
    params = unreal.MetaHumanDCCExportParams()
    for k, v in {'archive_name': req.get('name') or asset.get_name(), 'bake_make_up': bool(req.get('bake_makeup', False)),
                 'compress_in_zip_file': False, 'external_path': str(out)}.items():
        params.set_editor_property(k, v)
    unreal.MetaHumanCharacterExportBlueprintLibrary.export_dcc(asset, params)
    rows = files_under(out)
    if not rows:
        raise ValueError('export_dcc wrote nothing')
    r.update(op='export_dcc', files=rows, status='METAHUMAN_PASS')


def export_dna(req):
    asset, sub = open_for_edit(req)
    out = JOB / 'dna'
    out.mkdir(exist_ok=True)
    params = unreal.MetaHumanDNAExportParams()
    for k, v in {'dna_head': True, 'dna_body': True, 'external_path': str(out)}.items():
        params.set_editor_property(k, v)
    unreal.MetaHumanCharacterExportBlueprintLibrary.export_dna(asset, params)
    rows = files_under(out)
    if not rows:
        raise ValueError('export_dna wrote nothing')
    r.update(op='export_dna', files=rows, status='METAHUMAN_PASS')


def build(req):
    """Assemble to a standard MetaHuman (skeletal meshes, grooms, materials) as Unreal assets under an absolute folder."""
    asset, sub = open_for_edit(req)
    out = JOB / 'built'
    out.mkdir(exist_ok=True)
    params = unreal.MetaHumanCharacterEditorBuildParameters()
    params.set_editor_property('pipeline_type', getattr(unreal.MetaHumanDefaultPipelineType, req.get('pipeline', 'OPTIMIZED')))
    params.set_editor_property('pipeline_quality', getattr(unreal.MetaHumanQualityLevel, req.get('quality', 'HIGH')))
    params.set_editor_property('absolute_build_path', str(out))
    sub.build_meta_human(asset, params)
    rows = files_under(out)
    if not rows:
        raise ValueError('build wrote nothing')
    r.update(op='build', files=rows, status='METAHUMAN_PASS')


def export_texture(tex, target_base):
    """Texture2D -> PNG (falls back to TGA); returns the written path or None."""
    for suffix in ('.png', '.tga'):
        target = pathlib.Path(str(target_base) + suffix)
        task = unreal.AssetExportTask()
        for k, v in {'object': tex, 'filename': str(target), 'automated': True, 'prompt': False, 'replace_identical': True}.items():
            task.set_editor_property(k, v)
        try:
            ok = unreal.Exporter.run_asset_export_task(task)
        except Exception:
            ok = False
        if ok and target.is_file() and target.stat().st_size:
            return target
    return None


def gltf_options():
    o = unreal.GLTFExportOptions()
    for key, value in [('bake_material_inputs', getattr(unreal.GLTFMaterialBakeMode, 'DISABLED', None)), ('export_vertex_skin_weights', True),
                       ('export_animation_sequences', False), ('export_morph_targets', True), ('export_mesh_quantization', False),
                       ('texture_image_format', getattr(unreal.GLTFTextureImageFormat, 'NONE', None))]:
        if value is None:
            continue
        try:
            o.set_editor_property(key, value)
        except Exception:
            pass
    return o


def export_godot_inputs(req):
    """Headless inputs for Godot: skeletal meshes as GLB (head, body, full body), the character's base texture maps, and the DNA files.
    Epic's baked material textures need the TextureGraph (a graphics device); the stored base maps do not."""
    mark('open')
    asset, sub = open_for_edit(req)
    notes = []
    mark('opened; export_geometry')
    # 1) geometry -> in-memory skeletal mesh assets -> GLB
    project_path = '/Game/WLK_MH_Export'
    gp = unreal.MetaHumanGeometryExportParams()
    for k, v in {'head_skeletal_mesh': True, 'body_skeletal_mesh': True, 'full_body_skeletal_mesh': True, 'overwrite_existing_assets': True, 'project_path': project_path}.items():
        gp.set_editor_property(k, v)
    unreal.MetaHumanCharacterExportBlueprintLibrary.export_geometry(asset, gp)
    mark('export_geometry done')
    glb = JOB / 'parts' / 'meshes'
    glb.mkdir(parents=True, exist_ok=True)
    found = []
    try:
        found = list(unreal.EditorAssetLibrary.list_assets(project_path, recursive=True, include_folder=False))
    except Exception as e:
        notes.append('list_assets: ' + str(e)[:200])
    meshes = []
    for path in found:
        obj = unreal.load_asset(path)
        if obj is None or obj.get_class().get_name() != 'SkeletalMesh':
            continue
        target = glb / (obj.get_name() + '.glb')
        try:
            ok = unreal.GLTFExporter.export_to_gltf(obj, str(target), gltf_options(), set())
            ok = ok[0] if isinstance(ok, tuple) else ok
        except Exception as e:
            ok = False
            notes.append('gltf %s: %s' % (obj.get_name(), str(e)[:200]))
        if ok and target.is_file():
            meshes.append(target.name)
    r['mesh_assets_seen'] = found
    mark('glb done: %d meshes' % len(meshes))
    # 2) textures: the character's synthesized/composited skin maps are generated at edit time (CPU texture synthesis, then the
    #    GPU TextureGraph) and carry no exportable source data - exporting them asserts in the engine. Stored textures
    #    (T_*_Normal_*) are exported separately with the normal Texture2D path; see metahuman_unreal.py.
    textures = []
    notes.append('skin base-colour/composited maps need a graphics device (TextureGraph); not produced headlessly')
    # 3) DNA
    dna = JOB / 'parts' / 'dna'
    dna.mkdir(parents=True, exist_ok=True)
    dp = unreal.MetaHumanDNAExportParams()
    for k, v in {'dna_head': True, 'dna_body': True, 'external_path': str(dna)}.items():
        dp.set_editor_property(k, v)
    unreal.MetaHumanCharacterExportBlueprintLibrary.export_dna(asset, dp)
    rows = files_under(JOB / 'parts')
    r.update(op='export_godot_inputs', files=rows, meshes=meshes, textures=textures, notes=notes)
    r['status'] = 'METAHUMAN_PASS' if len(meshes) >= 3 and any(f['file'].endswith('.dna') for f in rows) else 'METAHUMAN_PARTIAL' if rows else 'FAIL'


def tex_info(req):
    """Metadata of the character's stored texture maps (no export, so no exporter assertion)."""
    asset = unreal.load_asset(req['asset'])
    out = {}
    for prop in ('synthesized_face_textures', 'body_textures', 'synthesized_face_textures_info', 'high_res_body_textures_info'):
        rows = {}
        try:
            mapping = dict(asset.get_editor_property(prop).items())
        except Exception as e:
            out[prop] = 'ERR ' + str(e)[:200]
            continue
        for key, val in mapping.items():
            row = {'value': repr(val)[:300]}
            if isinstance(val, unreal.Texture2D):
                row['class'] = val.get_class().get_name()
                for q in ('compression_settings', 'srgb', 'mip_gen_settings', 'lod_group', 'virtual_texture_streaming', 'never_stream', 'source_color_settings'):
                    try:
                        row[q] = repr(val.get_editor_property(q))[:80]
                    except Exception:
                        pass
                try:
                    row['size'] = [val.blueprint_get_size_x(), val.blueprint_get_size_y()]
                except Exception:
                    pass
                try:
                    row['path'] = val.get_path_name()
                except Exception:
                    pass
            rows[str(key)] = row
        out[prop] = rows
    r['textures_info'] = out
    r['status'] = 'PROBE_DONE'


try:
    req = json.loads((JOB / 'request.json').read_text())
    {'probe': probe, 'docs': docs, 'why': why, 'export_dcc': export_dcc, 'export_godot_inputs': export_godot_inputs, 'tex_info': tex_info, 'export_dna': export_dna, 'build': build}[req['op']](req)
except Exception:
    r['error'] = traceback.format_exc()
(JOB / 'native-result.json').write_text(json.dumps(r, indent=2))
try:
    unreal.SystemLibrary.execute_console_command(None, 'QUIT_EDITOR')
except Exception:
    pass
if r['status'] == 'FAIL':
    raise RuntimeError(r.get('error', 'MetaHuman stage failed'))
