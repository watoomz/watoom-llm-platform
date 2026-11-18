import { test } from "node:test";
import assert from "node:assert/strict";
import { install, parseScope } from "../../ansible/roles/watoom-code/files/image-scope/index.js";
const text="Positive prompt:\nA wooden park bench. outdoors, park\n\nNegative prompt:\nwatermark, blur\n\nExecution settings:\nTask: Create 3 images.\n\nSpecification:\n- Number of images: 3\n";
async function fixture(messages=[{id:"usr_fixture",type:"user",text}],parents={}) {
 const hooks=new Map(),audit=new Map(),reads=[];
 await install({tool:{async hook(name,fn){hooks.set(name,fn);}},session:{async get({sessionID}){return {id:sessionID,...parents[sessionID]};},async context({sessionID}){reads.push(sessionID);return messages;}},storage:{async set(k,v){audit.set(k,v);},async get(k){return audit.get(k);}}});
 return {run:hooks.get("execute.before"),after:hooks.get("execute.after"),audit,reads};
}
const call=(input={request_id:"fixture-one",prompt:"A wooden park bench viewed from the front. outdoors, park",installation_id:"a".repeat(64),revision:"b".repeat(40),settings:{width:512,height:512,seed:7}})=>({tool:"watoom-images_submit_image",sessionID:"ses_fixture",id:"call_fixture",input});
test("omitted negatives are restored without flattening per-image positives",async()=>{
 const f=await fixture(),event=call();const before={...event.input};await f.run(event);
 assert.equal(event.input.prompt,before.prompt);assert.equal(event.input.negative_prompt,"watermark, blur");
 for(const k of ["request_id","installation_id","revision","settings"])assert.deepEqual(event.input[k],before[k]);
 const audit=[...f.audit.values()][0];assert.equal(audit.requestedCount,3);assert.equal(audit.positiveRestored,false);assert.ok(audit.negativeRestored);
 assert.ok(!JSON.stringify(audit).includes("watermark"));assert.ok(!JSON.stringify(audit).includes("wooden"));
});
test("three distinct positive variants survive while negatives and request IDs stay intact",async()=>{
 const f=await fixture();const requests=[];
 for(let i=0;i<3;i++){const e=call();e.id+="-"+i;e.input.request_id+="-"+i;e.input.prompt=["A wooden park bench, front view.","A wooden park bench, side view.","A wooden park bench, rear view."][i];await f.run(e);requests.push(e.input);}
 assert.equal(new Set(requests.map(x=>x.request_id)).size,3);assert.ok(requests.every(x=>x.negative_prompt==="watermark, blur"));
 assert.equal(new Set(requests.map(x=>x.prompt)).size,3);
});
test("child tools use the original root user's blocks",async()=>{
 const f=await fixture(undefined,{ses_child:{parentID:"ses_fixture"}}),e=call();e.sessionID="ses_child";await f.run(e);assert.deepEqual(f.reads,["ses_fixture"]);assert.equal(e.input.negative_prompt,"watermark, blur");
});
test("exact continuation can recover original reviewed blocks",async()=>{
 const f=await fixture([{id:"usr_1",type:"user",text},{id:"usr_2",type:"user",text:"continue"}]),e=call();await f.run(e);assert.equal(e.input.negative_prompt,"watermark, blur");
});
test("a new unrelated request does not inherit old scene data",async()=>{
 const f=await fixture([{id:"usr_1",type:"user",text},{id:"usr_2",type:"user",text:"Make a new blue cube"}]),e=call();await f.run(e);assert.equal(e.input.prompt,"A wooden park bench viewed from the front. outdoors, park");assert.equal(f.audit.size,0);
});
test("an absent negative block removes invented exclusions",async()=>{
 const scope=text.replace("Negative prompt:\nwatermark, blur\n\n","");const f=await fixture([{id:"usr_fixture",type:"user",text:scope}]),e=call();e.input.negative_prompt="invented";await f.run(e);assert.equal(e.input.negative_prompt,"");
});
test("incomplete, ambiguous and oversized scope fails closed",()=>{
 assert.throws(()=>parseScope("Positive prompt:\nA bench", "u"),/INCOMPLETE/);
 assert.throws(()=>parseScope(text+"\nPositive prompt:\nOther", "u"),/AMBIGUOUS/);
 assert.throws(()=>parseScope(text.replace("A wooden park bench. outdoors, park","x".repeat(4097)),"u"),/BOUNDS/);
});
test("other tools remain untouched",async()=>{const f=await fixture(),e=call();e.tool="watoom-images_list_image_models";await f.run(e);assert.equal(e.input.prompt,"A wooden park bench viewed from the front. outdoors, park");assert.equal(f.reads.length,0);});
test("native source failure blocks submission rather than dropping negatives",async()=>{
 let hook;await install({tool:{async hook(n,f){if(n==="execute.before")hook=f;}},session:{async get(){throw Error("source unavailable");}}});await assert.rejects(()=>hook(call()),/source unavailable/);
});

test("successful tool receipt exposes native prompt preservation without prompt text",async()=>{
 const f=await fixture(),e=call();await f.run(e);const after={...e,status:"completed",result:{output:{job_id:"a".repeat(64),state:"QUEUED"},content:[]}};await f.after(after);
 assert.equal(after.result.output.scope_transport.negativeChars,15);assert.equal(after.result.output.scope_transport.negativeUnchanged,true);assert.equal(after.result.metadata.image_scope.source,"native_user_scope_and_per_image_prompt");assert.ok(!JSON.stringify(after.result).includes("watermark"));
});
test("failed or unconfirmed submissions do not receive a preservation receipt",async()=>{
 const f=await fixture(),e=call();await f.run(e);const after={...e,status:"error",result:{output:{error:"rejected"},content:[]}};await f.after(after);assert.equal(after.result.metadata,undefined);
});

test("explicit verbatim positive mode copies the reviewed block",async()=>{
 const f=await fixture([{id:"usr_exact",type:"user",text:text+"\n- Positive prompt handling: verbatim\n"}]),e=call();await f.run(e);assert.equal(e.input.prompt,"A wooden park bench. outdoors, park");assert.equal(e.input.negative_prompt,"watermark, blur");
});
test("an explicit Task verbatim request overrides a polishing default",()=>{
 const scope=parseScope(text.replace("Task: Create 3 images.","Task: Use the positive prompt verbatim.")+"\n- Positive prompt handling: Light polish\n","u");assert.equal(scope.policy,"verbatim");
});
