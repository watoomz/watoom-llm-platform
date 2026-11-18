"""Bounded read-only native format probe. Does not certify shader fidelity or gameplay."""
import unreal,pathlib,json,collections,hashlib,traceback,struct
root=pathlib.Path(unreal.Paths.project_dir());receipt={"status":"RUNNING","engine":unreal.SystemLibrary.get_engine_version(),"meshes":[]}
try:
 registry=unreal.AssetRegistryHelpers.get_asset_registry();registry.scan_paths_synchronous(["/Game"],True)
 assets=registry.get_assets_by_path("/Game",recursive=True);assert len(assets)<=20000,"Pack metadata budget"
 receipt["asset_classes"]=dict(collections.Counter(str(a.asset_class_path.asset_name) for a in assets))
 meshes=sorted([a for a in assets if str(a.asset_class_path.asset_name)=="StaticMesh"],key=lambda a:str(a.package_name))
 # Choose small ordinary meshes; huge showcase scenes are not needed for format acceptance.
 meshes=sorted(meshes,key=lambda a:(0 if any(w in str(a.package_name).lower() for w in ("floor","wall","brick","chair")) else 1,len(str(a.package_name)),str(a.package_name)))[:2]
 if not meshes:
  dynamic=[a for a in assets if str(a.asset_class_path.asset_name) in ("GeometryCache","NiagaraSystem","SkeletalMesh","AnimSequence")]
  assert dynamic,"No supported native mesh/effect asset found"
  asset=dynamic[0];obj=unreal.load_asset(str(asset.package_name));assert obj is not None
  receipt.update(status="NATIVE_DYNAMIC_LOAD_PASS",dynamic_class=str(obj.get_class().get_name()),dynamic_asset=str(asset.package_name),portable_conversion="BLOCKED: GeometryCache/Niagara are outside the static GLTF exporter contract; a separate animation/effects bake is required",motion_validation="NOT TESTED")
 else:
  for asset in meshes:
   package=str(asset.package_name);path=root/"Content"/(package.removeprefix("/Game/")+".uasset")
   before=hashlib.sha256(path.read_bytes()).hexdigest();obj=unreal.load_asset(package);assert isinstance(obj,unreal.StaticMesh)
   bounds=obj.get_bounding_box();triangles=obj.get_num_triangles(0);assert triangles>0
   materials=obj.get_editor_property("static_materials");assert materials and all(m.material_interface is not None for m in materials),"Missing saved material references"
   assert before==hashlib.sha256(path.read_bytes()).hexdigest()
   receipt["meshes"].append({"package":package,"triangles":triangles,"lods":obj.get_num_lods(),"materials":[str(m.material_interface.get_path_name()) for m in materials],"source_sha256":before,"source_unchanged":True,"bounds_min":[bounds.min.x,bounds.min.y,bounds.min.z],"bounds_max":[bounds.max.x,bounds.max.y,bounds.max.z]})
   if len(receipt["meshes"])==1:
    options=unreal.GLTFExportOptions();options.set_editor_property("bake_material_inputs",unreal.GLTFMaterialBakeMode.DISABLED);options.set_editor_property("export_source_model",False)
    output=root/"geometry.glb";messages=unreal.GLTFExporter.export_to_gltf(obj,str(output),options,set())
    assert isinstance(messages,unreal.GLTFExportMessages);assert not list(messages.get_editor_property("errors"))
    blob=output.read_bytes();assert len(blob)<=64*1024**2 and struct.unpack_from("<4sII",blob)==(b"glTF",2,len(blob))
    document=json.loads(blob[20:20+struct.unpack_from("<I",blob,12)[0]]);assert document.get("meshes")
    receipt["glb"]={"sha256":hashlib.sha256(blob).hexdigest(),"bytes":len(blob),"meshes":len(document["meshes"]),"warnings":list(messages.get_editor_property("warnings"))}
  receipt.update(status="PASS",scope="Native sampled mesh/material references and portable geometry only; material baking disabled under NullRHI",material_render="NOT TESTED",whole_pack_certified=False)
except Exception:receipt.update(status="FAIL",error=traceback.format_exc())
finally:
 (root/"pack-native.json").write_text(json.dumps(receipt,indent=2))
 if receipt["status"]=="FAIL":raise RuntimeError(receipt["error"])
