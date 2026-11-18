"""Read-only bounded pack inspection; execute in an isolated Unreal Python commandlet."""
import unreal,pathlib,json,collections,hashlib,traceback
root=pathlib.Path(unreal.Paths.project_dir())
request=json.loads((root/"inspection-request.json").read_text())
receipt={"schema":1,"status":"RUNNING","version":unreal.SystemLibrary.get_engine_version(),"meshes":[]}
try:
    assert len(request["meshes"])<=24
    registry=unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous(["/Game"],True)
    assets=registry.get_assets_by_path("/Game",recursive=True)
    assert len(assets)<=20000,"Pack metadata budget exceeded"
    receipt["asset_classes"]=dict(collections.Counter(str(a.asset_class_path.package_name)+"."+str(a.asset_class_path.asset_name) for a in assets))
    receipt["blueprints"]=[str(a.package_name) for a in assets if str(a.asset_class_path.asset_name) in ("Blueprint","PCGGraph")][:256]
    options=unreal.AssetRegistryDependencyOptions()
    for relative in request["meshes"]:
        source=root/"Content"/relative
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        package="/Game/"+str(pathlib.PurePosixPath(relative).with_suffix(""))
        obj=package+"."+pathlib.PurePosixPath(package).name
        mesh=unreal.load_asset(obj)
        assert isinstance(mesh,unreal.StaticMesh),obj
        bounds=mesh.get_bounding_box()
        materials=mesh.get_editor_property("static_materials")
        pending=[package];visited=set();dependencies=[]
        while pending:
            current=pending.pop()
            if current in visited:continue
            visited.add(current)
            if len(visited)>256:raise RuntimeError("Selected dependency closure exceeded256packages")
            for name in registry.get_dependencies(current,options):
                name=str(name)
                if name.startswith("/Game/") and name not in visited:pending.append(name)
                elif not name.startswith(("/Game/","/Engine/","/Script/")):dependencies.append(name)
        # Commandlets do not initialize editor subsystems; inspect saved physics data.
        body=mesh.get_editor_property("body_setup")
        if body:
            geometry=body.get_editor_property("agg_geom")
            shapes={name:len(geometry.get_editor_property(name)) for name in ("box_elems","sphere_elems","sphyl_elems","convex_elems")}
            complexity=str(body.get_editor_property("collision_trace_flag"))
        else:shapes={};complexity="NO_BODY_SETUP"
        receipt["meshes"].append({"path":obj,"source":relative,"sha256":before,
            "min_cm":[bounds.min.x,bounds.min.y,bounds.min.z],"max_cm":[bounds.max.x,bounds.max.y,bounds.max.z],
            "simple_collision_count":sum(shapes.values()),"collision_shapes":shapes,
            "collision_complexity":complexity,
            "lods":mesh.get_num_lods(),"triangles":mesh.get_num_triangles(0),
            "nanite_triangles":mesh.get_num_nanite_triangles(),
            "materials":[str(m.material_interface.get_path_name()) if m.material_interface else None for m in materials],
            "game_dependencies":sorted(visited),"external_dependencies":sorted(set(dependencies)),
            "source_unchanged":before==hashlib.sha256(source.read_bytes()).hexdigest()})
    assert all(x["source_unchanged"] for x in receipt["meshes"])
    receipt["status"]="PASS"
except Exception:
    receipt["status"]="FAIL";receipt["error"]=traceback.format_exc()
finally:
    (root/"pack-inspection.json").write_text(json.dumps(receipt,indent=2))
    print("WATOOM_PACK_INSPECTION_"+receipt["status"])
    if receipt["status"]!="PASS":raise RuntimeError(receipt.get("error","Inspection failed"))
