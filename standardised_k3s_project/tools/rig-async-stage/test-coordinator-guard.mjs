import {mkdtemp,readFile,rm,symlink} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
const reviewTestRoot=await mkdtemp(join(tmpdir(),"watoom-image-review-"));
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {install,BUDGET,assertAllowed,reviewReceipt,receiptMismatch,recoveryGrant,constrainDelegation,receiptPath,constrainReceipt,finalReceipt,terminalSchema,toolRecovery,archiveViewedImage,typedToolkitInput,requestContainsImage,semanticReceipt,isolatedReviewBody} from "./guard-source/index.js";
const clone=x=>x===undefined?undefined:structuredClone(x);
async function fixture(store=new Map(),seed) {
 const tools=new Map(),hooks=new Map(),toolHooks=new Map();
 let actual=0;
 const lastImageBySession=new Map();
 const result={content:[{type:"text",text:"ok"}]};
 for(const name of ["read","shell","write","edit","execute","subagent","skill","question"])tools.set(name,{id:name,name,execute:async(input)=>{
  actual++;
  if(input.fail)throw new Error("fixture failure");
  if(input.result)return input.result;
  return clone(result);
 }});
 const ctx={options:{imageReviewRoot:join(reviewTestRoot,"fixture"),verifiedVisionModels:["watoom/swift-qwen38-coder","watoom/qwen38-uncensored-mtp"]},
 storage:{get:async k=>clone(store.get(k)),set:async(k,v)=>{store.set(k,clone(v));}},
 session:{get:async()=>({metadata:{watoomCoordinationSeed:seed}}),hook:async(n,f)=>hooks.set(n,f)},
 tool:{hook:async(n,f)=>toolHooks.set(n,f),transform:async fn=>fn({list:()=>[...tools.values()],add:tool=>tools.set(tool.name,{...tool,id:tool.name}),update:(id,fn)=>fn(tools.get(id))})}};
 await install(ctx);
 let id=0;
 return {store,ctx,hooks,actual:()=>actual,raw:(name,input,context)=>tools.get(name).execute(input,context),call:async(name,input={},agent="watoom-workflow",sessionID="s")=>{
 const context={agent,sessionID,messageID:"m",id:"c"+(++id)},event={...context,tool:name,input};
 if(toolHooks.has("execute.before"))await toolHooks.get("execute.before")(event);
 let result;
 try {result=await tools.get(name).execute(input,context);}
 catch(error){if(toolHooks.has("execute.after"))await toolHooks.get("execute.after")({...event,status:"error",error});throw error;}
 const image=(Array.isArray(result?.content)?result.content:[]).find(p=>p.type==="file" && p.uri?.startsWith("data:image/"));if(image)lastImageBySession.set(sessionID,image.uri);
 if(toolHooks.has("execute.after"))await toolHooks.get("execute.after")({...event,status:"completed",result});
 return result;
 },
 context:async(agent="watoom-workflow",messages=[],sessionID="s",model={providerID:"watoom",id:"swift-qwen38-coder"})=>{
  const event={agent,sessionID,model,messages,tools:Object.fromEntries([...tools].map(([n])=>[n,{}])),system:[]};await hooks.get("context")(event);
  if(messages.length && lastImageBySession.has(sessionID)) {
   const request={sessionID,agent,model,kind:"primary",request:new Request("http://local/v1/chat/completions",{method:"POST",body:JSON.stringify({messages:[{content:[{type:"image_url",image_url:{url:lastImageBySession.get(sessionID)}}]}],tools:Object.keys(event.tools).map(name=>({type:"function",function:{name}}))})})};
   await hooks.get("http.request")(request);await hooks.get("http.response")({...request,response:new Response("{}",{status:200})});
  }
  return event;
 }};
}
let f=await fixture();
for(let n=0;n<BUDGET;n++)await f.call("shell",{command:"different-"+n});
assert(!("shell" in (await f.context()).tools));
await assert.rejects(()=>f.call("shell"),/HANDOFF_REQUIRED/);
await f.call("write",{path:"/p/.opencode/work/t/checkpoint.md",content:"resume"});
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder",background:true}),/SERIAL/);
await f.call("subagent",{agent:"watoom-critic",result:{output:{sessionID:"child",status:"completed"},content:"<subagent>ok</subagent>"}});
assert("shell" in (await f.context()).tools);
assert.equal(f.store.get("session/s").lastHandoff.sessionID,"child");
// Persist budget across restart and ensure unrelated sessions/agents stay independent.
for(let n=0;n<BUDGET;n++)await f.call("shell",{command:"work-"+n});
const restored=await fixture(f.store);
assert(!("shell" in (await restored.context()).tools));
assert("shell" in (await restored.context("watoom-workflow",[],"other")).tools);
await restored.call("shell",{},"watoom-builder");
f=await fixture();
await assert.rejects(()=>f.call("shell",{fail:true}));
await assert.rejects(()=>f.call("shell",{fail:true}));
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder"}),/CRITIC_REQUIRED/);
await f.call("subagent",{agent:"watoom-critic",result:{output:{sessionID:"critic",status:"completed"},content:[]}});
assert("shell" in (await f.context()).tools);
// Only a real completed child resets budget; running child must be continued.
f=await fixture(new Map(),{direct:6});
await f.call("subagent",{agent:"watoom-builder",result:{output:{sessionID:"pending",status:"running"},content:[]}});
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder"}),/CHILD_PENDING/);
assert(!("shell" in (await f.context()).tools));
await f.call("subagent",{agent:"watoom-builder",sessionID:"pending",result:{output:{sessionID:"pending",status:"completed"},content:[]}});
// Pixel provenance, verified-model presentation and structured receipt enforcement.
f=await fixture();
const bytes=Buffer.from("testimage"),uri="data:image/png;base64,"+bytes.toString("base64"),sha=createHash("sha256").update(bytes).digest("hex");
await f.call("read",{path:"/p/render.png",result:{content:[{type:"file",uri,mime:"image/png"}]}});
await assert.rejects(()=>f.call("shell",{command:"identify render.png"}),/VISION_REVIEW_REQUIRED/);
let event=await f.context("watoom-workflow",[]);
assert(!("shell" in event.tools));
const receipt={path:"/p/.opencode/validation/t/visual-review.json",content:JSON.stringify({image_path:"/p/render.png",image_sha256:sha,model:"watoom/swift-qwen38-coder",basis:"pixels",review_version:2,review_scope:"single_frame_pixels",framing:{usable:true,issues:[]},uncertainties:[],inferences:[],verdict:"PASS",observations:["A green triangle is on the left.","A purple circle is on the right."]})};
await assert.rejects(()=>f.call("write",receipt),/VISION_REVIEW_REQUIRED/);
await f.context("watoom-workflow",[{content:[{type:"media",media:{mime:"image/png"}}]}]);
await assert.rejects(()=>f.call("write",{...receipt,content:receipt.content.replace(sha,"0".repeat(64))}),/VISION_REVIEW_REQUIRED/);
await f.call("write",receipt);
assert.equal(f.store.get("session/s").pendingVisual,null);
assert.equal(f.store.get("session/s").reviews[0].sha256,sha);
assert(!("shell" in (await f.context()).tools));
await f.call("subagent",{agent:"watoom-critic",result:{output:{sessionID:"corrective-critic",status:"completed"},content:[]}});
assert("shell" in (await f.context()).tools);
// Same accepted hash is reusable, and metadata-only reads do not become visual evidence.
await f.call("read",{path:"/p/render.png",result:{content:[{type:"file",uri,mime:"image/png"}]}});
assert.equal(f.store.get("session/s").pendingVisual,null);
f=await fixture();await f.call("read",{path:"/p/info.json"});
assert.equal(f.store.get("session/s").pendingVisual,null);
f=await fixture();await f.call("read",{path:"/p/render.png",result:{content:[{type:"file",uri,mime:"image/png"}]}});
await f.context("watoom-workflow",[{content:[{type:"media"}]}],"s",{providerID:"other",id:"text-only"});
assert.equal(f.store.get("session/s").pendingVisual.presentedBy,null);
// Parallel direct calls cannot bypass the same-session reservation.
f=await fixture();
const settled=await Promise.allSettled(Array.from({length:10},(_,n)=>f.call("shell",{command:String(n)})));
assert.equal(settled.filter(x=>x.status==="fulfilled").length,BUDGET);
assert.equal(f.actual(),BUDGET);
// Read-only child review must be genuine; retain its identity on invalid completion.
f=await fixture(new Map(),{direct:6});
const childState={version:1,direct:0,errors:0,child:null,pendingVisual:{path:"/p/render.png",sha256:sha,presentedBy:"watoom/swift-qwen38-coder",reviewMode:"isolated-image-v2",additionalReads:0},reviews:[],calls:[]};
f.store.set("session/visual-child",childState);
await assert.rejects(()=>f.call("subagent",{agent:"watoom-reviewer",result:{output:{sessionID:"visual-child",status:"completed",output:"It looks good."},content:"done"}}),/VISION_CHILD_REVIEW_REQUIRED/);
assert.equal(f.store.get("session/s").child,"visual-child");
assert.equal(f.store.get("session/s").errors,0);
await assert.rejects(()=>f.call("subagent",{agent:"watoom-reviewer"}),/CHILD_PENDING/);
await f.call("subagent",{agent:"watoom-reviewer",sessionID:"visual-child",result:{output:{sessionID:"visual-child",status:"completed",output:receipt.content},content:"done"}});
assert.equal(f.store.get("session/s").child,null);
assert.equal(f.store.get("session/s").reviews[0].receipt.basis,"pixels");
assert.equal(f.store.get("session/visual-child").pendingVisual,null);
// Unfinished image evidence cannot be replaced; ordinary prompt prefix stays stable.
f=await fixture();const open1=(await f.context()).system;
await f.call("read",{path:"/p/info.json"});assert.deepEqual((await f.context()).system,open1);
await f.call("read",{path:"/p/render.png",result:{content:[{type:"file",uri,mime:"image/png"}]}});
await assert.rejects(()=>f.call("read",{path:"/p/other.png"}),/current image review/);
assert.equal(f.store.get("session/s").pendingVisual.sha256,sha);
// Reused outer Code Mode call IDs cannot make nested executions free.
f=await fixture();
const outer={agent:"watoom-workflow",sessionID:"s",messageID:"same-message",id:"same-call"};
for(let n=0;n<BUDGET;n++)await f.raw("shell",{command:"identical"},outer);
await assert.rejects(()=>f.raw("shell",{command:"identical"},outer),/HANDOFF_REQUIRED/);
// Exhausted coordinators cannot burn tokens loading skills or rewriting checkpoints.
f=await fixture(new Map(),{direct:6});
await assert.rejects(()=>f.call("skill",{id:"opencode"}),/HANDOFF_REQUIRED/);
assert(!("skill" in (await f.context()).tools));
await f.call("write",{path:"/p/.opencode/work/t/checkpoint.md",content:"handoff required"});
await assert.rejects(()=>f.call("write",{path:"/p/.opencode/work/t/checkpoint.md",content:"same checkpoint again"}),/HANDOFF_REQUIRED/);
assert(!("write" in (await f.context()).tools));
assert.deepEqual(Object.keys((await f.context()).tools),["subagent"]);
// Concurrent foreground subagent admission is serialized before native spawn.
f=await fixture();
const concurrent=await Promise.allSettled([
 f.call("subagent",{agent:"watoom-investigator",result:{output:{sessionID:"one",status:"completed"},content:"ok"}}),
 f.call("subagent",{agent:"watoom-investigator",result:{output:{sessionID:"two",status:"completed"},content:"ok"}})
]);
assert.equal(concurrent.filter(x=>x.status==="fulfilled").length,1);
assert.equal(f.actual(),1);
assert.equal(f.store.get("session/s").childCall,null);
f.store.get("session/s").childCall="stale";await f.context();assert.equal(f.store.get("session/s").childCall,null);
console.log("PASS budget/bypass, durable restart, scope, serial child, critic, image provenance, model verification, receipt validation, replay and concurrent reservation");

