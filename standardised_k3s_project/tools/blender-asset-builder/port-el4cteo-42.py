#!/usr/bin/env python3
# Reproducible scoped Blender 4.2 port of pinned EL4CTEO 71d031d (original preserved).
import pathlib,re,sys,json,hashlib
p=pathlib.Path(sys.argv[1]).resolve()
def edit(n,old,new):
 f=p/n;s=f.read_text();assert old in s,(n,old);f.write_text(s.replace(old,new))
for f in list((p/'skills').rglob('*.py'))+list((p/'tests').glob('*.py')):
 s=f.read_text();lines=[]
 for line in s.splitlines(True):
  lines.append(line)
  m=re.match(r'^(\s*)([A-Za-z_][\w.]*) = .*bpy.data.(?:materials|worlds).new\(',line)
  if m:lines.append(m[1]+m[2]+'.use_nodes = True  # WatooM Blender 4.2 compatibility\n')
 f.write_text(''.join(lines))
for f in (p/'skills').rglob('*.py'):
 s=f.read_text()
 s=re.sub(r'^(\s*)(nt|wt) = (mat|world|w|slot.material).node_tree$',r'\1\3.use_nodes = True\n\1\2 = \3.node_tree',s,flags=re.M)
 s=s.replace('device="GPU"','device="AUTO"').replace('default="GPU", choices=["GPU", "CPU"]','default="AUTO", choices=["AUTO", "GPU", "OPTIX", "CPU"]')
 s=s.replace('s.media_type = media  # 5.0+: must precede file_format','if hasattr(s, "media_type"):\n        s.media_type = media')
 s=s.replace('r.image_settings.media_type = "IMAGE"','if hasattr(r.image_settings, "media_type"):\n            r.image_settings.media_type = "IMAGE"')
 f.write_text(s)
for n,fn in [('blender-texture-baking','_set_device'),('blender-rendering','_gpu')]:
 f=p/'skills'/n/'scripts'/('bake_maps.py' if n.endswith('baking') else 'render_batch.py')
 s=f.read_text();start=s.index('def '+fn+'(');end=s.index('\n\ndef ',start)
 s=s[:start]+f'def {fn}(sc, device):\n    return bx.configure_device(sc, device)'+s[end:];f.write_text(s)
edit('skills/blender-character-rigging/scripts/rig_check.py','verts[:: max(1, len(verts) // 2000)]','list(verts)[:: max(1, len(verts) // 2000)]')
n='skills/blender-animation/scripts/bake_action.py'
edit(n,'cbs = [cb for layer in a.layers for strip in layer.strips for cb in strip.channelbags]','cbs = [cb for layer in a.layers for strip in layer.strips for cb in strip.channelbags] if hasattr(a, "layers") else []')
edit(n,'[f"{s.target_id_type}:{s.name_display}" for s in a.slots]','[f"{s.target_id_type}:{s.name_display}" for s in a.slots] if hasattr(a, "slots") else []')
edit(n,'sum(len(cb.fcurves) for cb in cbs)','sum(len(cb.fcurves) for cb in cbs) if hasattr(a, "layers") else len(a.fcurves)')
edit(n,'a.use_cyclic','getattr(a, "use_cyclic", False)')
edit(n,'if ob.animation_data.action_slot is None:','if hasattr(ob.animation_data, "action_slot") and ob.animation_data.action_slot is None:')
edit(n,'if any(s.target_id_type == "OBJECT" for s in a.slots)','if (not hasattr(a, "slots") or any(s.target_id_type == "OBJECT" for s in a.slots))')
edit(n,'new.use_cyclic = getattr(a, "use_cyclic", False)','if hasattr(new, "use_cyclic"):\n            new.use_cyclic = getattr(a, "use_cyclic", False)')
n='skills/blender-geometry-nodes/scripts/gn_builder.py'
edit(n,'        item = getattr(mod.properties.inputs, ids[k])','''        if not hasattr(mod, "properties"):
            key = ids[k]
            attr = isinstance(v, str) and v.startswith("@")
            mod[key + "_use_attribute"] = attr
            if attr:
                mod[key + "_attribute_name"] = v[1:]
            else:
                mod[key] = bpy.data.objects.get(v, v) if isinstance(v, str) else v
            ob.update_tag()
            bpy.context.view_layer.update()
            continue
        item = getattr(mod.properties.inputs, ids[k])''')
