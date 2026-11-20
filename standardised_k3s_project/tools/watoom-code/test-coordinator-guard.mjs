import {mkdtemp,readFile,rm,symlink} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";
const reviewTestRoot=await mkdtemp(join(tmpdir(),"watoom-image-review-"));
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {expectedSearchMiss,recordToolFailure,findingsHandoff,install,BUDGET,READ_BUDGET,promptDrop,trimSections,developmentProject,assertAllowed,reviewReceipt,receiptMismatch,recoveryGrant,constrainDelegation,receiptPath,constrainReceipt,finalReceipt,terminalSchema,toolRecovery,archiveViewedImage,typedToolkitInput,requestContainsImage,semanticReceipt,isolatedReviewBody,enqueueReview,REVIEW_QUEUE_TTL_MS} from "../../ansible/roles/watoom-code/files/coordinator-guard/index.js";
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
const receipt={path:"/p/.opencode/validation/t/visual-review.json",content:JSON.stringify({image_path:"/p/render.png",image_sha256:sha,model:"watoom/swift-qwen38-coder",basis:"pixels",review_version:2,review_scope:"single_frame_pixels",framing:{usable:true,issues:[]},defects:[],uncertainties:[],inferences:[],verdict:"PASS",observations:["A green triangle is on the left.","A purple circle is on the right."]})};
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
await assert.rejects(()=>f.call("read",{path:"/p/other.png"}),/queued for review after the current image/);
assert.equal(f.store.get("session/s").pendingVisual.sha256,sha);
// Reused outer Code Mode call IDs cannot make nested executions free.
f=await fixture();
const outer={agent:"watoom-workflow",sessionID:"s",messageID:"same-message",id:"same-call"};
for(let n=0;n<BUDGET;n++)await f.raw("shell",{command:"identical"},outer);
await assert.rejects(()=>f.raw("shell",{command:"identical"},outer),/HANDOFF_REQUIRED/);
// Exhausted coordinators may still load skills (free knowledge) but cannot rewrite checkpoints or do work.
f=await fixture(new Map(),{direct:BUDGET});
await f.call("skill",{id:"opencode"});
assert("skill" in (await f.context()).tools);
await f.call("write",{path:"/p/.opencode/work/t/checkpoint.md",content:"handoff required"});
await assert.rejects(()=>f.call("write",{path:"/p/.opencode/work/t/checkpoint.md",content:"same checkpoint again"}),/HANDOFF_REQUIRED/);
assert(!("write" in (await f.context()).tools));
assert.deepEqual(Object.keys((await f.context()).tools).sort(),["skill","subagent"]);
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
await assert.rejects(()=>f.call("shell"),/CRITIC_REQUIRED: .*agent watoom-critic/);
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
f=await fixture();f.store.set("session/old-worker",{...structuredClone(childState),pendingVisual:null,callingAgent:"watoom-builder",guardRejections:20,readEvidence:["/old/package/evidence"]});
await f.call("subagent",{agent:"watoom-builder",sessionID:"old-worker",result:{output:{sessionID:"old-worker",status:"completed",output:"PASS bounded package"},content:[]}});
assert.equal(f.store.get("session/s").errors,0);
await assert.rejects(()=>f.call("write",receipt),/PROVENANCE_REQUIRED/);
const canonical={...childState,callingAgent:"watoom-builder",isChild:true,sessionID:"kid",pendingVisual:null};
assert.throws(()=>assertAllowed("write",{path:"/p/.opencode/work/t/checkpoint.json",content:"{}"},canonical,false),/CHECKPOINT_OWNER/);
assert.doesNotThrow(()=>assertAllowed("write",{path:"/p/.opencode/work/t/children/kid/findings.json",content:"{}"},canonical,false));
assert.deepEqual(f.store.get("session/old-worker").readEvidence,[],"new package cannot inherit evidence from an old diagnosis");
console.log("PASS stale child counters, receipt provenance and canonical checkpoint ownership");