// Relative receipt paths get an exact diagnostic; repeated child rejections return control.
f=await fixture();
await f.call("read",{path:"/p/render.png",result:{content:[{type:"file",uri,mime:"image/png"}]}},"watoom-investigator","child-bad");
await f.context("watoom-investigator",[{content:[{type:"media"}]}],"child-bad");
const bad={...receipt,content:receipt.content.replace('"/p/render.png"','"render.png"')};
await assert.rejects(()=>f.call("write",bad,"watoom-investigator","child-bad"),/READ_ONLY_HANDOFF/);
await assert.rejects(()=>f.call("write",bad,"watoom-investigator","child-bad"),/READ_ONLY_HANDOFF/);
assert.deepEqual(Object.keys((await f.context("watoom-investigator",[],"child-bad")).tools),["subagent"]);
await f.call("subagent",{agent:"watoom-investigator",result:{output:{sessionID:"child-bad",status:"completed",output:receipt.content},content:[]}},"watoom-workflow","parent-bad");
assert.equal(f.store.get("session/parent-bad").errors,2);
console.log("PASS exact receipt diagnosis and child critic escalation");

// Child delegation is limited to exactly one foreground critic; critic cannot delegate.
f=await fixture();
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder"},"watoom-investigator","i"),/CRITIC_ONLY/);
await assert.rejects(()=>f.call("subagent",{agent:"watoom-critic",background:true},"watoom-investigator","i"),/SERIAL/);
await f.call("subagent",{agent:"watoom-critic",result:{output:{sessionID:"nested-critic",status:"completed"},content:[]}},"watoom-investigator","i");
await assert.rejects(()=>f.call("subagent",{agent:"watoom-critic"},"watoom-investigator","i"),/RETURN_TO_COORDINATOR/);
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder"},"watoom-critic","nested-critic"),/CRITIC_ONLY/);
console.log("PASS critic-only nested foreground delegation");