n='skills/blender-export-pipelines/scripts/export_asset.py'
edit(n,'    out = bpy.path.abspath(out) if out else os.path.join(','''    operator = {"fbx": bpy.ops.export_scene.fbx, "gltf": bpy.ops.export_scene.gltf, "usd": bpy.ops.wm.usd_export}[fmt]
    properties = operator.get_rna_type().properties
    explicit = {item.split("=", 1)[0] for item in set or []}
    optional = {"export_meshopt_compression_enable", "export_textures_mode", "only_deform_bones", "export_shapekeys", "convert_orientation"}
    for key in list(kw):
        if key not in properties and key in optional and key not in explicit:
            warn.append(f"Blender {bpy.app.version_string}: optional preset option {key} unavailable; omitted")
            del kw[key]
    if "export_image_format" in kw and kw["export_image_format"] not in {x.identifier for x in properties["export_image_format"].enum_items} and "export_image_format" not in explicit:
        warn.append("Requested preset image encoding unavailable; using AUTO")
        kw["export_image_format"] = "AUTO"
    out = bpy.path.abspath(out) if out else os.path.join(''')
n='skills/blender-simulation/scripts/sim_setup.py'
edit(n,'    bx.object_mode()','    if gn_cloth and bpy.app.version < (5, 2, 0):\n        raise ValueError("UNSUPPORTED: Geometry Nodes cloth assets require Blender 5.2; use classic cloth on 4.2")\n    bx.object_mode()')
edit('tests/test_simulation.py','def test_gn_cloth_52_asset():','def test_gn_cloth_52_asset():\n    if bpy.app.version < (5, 2, 0):\n        from run_all import Skip\n        raise Skip("UNSUPPORTED on 4.2: built-in Geometry Nodes cloth requires 5.2")')
edit('tests/test_core.py','startswith(("5.", "6."))','startswith(("4.2.", "5.", "6."))')
edit('tests/test_core.py','"BLENDER_EEVEE" in r["engines"]','("BLENDER_EEVEE_NEXT" if bpy.app.version < (5, 0, 0) else "BLENDER_EEVEE") in r["engines"]')
n='skills/blender-core/references/bpy-patterns.md'
edit(n,'nt = mat.node_tree','mat.use_nodes = True\nnt = mat.node_tree')
edit(n,'getattr(mod.properties.inputs, sock.identifier).value = 2.0','if hasattr(mod, "properties"):\n    getattr(mod.properties.inputs, sock.identifier).value = 2.0\nelse:\n    mod[sock.identifier] = 2.0')
f=p/n;s=f.read_text();a=s.index('slot = ob.animation_data.action_slot');b=s.index('```',a)
s=s[:a]+'''for frame, x in ((1, 0.0), (24, 2.0)):
    ob.location = (x, 0, 0)
    ob.keyframe_insert("location", frame=frame)
'''+s[b:];f.write_text(s)
changes={str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.rglob('*')) if f.is_file() and '__pycache__' not in f.parts}
(p.parent/'ported-files.json').write_text(json.dumps(changes,indent=2))
print('PASS: compatibility port generated; runtime validation required')

# Follow-up API adaptations discovered by real 4.2 module tests.
edit('tests/test_geonodes.py','assert getattr(mod.properties.inputs, ident).value == 50','assert (getattr(mod.properties.inputs, ident).value if hasattr(mod, "properties") else mod[ident]) == 50')
edit('skills/blender-weather-fx/scripts/precipitation.py','        getattr(mod.properties.inputs, ids[k]).value = v','''        if hasattr(mod, "properties"):
            getattr(mod.properties.inputs, ids[k]).value = v
        else:
            mod[ids[k]] = v
    ob.update_tag()
    bpy.context.view_layer.update()''')
edit('skills/blender-weather-fx/scripts/surface_weather.py','return n.outputs["Factor"]','return n.outputs.get("Factor") or n.outputs["Fac"]')
edit('skills/blender-weather-fx/scripts/surface_weather.py','                getattr(md.properties.inputs, ids[k]).value = v','''                if hasattr(md, "properties"):
                    getattr(md.properties.inputs, ids[k]).value = v
                else:
                    md[ids[k]] = v
            o.update_tag()
            bpy.context.view_layer.update()''')
