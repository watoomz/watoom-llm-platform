import copy,hashlib,json,pathlib,tempfile,unittest
import dungeon_pipeline as dungeon
from asset_catalog import checksum

class CatalogFixture:
    def __init__(self,root):
        self.records={};self.root=pathlib.Path(root)
    def add(self,name,data=b"test"):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        key="ast_"+hashlib.sha256(name.encode()).hexdigest()[:24]
        self.records[key]={"id":key,"path":name,"bytes":len(data),"sha256":checksum(path)}
        return key
    def load(self):return {"records":self.records}
    def resolve(self,key):
        record=self.records[key];path=self.root/record["path"]
        if checksum(path)!=record["sha256"]:raise ValueError("Source changed")
        return path,copy.deepcopy(record)
    def adapter(self):
        anchor=self.add("anchor.uasset");files=[];modules={}
        for role in ("floor","wall","doorway","stairs"):
            path="Pack/"+role+".uasset";key=self.add(path,role.encode())
            files.append({"id":key,"content_path":path,"sha256":self.records[key]["sha256"]})
            modules[role]=[{"object_path":"/Game/Pack/"+role+"."+role,"span_cm":200,
                           "pivot_offset_cm":[0,0,0],"collision_verified":True,"materials_verified":True,
                           "rise_cm":400,"run_cm":400}]
        self.records[anchor]["dungeon_adapter"]={"schema":1,"status":"VERIFIED","style":"dungeon-builder",
            "engine_version":"5.8.3","anchor_sha256":self.records[anchor]["sha256"],
            "inspection_receipt_sha256":"a"*64,"native_qa_receipt_sha256":"b"*64,"tile_cm":200,"modules":modules,"files":files}
        return anchor

class DungeonPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name);self.catalog=CatalogFixture(self.root/"assets")
        self.anchor=self.catalog.adapter()
        self.request={"asset_id":self.anchor,"seed":42,"dungeon":{"style":"dungeon-builder","rooms":8,"levels":2}}
    def test_fixed_board_reuses_verified_native_adapters(self):
        request={**self.request,"dungeon":{"style":"dungeon-builder","fixed_layout":{"cols":3,"rows":2,"cell_cm":200,"rock_cells":[[2,1]],"door_edges":[[[0,0],[1,0]]]}}}
        first=dungeon.prepare(request,self.catalog)
        self.assertEqual(first,dungeon.prepare(request,self.catalog))
        self.assertEqual(first["effective_options"]["board_cm"],[600,400])
        self.assertEqual(sum(p["role"]=="floor" for p in first["placements"]),5)
        self.assertEqual(first["layout"]["stairs"],[])
        for bad in [{**request["dungeon"],"rooms":2},{**request["dungeon"],"fixed_layout":{"cols":True,"rows":3}}]:
            with self.assertRaises(ValueError):dungeon.prepare({**request,"dungeon":bad},self.catalog)
    def test_native_contract_never_falls_back_to_portable_world(self):
        import creative
        request={"task":"3d-creative","operation":"world",**self.request}
        creative.validate(request)
        self.assertIn("dungeon.umap",creative.names(request))
        for parameters in ([],False,{"instances":3}):
            with self.assertRaises(ValueError):creative.validate({**request,"parameters":parameters})
        with self.assertRaisesRegex(ValueError,"not enabled"):
            creative.command(request,self.root/"job",self.catalog)
    def test_preparation_replay_and_native_gates(self):
        first=dungeon.prepare(self.request,self.catalog)
        self.assertEqual(first,dungeon.prepare(self.request,self.catalog))
        self.assertTrue(first["placements"])
        self.assertEqual(first["qa"]["native_navigation"],"NOT TESTED")
        self.assertEqual(first["layout"]["rooms"][first["layout"]["exit"]]["archetype"],"boss")
        self.assertEqual(len([p for p in first["placements"] if p["role"]=="stairs"]),1)
    def test_unverified_or_stale_pack_rejected(self):
        record=self.catalog.records[self.anchor]
        for change in ({"status":"UNVERIFIED"},{"anchor_sha256":"b"*64},{"engine_version":"5.7.0"},{"inspection_receipt_sha256":None},{"native_qa_receipt_sha256":None}):
            with self.subTest(change=change):
                original=copy.deepcopy(record["dungeon_adapter"])
                record["dungeon_adapter"].update(change)
                with self.assertRaises(ValueError):dungeon.prepare(self.request,self.catalog)
                record["dungeon_adapter"]=original
    def test_mixed_rejected_without_compatibility(self):
        with self.assertRaises(ValueError):
            dungeon.prepare({**self.request,"dungeon":{"style":"mixed"}},self.catalog)
    def test_dependency_and_grid_rejected(self):
        adapter=self.catalog.records[self.anchor]["dungeon_adapter"]
        adapter["files"][0]["content_path"]="../escape.uasset"
        with self.assertRaises(ValueError):dungeon.prepare(self.request,self.catalog)
        adapter["files"][0]["content_path"]="Pack/floor.uasset"
        with self.assertRaises(ValueError):
            dungeon.prepare({**self.request,"dungeon":{"style":"dungeon-builder","room_size":500}},self.catalog)
    def test_dependency_budget_rejected_before_hashing(self):
        adapter=self.catalog.records[self.anchor]["dungeon_adapter"]
        self.catalog.records[adapter["files"][0]["id"]]["bytes"]=513*1024**2
        with self.assertRaisesRegex(ValueError,"budget"):dungeon.prepare(self.request,self.catalog)
    def test_source_changes_rejected(self):
        adapter=self.catalog.records[self.anchor]["dungeon_adapter"]
        item=adapter["files"][0];(self.catalog.root/self.catalog.records[item["id"]]["path"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):dungeon.prepare(self.request,self.catalog)
    def test_vertical_bay_is_open_only_above_and_requires_runtime_acceptance(self):
        adapter=self.catalog.records[self.anchor]["dungeon_adapter"];adapter["tile_cm"]=300
        for entries in adapter["modules"].values():
            for module in entries:module["span_cm"]=300
        adapter["modules"]["stairs"][0].update(stairwell="east-bay-v1",run_cm=600)
        adapter["modules"]["railing"]=[copy.deepcopy(adapter["modules"]["wall"][0])]
        request={**self.request,"dungeon":{"style":"dungeon-builder","rooms":4,"levels":2}}
        with self.assertRaisesRegex(ValueError,"vertical acceptance"):dungeon.prepare(request,self.catalog)
        plan=dungeon.prepare(request,self.catalog,candidate_adapters={self.anchor:adapter})
        self.assertEqual(plan["vertical_contract"],"east-bay-v1")
        room=plan["layout"]["rooms"][2]
        floor=[p for p in plan["placements"] if p["room"]==2 and p["role"]=="floor" and p["position"][0]==room["position"][0]+300 and abs(p["position"][1]-room["position"][1])<=300]
        self.assertEqual(floor,[])
        self.assertEqual(len([p for p in plan["placements"] if p["role"]=="railing"]),1)
        landing=[p for p in plan["placements"] if p["room"]==2 and p["role"]=="floor" and p["scale"][1]==.5]
        self.assertEqual(len(landing),1)
        self.assertEqual(landing[0]["position"],[room["position"][0]+300,room["position"][1]-375,room["position"][2]])
        with self.assertRaisesRegex(ValueError,"900cm"):
            dungeon.prepare({**request,"dungeon":{**request["dungeon"],"room_size":1500,"cell_size":1800}},self.catalog,candidate_adapters={self.anchor:adapter})
        for edge in plan["layout"]["connections"]:
            if edge["kind"]!="corridor":continue
            a,b=[plan["layout"]["rooms"][edge[k]] for k in ("from","to")]
            if a["id"] in (0,2):self.assertNotEqual([b["cell"][0]-a["cell"][0],b["cell"][1]-a["cell"][1]],[1,0])
    def test_measured_adapter_grid_controls_omitted_dimensions(self):
        adapter=self.catalog.records[self.anchor]["dungeon_adapter"];adapter["tile_cm"]=300
        for role in ("floor","wall","doorway"):
            for module in adapter["modules"][role]:module["span_cm"]=300
        request={**self.request,"dungeon":{"style":"dungeon-builder","rooms":4}}
        plan=dungeon.prepare(request,self.catalog)
        self.assertEqual(plan["effective_options"]["room_size"],900)
        self.assertEqual(plan["effective_options"]["cell_size"],1200)
        self.assertTrue(all(room["size"]==[900,900] for room in plan["layout"]["rooms"]))
    def test_compound_parts_are_source_pinned_and_rotated(self):
        adapter=self.catalog.records[self.anchor]["dungeon_adapter"]
        floor=adapter["modules"]["floor"][0]
        floor["parts"]=[{"object_path":floor["object_path"],"position_cm":[25,0,0],"rotation":[0,30,0],"scale":[1,1,1]}]
        plan=dungeon.prepare(self.request,self.catalog)
        first=next(p for p in plan["placements"] if p["role"]=="floor")
        self.assertEqual(first["rotation"],[0,30,0])
        floor["parts"][0]["object_path"]="/Game/Unknown.Mesh"
        with self.assertRaises(ValueError):dungeon.prepare(self.request,self.catalog)
    def test_private_inspection_does_not_enable_unverified_runtime(self):
        adapter=self.catalog.records[self.anchor]["dungeon_adapter"];adapter["status"]="INSPECTED"
        with self.assertRaises(ValueError):dungeon.prepare(self.request,self.catalog)
        plan=dungeon.prepare(self.request,self.catalog,candidate_adapters={self.anchor:adapter})
        self.assertEqual(plan["status"],"PREPARED_NOT_EXECUTED")
    def test_corridors_are_bounded_by_native_wall_modules(self):
        plan=dungeon.prepare(self.request,self.catalog)
        floors=[p for p in plan["placements"] if p["role"]=="floor"]
        walls=[p for p in plan["placements"] if p["role"]=="wall"]
        rooms=plan["layout"]["rooms"];corridors=[]
        for floor in floors:
            if not any(abs(floor["position"][0]-room["position"][0])<room["size"][0]/2 and abs(floor["position"][1]-room["position"][1])<room["size"][1]/2 and floor["position"][2]==room["position"][2] for room in rooms):
                corridors.append(floor)
        self.assertTrue(corridors)
        for floor in corridors:
            nearby=[w for w in walls if w["position"][2]==floor["position"][2] and sum((w["position"][i]-floor["position"][i])**2 for i in (0,1))==100**2]
            self.assertEqual(len(nearby),2)
            self.assertEqual([nearby[0]["position"][i]+nearby[1]["position"][i] for i in (0,1)],[2*floor["position"][i] for i in (0,1)])
    def test_portable_derivative_is_pinned_to_source_lod_and_bake(self):
        module=self.catalog.records[self.anchor]["dungeon_adapter"]["modules"]["floor"][0]
        key=self.catalog.add("derived/floor.glb",b"verified-derivative")
        module["portable"]={"id":key,"sha256":self.catalog.records[key]["sha256"],
            "source_sha256":self.catalog.records[self.anchor]["dungeon_adapter"]["files"][0]["sha256"],
            "lod":0,"images":2,"bake_receipt_sha256":"c"*64}
        plan=dungeon.prepare(self.request,self.catalog)
        self.assertEqual(len(plan["portable_modules"]),1)
        for change in ({"sha256":"d"*64},{"source_sha256":"e"*64},{"lod":2},{"images":0},{"bake_receipt_sha256":None}):
            original=copy.deepcopy(module["portable"]);module["portable"].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):dungeon.prepare(self.request,self.catalog)
            module["portable"]=original
    def test_staging_recovery_integrity_and_cancel(self):
        plan=dungeon.prepare(self.request,self.catalog);project=self.root/"job"
        before={name:checksum(pathlib.Path(item["source"])) for name,item in plan["files"].items()}
        with self.assertRaises(InterruptedError):dungeon.stage(plan,project,lambda:True)
        first=dungeon.stage(plan,project);second=dungeon.stage(plan,project)
        self.assertEqual(first,second)
        self.assertEqual(before,{name:checksum(pathlib.Path(item["source"])) for name,item in plan["files"].items()})
        (project/"Content/Pack/floor.uasset").write_bytes(b"tampered")
        with self.assertRaises(ValueError):dungeon.stage(plan,project)
    def test_stage_identity_and_symlink_boundary(self):
        plan=dungeon.prepare(self.request,self.catalog);project=self.root/"job"
        dungeon.stage(plan,project)
        with self.assertRaises(ValueError):dungeon.stage({**plan,"plan_sha256":"other"},project)
        other=self.root/"other";other.mkdir();(other/"Content").symlink_to(self.catalog.root,target_is_directory=True)
        with self.assertRaises(ValueError):dungeon.stage(plan,other)

if __name__=="__main__":unittest.main()