await assert.rejects(()=>f.call("write",{path:"/p/file",content:"no"},"watoom-critic","nested-critic"),/CRITIC_READ_ONLY/);

// A pending visual child can return evidence even after parent errors, then critic remains mandatory.
f=await fixture(new Map(),{direct:6});
f.store.set("session/review-recovery",{...structuredClone(childState),callingAgent:"watoom-reviewer",guardRejections:2});
await assert.rejects(()=>f.call("subagent",{agent:"watoom-reviewer",result:{output:{sessionID:"review-recovery",status:"completed",output:"BLOCKED prose, no matching JSON"},content:[]}}),/VISION_CHILD_REVIEW_REQUIRED/);
f.store.get("session/s").errors=2;
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder",sessionID:"review-recovery"}),/CHILD_AGENT_MISMATCH/);
await f.call("subagent",{agent:"watoom-reviewer",sessionID:"review-recovery",result:{output:{sessionID:"review-recovery",status:"completed",output:receipt.content},content:[]}});
assert.equal(f.store.get("session/review-recovery").pendingVisual,null);
assert.equal(f.store.get("session/s").errors,2);
await assert.rejects(()=>f.call("shell"),/HANDOFF_REQUIRED/);
console.log("PASS existing-child evidence recovery retains critic and pixel validation");

