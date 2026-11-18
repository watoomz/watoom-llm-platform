import {test,expect} from "bun:test"
import {validate,outputs} from "../src/watoom/creative-contract"
const id="ast_"+"a".repeat(24)
const good={task:"3d-creative",operation:"world",asset_id:id,seed:42,dungeon:{style:"dungeon-builder",rooms:8,levels:2}}
test("native dungeon stays in world.compose and requires editable map evidence",()=>{
 expect(()=>validate(good,"world.compose")).not.toThrow()
 expect(outputs(good)).toContain("dungeon.umap")
 expect(outputs(good)).not.toContain("asset.blend")
 expect(()=>validate({...good,operation:"inspect"},"asset.inspect")).toThrow()
})
test("dungeon dimensions, styles and references are bounded",()=>{
 for(const dungeon of [
 {style:"unknown"},{style:"dungeon-builder",rooms:65},{style:"dungeon-builder",levels:5},
 {style:"dungeon-builder",rooms:2,levels:3},{style:"dungeon-builder",rooms:64,grid:2},
 {style:"dungeon-builder",room_size:900},{style:"dungeon-builder",rooms:2.5},
 {style:"dungeon-builder",script:"exec-anything"},
 ]) expect(()=>validate({...good,dungeon},"world.compose")).toThrow()
 for(const parameters of [{instances:3},[],false]) expect(()=>validate({...good,parameters},"world.compose")).toThrow()
})
test("mixed mode requires distinct indexed anchors",()=>{
 expect(()=>validate({...good,dungeon:{style:"mixed"}},"world.compose")).toThrow()
 expect(()=>validate({...good,asset_ids:[id],dungeon:{style:"mixed"}},"world.compose")).toThrow()
 expect(()=>validate({...good,asset_ids:["ast_"+"b".repeat(24)],dungeon:{style:"mixed"}},"world.compose")).not.toThrow()
})
