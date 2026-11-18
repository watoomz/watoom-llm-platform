import {test,expect} from "bun:test"
import {backend} from "../src/watoom/specialist-backends"
import {outputs,validate} from "../src/watoom/creative-contract"
import {mkdtemp,mkdir,writeFile,rm} from "node:fs/promises"
import {tmpdir} from "node:os"
import path from "node:path"
import {createHash} from "node:crypto"
test("native creative HTTP route binds operation identity and verifies published bytes",async()=>{
 const root=await mkdtemp(path.join(tmpdir(),"creative-http-"))
 const id="1".repeat(16);const relative="generated/watoom-toolkit-3d/v1/"+id
 await mkdir(path.join(root,relative),{recursive:true})
 const bytes=Buffer.from("owned evidence fixture");const sha=createHash("sha256").update(bytes).digest("hex")
 let badIdentity=false;let submitted:Record<string,unknown>={}
 const server=Bun.serve({hostname:"127.0.0.1",port:0,async fetch(request){
  submitted=await request.json() as Record<string,unknown>
  const names=outputs(submitted)
  for(const name of names)await writeFile(path.join(root,relative,name),bytes)
  const artifacts=names.map(name=>({root:"state",path:"jobs/"+id+"/worker/artifacts/"+name,bytes:bytes.length,sha256:sha}))
  return Response.json({id,task:submitted.task,operation_id:badIdentity?"f".repeat(64):submitted.operation_id,status:"PASS",exit_code:0,verification:{status:"PASS"},contract:{id:"watoom-creative/v1",available:true,outputs:artifacts.map(({root,path})=>({root,path}))},artifacts,published:{root:"assets",path:relative,files:names.map(path=>({path,bytes:bytes.length,sha256:sha}))},result:{results:[{id:"ast_"+"a".repeat(24)}]}})
 }})
 try {
 const driver=backend({backend:"toolkit-3d",url:server.url.origin,artifactRoot:root} as Parameters<typeof backend>[0])
 for(const [capability,input] of [
 ["asset.search",{task:"asset-search",query:"tree",limit:4}],
 ...[["asset.optimize","optimize"],["world.compose","world"],["character.prepare","character"],["material.derive","material"]].map(([capability,operation])=>[capability,{task:"3d-creative",operation,asset_id:"ast_"+"a".repeat(24)}])
 ] as [string,Record<string,unknown>][]) {
  driver.validateInput(input,capability)
  const result=await driver.execute("a".repeat(64),input,AbortSignal.timeout(5000))
  expect(submitted.operation_id).toBe("a".repeat(64))
  expect(await driver.verifyArtifacts!(result)).toBe(true)
  expect(result.artifacts.length).toBeLessThanOrEqual(16)
  expect(result.summary.length).toBeLessThanOrEqual(2048)
  expect(Buffer.byteLength(JSON.stringify(result))).toBeLessThanOrEqual(8192)
  if(capability==="asset.search")expect(result.summary).toContain("ast_")
 }
 badIdentity=true
 await expect(driver.execute("a".repeat(64),{task:"asset-search"},AbortSignal.timeout(5000))).rejects.toThrow("operation receipt mismatch")
 } finally {server.stop(true);await rm(root,{recursive:true,force:true})}
})

test("aborting a native creative job sends its durable operation identity to Toolkit cancellation",async()=>{
 let started!:()=>void
 const accepted=new Promise<void>(resolve=>{started=resolve})
 const cancellations:unknown[]=[]
 const server=Bun.serve({hostname:"127.0.0.1",port:0,async fetch(request){
  const body=await request.json()
  if(new URL(request.url).pathname==="/api/jobs/cancel"){
   cancellations.push(body)
   return Response.json({status:"CANCELLATION_REQUESTED"})
  }
  started()
  await Bun.sleep(500)
  return Response.json({status:"INTENTIONALLY_INVALID_UNABORTED_RESPONSE"})
 }})
 const abort=new AbortController()
 try {
  const driver=backend({backend:"toolkit-3d",url:server.url.origin,artifactRoot:tmpdir()} as Parameters<typeof backend>[0])
  const pending=driver.execute("c".repeat(64),{task:"3d-creative",operation:"world",asset_id:"ast_"+"a".repeat(24)},abort.signal)
  const failed=pending.then(()=>undefined,error=>error)
  await accepted
  abort.abort()
  expect(await failed).toBeTruthy()
  expect(cancellations).toEqual([{operation_id:"c".repeat(64)}])
 } finally {server.stop(true)}
})
test("extended timeout is confined to native dungeon world generation",()=>{
 const request={task:"3d-creative",operation:"world",asset_id:"ast_"+"a".repeat(24),timeout:600}
 expect(()=>validate({...request,dungeon:{style:"dungeon-builder",rooms:4}},"world.compose")).not.toThrow()
 expect(()=>validate(request,"world.compose")).toThrow("timeout")
 expect(()=>validate({...request,dungeon:{style:"dungeon-builder"},timeout:841},"world.compose")).toThrow("timeout")
})