// Repeated completed-without-receipt returns stop parent retries without accepting evidence.
f=await fixture(new Map(),{direct:6});
f.store.set("session/loop-child",{...structuredClone(childState),callingAgent:"watoom-builder",guardRejections:2,criticConsulted:true});
const invalid={output:{sessionID:"loop-child",status:"completed",output:"BLOCKED, no valid receipt"},content:[]};
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder",result:invalid}),/VISION_CHILD_REVIEW_REQUIRED/);
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder",sessionID:"loop-child",result:invalid}),/VISION_CHILD_REVIEW_REQUIRED/);
assert.equal(f.store.get("session/s").childReviewBlocked,true);
const stopped=await f.context();
assert.equal(Object.keys(stopped.tools).length,0);
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder",sessionID:"loop-child"}),/VISION_CHILD_BLOCKED/);
assert(f.store.get("session/loop-child").pendingVisual);
const exhausted=await f.context("watoom-builder",[],"loop-child");
assert.deepEqual(Object.keys(exhausted.tools),["write"]);
assert(JSON.stringify(exhausted.system).includes("use native write to save"));
await assert.rejects(()=>f.call("write",{path:"/p/ordinary.txt",content:"bypass"},"watoom-builder","loop-child"),/VISION_REVIEW_REQUIRED/);
await f.call("write",receipt,"watoom-builder","loop-child");
assert.equal(f.store.get("session/loop-child").pendingVisual,null);
assert.equal(f.store.get("session/loop-child").reviews[0].sha256,sha);
console.log("PASS bounded visual-child retries and consistent exhausted-builder final receipt");

// Exact observed/observations regression: do not misdiagnose valid paths.
const malformed={...receipt,content:JSON.stringify({...JSON.parse(receipt.content),observations:undefined,observed:["A real visible observation.","A second visible observation."]})};
assert.match(receiptMismatch(malformed,childState),/observations must be an array/);
assert.equal(reviewReceipt({...receipt,content:"null"},childState),false);
assert.match(receiptMismatch({...receipt,content:"null"},childState),/JSON object/);
f=await fixture();f.store.set("session/schema-child",{...structuredClone(childState),callingAgent:"watoom-builder"});
await assert.rejects(()=>f.call("write",malformed,"watoom-builder","schema-child"),/observations must/);
await assert.rejects(()=>f.call("write",malformed,"watoom-builder","schema-child"),/observations must/);
let limited=await f.context("watoom-builder",[],"schema-child");
assert(!Object.keys(limited.tools).includes("write"));
f.store.get("session/schema-child").criticConsulted=true;
limited=await f.context("watoom-builder",[],"schema-child");assert(Object.keys(limited.tools).includes("write"));
await assert.rejects(()=>f.call("write",malformed,"watoom-builder","schema-child"),/observations must/);
limited=await f.context("watoom-builder",[],"schema-child");assert.equal(Object.keys(limited.tools).length,0);
// Honest corrected evidence remains valid; the parent can also verify final JSON.
await f.call("write",receipt,"watoom-builder","schema-child");
assert.equal(f.store.get("session/schema-child").pendingVisual,null);
console.log("PASS exact receipt field diagnostics, critic boundary and bounded post-critic correction");

// Child execution failure -> one critic -> one changed repair; no continuing failure cycle.
f=await fixture();
await assert.rejects(()=>f.call("shell",{fail:true},"watoom-builder","worker"),/fixture failure/);
await f.call("execute",{result:{isError:true,content:[]}},"watoom-builder","worker");
assert.deepEqual(Object.keys((await f.context("watoom-builder",[],"worker")).tools),["subagent"]);
await f.call("subagent",{agent:"watoom-critic",result:{output:{sessionID:"failure-critic",status:"completed",output:"REVISE"},content:[]}},"watoom-builder","worker");
await assert.rejects(()=>f.call("shell",{fail:true},"watoom-builder","worker"),/fixture failure/);
assert.equal(Object.keys((await f.context("watoom-builder",[],"worker")).tools).length,0);
await assert.rejects(()=>f.call("subagent",{agent:"watoom-critic",model:"other/model"},"watoom-builder","worker"),/MODEL_INHERIT/);
console.log("PASS worker failure escalation, single post-critic repair and inherited model");

// Historic child failures do not create a new critic cycle on clean continuation.
f=await fixture();f.store.set("session/old-worker",{...structuredClone(childState),pendingVisual:null,callingAgent:"watoom-builder",guardRejections:20});
await f.call("subagent",{agent:"watoom-builder",sessionID:"old-worker",result:{output:{sessionID:"old-worker",status:"completed",output:"PASS bounded package"},content:[]}});
assert.equal(f.store.get("session/s").errors,0);
await assert.rejects(()=>f.call("write",receipt),/PROVENANCE_REQUIRED/);
const canonical={...childState,callingAgent:"watoom-builder",isChild:true,sessionID:"kid",pendingVisual:null};
assert.throws(()=>assertAllowed("write",{path:"/p/.opencode/work/t/checkpoint.json",content:"{}"},canonical,false),/CHECKPOINT_OWNER/);
assert.doesNotThrow(()=>assertAllowed("write",{path:"/p/.opencode/work/t/children/kid/findings.json",content:"{}"},canonical,false));
console.log("PASS stale child counters, receipt provenance and canonical checkpoint ownership");