n='skills/blender-time-of-day/scripts/scene_mood.py'
edit(n,'bx.set_enum(sky, "sky_type", "MULTIPLE_SCATTERING")','bx.set_enum(sky, "sky_type", "NISHITA" if bpy.app.version < (5, 2, 0) else "MULTIPLE_SCATTERING")')
edit(n,'    cur = sc.compositing_node_group','''    if not hasattr(sc, "compositing_node_group"):
        sc.use_nodes = True
        nt = sc.node_tree
        if nt.name not in (GRADE, "Compositing Nodetree"):
            return "kept existing compositor tree"
        nt["watoom_grade"] = GRADE
        nt.nodes.clear()
        rl = nt.nodes.new("CompositorNodeRLayers")
        img = rl.outputs["Image"]
        if p["bloom"] > 0:
            g = nt.nodes.new("CompositorNodeGlare")
            g.glare_type, g.quality, g.threshold = "FOG_GLOW", "HIGH", ev_to_threshold
            g.mix = -1.0 + min(1.0, p["bloom"])
            nt.links.new(img, g.inputs["Image"])
            img = g.outputs["Image"]
        if p["saturation"] != 1.0:
            hs = nt.nodes.new("CompositorNodeHueSat")
            hs.inputs["Saturation"].default_value = p["saturation"]
            nt.links.new(img, hs.inputs["Image"])
            img = hs.outputs["Image"]
        output = nt.nodes.new("CompositorNodeComposite")
        nt.links.new(img, output.inputs["Image"])
        sc.render.use_compositing = True
        return GRADE
    cur = sc.compositing_node_group''')
edit(n,'    warnings = []','''    warnings = []
    if bpy.app.version < (5, 2, 0):
        warnings.append("Blender 4.2 uses Nishita sky; 5.2 irradiance table is approximate, not a calibrated 4.2 measurement")
        if p["white_point"] != 6500 and grade:
            warnings.append("Blender 4.2 compositor: white-point temperature grade unsupported; saturation and fog glow applied")''')
edit('tests/test_atmosphere.py','ng = bpy.context.scene.compositing_node_group','ng = bpy.context.scene.compositing_node_group if hasattr(bpy.context.scene, "compositing_node_group") else bpy.context.scene.node_tree')

edit('tests/test_atmosphere.py','assert ng.name == "ENV_Grade" and','assert (ng.name if hasattr(bpy.context.scene, "compositing_node_group") else ng.get("watoom_grade")) == "ENV_Grade" and')

edit('skills/blender-lighting-lookdev/scripts/turntable.py','    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)','    if not hasattr(ad, "action_slot"):\n        return list(ad.action.fcurves)\n    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)')

# Worker execution policy is shared across all component families.
import shutil
maintained=pathlib.Path(__file__).resolve().parents[2]/'ansible/roles/watoom-code/files/skills'
for family in (p/'skills').glob('blender-*'):
 scripts=family/'scripts'
 if not (scripts/'_bpyx.py').exists():continue
 for name in ('worker_profile.py','worker-profiles.json','_worker_runtime.py'):
  shutil.copy2(maintained/'blender-core/scripts'/name,scripts/name)
 helper=scripts/'_bpyx.py';code=helper.read_text()
 if 'from worker_profile import' not in code:helper.write_text(code+'\nfrom worker_profile import configure_device, verify_external, descriptor\n')
shutil.copy2(maintained/'blender-core/scripts/run_in_blender.py',p/'skills/blender-core/scripts/run_in_blender.py')

# The upstream test harness imports shared/_bpyx before family modules.
if (p/'shared/_bpyx.py').exists():
 for name in ('worker_profile.py','worker-profiles.json','_worker_runtime.py'):
  shutil.copy2(maintained/'blender-core/scripts'/name,p/'shared'/name)
 helper=p/'shared/_bpyx.py';code=helper.read_text()
 if 'from worker_profile import' not in code:helper.write_text(code+'\nfrom worker_profile import configure_device, verify_external, descriptor\n')