// The /data/github mount is readOnly:true for every repo under it (resources.json.j2), so an edit/write/patch
// or a non-read-only shell command targeting it is rejected up front instead of failing later as an opaque
// OS "Read-only file system" error after wasted discovery (or a remount attempt).
assert.throws(()=>assertAllowed("edit",{path:"/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/esp32/contract.py",old_string:"a",new_string:"b"},{},false),/SOURCE_REPO_READ_ONLY/);
assert.throws(()=>assertAllowed("write",{path:"/data/github/some-other-repo/README.md",content:"x"},{},false),/SOURCE_REPO_READ_ONLY/);
assert.throws(()=>assertAllowed("shell",{command:"mount -o remount,rw /data/github"},{},false),/SOURCE_REPO_READ_ONLY/);
assert.doesNotThrow(()=>assertAllowed("shell",{command:"cat /data/github/watoom-standardised-homelab/standardised_k3s_project/tools/esp32/contract.py"},{},false));
assert.doesNotThrow(()=>assertAllowed("write",{path:"/p/.opencode/work/t/notes.json",content:"{}"},{},false));
console.log("PASS /data/github is read-only for write/edit/patch and non-read-only shell, reads remain unaffected");

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
// A completed child is not offered for resume (its history would be replayed into context every call).
assert(!("sessionID" in knownChild.tools.subagent.input.properties));
assert(!(knownChild.tools.subagent.input.required || []).includes("sessionID"));
// A running or failed child is still resumed, exactly and only.
const pendingChild={agent:"watoom-workflow",sessionID:"parent",tools:{subagent:{input:{type:"object",properties:{sessionID:{type:"string"}}}}}};
constrainDelegation(pendingChild,{child:"stuck-child",lastHandoff:{sessionID:"real-child",agent:"watoom-investigator",completed:true}},{callingAgent:"watoom-builder"});
assert.deepEqual(pendingChild.tools.subagent.input.properties.sessionID.enum,["stuck-child"]);
assert(pendingChild.tools.subagent.input.required.includes("sessionID"));
console.log("PASS model-visible delegation choices match enforced role and pending-child identity");

// Regression: errors can reach 2 purely from guard-level rejections (a typo, a stale sessionID), with the
// outstanding child never having actually run and failed. The OLD precedence force-locked agent to that
// child's own (non-critic) agent -- the one and only schema-valid call -- while the execution gate separately
// demanded agent==="critic" for it: CHILD_AGENT_MISMATCH on one side, COORDINATOR_CRITIC_REQUIRED on the
// other, no reachable call either way. Critic-mandatory must win the lock and drop the stale resume identity.
const deadlocked={agent:"watoom-workflow",sessionID:"parent",tools:{subagent:{input:{type:"object",properties:{sessionID:{type:"string"}}}}}};
constrainDelegation(deadlocked,{child:"stuck-builder",errors:2},{callingAgent:"watoom-builder"});
assert.deepEqual(deadlocked.tools.subagent.input.properties.agent.enum,["watoom-critic"]);
assert(!("sessionID" in deadlocked.tools.subagent.input.properties),"a fresh critic child must be reachable, not locked to the stuck non-critic session");
assert(!(deadlocked.tools.subagent.input.required || []).includes("sessionID"));
assert.match(deadlocked.tools.subagent.description,/FRESH critic child/);
// But resuming a child that already IS the mandated critic (mid-review, itself guard-rejected twice) still works.
const criticChild={agent:"watoom-workflow",sessionID:"parent",tools:{subagent:{input:{type:"object",properties:{sessionID:{type:"string"}}}}}};
constrainDelegation(criticChild,{child:"the-critic",errors:2},{callingAgent:"watoom-critic"});
assert.deepEqual(criticChild.tools.subagent.input.properties.agent.enum,["watoom-critic"]);
assert.deepEqual(criticChild.tools.subagent.input.properties.sessionID.enum,["the-critic"]);
console.log("PASS critic-mandatory beats a stale non-critic resume lock, and still resumes an in-flight critic child");

// Full end-to-end reproduction of the reported live regression: the first fix changed the SCHEMA (above),
// but execute.before's own COORDINATOR_CHILD_PENDING check (assertAllowed) still unconditionally demanded
// input.sessionID===state.child whenever state.child was set -- rejecting the exact call the fixed schema
// now produces (agent:critic, no sessionID), trading CHILD_AGENT_MISMATCH for a new deadlock under a
// different name instead of actually resolving it. This drives the real hooks end to end, not just the
// schema builder, to prove the fresh critic call now actually succeeds.
f=await fixture();
f.store.set("session/s",{direct:0,reads:0,errors:2,calls:[],reviews:[],child:"stuck-builder",guardRejections:2});
f.store.set("session/stuck-builder",{callingAgent:"watoom-builder"});
await f.call("subagent",{agent:"watoom-critic",description:"d",prompt:"p",background:false},"watoom-workflow","s");
assert.equal(f.store.get("session/s").child,"stuck-builder","fixture's bare execute stub never reports running/completed; state.child only moves once a real completion event arrives");
console.log("PASS a fresh critic child is actually reachable end-to-end once errors>=2 strands a non-critic child");