// Operator recovery is exact, single use and still requires matching child pixel JSON.
f=await fixture(new Map(),{direct:6});
f.store.set("session/blocked-critic",{...structuredClone(childState),callingAgent:"watoom-critic"});
f.store.set("session/s",{direct:6,errors:2,reviews:[],calls:[],child:"blocked-critic",childReviewBlocked:true,childReviewAttempts:2});
const grant={parentSessionID:"s",childSessionID:"blocked-critic",image_sha256:sha,nonce:"a".repeat(64)};
f.ctx.options.visualRecoveryGrants=[grant];
assert.deepEqual(Object.keys((await f.context()).tools),["subagent"]);
await f.call("subagent",{agent:"watoom-critic",sessionID:"blocked-critic",result:{output:{sessionID:"blocked-critic",status:"completed",output:receipt.content},content:[]}});
assert.equal(f.store.get("session/blocked-critic").pendingVisual,null);
assert.equal(f.store.get("session/s").childReviewBlocked,false);
assert(f.store.get("session/s").consumedRecoveryGrants.includes(grant.nonce));
const blocked={child:"blocked-critic",childReviewBlocked:true,consumedRecoveryGrants:[grant.nonce]};
assert.equal(recoveryGrant(blocked,"s",f.ctx.options,childState),undefined);
assert.equal(recoveryGrant({...blocked,consumedRecoveryGrants:[]},"wrong-parent",f.ctx.options,childState),undefined);
console.log("PASS single-use exact-child operator reconciliation; evidence not bypassed");

assert.throws(()=>assertAllowed("write",{path:"/p/.opencode/work/task/children/child/../../checkpoint.json",content:"x"},{isChild:true,sessionID:"child",callingAgent:"watoom-builder"},false),/CHECKPOINT_OWNER/);
console.log("PASS canonical checkpoint parent-traversal rejection");

for(const role of ["watoom-investigator","watoom-reviewer"]) {
 assert.throws(()=>assertAllowed("watoom_specialist_run",{capability:"world.compose"},{callingAgent:role},false),/READ_ONLY_PIPELINE/);
 assert.throws(()=>assertAllowed("watoom_specialist_run",{capability:"asset.index"},{callingAgent:role},false),/READ_ONLY_PIPELINE/);
 assert.doesNotThrow(()=>assertAllowed("watoom_specialist_run",{capability:"asset.search"},{callingAgent:role},false));
}
assert.doesNotThrow(()=>assertAllowed("watoom_specialist_run",{capability:"world.compose"},{callingAgent:"watoom-builder"},false));
console.log("PASS read-only pipeline dispatch boundary with catalog search retained");

// Native pre-execution hook rejection must survive its thrown API error.
f=await fixture();
await assert.rejects(()=>f.call("subagent",{agent:"explore"},"watoom-builder","bad-child"),/CRITIC_ONLY/);
await assert.rejects(()=>f.call("subagent",{agent:"explore"},"watoom-builder","bad-child"),/CRITIC_ONLY/);
assert.equal(f.store.get("session/bad-child").guardRejections,2);
assert.match(f.store.get("session/bad-child").lastGuardError,/CRITIC_ONLY/);
const badContext=await f.context("watoom-builder",[],"bad-child");
assert.deepEqual(Object.keys(badContext.tools),["subagent"]);
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder",sessionID:"s"}),/CHILD_SESSION_REQUIRED/);
assert.match(f.store.get("session/s").lastGuardError,/CHILD_SESSION_REQUIRED/);
console.log("PASS durable native delegation rejection and parent/child resume identity");

const shaped={agent:"watoom-builder",sessionID:"parent",tools:{subagent:{description:"Available: explore general",input:{type:"object",properties:{model:{type:"string"}},required:["agent","prompt"]}}}};
constrainDelegation(shaped,{callingAgent:"watoom-builder"});
assert.deepEqual(shaped.tools.subagent.input.properties.agent.enum,["watoom-critic"]);
assert(!("model" in shaped.tools.subagent.input.properties));
assert(!shaped.tools.subagent.description.includes("explore"));
constrainDelegation(shaped,{criticConsulted:true});
assert(!shaped.tools.subagent);
const parentShape={agent:"watoom-workflow",sessionID:"parent",tools:{subagent:{input:{type:"object",properties:{}}}}};
constrainDelegation(parentShape,{child:"child"},{callingAgent:"watoom-builder"});
assert.deepEqual(parentShape.tools.subagent.input.properties.agent.enum,["watoom-builder"]);
assert.deepEqual(parentShape.tools.subagent.input.properties.sessionID.enum,["child"]);
assert(parentShape.tools.subagent.input.required.includes("sessionID"));
assert.deepEqual(parentShape.tools.subagent.input.properties.background.enum,[false]);

const freshCritic={agent:"watoom-investigator",sessionID:"parent",tools:{subagent:{input:{type:"object",properties:{sessionID:{type:"string"},prompt:{type:"string"}},required:["prompt","sessionID"]}}}};
constrainDelegation(freshCritic,{callingAgent:"watoom-investigator",errors:2});
assert(!("sessionID" in freshCritic.tools.subagent.input.properties));
assert(!freshCritic.tools.subagent.input.required.includes("sessionID"));
assert.equal(freshCritic.tools.subagent.input.additionalProperties,false);
const knownChild={agent:"watoom-workflow",sessionID:"parent",tools:{subagent:{input:{type:"object",properties:{sessionID:{type:"string"}}}}}};
constrainDelegation(knownChild,{lastHandoff:{sessionID:"real-child",agent:"watoom-investigator",completed:true}});
assert.deepEqual(knownChild.tools.subagent.input.properties.sessionID.enum,["real-child"]);
assert(!(knownChild.tools.subagent.input.required || []).includes("sessionID"));
console.log("PASS model-visible delegation choices match enforced role and pending-child identity");

