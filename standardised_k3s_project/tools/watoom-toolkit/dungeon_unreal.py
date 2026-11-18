"""Native dungeon assembly and real collision/navigation QA in an isolated editor project.
Original pack namespaces must be staged or mounted read-only; this saves only GeneratedDungeon.
"""
import json,pathlib,math,hashlib,shutil,time,traceback

TAG="WATOOM_GENERATED_DUNGEON"

def assemble(unreal,plan,project):
    if plan.get("status")!="PREPARED_NOT_EXECUTED" or not 1<=len(plan.get("placements",[]))<=4096:
        raise ValueError("A bounded prepared dungeon assembly is required")
    project=pathlib.Path(project)
    identity=project/"native-assembly-identity.json"
    if identity.exists() and json.loads(identity.read_text()).get("plan_sha256")!=plan["plan_sha256"]:
        raise ValueError("Existing native project belongs to another dungeon plan")
    identity.write_text(json.dumps({"plan_sha256":plan["plan_sha256"]}))
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not levels or not actors:raise RuntimeError("Native editor subsystems are required")
    source=project/"Content/GeneratedDungeon/Dungeon.umap"
    if source.exists():
        shutil.copyfile(source,project/"dungeon-before.umap.snapshot")
        if not levels.load_level("/Game/GeneratedDungeon/Dungeon"):raise RuntimeError("Could not resume native map")
        for actor in actors.get_all_level_actors():
            if TAG in [str(t) for t in actor.tags]:actors.destroy_actor(actor)
    elif not levels.new_level("/Game/GeneratedDungeon/Dungeon"):
        raise RuntimeError("Could not create isolated native dungeon map")
    meshes={};placed=[]
    for index,item in enumerate(plan["placements"]):
        name=item["asset"]
        if name not in meshes:
            mesh=unreal.load_asset(name)
            if mesh is None or not isinstance(mesh,unreal.StaticMesh):
                raise RuntimeError("Missing or incompatible verified module: "+name)
            bounds=mesh.get_bounds()
            if any(not math.isfinite(x) or x<=0 for x in (bounds.box_extent.x,bounds.box_extent.y,bounds.box_extent.z)):
                raise RuntimeError("Invalid native module dimensions: "+name)
            meshes[name]=mesh
        rotation=item.get("rotation",[0,item["yaw"],0])
        actor=actors.spawn_actor_from_class(unreal.StaticMeshActor,
            unreal.Vector(*item["position"]),unreal.Rotator(pitch=rotation[0],yaw=rotation[1],roll=rotation[2]))
        if actor is None:raise RuntimeError("Actor creation failed")
        actor.tags=[TAG];actor.set_actor_label("Dungeon_%04d_%s"%(index,item["role"]))
        component=actor.static_mesh_component;component.set_static_mesh(meshes[name])
        actor.set_actor_scale3d(unreal.Vector(*item["scale"]))
        lod=item.get("lod",0)
        if not 0<=lod<meshes[name].get_num_lods():raise RuntimeError("Verified LOD unavailable")
        component.set_editor_property("forced_lod_model",lod+1)
        component.set_collision_profile_name("BlockAll")
        if component.get_num_materials()<1 or any(component.get_material(slot) is None for slot in range(component.get_num_materials())):
            raise RuntimeError("Module has unresolved native materials: "+name)
        actual_rotation=actor.get_actor_rotation()
        placed.append({"label":actor.get_actor_label(),"module":name,"role":item["role"],"lod":lod,
            "rotation_pitch_yaw_roll":[actual_rotation.pitch,actual_rotation.yaw,actual_rotation.roll]})
    for room in plan["layout"]["rooms"]:
        marker=actors.spawn_actor_from_class(unreal.TargetPoint,unreal.Vector(*room["position"]))
        marker.tags=[TAG];marker.set_actor_label("DungeonRoom_%d_%s"%(room["id"],room["archetype"]))
        if plan["layout"].get("mode")=="fixed-grid" and room["id"]%32:continue
        light=actors.spawn_actor_from_class(unreal.PointLight,
            unreal.Vector(room["position"][0],room["position"][1],room["position"][2]+250))
        light.tags=[TAG];light.set_actor_label("DungeonLight_%d"%room["id"])
    if not levels.save_current_level():raise RuntimeError("Native level save failed")
    if not source.is_file() or source.stat().st_size<100:raise RuntimeError("Native map artifact missing")
    receipt={"schema":1,"status":"ASSEMBLED_NATIVE_QA_PENDING",
        "plan_sha256":plan["plan_sha256"],"engine_version":unreal.SystemLibrary.get_engine_version(),
        "map":"/Game/GeneratedDungeon/Dungeon","actors":len(placed),"unique_modules":len(meshes),
        "materials_resolved":"PASS","logical_connectivity":plan["qa"]["logical_connectivity"],
        "native_collision":"NOT TESTED","native_navigation":"NOT TESTED","render":"NOT TESTED",
        "placements":placed,"map_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
    (project/"native-assembly-receipt.json").write_text(json.dumps(receipt,indent=2))
    return receipt

def verify(unreal,plan,project,receipt):
    """Keep the editor alive until actual Recast paths and physical sweeps finish."""
    project=pathlib.Path(project);actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    rooms=plan["layout"]["rooms"]
    if plan["layout"]["stairs"] and plan.get("vertical_contract")!="east-bay-v1":raise RuntimeError("Multi-level native traversal requires the verified vertical contract")
    positions=[r["position"] for r in rooms]
    size=max(r["size"][0] for r in rooms)
    low=[min(p[i] for p in positions)-size for i in range(3)]
    high=[max(p[i] for p in positions)+size for i in range(3)]
    center=[(low[i]+high[i])/2 for i in range(3)]
    volume=actors.spawn_actor_from_class(unreal.NavMeshBoundsVolume,unreal.Vector(*center));volume.tags=[TAG]
    _,extent=volume.get_actor_bounds(False)
    if min(extent.x,extent.y,extent.z)<=0:raise RuntimeError("Navigation volume has no brush")
    volume.set_actor_scale3d(unreal.Vector(*[(high[i]-low[i])/200 for i in range(3)]))
    nav=unreal.NavigationSystemV1.get_navigation_system(world);nav.on_navigation_bounds_updated(volume)
    # Saving from a Slate tick callback returned false in this engine even after writing
    # the package. Save the authored map/volume before asynchronous navigation work.
    if not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level():
        raise RuntimeError("Authored navigation volume save failed")
    receipt["navigation_storage"]="Bounds volume saved; Recast generated during runtime QA"
    receipt["ground_checks"]=[];receipt["capsule_checks"]=[];receipt["wall_checks"]=[];receipt["paths"]=[]
    def physical_checks():
        # The native Python wrapper returns HitResult or None, not the C++ bool/out tuple.
        for room in rooms:
            p=room["position"];start=unreal.Vector(p[0],p[1],p[2]+150);end=unreal.Vector(p[0],p[1],p[2]-30)
            hit=unreal.SystemLibrary.line_trace_single(world,start,end,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                False,[],unreal.DrawDebugTrace.NONE,True)
            if hit is None:raise RuntimeError("Missing physical floor under room "+str(room["id"]))
            receipt["ground_checks"].append({"room":room["id"],"blocking":True})
        for edge in plan["layout"]["connections"]:
            if edge["kind"]=="stairs":continue # sweep the actual complete Recast route below
            a,b=[rooms[edge[k]]["position"] for k in ("from","to")]
            hit=unreal.SystemLibrary.capsule_trace_single(world,unreal.Vector(a[0],a[1],a[2]+100),
                unreal.Vector(b[0],b[1],b[2]+100),30,88,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
                False,[],unreal.DrawDebugTrace.NONE,True)
            if hit is not None:raise RuntimeError("Physical doorway/corridor is blocked: "+json.dumps(edge)+" hit="+str(hit))
            receipt["capsule_checks"].append({"from":edge["from"],"to":edge["to"],"radius_cm":30,"half_height_cm":88,"blocked":False})
        for actor in actors.get_all_level_actors():
            if TAG not in [str(t) for t in actor.tags] or not actor.get_actor_label().endswith("_wall"):continue
            center,extent=actor.get_actor_bounds(False)
            yaw=math.radians(actor.get_actor_rotation().yaw)
            normal=[math.sin(yaw),-math.cos(yaw)]
            hit=unreal.SystemLibrary.line_trace_single(world,
                unreal.Vector(center.x+normal[0]*100,center.y+normal[1]*100,center.z),
                unreal.Vector(center.x-normal[0]*100,center.y-normal[1]*100,center.z),
                unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
            if hit is None:raise RuntimeError("Wall has no physical blocking collision: "+actor.get_actor_label())
            receipt["wall_checks"].append({"actor":actor.get_actor_label(),"blocking":True})
    started=time.monotonic();built=False
    unreal.EditorPythonScripting.set_keep_python_script_alive(True)
    def finish():
        (project/"native-assembly-receipt.json").write_text(json.dumps(receipt,indent=2))
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
    def tick(_delta):
        nonlocal built
        try:
            elapsed=time.monotonic()-started
            if elapsed>150:raise RuntimeError("Native navigation exceeded150seconds")
            if elapsed<3:return
            if not built:
                if not any(isinstance(a,unreal.RecastNavMesh) for a in actors.get_all_level_actors()):return
                physical_checks()
                receipt["physics_settle_seconds"]=round(elapsed,3)
                unreal.SystemLibrary.execute_console_command(world,"RebuildNavigation");built=True;return
            if unreal.NavigationSystemV1.is_navigation_being_built(world):return
            for edge in plan["layout"]["connections"]:
                a,b=[rooms[edge[k]]["position"] for k in ("from","to")]
                path=unreal.NavigationSystemV1.find_path_to_location_synchronously(world,
                    unreal.Vector(a[0],a[1],a[2]+20),unreal.Vector(b[0],b[1],b[2]+20))
                if not path or not path.is_valid() or path.is_partial():
                    receipt["failed_path"]={"from":edge["from"],"to":edge["to"],"kind":edge["kind"],
                        "valid":bool(path and path.is_valid()),"partial":bool(path and path.is_partial()),
                        "points":[[p.x,p.y,p.z] for p in path.path_points] if path else []}
                    raise RuntimeError("Native Recast path failed: "+json.dumps(receipt["failed_path"]))
                if edge["kind"]=="stairs":
                    for start,end in zip(path.path_points,path.path_points[1:]):
                        hit=unreal.SystemLibrary.capsule_trace_single(world,start+unreal.Vector(0,0,100),end+unreal.Vector(0,0,100),30,88,unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,False,[],unreal.DrawDebugTrace.NONE,True)
                        if hit is not None:raise RuntimeError("Physical capsule blocked on actual stair navigation route")
                    receipt["capsule_checks"].append({"from":edge["from"],"to":edge["to"],"route":"actual Recast stair path","segments":len(path.path_points)-1,"radius_cm":30,"half_height_cm":88,"blocked":False})
                receipt["paths"].append({"from":edge["from"],"to":edge["to"],"kind":edge["kind"],"points":len(path.path_points),"complete":True})
            receipt.update(status="NATIVE_QA_PASS_EXPORT_RENDER_PENDING",native_collision="PASS",native_navigation="PASS")
            receipt["map_sha256"]=hashlib.sha256((project/"Content/GeneratedDungeon/Dungeon.umap").read_bytes()).hexdigest()
        except Exception:receipt.update(status="FAIL",error=traceback.format_exc())
        finish()
    handle=unreal.register_slate_post_tick_callback(tick)

if __name__=="__main__":
    import unreal
    project=pathlib.Path(unreal.Paths.project_dir())
    try:
        plan=json.loads((project/"dungeon-assembly.json").read_text())
        receipt=assemble(unreal,plan,project);verify(unreal,plan,project,receipt)
    except Exception:
        failure=dict(locals().get("receipt",{}));failure.update(status="FAIL",error=traceback.format_exc())
        (project/"native-assembly-receipt.json").write_text(json.dumps(failure,indent=2))
        unreal.EditorPythonScripting.set_keep_python_script_alive(False)
