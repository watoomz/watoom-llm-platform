import { test, expect } from "bun:test"
import fs from "node:fs/promises"
import path from "node:path"
import os from "node:os"
test("explicit writes survive separate process; native milestone/delegation/compaction/stop capture is bounded and deduplicated", async () => {
  const root=await fs.mkdtemp(path.join(os.tmpdir(),"memory-lifecycle-"))
  const records: {id:string;content:string;project:string;agentId:string}[]=[]
  const server=Bun.serve({hostname:"127.0.0.1",port:0,async fetch(request){
    const body=await request.json() as {content:string;project:string;agentId:string}
    if(new URL(request.url).pathname.endsWith("/remember")) {
      const memory={id:"fixture-"+records.length,...body};records.push(memory)
      return Response.json({success:true,memory})
    }
    return Response.json({results:records.map(m=>({observation:{id:m.id,narrative:m.content}}))})
  }})
  const run=async(mode:string,db:string)=>{
    const child=Bun.spawn([process.execPath,path.join(import.meta.dirname,"fixture/watoom-memory-process.ts"),path.join(root,db),mode,root],
      {env:{...process.env,AGENTMEMORY_URL:server.url.origin,AGENTMEMORY_SECRET:"",WATOOM_MEMORY_TEST_PROJECT:db,GOMAXPROCS:"2"},stdout:"pipe",stderr:"pipe"})
    const [rc,out,err]=await Promise.all([child.exited,new Response(child.stdout).text(),new Response(child.stderr).text()])
    if(rc)throw Error(err.slice(-4000))
    return JSON.parse(out.trim().split("\n").at(-1)!)
  }
  try {
    const explicit=await run("commands","explicit.sqlite")
    expect(explicit.saved.state).toBe("observed")
    expect(explicit.duplicate.id).toBe(explicit.saved.id)
    expect(explicit.found).toHaveLength(1)
    expect(explicit.isolated).toHaveLength(0)
    expect(records).toHaveLength(1)
    const restarted=await run("commands-recover","explicit.sqlite")
    expect(restarted.found[0].content).toBe("unique durable fact: platypus-204420")
    expect(records).toHaveLength(1)
    const lifecycle=await run("lifecycle","lifecycle.sqlite")
    const facts=lifecycle.facts.map((f:{body:string;checkpoint_body:string;state:string})=>({...JSON.parse(f.body),checkpoint:JSON.parse(f.checkpoint_body),state:f.state}))
    expect(facts.every((f:{state:string})=>f.state==="observed")).toBe(true)
    expect(facts.filter((f:{job:string})=>f.job.endsWith("evt_milestone_fixture"))).toHaveLength(2)
    expect(facts.some((f:{kind:string})=>f.kind==="compaction")).toBe(true)
    expect(facts.some((f:{content:string})=>f.content.includes("shutdown"))).toBe(true)
    expect(facts.some((f:{scope:{agent:string}})=>f.scope.agent==="fixture-parent")).toBe(true)
    expect(facts.filter((f:{kind:string;checkpoint:{references:unknown[]}})=>f.kind==="compaction").every((f:{checkpoint:{references:unknown[]}})=>f.checkpoint.references.length>0)).toBe(true)
  } finally {await server.stop(true)}
},60000)
