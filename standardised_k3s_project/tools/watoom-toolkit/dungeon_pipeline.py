"""Native dungeon preparation for the existing creative world operation.
Verified adapter annotations live on existing Catalog records, not a second registry.
This module does no model calls, engine launches, or source writes.
"""
import hashlib,json,math,pathlib,random,re
from dungeon_layout import layout

STYLES={"dungeon-builder","dungeon-forge","mixed"}
FIELDS={"style","rooms","levels","grid","room_size","cell_size","floor_height","fixed_layout"}
OUTPUTS=["dungeon.umap","asset.glb","perspective.png","manifest.json","validation.json",
         "dungeon-layout.json","dungeon-assembly.json","provenance.json"]

def output_names(options):
    return OUTPUTS+(["overhead.png"] if "fixed_layout" in options else [])

def validate(options,seed=0):
    if not isinstance(options,dict) or set(options)-FIELDS:
        raise ValueError("Unknown dungeon option")
    if options.get("style") not in STYLES:
        raise ValueError("Select dungeon-builder, dungeon-forge or verified mixed style")
    if "fixed_layout" in options:
        if set(options)!={"style","fixed_layout"}:raise ValueError("Fixed layout cannot be mixed with procedural options")
        import fixed_layout
        return fixed_layout.validate(options["fixed_layout"])
    parameters={name:value for name,value in options.items() if name!="style"}
    return layout(seed,**parameters)

def _finite_vector(value):
    return isinstance(value,list) and len(value)==3 and all(type(x) in (float,int) and math.isfinite(x) and abs(x)<=100000 for x in value)