// Established pipeline reports paths are accepted only for the pending revision.
const pipelineState={pendingVisual:{path:"/data/ai/projects/llm/pipelines/bench-v1/renders/side.png",sha256:sha,presentedBy:"watoom/swift-qwen38-coder",reviewMode:"isolated-image-v2"}};
const pipelineReceipt={path:"/data/ai/projects/llm/pipelines/bench-v1/reports/visual-review.json",content:JSON.stringify({...JSON.parse(receipt.content),image_path:pipelineState.pendingVisual.path})};
assert(reviewReceipt(pipelineReceipt,pipelineState));
assert(!receiptPath("/data/ai/projects/llm/pipelines/bench-v2/reports/visual-review.json",pipelineState));
assert(!receiptPath("/data/ai/projects/llm/pipelines/bench-v1/reports/../reports/visual-review.json",pipelineState));
assert(!reviewReceipt({...pipelineReceipt,content:pipelineReceipt.content.replace(sha,"0".repeat(64))},pipelineState));
const receiptEvent={sessionID:"child-review",tools:{write:{input:{type:"object",properties:{path:{type:"string"},content:{type:"string"}}}}}};
constrainReceipt(receiptEvent,pipelineState);
assert(reviewReceipt({...pipelineReceipt,path:receiptEvent.tools.write.input.properties.path.enum[0]},pipelineState));
assert(receiptEvent.tools.write.input.properties.content);
console.log("PASS revision-bound pipeline receipt path, provenance checks and exact write schema");
// Capture images under <project>/.opencode/captures/ get a project-level receipt, not a nested .opencode tree.
{
 const capture={pendingVisual:{path:"/data/ai/projects/games/magpie/.opencode/captures/p6-asset-review/terrain-wild.png",sha256:sha,presentedBy:"watoom/swift-qwen38-coder",reviewMode:"isolated-image-v2"}};
 const ev={sessionID:"ses_x",tools:{write:{input:{type:"object",properties:{path:{type:"string"},content:{type:"string"}}}}}};
 constrainReceipt(ev,capture);
 const target=ev.tools.write.input.properties.path.enum[0];
 assert.equal(target,"/data/ai/projects/games/magpie/.opencode/validation/ses_x/visual-review.json");
 assert(receiptPath(target,capture));
 assert(reviewReceipt({path:target,content:JSON.stringify({...JSON.parse(receipt.content),image_path:capture.pendingVisual.path})},capture));
 console.log("PASS capture receipts anchor at the project validation folder");
}

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

// A child's reported request_id must exist as a native protocol file (2026-11-04 compacted builder invented one).
{
 const project=await mkdtemp(join(tmpdir(),"watoom-claim-"));
 const {mkdir:mk,writeFile:wf}=await import("node:fs/promises");
 const real="a".repeat(64),fake="954e3b26d6313d71a627e266b1b4b33e2e33d61e6813b5462338d24302d489ab";
 await mk(join(project,".opencode/worker-requests"),{recursive:true});await wf(join(project,".opencode/worker-requests",real+".json"),"{}");
 const fc=await fixture();
 fc.ctx.session.get=async()=>({location:{directory:project}});
 const child=(id,text)=>({output:{sessionID:id,status:"completed",output:text},content:[]});
 await assert.rejects(()=>fc.call("subagent",{agent:"watoom-builder",result:child("liar","All done. Regression-3 was queued with request_id `"+fake+"`.")}),/CHILD_CLAIM_UNVERIFIED/);
 assert.equal(fc.store.get("session/s").child,"liar");
 await fc.call("subagent",{agent:"watoom-builder",sessionID:"liar",result:child("liar","Queued: request_id "+real+"; image sha256 "+"c".repeat(64))});
 assert.equal(fc.store.get("session/s").child,null);
 await rm(project,{recursive:true,force:true});
 console.log("PASS invented child worker request IDs are rejected; real protocol files and unrelated hashes pass");
}

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

