import { test, expect } from "bun:test"
import { validate, outputs } from "../src/watoom/creative-contract"
import { validateReceipt } from "../src/watoom/toolkit-3d"
const asset = "ast_"+"a".repeat(24)
test("creative route rejects guessed paths, mismatched operations and unbounded input",()=>{
 const good = {task:"3d-creative",operation:"world",asset_id:asset,seed:42,parameters:{instances:8}}
 expect(()=>validate(good,"world.compose")).not.toThrow()
 for(const bad of [
 {...good,task:"3d-generate"}, {...good,operation:"character"}, {...good,asset_id:"/assets/private"},
 {...good,asset_ids:"not-array"}, {...good,seed:-1}, {...good,parameters:{instances:65}},
 {...good,parameters:{texture_resolution:64.5}}, {...good,operation_id:"a".repeat(64)},
 {...good,timeout:181}, {...good,parameters:{unexpected:1}}
 ]) expect(()=>validate(bad,"world.compose")).toThrow()
 expect(()=>validate({task:"asset-search",query:"tree",limit:16},"asset.search")).not.toThrow()
 expect(()=>validate({task:"asset-search",limit:17},"asset.search")).toThrow()
})
test("all creative receipts require complete published artifact identity and hashes",()=>{
 for(const input of [
 {task:"asset-search"},{task:"asset-index"},
 ...["inspect","optimize","world","character","material"].map(operation=>({task:"3d-creative",operation}))
 ]) {
 const names=outputs(input);const id="a".repeat(16)
 const artifacts=names.map(name=>({root:"state",path:"jobs/"+id+"/worker/artifacts/"+name,sha256:"b".repeat(64),bytes:100}))
 const receipt={id,task:input.task,status:"PASS",exit_code:0,artifacts,verification:{status:"PASS"},contract:{id:"watoom-creative/v1",available:true,outputs:artifacts.map(({root,path})=>({root,path}))},published:{root:"assets",path:"generated/watoom-toolkit-3d/v1/"+id,files:names.map(path=>({path,sha256:"b".repeat(64),bytes:100}))}}
 const options={contract:"watoom-creative/v1",expected:names}
 expect(validateReceipt(receipt,input.task,options).status).toBe("PASS")
 for(const mutate of [
 (v:typeof receipt)=>{v.artifacts.pop()},
 (v:typeof receipt)=>{v.contract.id="watoom-3d/v1"},
 (v:typeof receipt)=>{v.published.files[0].sha256="c".repeat(64)},
 (v:typeof receipt)=>{v.artifacts[0].path="jobs/../credentials"},
 (v:typeof receipt)=>{v.contract.outputs[1]=v.contract.outputs[0]}
 ]) {const bad=structuredClone(receipt);mutate(bad);expect(()=>validateReceipt(bad,input.task,options)).toThrow()}
 }
})