def prepare(payload,catalog,*,candidate_adapters=None):
    options=payload["dungeon"];graph=validate(options,payload.get("seed",0))
    if "fixed_layout" in options:
        import fixed_layout
        seed_payload={**payload,"dungeon":{"style":options["style"],"rooms":2,"levels":1}}
        base=prepare(seed_payload,catalog,candidate_adapters=candidate_adapters)
        records=catalog.load()["records"];ids=[payload["asset_id"],*payload.get("asset_ids",[])]
        adapters=[(candidate_adapters or {}).get(i,records[i].get("dungeon_adapter")) for i in ids]
        return fixed_layout.assemble(base,options["fixed_layout"],adapters)
    ids=[payload["asset_id"],*payload.get("asset_ids",[])]
    if len(set(ids))!=len(ids) or len(ids)!=(2 if options["style"]=="mixed" else 1):
        raise ValueError("Select one pack anchor, or exactly two compatible anchors for mixed style")
    records=catalog.load()["records"]
    adapters=[];provenance=[];files={};total=0;portable={};portable_bytes=0
    for anchor_id in ids:
        if records.get(anchor_id,{}).get("bytes",4*1024**2+1)>4*1024**2:raise ValueError("Pack anchor exceeds bounded inspection size")
        source,anchor=catalog.resolve(anchor_id)
        adapter=(candidate_adapters or {}).get(anchor_id,anchor.get("dungeon_adapter"))
        if not isinstance(adapter,dict) or adapter.get("schema")!=1 or adapter.get("status") not in (("VERIFIED","INSPECTED") if candidate_adapters is not None else ("VERIFIED",)):
            raise ValueError("Selected pack has no verified native dungeon adapter")
        if adapter.get("anchor_sha256")!=anchor["sha256"] or adapter.get("engine_version")!="5.8.3":
            raise ValueError("Adapter source or engine verification is stale")
        if not re.fullmatch("[a-f0-9]{64}",str(adapter.get("inspection_receipt_sha256",""))):
            raise ValueError("Adapter requires a pinned engine inspection receipt")
        if candidate_adapters is None and not re.fullmatch("[a-f0-9]{64}",str(adapter.get("native_qa_receipt_sha256",""))):
            raise ValueError("Adapter requires a pinned native collision/navigation acceptance receipt")
        if adapter.get("style") not in STYLES-{"mixed"}:
            raise ValueError("Adapter style is invalid")
        closure=adapter.get("files")
        if not isinstance(closure,list) or not 1<=len(closure)<=256:
            raise ValueError("Verified dependency closure must contain1..256files")
        for item in closure:
            asset_id=item["id"]
            if asset_id not in records:raise ValueError("Dependency is not in existing catalog")
            if records[asset_id].get("bytes",512*1024**2+1)>512*1024**2-total:raise ValueError("Dependency exceeds remaining staging budget")
            path,record=catalog.resolve(asset_id)
            relative=item["content_path"]
            parts=pathlib.PurePosixPath(relative)
            if not isinstance(relative,str) or parts.is_absolute() or "\\" in relative or any(x in ("","..",".") for x in relative.split("/")) or parts.suffix not in (".uasset",".umap",".ubulk",".uexp"):
                raise ValueError("Dependency content path is unsafe")
            if record["sha256"]!=item["sha256"]:raise ValueError("Verified dependency changed")
            if relative in files and files[relative]["sha256"]!=record["sha256"]:
                raise ValueError("Mixed packs collide in /Game namespace")
            if relative not in files:
                total+=record["bytes"]
                if total>512*1024**2:raise ValueError("Selected dependency closure exceeds512MiB staging budget")
                files[relative]={"id":asset_id,"source":str(path),"sha256":record["sha256"],"bytes":record["bytes"]}
        modules=adapter.get("modules",{})
        for role in ("floor","wall","doorway"):
            if not modules.get(role):raise ValueError("Verified adapter lacks "+role)
        for role,entries in modules.items():
            if role not in ("floor","wall","doorway","stairs","prop","railing") or not isinstance(entries,list) or not 1<=len(entries)<=32:
                raise ValueError("Unsupported bounded module role")
            for module in entries:
                object_path=module.get("object_path","")
                match=re.fullmatch(r"/Game/([A-Za-z0-9_/]+)\.([A-Za-z0-9_]+)",object_path)
                if not match or match[1].split("/")[-1]!=match[2] or match[1]+".uasset" not in files:
                    raise ValueError("Module is absent from verified dependency closure")
                collision=module.get("collision_verified") is True or (candidate_adapters is not None and module.get("collision_configured") is True)
                materials=module.get("materials_verified") is True or (candidate_adapters is not None and module.get("materials_resolved") is True)
                if not collision or not materials or not _finite_vector(module.get("pivot_offset_cm")):
                    raise ValueError("Module collision, materials or pivot not verified")
                if type(module.get("lod",0)) is not int or not 0<=module.get("lod",0)<=8:raise ValueError("Invalid verified module LOD")
                derivative=module.get("portable")
                if derivative is not None:
                    if not isinstance(derivative,dict) or not re.fullmatch("ast_[a-f0-9]{24}",str(derivative.get("id",""))):
                        raise ValueError("Invalid portable module reference")
                    record=records.get(derivative["id"],{})
                    if record.get("bytes",32*1024**2+1)>32*1024**2:
                        raise ValueError("Portable module exceeds32MiB budget")
                    path,record=catalog.resolve(derivative["id"])
                    if path.suffix.lower()!=".glb" or record["sha256"]!=derivative.get("sha256") or derivative.get("source_sha256")!=files[match[1]+".uasset"]["sha256"]:
                        raise ValueError("Portable derivative source or content changed")
                    if derivative.get("lod")!=module.get("lod",0) or derivative.get("images",0)<1 or not re.fullmatch("[a-f0-9]{64}",str(derivative.get("bake_receipt_sha256",""))):
                        raise ValueError("Portable derivative lacks verified LOD/material bake")
                    item={"id":record["id"],"object_path":object_path,"file":str(path),"sha256":record["sha256"],"lod":derivative["lod"],"images":derivative["images"],"bake_receipt_sha256":derivative["bake_receipt_sha256"]}
                    if object_path in portable and portable[object_path]!=item:raise ValueError("Conflicting portable module")
                    if object_path not in portable:portable_bytes+=record["bytes"]
                    if portable_bytes>64*1024**2:raise ValueError("Portable module closure exceeds64MiB")
                    portable[object_path]=item
                parts=module.get("parts",[])
                if not isinstance(parts,list) or len(parts)>256:raise ValueError("Compound module exceeds256parts")
                for part in parts:
                    name=part.get("object_path","")
                    match=re.fullmatch(r"/Game/([A-Za-z0-9_/]+)\.([A-Za-z0-9_]+)",name)
                    if not match or match[1].split("/")[-1]!=match[2] or match[1]+".uasset" not in files:
                        raise ValueError("Compound module has an unverified dependency")
                    if not _finite_vector(part.get("position_cm")) or not _finite_vector(part.get("rotation")) or not _finite_vector(part.get("scale")) or any(not .05<=x<=20 for x in part["scale"]):
                        raise ValueError("Compound module has invalid transforms")
        tile=adapter.get("tile_cm")
        if type(tile) is not int or not 50<=tile<=400:raise ValueError("Invalid verified tile grid")
        for role in ("floor","wall","doorway"):
            if any(module.get("span_cm")!=tile for module in modules[role]):
                raise ValueError("Module spans are incompatible with verified tile grid")
        adapters.append(adapter)
        provenance.append({"id":anchor_id,"sha256":anchor["sha256"],"style":adapter["style"],
                           "inspection_receipt_sha256":adapter["inspection_receipt_sha256"]})
    if options["style"]!="mixed" and adapters[0]["style"]!=options["style"]:
        raise ValueError("Selected pack does not match requested style")
    if options["style"]=="mixed":
        if {x["style"] for x in adapters}!=STYLES-{"mixed"} or not adapters[0].get("compatibility_group") or len({(x.get("compatibility_group"),x["tile_cm"]) for x in adapters})!=1:
            raise ValueError("Mixed pack compatibility has not been verified")
    tile=adapters[0]["tile_cm"];size=options.get("room_size",tile*3);cell=options.get("cell_size",size+tile)
    effective={key:value for key,value in options.items() if key!="style"}
    effective.setdefault("room_size",size);effective.setdefault("cell_size",cell);effective.setdefault("rooms",4)
    graph=layout(payload.get("seed",0),**effective)
    height=options.get("floor_height",400)
    if size%tile or cell%tile or (size//tile)%2!=1 or cell-size<tile:
        raise ValueError("Rooms and corridor spacing must align to odd-width verified module grid")
    rng=random.Random(payload.get("seed",0));placements=[]
    def place(role,position,yaw,room_id,adapter,module=None):
        module=module or rng.choice(adapter["modules"][role])
        angle=math.radians(yaw);x,y,z=module["pivot_offset_cm"]
        offset=[x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle),z]
        parts=module.get("parts") or [{"object_path":module["object_path"],"position_cm":[0,0,0],"rotation":[0,0,0],"scale":[1,1,1]}]
        for part in parts:
            px,py,pz=part["position_cm"]
            rotated=[px*math.cos(angle)-py*math.sin(angle),px*math.sin(angle)+py*math.cos(angle),pz]
            rotation=list(part["rotation"]);rotation[1]+=yaw
            placements.append({"role":role,"room":room_id,"asset":part["object_path"],
                               "position":[round(position[i]+offset[i]+rotated[i],6) for i in range(3)],
                               "yaw":rotation[1],"rotation":rotation,"scale":part["scale"],
                               "lod":module.get("lod",0)})
            if len(placements)>4096:raise ValueError("Native placement budget exceeded; reduce rooms or decoration")
    openings={room["id"]:set() for room in graph["rooms"]}
    for edge in graph["connections"]:
        if edge["kind"]!="corridor":continue
        a,b=[graph["rooms"][edge[k]] for k in ("from","to")]
        dx=b["cell"][0]-a["cell"][0];dy=b["cell"][1]-a["cell"][1]
        openings[a["id"]].add((dx,dy));openings[b["id"]].add((-dx,-dy))
        midpoint=[(a["position"][i]+b["position"][i])/2 for i in range(3)]
        gap=cell-size
        for step in range(gap//tile):
            pos=midpoint.copy();pos[0]+=dx*(-gap/2+tile/2+step*tile);pos[1]+=dy*(-gap/2+tile/2+step*tile)
            adapter=adapters[a["id"]%len(adapters)]
            place("floor",pos,0,a["id"],adapter)
            for side in (-1,1):
                wall=pos.copy();wall[0]+=-dy*side*tile/2;wall[1]+=dx*side*tile/2
                normal=(-dy*side,dx*side)
                wall_yaw={(0,1):0,(1,0):270,(0,-1):180,(-1,0):90}[normal]
                place("wall",wall,wall_yaw,a["id"],adapter)
    incoming={edge["to"] for edge in graph["stairs"]}
    stair_rooms={edge[key] for edge in graph["stairs"] for key in ("from","to")}
    vertical=bool(graph["stairs"]) and all(m.get("stairwell")=="east-bay-v1" for edge in graph["stairs"] for m in adapters[edge["from"]%len(adapters)]["modules"].get("stairs",[]))
    if vertical and (tile!=300 or size!=900 or height!=400 or any(not adapters[rid%len(adapters)]["modules"].get("stairs") or not adapters[rid%len(adapters)]["modules"].get("railing") for rid in stair_rooms)):
        raise ValueError("Vertical contract needs inspected stairs/railings,300cm grid,900cm rooms and400cm floors")
    if vertical and candidate_adapters is None and any(a.get("vertical_verified") is not True or not re.fullmatch("[a-f0-9]{64}",str(a.get("vertical_receipt_sha256",""))) for a in adapters):
        raise ValueError("Selected adapter has not passed native vertical acceptance")
    half=(size//tile)//2
    for room in graph["rooms"]:
        rid=room["id"];adapter=adapters[rid%len(adapters)];x,y,z=room["position"]
        room["archetype"]="boss" if rid==graph["exit"] else "ordinary" if rid==graph["entrance"] else rng.choice(["ordinary","ordinary","encounter","treasure","special"])
        for ix in range(-half,half+1):
            for iy in range(-half,half+1):
                if vertical and rid in incoming and ix==half:continue
                place("floor",[x+ix*tile,y+iy*tile,z],0,rid,adapter)
        for dx,dy,yaw in ((0,1,0),(1,0,270),(0,-1,180),(-1,0,90)):
            for offset in range(-half,half+1):
                role="doorway" if offset==0 and (dx,dy) in openings[rid] else "wall"
                place(role,[x+dx*size/2+(offset*tile if dy else 0),y+dy*size/2+(offset*tile if dx else 0),z],yaw,rid,adapter)
        if vertical and rid in incoming:
            # A 300x150cm top landing joins the stair crest to the upper floor.
            # Keep the remaining bay open for capsule headroom over the flights.
            floor=adapter["modules"]["floor"][0]
            parts=floor.get("parts") or [{"object_path":floor["object_path"],"position_cm":[0,0,0],"rotation":[0,0,0],"scale":[1,1,1]}]
            landing={**floor,"pivot_offset_cm":[floor["pivot_offset_cm"][0],floor["pivot_offset_cm"][1]/2,floor["pivot_offset_cm"][2]],
                "parts":[{**part,"position_cm":[part["position_cm"][0],part["position_cm"][1]/2,part["position_cm"][2]],
                    "scale":[part["scale"][0],part["scale"][1]/2,part["scale"][2]]} for part in parts]}
            place("floor",[x+300,y-375,z],0,rid,adapter,landing)
            place("railing",[x+size/2-tile,y,z],270,rid,adapter)
        if adapter["modules"].get("prop"):
            for number in range(1 if room["archetype"]=="ordinary" else 2):
                module=rng.choice(adapter["modules"]["prop"])
                px=x+(-1 if (number%2==0 or rid in stair_rooms) else 1)*(size/2-120)
                py=y-size/2 if module.get("attachment")=="south-wall" else y+(size/2-120)
                place("prop",[px,py,z],0,rid,adapter,module)
    for edge in graph["stairs"]:
        room=graph["rooms"][edge["from"]];adapter=adapters[room["id"]%len(adapters)]
        if not adapter["modules"].get("stairs") or any(m.get("rise_cm")!=height or m.get("run_cm",size+1)>size for m in adapter["modules"]["stairs"]):
            raise ValueError("Vertical layout requires verified stairs fitting the room and floor height")
        position=room["position"].copy()
        if vertical:position[0]+=size/2-450
        place("stairs",position,0,room["id"],adapter)
    assembly={"schema":1,"status":"PREPARED_NOT_EXECUTED","layout":graph,"placements":placements,
              "files":files,"portable_modules":[portable[key] for key in sorted(portable)],"provenance":provenance,"effective_options":effective,"qa":{"logical_connectivity":"PASS","grid_alignment":"PASS",
              "native_collision":"NOT TESTED","native_navigation":"NOT TESTED","materials":"NOT TESTED","render":"NOT TESTED"}}
    if vertical:assembly["vertical_contract"]="east-bay-v1"
    stable={k:v for k,v in assembly.items() if k!="files"}
    stable["portable_modules"]=[{k:v for k,v in item.items() if k!="file"} for item in [portable[key] for key in sorted(portable)]]
    stable["files"]={name:{key:item[key] for key in ("id","sha256","bytes")} for name,item in files.items()}
    assembly["plan_sha256"]=hashlib.sha256(json.dumps(stable,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return assembly


def stage(assembly,project,cancelled=lambda:False):
    """Stage only the verified dependency closure; resume matching files without duplication."""
    import os
    from asset_catalog import atomic,checksum
    project=pathlib.Path(project).resolve()
    project.mkdir(parents=True,exist_ok=True)
    checkpoint=project/"dungeon-stage.json"
    if checkpoint.exists() and json.loads(checkpoint.read_text()).get("plan_sha256")!=assembly["plan_sha256"]:
        raise ValueError("Existing job contains a different dungeon plan")
    atomic(checkpoint,{"status":"STAGING","plan_sha256":assembly["plan_sha256"]})
    content=project/"Content";content.mkdir(exist_ok=True)
    if content.is_symlink():raise ValueError("Project Content cannot be a symlink")
    count=0
    for relative,record in sorted(assembly["files"].items()):
        if cancelled():raise InterruptedError("Dungeon staging cancelled")
        if not isinstance(relative,str) or pathlib.PurePosixPath(relative).is_absolute() or "\\" in relative or any(part in ("","..",".") for part in relative.split("/")):
            raise ValueError("Staging content path is unsafe")
        destination=content/relative
        parent=destination.parent
        while parent!=project:
            if parent.is_symlink():raise ValueError("Staging path follows a symlink")
            parent=parent.parent
        destination.parent.mkdir(parents=True,exist_ok=True)
        source=pathlib.Path(record["source"])
        if destination.is_symlink():raise ValueError("Staging target cannot be a symlink")
        if destination.exists():
            if checksum(destination)!=record["sha256"]:raise ValueError("Existing staged dependency changed")
        else:
            partial=destination.with_suffix(destination.suffix+".partial")
            descriptor=os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            digest=hashlib.sha256();size=0
            with source.open("rb") as incoming,os.fdopen(descriptor,"wb") as outgoing:
                for block in iter(lambda:incoming.read(1024*1024),b""):
                    if cancelled():raise InterruptedError("Dungeon staging cancelled")
                    size+=len(block)
                    if size>record["bytes"]:raise ValueError("Dependency grew during staging")
                    digest.update(block);outgoing.write(block)
                outgoing.flush();os.fsync(outgoing.fileno())
            if size!=record["bytes"] or digest.hexdigest()!=record["sha256"]:
                raise ValueError("Source changed while staging")
            os.chmod(partial,0o644);os.replace(partial,destination)
            descriptor=os.open(destination.parent,os.O_RDONLY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
        count+=1
        atomic(checkpoint,{"status":"STAGING","plan_sha256":assembly["plan_sha256"],"files":count})
    atomic(checkpoint,{"status":"PASS","plan_sha256":assembly["plan_sha256"],"files":count})
    return {"status":"PASS","files":count,"plan_sha256":assembly["plan_sha256"]}