{
 // Multi-image review: extra capture views queue instead of being refused/abandoned.
 const img=n=>{const b=Buffer.from("view-"+n);return {uri:"data:image/png;base64,"+b.toString("base64"),sha:createHash("sha256").update(b).digest("hex")};};
 const [v1,v2,v3]=[img(1),img(2),img(3)];
 const rec=(path,v)=>({path:"/p/.opencode/validation/t/visual-review.json",content:JSON.stringify({image_path:path,image_sha256:v.sha,model:"watoom/swift-qwen38-coder",basis:"pixels",review_version:2,review_scope:"single_frame_pixels",framing:{usable:false,issues:["Mostly empty frame."]},defects:["Flat single colour field."],uncertainties:[],inferences:[],verdict:"FAIL",observations:["A flat grey field fills the frame.","A tiny white dot sits at centre."]})});
 const q=await fixture();
 await q.call("read",{path:"/p/world_wide.png",result:{content:[{type:"file",uri:v1.uri,mime:"image/png"}]}});
 await assert.rejects(()=>q.call("read",{path:"/p/companions_medium.png"}),/VISION_REVIEW_QUEUED/);
 await assert.rejects(()=>q.call("read",{path:"/p/companion_close.png"}),/VISION_REVIEW_QUEUED/);
 let st=q.store.get("session/s");
 assert.deepEqual(st.reviewQueue.map(x=>x.path),["/p/companions_medium.png","/p/companion_close.png"]);
 assert.equal(st.guardRejections||0,0);assert.equal(st.errors,0);
 // A repeated read of an already-queued image is a real rejection again (loop protection).
 await assert.rejects(()=>q.call("read",{path:"/p/companions_medium.png"}),/VISION_REVIEW_REQUIRED/);
 assert.equal(q.store.get("session/s").guardRejections,1);
 // No queue prompt while a review is pending.
 let ev=await q.context("watoom-workflow",[{content:[{type:"media",media:{mime:"image/png"}}]}]);
 assert(!ev.system.some(x=>x.text.includes("VISION QUEUE")));
 await q.call("write",rec("/p/world_wide.png",v1));
 assert.equal(q.store.get("session/s").pendingVisual,null);
 ev=await q.context();
 const note=ev.system.map(x=>x.text).join("\n");
 assert(note.includes("VISION QUEUE: 2 more image(s)") && note.includes("Read the next one now (/p/companions_medium.png)"));
 await q.call("read",{path:"/p/companions_medium.png",result:{content:[{type:"file",uri:v2.uri,mime:"image/png"}]}});
 st=q.store.get("session/s");
 assert.equal(st.pendingVisual.path,"/p/companions_medium.png");
 assert.deepEqual(st.reviewQueue.map(x=>x.path),["/p/companion_close.png"]);
 await q.context("watoom-workflow",[{content:[{type:"media",media:{mime:"image/png"}}]}]);
 await q.call("write",rec("/p/companions_medium.png",v2));
 await q.call("read",{path:"/p/companion_close.png",result:{content:[{type:"file",uri:v3.uri,mime:"image/png"}]}});
 await q.context("watoom-workflow",[{content:[{type:"media",media:{mime:"image/png"}}]}]);
 await q.call("write",rec("/p/companion_close.png",v3));
 st=q.store.get("session/s");
 assert.equal(st.reviews.length,3);assert.deepEqual(st.reviewQueue,[]);
 assert(!(await q.context()).system.some(x=>x.text.includes("VISION QUEUE")));
 // An image arriving from another tool while one is pending is queued, not counted as an execution failure.
 const r=await fixture();
 await r.call("read",{path:"/p/a.png",result:{content:[{type:"file",uri:v1.uri,mime:"image/png"}]}});
 await r.context("watoom-workflow",[{content:[{type:"media",media:{mime:"image/png"}}]}]);
 await assert.rejects(()=>r.call("read",{path:"/p/a.png",result:{content:[{type:"file",uri:v2.uri,mime:"image/png"}]}}),/VISION_REVIEW_QUEUED/);
 st=r.store.get("session/s");
 assert.equal(st.pendingVisual.sha256,v1.sha);assert.equal(st.errors,0);
 // Expired entries drop out.
 const old={reviewQueue:[{path:"/p/stale.png",time:0}]};
 assert.equal(enqueueReview(old,"/p/new.png",REVIEW_QUEUE_TTL_MS+1),true);assert.deepEqual(old.reviewQueue.map(x=>x.path),["/p/new.png"]);
 console.log("PASS multi-image review queue: extra views queue without penalty, are offered in order, and every view gets its own receipt");
}

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