// Established pipeline reports paths are accepted only for the pending revision.
const pipelineState={pendingVisual:{path:"/data/ai/projects/pipelines/bench-v1/renders/side.png",sha256:sha,presentedBy:"watoom/swift-qwen38-coder",reviewMode:"isolated-image-v2"}};
const pipelineReceipt={path:"/data/ai/projects/pipelines/bench-v1/reports/visual-review.json",content:JSON.stringify({...JSON.parse(receipt.content),image_path:pipelineState.pendingVisual.path})};
assert(reviewReceipt(pipelineReceipt,pipelineState));
assert(!receiptPath("/data/ai/projects/pipelines/bench-v2/reports/visual-review.json",pipelineState));
assert(!receiptPath("/data/ai/projects/pipelines/bench-v1/reports/../reports/visual-review.json",pipelineState));
assert(!reviewReceipt({...pipelineReceipt,content:pipelineReceipt.content.replace(sha,"0".repeat(64))},pipelineState));
const receiptEvent={sessionID:"child-review",tools:{write:{input:{type:"object",properties:{path:{type:"string"},content:{type:"string"}}}}}};
constrainReceipt(receiptEvent,pipelineState);
assert(reviewReceipt({...pipelineReceipt,path:receiptEvent.tools.write.input.properties.path.enum[0]},pipelineState));
assert(receiptEvent.tools.write.input.properties.content);
console.log("PASS revision-bound pipeline receipt path, provenance checks and exact write schema");

// Model prose around one receipt is formatting, not missing provenance.
assert.deepEqual(finalReceipt("I have reviewed the image.\n\n"+receipt.content),JSON.parse(receipt.content));
assert.deepEqual(finalReceipt("```json\n"+receipt.content+"\n```"),JSON.parse(receipt.content));
assert.equal(finalReceipt(receipt.content+"\n"+receipt.content),null);
assert.equal(finalReceipt("<tool_call><function=read></function></tool_call>"),null);
assert.equal(finalReceipt("x".repeat(32769)+receipt.content),null);
f=await fixture();
f.store.set("session/wrapped-child",{direct:0,errors:0,reviews:[],calls:[],pendingVisual:{path:"/p/render.png",sha256:sha,presentedBy:"watoom/swift-qwen38-coder",reviewMode:"isolated-image-v2"}});
await f.call("subagent",{agent:"watoom-reviewer",result:{output:{sessionID:"wrapped-child",status:"completed",output:"Returning the receipt:\n"+receipt.content},content:[]}});
assert.equal(f.store.get("session/wrapped-child").pendingVisual,null);
assert.equal(f.store.get("session/s").child,null);
console.log("PASS prose-wrapped receipt reconciles native child without bypassing provenance; ambiguity/XML rejected");

// Never accept simulated tool XML as a completed native child package.
f=await fixture();
const simulated={output:{sessionID:"xml-child",status:"completed",output:"<tool_call>\n<function=read>ignored</function>\n</tool_call>"},content:[]};
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder",result:simulated}),/NATIVE_TOOL_CALL_REQUIRED/);
assert.equal(f.store.get("session/s").child,"xml-child");
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder",sessionID:"xml-child",result:simulated}),/NATIVE_TOOL_CALL_REQUIRED/);
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder",sessionID:"xml-child",result:simulated}),/NATIVE_CHILD_BLOCKED/);
assert.deepEqual(Object.keys((await f.context()).tools),[]);
assert.throws(()=>assertAllowed("shell",{command:"godot --headless -s res://scripts/test_runner.gd"},{},false),/EXTERNAL_GODOT_REGRESSION_REQUIRED/);
assert.doesNotThrow(()=>assertAllowed("shell",{command:"godot --headless --check-only -s scripts/shepherd.gd"},{},false));
console.log("PASS simulated child calls bounded/rejected and full regression fenced out of app shell");

assert.doesNotThrow(()=>assertAllowed("shell",{command:"rg -n failure /data/ai/projects/games/magpie-flight-godot-candidate/scripts/test_runner.gd"},{},false));

// Syntax-only checking never executes the test suite and must remain available.
assert.doesNotThrow(()=>assertAllowed("shell",{command:"godot --headless --check-only -s scripts/test_runner.gd"},{},false));
assert.throws(()=>assertAllowed("shell",{command:"godot --headless -s scripts/test_runner.gd"},{},false),/EXTERNAL_GODOT_REGRESSION_REQUIRED/);
assert.equal(terminalSchema({},"s").properties.result.const,"BLOCKED");
f=await fixture();f.store.set("session/s",{terminalReport:true,lastGuardError:"guard boundary"});
const http={model:{providerID:"watoom",id:"swift-qwen38-coder"},sessionID:"s",agent:"watoom-workflow",kind:"primary",request:new Request("http://local/v1/chat/completions",{method:"POST",body:JSON.stringify({messages:[],tools:[]})})};
await f.hooks.get("http.request")(http);
assert.equal((await http.request.json()).response_format.json_schema.schema.properties.blocker.const,"guard boundary");
const withTools={...http,request:new Request("http://local/v1/chat/completions",{method:"POST",body:JSON.stringify({tools:[{name:"read"}]})})};
await f.hooks.get("http.request")(withTools);assert.equal((await withTools.request.json()).response_format,undefined);
const recoveryState={child:"c",simulatedCallBlocked:"c"},g={parentSessionID:"p",childSessionID:"c",nonce:"a".repeat(64)},childRecovery={errors:0,lastGuardError:"EXTERNAL_GODOT_REGRESSION_REQUIRED: old parse-only rejection"};
assert.equal(toolRecovery(recoveryState,"p",{toolRecoveryGrants:[g]},childRecovery),g);
assert.equal(toolRecovery(recoveryState,"p",{toolRecoveryGrants:[g]},{...childRecovery,pendingVisual:{}}),undefined);
assert.equal(toolRecovery(recoveryState,"p",{toolRecoveryGrants:[g]},{...childRecovery,errors:2}),undefined);
console.log("PASS parse-only classification, constrained tool-disabled transport and scoped nonvisual recovery");

