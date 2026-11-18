import {Optimisation} from "./optimisation.mjs";
import {verifyWorker} from "./worker_verifier.mjs";
import {Learning,hash} from "./engine.mjs";
import {mkdir,lstat,realpath,writeFile,readFile,rename,readdir,open,link,unlink} from "node:fs/promises";
import path from "node:path";
import {randomUUID} from "node:crypto";
import {watch} from "node:fs";
// Exclusive hard-link publication preserves immutable bodies across lazy project instances.
// Each writer owns its temporary file; legacy shared partials remain untouched.
export async function publishArtifact(root,target,body){
 const tmp=target+".tmp-"+randomUUID();
 const f=await open(tmp,"wx",0o600);
 try{
  try{await f.writeFile(body);await f.sync();}finally{await f.close();}
  try{await link(tmp,target);}catch(e){
   if(e.code!=="EEXIST")throw e;
   const st=await lstat(target);if(st.isSymbolicLink()||!st.isFile()||await readFile(target,"utf8")!==body)throw Error("Immutable skill collision");
  }
  const dir=await open(root,"r");try{await dir.sync();}finally{await dir.close();}
  return target;
 }finally{await unlink(tmp).catch(e=>{if(e.code!=="ENOENT")throw e;});}
}
export async function install(ctx){
 const options=ctx.options||{},base=options.root;
 const metadataBytes=options.metadataBytes??1024;if(!Number.isInteger(metadataBytes)||metadataBytes<0||metadataBytes>4096)throw Error("Metadata byte budget invalid");
 if(typeof base!=="string"||!path.isAbsolute(base))throw Error("Explicit isolated learning root required");
 await mkdir(base,{recursive:true,mode:0o700});
 if((await lstat(base)).isSymbolicLink()||await realpath(base)!==base)throw Error("Unsafe learning root");
 const artifactRoot=path.join(base,"skills");await mkdir(artifactRoot,{recursive:true,mode:0o700});
 if((await lstat(artifactRoot)).isSymbolicLink())throw Error("Unsafe skill root");
 const safe=async p=>{if(path.dirname(p)!==artifactRoot||(await lstat(p)).isSymbolicLink()||await realpath(p)!==p)throw Error("Unsafe artifact");return p;};
 const artifacts={
  async write(id,body){
   if(!/^[a-z0-9-]+$/.test(id))throw Error("Invalid skill identity");
   const target=path.join(artifactRoot,id+".md");
   try{const old=await readFile(await safe(target),"utf8");if(old!==body)throw Error("Immutable skill collision");return target;}catch(e){if(e.code!=="ENOENT")throw e;}
   return publishArtifact(artifactRoot,target,body);
  },
  async read(p){return readFile(await safe(p),"utf8");}
 };
 const agent=options.agent||"build",scope={project:ctx.location.project.id,repository:ctx.location.directory,agent};
 async function post(route,body,method="POST"){
  const url=process.env.AGENTMEMORY_URL;
  if(!url)throw Error("Existing AgentMemory not configured");
  const r=await fetch(new URL(route,url),{method,headers:{"content-type":"application/json",...(process.env.AGENTMEMORY_SECRET?{authorization:"Bearer "+process.env.AGENTMEMORY_SECRET}:{})},body:method==="GET"?undefined:JSON.stringify(body),signal:AbortSignal.timeout(5000)});
  if(r.status===404&&method==="GET")return null;if(!r.ok)throw Error("Memory request failed");const text=await r.text();if(Buffer.byteLength(text)>262144)throw Error("Memory response too large");return JSON.parse(text);
 }
 const memory={
  idempotent:true,
  async remember(e){
   const id="mem_learning_"+e.id,now=new Date().toISOString();
   const record={id,createdAt:now,updatedAt:now,type:"workflow",title:"Verified workflow "+e.id.slice(0,16),content:JSON.stringify(e),concepts:["watoom-verified-workflow"],files:[],sessionIds:[],strength:7,version:1,sourceObservationIds:[],isLatest:true,origin:{channel:"agent",capturedAt:now},project:e.scope.project,agentId:e.scope.agent};
   const r=await post("/agentmemory/import",{strategy:"skip",exportData:{version:options.agentMemoryVersion||"0.9.29",exportedAt:now,sessions:[],observations:{},memories:[record],summaries:[]}});
   if(r.success!==true)throw Error("Memory import not acknowledged");
   const receipt=await this.reconcile(e);if(!receipt)throw Error("Memory record not independently verified");return receipt;
  },
  async reconcile(e){
   const r=await post("/agentmemory/memories/"+"mem_learning_"+e.id,undefined,"GET");if(!r)return;
   const m=r.memory;if(m?.content!==JSON.stringify(e)||m.project!==e.scope.project||m.agentId!==e.scope.agent||m.id!=="mem_learning_"+e.id)throw Error("Memory identity/content collision; preserve existing record");
   return {memoryId:m.id,id:e.id,digest:e.digest};
  }
 };
 let workerFingerprint;
 if(options.workerGuardPackage){const guard=await import(path.join(options.workerGuardPackage,"index.js"));workerFingerprint=guard.gameSourceFingerprint;if(typeof workerFingerprint!=="function")throw Error("Installed worker fingerprint interface unavailable");}
 const learning=new Learning({verify:(p,e)=>verifyWorker(p,e,scope,workerFingerprint),storage:ctx.storage,scope,policies:options.policies||[],memory,artifacts});
 const optimisation=new Optimisation({storage:ctx.storage,scope,artifacts});
 // Freeze selected revisions for this instance. Never hot-swap an existing
 // Skill in refresh()/curator or in the middle of a session.
 const overrides=await optimisation.frozenOverrides(options.optimisationRevisions||[]);
 let startupReturned=false,existingRegistered=false,synchronising;
 const originals=new Map();
 async function syncExisting(){
  if(!startupReturned)return;
  if(synchronising)return synchronising;
  synchronising=(async()=>{
   const reply=await ctx.skill.list(),all=reply.data;
   const present=new Set(all.map(k=>k.id));
   if(!(options.existingSkillIDs||[]).every(id=>present.has(id)))return;
   const original=all.map(k=>{const revision=overrides.find(r=>r.id===k.id);return revision&&hash(k.content)===hash(revision.content)&&originals.has(k.id)?originals.get(k.id):k;});
   for(const k of original)originals.set(k.id,k);
   await optimisation.inventory(original);
   if(!existingRegistered){
    // Filesystem Skill discovery registers after user plugin setup. Register
    // this frozen overlay only after the complete native registry is available.
    await ctx.skill.transform(editor=>{for(const revision of overrides){const current=editor.get(revision.id);if(current&&hash(current.content)===revision.sourceHash)editor.update(revision.id,k=>{k.content=revision.content;});}});
    existingRegistered=true;
   }
  })();try{await synchronising;}finally{synchronising=null;}
 }
 let stopping=false,busy=false,pendingCuration=false;
 async function nativeSkills(){
  const s=await learning.state(),result=[];
  for(const k of Object.values(s.skills).filter(k=>k.state==="active"&&(options.policies||[]).some(p=>p.id===k.policy&&hash(p.environment||{})===hash(k.environment||{})))){
   try{const content=await artifacts.read(k.path);if(hash(content)!==k.sha256)continue;result.push({id:k.id,name:k.name,description:k.description,path:k.path,content:content.replace(/^---\n[\s\S]*?\n---\n/,"")});}catch{}
  }return result;
 }
 let skills=await nativeSkills();
 await ctx.skill.transform(editor=>{for(const k of skills)editor.add(k);});
 async function refresh(){
  skills=await nativeSkills();await ctx.skill.reload();
 }
 async function curate(){
  if(stopping)return;if(busy){pendingCuration=true;return;}busy=true;
  try{
   await syncExisting();await learning.flush();await learning.curate();await optimisation.propose();
   // Native counters only. A successful model finish is never a verifier receipt.
   const os=await optimisation.state(),sessionIDs=Object.keys(os.sessions).filter(id=>os.sessions[id].loaded.length);
   const cursorKey="learning/accounting-cursor/"+hash(scope),older=sessionIDs.slice(0,-16),cursor=Number(await ctx.storage.get(cursorKey)||0)%Math.max(1,older.length);
   const accounting=[...new Set([...sessionIDs.slice(-16),...older.slice(cursor,cursor+16)])];
   for(const sid of accounting){
    try{const auth="Basic "+Buffer.from("opencode:"+process.env.OPENCODE_PASSWORD).toString("base64");const r=await fetch("http://127.0.0.1:4096/api/session/"+encodeURIComponent(sid),{headers:{authorization:auth},signal:AbortSignal.timeout(3000)});if(r.ok){const session=(await r.json()).data;await optimisation.account(sid,session.tokens,session.cost);}}catch{}
   }
   await ctx.storage.set(cursorKey,(cursor+16)%Math.max(1,older.length));
   // Attestations are operator-owned inputs mounted read-only, never model flags.
   if(options.evaluations){
    const d=await lstat(options.evaluations);
    if(d.isSymbolicLink()||d.uid!==0)throw Error("Evaluator directory must be operator-owned");
    for(const name of (await readdir(options.evaluations)).filter(n=>/^[a-z0-9-]+\.json$/.test(n))){
     const file=path.join(options.evaluations,name),st=await lstat(file);
     if(st.isSymbolicLink()||st.uid!==0||(st.mode&0o022))continue;
     const e=JSON.parse(await readFile(file,"utf8")),s=await learning.state(),k=s.skills[e.id];
     if(e.kind?.startsWith("existing-skill-")){
      if(!/^[a-f0-9]{32}$/.test(e.request||"")||s.operations?.[e.request]||JSON.stringify(e.scope)!==JSON.stringify(scope))continue;
      let result="PASS",reason="";
      try{
       if(e.kind==="existing-skill-baseline")await optimisation.baseline(e.id,e.report);
       else if(e.kind==="existing-skill-compare")await optimisation.compare(e.id,e.report);
       else if(e.kind==="existing-skill-regression")await optimisation.regression(e.id,e.receipt);
       else if(["existing-skill-select","existing-skill-rollback"].includes(e.kind)){
        // Verify native admission in this process; never trust a supplied fence flag.
        const gate=JSON.parse(await readFile(process.env.WATOOM_DEPLOYMENT_GATE_FILE,"utf8"));
        if(gate.version!==1||!/^[a-f0-9]{64}$/.test(gate.owner||""))throw Error("Native idle fence required");
        const auth="Basic "+Buffer.from("opencode:"+process.env.OPENCODE_PASSWORD).toString("base64");
        const r=await fetch("http://127.0.0.1:4096/api/session/active",{headers:{authorization:auth},signal:AbortSignal.timeout(5000)});
        if(!r.ok)throw Error("Cannot verify idle sessions");const active=await r.json();if(Object.keys(active.data||{}).length)throw Error("Active session prevents revision change");
        const fence={nativeGateHeld:true,activeSessions:0,rolloutAtIdle:true};
        await optimisation[e.kind.endsWith("select")?"select":"rollback"](e.id,fence);
       }else throw Error("Unknown existing Skill operation");
      }catch(error){result="FAIL";reason=String(error.message);}
      await learning.transaction(s=>{s.operations??={};s.operations[e.request]={action:e.kind,id:e.id,result,reason,time:new Date().toISOString()};});continue;
     }
     if(e.action){
      if(!/^[a-f0-9]{32}$/.test(e.request||"")||s.operations?.[e.request]||JSON.stringify(e.scope)!==JSON.stringify(scope))continue;
      if(!["enable","disable","rollback"].includes(e.action))continue;
      let result="PASS",reason="";try{await learning[e.action](e.id);}catch(error){result="FAIL";reason=String(error.message);}
      await learning.transaction(s=>{s.operations??={};s.operations[e.request]={action:e.action,id:e.id,result,reason,time:new Date().toISOString()};});continue;
     }
     if(!k||k.state==="active"||k.state==="disabled"||JSON.stringify(e.scope)!==JSON.stringify(scope))continue;
     await learning.evaluate(e.id,e);
     if(options.autoPromote===true&&!Object.values(s.skills).some(active=>active.id!==e.id&&active.policy===k.policy&&active.state==="active"))await learning.promote(e.id);
    }
   }
   await refresh();await ctx.storage.set("learning/curator-health/"+hash(scope),{healthy:true,time:new Date().toISOString()});
  }catch(error){await ctx.storage.set("learning/last-error/"+hash(scope),{time:new Date().toISOString(),message:String(error.message).slice(0,200)}).catch(()=>{});}
  finally{busy=false;if(pendingCuration&&!stopping){pendingCuration=false;const t=setTimeout(()=>{void curate().catch(()=>{});},100);t.unref?.();}}
 }
 if(options.fixture===true)await ctx.tool.transform(editor=>editor.add({name:"watoom_learning_fixture",description:"CPU-only isolated fixture: sort fixed development data, persist it and verify the result.",options:{codemode:false},input:{type:"object",properties:{},additionalProperties:false},execute:async()=>{const p=path.join(base,"fixture-result.json");await writeFile(p,JSON.stringify([3,1,2].sort()),{mode:0o600});if(await readFile(p,"utf8")!=="[1,2,3]")throw Error("Fixture validation failed");return {content:"Sorted fixture [1,2,3] verified"};}}));
 await ctx.tool.hook("execute.after",async e=>{
  try{await optimisation.observe(e);}catch{}
  if(e.agent!==agent)return;
  try{await learning.recordLoad(e);const observed=await learning.observe(e);if(observed.status==="VERIFIED")await optimisation.verified({sessionID:e.sessionID,receipt:hash([e.sessionID,e.messageID,e.id,e.tool]),success:true,correctionSignature:hash([e.tool,e.input]),lesson:(options.policies||[]).find(p=>p.id===observed.policy)?.recovery});await learning.flush();}
  catch(error){await ctx.storage.set("learning/last-error/"+hash(scope),{time:new Date().toISOString(),message:String(error.message).slice(0,200)}).catch(()=>{});}
 });
 await ctx.tool.transform(editor=>editor.add({
  name:"watoom_learning_status",description:"Review this project's learned Skill candidates, validation, versions, curation and usage. No promotion or permission changes.",
  options:{codemode:false},input:{type:"object",properties:{},additionalProperties:false},
  execute:async()=>{const s=await learning.state();const output={scope,skills:Object.values(s.skills),metrics:s.metrics,curation:s.curation.slice(-5),operations:s.operations||{},archives:s.archives||[],existingSkills:{priorities:await optimisation.priorities(),history:(await optimisation.state()).history},deliveries:Object.values(s.outbox).reduce((a,e)=>(a[e.state]=(a[e.state]||0)+1,a),{})};return {content:JSON.stringify(output)};}
 }));
 await ctx.session.hook("context",async e=>{
  try{
  await syncExisting();
  if(e.agent!==agent)return;
  const query=JSON.stringify(e.messages.slice(-2)).slice(-4096);
  const prefix="Relevant verified project procedures (metadata only; use native skill tool when needed; preserve user preferences and permissions):\n";
  const found=await learning.retrieve(query,Math.max(0,metadataBytes-Buffer.byteLength(prefix)));
  const available=new Set(skills.map(k=>k.id)),ready=found.filter(k=>available.has(k.id));
  if(ready.length)e.system.push({type:"text",text:prefix+JSON.stringify(ready)});
  }catch(error){await ctx.storage.set("learning/last-error/"+hash(scope),{time:new Date().toISOString(),message:"Learning metadata unavailable; original session preserved"}).catch(()=>{});}
 });
 await curate();
 startupReturned=true;const startupTimer=setTimeout(()=>{void curate().catch(()=>{});},500);startupTimer.unref?.();
 let evaluationWatcher;try{if(options.evaluations)evaluationWatcher=watch(options.evaluations,{persistent:false},()=>{const t=setTimeout(()=>{void curate().catch(()=>{});},100);t.unref?.();});}catch{}
 const interval=setInterval(()=>{void curate().catch(()=>{});},Math.max(30000,options.curatorMs??900000));interval.unref?.();
 return ()=>{stopping=true;clearTimeout(startupTimer);evaluationWatcher?.close();clearInterval(interval);};
}
export default {id:"watoom.self-learning",setup:install};