// Magpie 2026-10-29: a reused builder with a spent budget stayed tool-less and echoed its old
// blocker for every new package. New coordinator work restores a fresh per-package budget.
{
 const f=await fixture();
 await assert.rejects(()=>f.call("shell",{fail:true},"watoom-builder","spent"),/fixture failure/);
 await f.call("execute",{result:{isError:true,content:[]}},"watoom-builder","spent");
 await f.call("subagent",{agent:"watoom-critic",result:{output:{sessionID:"spent-critic",status:"completed",output:"REVISE"},content:[]}},"watoom-builder","spent");
 await assert.rejects(()=>f.call("shell",{fail:true},"watoom-builder","spent"),/fixture failure/);
 assert.equal(Object.keys((await f.context("watoom-builder",[],"spent")).tools).length,0);
 await f.call("subagent",{agent:"watoom-builder",result:{output:{sessionID:"spent",status:"completed",output:"BLOCKED"},content:[]}});
 assert.equal(f.store.get("session/s").child,null);
 await f.call("subagent",{agent:"watoom-builder",sessionID:"spent",result:{output:{sessionID:"spent",status:"completed",output:"QUEUED"},content:[]}});
 assert("shell" in (await f.context("watoom-builder",[],"spent")).tools,"new package restores the reused child's tools");
 // The per-package bound still applies after the reset.
 await assert.rejects(()=>f.call("shell",{fail:true},"watoom-builder","spent"),/fixture failure/);
 await f.call("execute",{result:{isError:true,content:[]}},"watoom-builder","spent");
 assert.deepEqual(Object.keys((await f.context("watoom-builder",[],"spent")).tools),["subagent"]);
 assert((await f.context("watoom-workflow",[],"hint")).system.some(s=>/watoom_game_worker is a DIRECT NATIVE tool/.test(s.text)));
}
console.log("PASS reused exhausted child gets a fresh per-package budget; bound still applies");