const observed={content:[{type:"file",uri:"data:image/png;base64,"+Buffer.from("neutral image fixture").toString("base64")}]};
const one=await archiveViewedImage(observed,{path:"/project/renders/side.png"},{sessionID:"ses_fixture",agent:"watoom-builder"},join(reviewTestRoot,"archive"));
const two=await archiveViewedImage(observed,{path:"/project/renders/side.png"},{sessionID:"ses_fixture",agent:"watoom-builder"},join(reviewTestRoot,"archive"));
assert.deepEqual(one,two);assert.equal((await readFile(one[0])).toString(),"neutral image fixture");
assert.equal(JSON.parse(await readFile(one[0]+".json","utf8")).source_path,"/project/renders/side.png");
await symlink(join(reviewTestRoot,"archive"),join(reviewTestRoot,"unsafe"));
await assert.rejects(()=>archiveViewedImage(observed,{}, {sessionID:"ses_fixture"},join(reviewTestRoot,"unsafe")),/symlink/);
await rm(reviewTestRoot,{recursive:true,force:true});
console.log("PASS viewed-image copy, deduplication, provenance and symlink rejection");

// A cleared recovery marker and completed child are both null, not a blocked identity.
f=await fixture();f.store.set("session/s",{direct:0,errors:0,calls:[],reviews:[],child:null,simulatedCallBlocked:null});
assert("subagent" in (await f.context()).tools);
await f.call("subagent",{agent:"watoom-builder",result:{output:{sessionID:"next-package",status:"completed",output:"RESULT=PARTIAL; runtime pending"},content:[]}});
assert("shell" in (await f.context()).tools);
console.log("PASS null recovery markers never block a completed-child coordinator");

const searchRequest={capability:"asset.search",specialistID:"local-toolkit",job:"bounded-search",payload:{query:"tree",limit:8}};
assert.deepEqual(typedToolkitInput("watoom_specialist_run",searchRequest).payload,{query:"tree",limit:8,task:"asset-search"});
assert.equal(searchRequest.payload.task,undefined);
const wrongTask={...searchRequest,payload:{task:"wrong"}};assert.equal(typedToolkitInput("watoom_specialist_run",wrongTask),wrongTask);
assert.equal(typedToolkitInput("other",searchRequest),searchRequest);
assert.equal(terminalSchema({lastExecutionError:{message:"Creative capability/task mismatch"}},"s").properties.blocker.const,"Creative capability/task mismatch");
console.log("PASS canonical search discriminator and precise terminal error provenance");

const exactPixels="data:image/png;base64,"+Buffer.from("verified pixels").toString("base64");
const exactSha=createHash("sha256").update("verified pixels").digest("hex");
assert(requestContainsImage({content:[{type:"image_url",image_url:{url:exactPixels}}]},exactSha));
assert(!requestContainsImage({type:"image_url",image_url:{url:exactPixels}},"0".repeat(64)));
assert(!requestContainsImage({type:"media"},exactSha));
f=await fixture();f.store.set("session/s",{direct:6,errors:2,calls:[],reviews:[],pendingVisual:{path:"/p/a.png",sha256:exactSha,presentedBy:null,additionalReads:0}});
assert("read" in (await f.context()).tools);
const provenanceEvent={sessionID:"s",agent:"watoom-workflow",model:{providerID:"watoom",id:"swift-qwen38-coder"},kind:"primary",request:new Request("http://local/v1/chat/completions",{method:"POST",body:JSON.stringify({messages:[{content:[{type:"image_url",image_url:{url:exactPixels}}]}]})})};
await f.hooks.get("http.request")(provenanceEvent);assert.equal(f.store.get("session/s").pendingVisual.presentedBy,null);
await f.hooks.get("http.response")({...provenanceEvent,response:new Response("failed",{status:500})});assert.equal(f.store.get("session/s").pendingVisual.presentedBy,null);
await f.hooks.get("http.request")(provenanceEvent);await f.hooks.get("http.response")({...provenanceEvent,response:new Response("{}",{status:200})});
assert.equal(f.store.get("session/s").pendingVisual.presentedBy,"watoom/swift-qwen38-coder");
console.log("PASS exact outbound image provenance, failed-response rejection and pending-review reread priority");

assert(!semanticReceipt({review_version:2,review_scope:"single_frame_pixels",verdict:"PASS",framing:{usable:false,issues:["subject clipped"]},uncertainties:[],inferences:[]}));
const neutralBody=isolatedReviewBody({messages:[{role:"system",content:"Expected lush hills and perfect trees"},{role:"user",content:[{type:"image_url",image_url:{url:exactPixels}}]}],tools:[{type:"function",function:{name:"write"}},{type:"function",function:{name:"shell"}}]}, {path:"/p/renders/a.png",sha256:exactSha},"watoom/swift-qwen38-coder","s");
assert(!JSON.stringify(neutralBody.messages).includes("Expected lush hills"));
assert.equal(neutralBody.tools.length,1);assert.equal(neutralBody.tools[0].function.name,"write");assert.equal(neutralBody.temperature,0);
assert(requestContainsImage(neutralBody.messages,exactSha));
const noWrite=isolatedReviewBody({messages:[{content:[{type:"image_url",image_url:{url:exactPixels}}]}]}, {path:"/p/a.png",sha256:exactSha},"watoom/swift-qwen38-coder","s");
assert.equal(noWrite.tools,undefined);assert.equal(noWrite.response_format.json_schema.schema.properties.review_version.const,2);
console.log("PASS isolated semantic review, framing rejection, exact pixels and role-preserving native write");

assert(!semanticReceipt({review_version:2,review_scope:"single_frame_pixels",verdict:"PASS",framing:{usable:true,issues:[]},uncertainties:[],inferences:["unverified source identity"]}));
assert(!semanticReceipt({review_version:2,review_scope:"single_frame_pixels",verdict:"FAIL",framing:{usable:false,issues:[]},uncertainties:[],inferences:[]}));

assert(!semanticReceipt({...JSON.parse(receipt.content),type:"object",properties:{}}));

// Text/object tool results are not image arrays and must not emit archive errors.
for (const content of ["plain text",{text:"structured tool result"},null,undefined]) assert.deepEqual(await archiveViewedImage({content},{},{sessionID:"shape-test"},reviewTestRoot),[]);

const workerRoleFixture=await fixture();
for(const role of ["watoom-workflow","watoom-builder"])assert("watoom_game_worker" in (await workerRoleFixture.context(role,[],"worker-"+role)).tools);
for(const role of ["watoom-critic","watoom-reviewer","watoom-investigator"])assert(!("watoom_game_worker" in (await workerRoleFixture.context(role,[],"worker-"+role)).tools));
console.log("PASS native game worker launch visibility follows modifying versus read-only roles");

assert.throws(()=>assertAllowed("shell",{command:"godot --headless --editor --quit --path /p"},{},true),/EXTERNAL_GODOT_IMPORT_REQUIRED/);
assert.doesNotThrow(()=>assertAllowed("shell",{command:"godot --headless --check-only -s script.gd"},{},true));

// Current missing image presentation must outrank a stale checkpoint edit error.
assert.match(terminalSchema({pendingVisual:{path:"/p/a.png",presentedBy:null},lastExecutionError:{message:"Could not find oldString"}},"s").properties.blocker.const,/VISION_MODEL_REQUIRED/);
assert.equal(terminalSchema({lastChildReviewError:"missing presentation",lastExecutionError:{message:"Could not find oldString"}},"s").properties.blocker.const,"missing presentation");
const missingPresentation=await fixture(new Map([
 ["session/s",{version:1,direct:0,errors:0,child:"missing-vision",reviews:[],calls:[]}],
 ["session/missing-vision",{callingAgent:"watoom-builder",pendingVisual:{path:"/p/a.png",sha256:"a".repeat(64),presentedBy:null}}]
]));
const blockedContext=await missingPresentation.context();
assert.equal(Object.keys(blockedContext.tools).length,0);
assert.match(blockedContext.system.map(x=>x.text).join("\n"),/VISION_MODEL_REQUIRED/);

// Conversational Sims intake must not trap ordinary replies behind a form.
{
 const f=await fixture();
 assert("question" in (await f.context()).tools);
 await f.call("skill",{id:"sims"});
 let event=await f.context();
 assert(!("question" in event.tools));assert("read" in event.tools);
 assert(event.system.some(x=>x.text.includes("END THE TURN")));
 await assert.rejects(f.call("question",{questions:[]}),/SIMS_CONVERSATIONAL_INTAKE/,"stale descriptors cannot execute a blocking question");
 const reloaded=await fixture(f.store);event=await reloaded.context();
 assert(!("question" in event.tools),"intake policy survives plugin reload");
 assert("question" in (await reloaded.context("watoom-workflow",[],"unrelated")).tools,"unrelated sessions retain questions");
 f.ctx.session.get=async({sessionID})=>sessionID==="child" ? {parentID:"s"} : {};
 assert(!("question" in (await f.context("watoom-builder",[],"child")).tools),"Sims child inherits conversational intake");
}
{
 const f=await fixture();await f.call("skill",{id:"asset-image-clip-capture"});
 assert("question" in (await f.context()).tools,"other skills do not change intake policy");
}
{
 const f=await fixture();await assert.rejects(f.call("skill",{id:"sims",fail:true}));
 assert("question" in (await f.context()).tools,"failed skill load cannot enable intake mode");
}
console.log("PASS Sims plain-chat intake, reload persistence, child inheritance and unrelated-session isolation");