{
// Read-only discovery has its own larger budget; execution keeps BUDGET.
let f=await fixture();
for(let n=0;n<BUDGET+2;n++)await f.call("read",{filePath:"/p/file-"+n});
assert("shell" in (await f.context()).tools);
for(let n=BUDGET+2;n<READ_BUDGET;n++)await f.call("read",{filePath:"/p/file-"+n});
await assert.rejects(()=>f.call("read",{filePath:"/p/more"}),/HANDOFF_REQUIRED/);
await f.call("subagent",{agent:"watoom-builder",result:{output:{sessionID:"child",status:"completed"},content:"<subagent>ok</subagent>"}});
await f.call("read",{filePath:"/p/after-child"});
assert.equal(f.store.get("session/s").reads,1);
f=await fixture();
for(let n=0;n<BUDGET;n++)await f.call("shell",{command:"x-"+n});
await assert.rejects(()=>f.call("read",{filePath:"/p/x"}),/HANDOFF_REQUIRED/);
console.log("PASS coordinator read-only discovery budget is separate and resets with a completed child");
}
{
// Prompt sections are dropped by exact heading for the role/project; the rest is byte-identical.
const text="intro\n## How you work\ncore\n## Making changes\nchange\n## Engine and asset worker routes\ngodot\n";
assert.equal(trimSections(text,promptDrop("watoom-workflow","/data/ai/projects/games/magpie")),text);
assert.equal(trimSections(text,promptDrop("watoom-critic","/data/ai/projects/games/magpie")),"intro\n## How you work\ncore\n");
assert.equal(trimSections(text,promptDrop("watoom-builder","/data/ai/projects/homelab/homelab-llm")),"intro\n## How you work\ncore\n## Making changes\nchange\n");
assert.equal(trimSections(text,promptDrop("watoom-kali",undefined)),"intro\n## How you work\ncore\n## Making changes\nchange\n");
assert(!developmentProject("/data/ai/projects/homelab") && !developmentProject("/workspace") && !developmentProject("/data/ai/projects/games/x") && ["work","writing","homelab","llm"].every(g=>developmentProject("/data/ai/projects/"+g+"/x")));
const f=await fixture();
const event={agent:"watoom-critic",sessionID:"s",model:{providerID:"watoom",id:"swift-qwen38-coder"},messages:[],tools:{},system:[{type:"text",text}]};
await f.hooks.get("context")(event);
assert(!event.system[0].text.includes("godot") && !event.system[0].text.includes("change") && event.system[0].text.includes("core"));
// Every listed heading exists in the managed agents, so a renamed section cannot silently stay.
const {readdir}=await import("node:fs/promises");
const dir=new URL("../../ansible/roles/watoom-code/files/native/agents/",import.meta.url);
const headings=new Set();
for(const name of await readdir(dir))for(const m of (await readFile(new URL(name,dir),"utf8")).matchAll(/^## (.+)$/gm))headings.add(m[1].trim());
for(const name of promptDrop("watoom-critic","/data/ai/projects/homelab/x"))assert(headings.has(name),"missing heading "+name);
console.log("PASS agent prompt sections trimmed by role and project");
}

// A long coordinator session must not dead-lock once the critic cap is reached:
// a successful package resets the cap, and a new prompt re-arms one critic review.
{
 const critic=id=>f2.call("subagent",{agent:"watoom-critic",result:{output:{sessionID:id,status:"completed"},content:[]}});
 const fail2=async()=>{await assert.rejects(()=>f2.call("shell",{fail:true}));await assert.rejects(()=>f2.call("shell",{fail:true}));};
 let f2=await fixture();
 for(let n=0;n<3;n++){await fail2();await critic("c"+n);}
 await fail2();
 await assert.rejects(()=>f2.call("subagent",{agent:"watoom-builder"}),/CRITIC_REQUIRED/);
 await assert.rejects(()=>critic("c3"),/CRITIC_ESCALATION_BOUND: .*end the turn/);
 await f2.hooks.get("prompt")({sessionID:"s",messageID:"m2",prompt:{text:"continue"}});
 await critic("c4");
 await f2.call("subagent",{agent:"watoom-builder",result:{output:{sessionID:"b1",status:"completed"},content:[]}});
 assert.equal(f2.store.get("session/s").criticEscalations,0);
 for(let n=0;n<3;n++){await fail2();await critic("d"+n);}
 console.log("PASS critic cap resets after a successful package and a new prompt re-arms one review");
}


// Regression: a read-only diagnosis survives failed optional host discovery,
// while tools stay stopped after the existing two-failure/critic boundary.
f=await fixture();
await f.call("read",{path:"/data/ai/artifacts/esp32/job/compile.log"},"watoom-investigator","diagnosis");
await assert.rejects(()=>f.call("read",{path:"/data/ai/missing",fail:true},"watoom-investigator","diagnosis"));
await assert.rejects(()=>f.call("read",{path:"/data/ai/missing2",fail:true},"watoom-investigator","diagnosis"));
assert.equal(f.store.get("session/diagnosis").lastExecutionError.kind,"discovery");
await f.call("subagent",{agent:"watoom-critic",result:{output:{sessionID:"diagnosis-critic",status:"completed",output:"REVISE: source was not compiled"},content:[]}},"watoom-investigator","diagnosis");
await f.call("shell",{command:"cat /etc/systemd/system/watoom-esp32-worker.service; find /data/ai/helper-scripts -name runner.py",result:{metadata:{exit:1},content:[{type:"text",text:"No such file or directory\nExited with code 1"}]}},"watoom-investigator","diagnosis");
const diagnosisContext=await f.context("watoom-investigator",[],"diagnosis");
assert.equal(Object.keys(diagnosisContext.tools).length,0,"discovery failures do not restore tools");
const diagnosisState=f.store.get("session/diagnosis");
assert.equal(diagnosisState.lastExecutionError.kind,"execution","compound shell failure is not exempted");
const report=terminalSchema(diagnosisState,"diagnosis");
assert.deepEqual(report.properties.result.enum,["PARTIAL","BLOCKED"]);
assert.deepEqual(report.properties.evidence.items.enum,["/data/ai/artifacts/esp32/job/compile.log"]);
assert.equal(report.properties.blocker.const,"Tool returned failure; exit=1");
assert(diagnosisContext.system.some(x=>x.text.includes("return PARTIAL findings")));
const reportRequest={agent:"watoom-investigator",sessionID:"diagnosis",kind:"primary",model:{providerID:"watoom",id:"swift-qwen38-coder"},request:new Request("http://local/v1/chat/completions",{method:"POST",body:JSON.stringify({messages:[],tools:[]})})};
await f.hooks.get("http.request")(reportRequest);
assert.deepEqual((await reportRequest.request.json()).response_format.json_schema.schema.properties.result.enum,["PARTIAL","BLOCKED"]);
assert.equal(terminalSchema({...diagnosisState,callingAgent:"watoom-builder"},"s").properties.result.const,"BLOCKED");
assert.equal(terminalSchema({...diagnosisState,readEvidence:[]},"s").properties.result.const,"BLOCKED");
assert.equal(terminalSchema({...diagnosisState,guardRejections:1},"s").properties.result.const,"BLOCKED");
assert.equal(terminalSchema({...diagnosisState,lastGuardError:"permission boundary"},"s").properties.result.const,"BLOCKED");
assert.equal(findingsHandoff({...diagnosisState,pendingVisual:{path:"/p/unseen.png"}}),false);
const failedRepair={criticConsulted:true,errors:0};
recordToolFailure(failedRepair,"watoom-builder","shell",{command:"build"},"compile failed");
assert.equal(failedRepair.errors,2);
assert.equal(failedRepair.lastExecutionError.kind,"execution");
const noMatch={metadata:{exit:1},content:[{type:"text",text:"Exited with code 1"}]};
assert(expectedSearchMiss("shell",{command:"rg needle /project/file"},noMatch));
assert(!expectedSearchMiss("shell",{command:"rg needle /project/file"}, {...noMatch,isError:true}));
assert(!expectedSearchMiss("shell",{command:"rg needle /project/file"},{...noMatch,content:[{type:"text",text:"Permission denied"}]}));
assert(!expectedSearchMiss("shell",{command:"rg needle /project/file; build"},noMatch));
assert(!expectedSearchMiss("shell",{command:"rg needle /project/file | cat"},noMatch));
assert(!expectedSearchMiss("shell",{command:"rg needle /project/file"},{...noMatch,metadata:{exit:2}}));
f=await fixture();
await f.call("shell",{command:"rg needle /project/file",result:noMatch},"watoom-investigator","miss");
assert.equal(f.store.get("session/miss").errors,0);
await f.call("shell",{command:"rg needle /project/file",result:noMatch},"watoom-builder","validation");
assert.equal(f.store.get("session/validation").errors,0,"a builder's read-only search miss is information");
await f.call("shell",{command:"npm test",result:noMatch},"watoom-builder","validation");
assert.equal(f.store.get("session/validation").errors,1,"builder validation exits are not exempted");

console.log("PASS read-only findings handoff, terminal transport, conservative no-match classification and unchanged repair/visual/security gates");

{
// 2026-11-20 rule audit: lookups, knowledge and gate restatements must not drive the coordinator into the critic loop.
const {MISS_CAP,knowledgeTool,discoveryCall,gateRejection,handoffMessage}=await import("../../ansible/roles/watoom-code/files/coordinator-guard/index.js");
const miss={metadata:{exit:1},content:[{type:"text",text:"Exited with code 1"}]};
// Coordinator lookup misses: missing files and empty greps are information until MISS_CAP of them.
let f=await fixture();
await assert.rejects(()=>f.call("read",{filePath:"/p/missing",fail:true}));
await f.call("shell",{command:"rg needle /p",result:miss});
await assert.rejects(()=>f.call("read",{filePath:"/p/missing2",fail:true}));
assert.equal(f.store.get("session/s").errors,0,"three lookup misses do not arm the critic gate");
assert("shell" in (await f.context()).tools);
await f.call("subagent",{agent:"watoom-investigator",result:{output:{sessionID:"inv",status:"completed"},content:[]}});
for(let n=0;n<MISS_CAP;n++)await assert.rejects(()=>f.call("read",{filePath:"/p/gone-"+n,fail:true}));
assert.equal(f.store.get("session/s").errors,1,"blind searching still converges on the critic");
// Real execution failures still require the critic after two.
f=await fixture();
await assert.rejects(()=>f.call("shell",{command:"make build",fail:true}));
await assert.rejects(()=>f.call("shell",{command:"make build",fail:true}));
await assert.rejects(()=>f.call("subagent",{agent:"watoom-builder"}),/CRITIC_REQUIRED/);
// Knowledge lookups are free: they never spend a budget and stay usable at the handoff gate.
f=await fixture();
const before=structuredClone(f.store.get("session/s") || {});
for(let n=0;n<40;n++)await f.call("skill",{id:"opencode-"+n});
const after=f.store.get("session/s");
assert.equal(after.direct||0,before.direct||0);assert.equal(after.reads||0,before.reads||0);
f=await fixture(new Map(),{direct:99});
await f.call("skill",{id:"godot"});
assert.deepEqual(Object.keys((await f.context()).tools).sort(),["skill","subagent","write"]);
await assert.rejects(()=>f.call("shell"),/HANDOFF_REQUIRED/);
for(const t of ["skill","watoom_skill_search","watoom_memory_recall","wlk_search","wlk_get"])assert(knowledgeTool(t) && discoveryCall(t,{}));
// Worker status polls and wait are discovery; a worker request is execution.
assert(discoveryCall("watoom_game_worker",{action:"status"}) && discoveryCall("wait",{}) && !discoveryCall("watoom_game_worker",{action:"request"}));
f=await fixture();
for(let n=0;n<BUDGET+4;n++)await f.call("read",{filePath:"/p/status-"+n});
assert.equal(f.store.get("session/s").direct,0);
// Gate restatements do not escalate errors; approach refusals still do.
f=await fixture(new Map(),{direct:99});
for(let n=0;n<4;n++)await f.call("shell",{command:"x"}).catch(()=>{});
assert.equal(f.store.get("session/s").errors||0,0,"hitting the handoff gate repeatedly does not arm the critic gate");
assert.equal(f.store.get("session/s").gateRejections,4);
assert(gateRejection("COORDINATOR_HANDOFF_REQUIRED: x") && !gateRejection("EXTERNAL_GODOT_WORKER_REQUIRED: x") && !gateRejection("RECEIPT_INVALID: x"));
// Every gate message names its exit.
assert.match(handoffMessage({child:"c1"}),/sessionID c1/);
assert.match(handoffMessage({errors:2}),/agent watoom-critic/);
assert.match(handoffMessage({direct:BUDGET}),/reply with the final result now/);
assert.match(handoffMessage({direct:BUDGET,gateCheckpointWritten:true}),/call subagent now/);
// The knowledge-first note costs nothing and disappears once a lookup happened.
f=await fixture();
const kf=e=>e.system.some(s=>/KNOWLEDGE FIRST/.test(s.text));
assert(kf(await f.context()));
await f.call("skill",{id:"godot"});
assert(!kf(await f.context()));
console.log("PASS rule audit: lookups/knowledge/gate restatements do not loop the coordinator; real failures and receipts still escalate");
}

{
// 2026-11-20 wasted-call audit: protected-path rules allow pure reads; ticket requests are validated at write; children learn their area.
const {shellCannotWrite,shellReadOnly,assertWorkerProtocolAccess,assertTicketRequest}=await import("../../ansible/roles/watoom-code/files/coordinator-guard/index.js");
const R="/p/.opencode/worker-requests/",G="/data/github/repo/tools/x.py";
for(const c of [`ls -la ${R} 2>&1 | head -20`,`sed -n 30,80p ${G}`,`git -C /data/github/repo log -1 --format='%h %s' -- x 2>&1`,`diff /config/a.py ${G}`,`find ${R} -name "*.json"`])
 {assert(shellCannotWrite(c),c);assert.doesNotThrow(()=>assertWorkerProtocolAccess("shell",{command:c}),c);}
for(const c of [`echo x > ${R}a.json`,`rm ${R}a`,`sed -i s/a/b/ ${G}`,`find ${R} -delete`,`find ${R} -exec rm {} ;`,`ls $(rm ${R}a)`,`echo a | tee ${R}b`,`git -C /data/github/repo commit -am x`,`ls ${R} && touch ${R}x`,`sed -n 'w /tmp/x' ${G}`])
 {assert(!shellCannotWrite(c),c);assert.throws(()=>assertWorkerProtocolAccess("shell",{command:c}),/WORKER_PROTOCOL_READ_ONLY|SOURCE_REPO_READ_ONLY/,c);}
assert(!shellReadOnly(`ls -la ${R} 2>&1 | head -20`),"the auto-allow test stays strict");
const T="/p/.opencode/tickets/";
assert.throws(()=>assertTicketRequest("write",{path:T+"T-0109.json",content:'{"id":"T-0109","title":"x"}'}),/TICKET_REQUEST_INVALID/);
assert.throws(()=>assertTicketRequest("write",{path:T+"a.json",content:'{"schema":1,"id":"a","action":"note","text":"x"}'}),/"ticket":"T-NNNN"/);
assert.doesNotThrow(()=>assertTicketRequest("write",{path:T+"t1-note.json",content:'{"schema":1,"id":"t1-note","action":"note","ticket":"T-0001","text":"x"}'}));
assert.doesNotThrow(()=>assertTicketRequest("write",{path:T+"new-bug.json",content:'{"schema":1,"id":"new-bug","title":"x"}'}));
let f=await fixture();
await f.call("write",{path:T+"T-9.json",content:"{}"}).catch(()=>{});
assert.equal(f.store.get("session/s").errors||0,0,"an invalid ticket request is guidance, not a failure");
f.store.set("session/kid",{version:1,direct:0,errors:0,isChild:true,callingAgent:"watoom-builder",reviews:[],calls:[]});
assert((await f.context("watoom-builder",[],"kid")).system.some(s=>s.text.includes("children/kid/")),"a child is told its own writable area");
console.log("PASS wasted-call audit: protected-path reads allowed, writes still refused; ticket requests validated at write; child work area named");
}

{
const {assertSkillId}=await import("../../ansible/roles/watoom-code/files/coordinator-guard/index.js");
assert.throws(()=>assertSkillId("skill",{id:"watoom-worker-contracts/references/game-worker.md"}),/read with path \/config\/skills\/watoom-worker-contracts\/references\/game-worker\.md/);
assert.doesNotThrow(()=>assertSkillId("skill",{id:"watoom-worker-contracts"}));
let f=await fixture();
await f.call("skill",{id:"x/references/y.md"}).catch(()=>{});
assert.equal(f.store.get("session/s").errors||0,0,"a skill-reference mix-up is guidance, not a failure");
console.log("PASS skill called with a reference path names the exact file to read");
}
