import test from "node:test";
import assert from "node:assert/strict";
import {verifyWorker} from "./worker_verifier.mjs";
import {Learning,hash} from "./engine.mjs";
const project="/data/ai/projects/games/fixture",id="a".repeat(64),fingerprint="b".repeat(64),receipt=project+"/.opencode/validation/operator-godot/r.json";
const policy={id:"cpu-regression",tool:"watoom_game_worker",match:{action:"status",operation:"regression"},verifier:"native-cpu-worker-v1",description:"Verified CPU regression procedure",steps:["Use the existing bounded worker."],validation:"Require the trusted current-revision root receipt.",recovery:"Preserve failed evidence."};
const result={request_id:id,project,operation:"regression",source_fingerprint:fingerprint,status:"COMPLETED",worker_result:{status:"PASS"},source_matches:true,receipt};
const proof={status:"PASS",original_project_untouched:true,live_source_still_matches_snapshot:true,runtime_error_count:0,summary:{failed:0,passed:154},exit_status:"0"};
function fixture(change={}){
 const io={lstat:async()=>({isFile:()=>true,isSymbolicLink:()=>false,uid:0,mode:0o100644,size:2000,...change}),realpath:async p=>p,readFile:async p=>JSON.stringify(p.endsWith(".status.json")?result:proof)};
 const event={tool:policy.tool,status:"completed",input:{action:"status",operation:"regression",job:"stable"},result:{content:JSON.stringify(result)}};
 return {io,event};
}
test("installed native CPU worker receipt contract verifies root-owned current success",async()=>{const {io,event}=fixture();const v=await verifyWorker(policy,event,{repository:project},async()=>fingerprint,io);assert.equal(v.id,"native-worker:"+id);assert.ok(v.receiptHash);});
test("worker verifier rejects wrong source, ownership and symlink evidence",async()=>{
 for(const change of [{uid:1001},{mode:0o100666},{isSymbolicLink:()=>true}]){const {io,event}=fixture(change);assert.equal(await verifyWorker(policy,event,{repository:project},async()=>fingerprint,io),false);}
 const {io,event}=fixture();assert.equal(await verifyWorker(policy,event,{repository:project},async()=>"c".repeat(64),io),false);
});
test("worker verifier rejects failed, stale or cross-project claims",async()=>{for(const override of [{status:"FAILED"},{source_matches:false},{project:"/other"}]){const {io,event}=fixture();event.result.content=JSON.stringify({...result,...override});assert.equal(await verifyWorker(policy,event,{repository:project},async()=>fingerprint,io),false);}});
test("one worker receipt cannot be replayed across sessions to manufacture three successes",async()=>{
 const data=new Map(),storage={get:async k=>structuredClone(data.get(k)),set:async(k,v)=>data.set(k,structuredClone(v))},files=new Map();
 const l=new Learning({scope:{project:"fixture",repository:project,agent:"watoom-workflow"},storage,policies:[policy],memory:{},artifacts:{write:async(id,s)=>{files.set(id,s);return id;}},verify:async()=>({id:"same-owned-worker-receipt"})});
 for(let i=0;i<3;i++)await l.observe({sessionID:"s"+i,messageID:"m",id:"call",tool:policy.tool,input:{action:"status",operation:"regression",job:"job"+i},status:"completed",result:{content:"{}"}});
 assert.equal(Object.keys((await l.state()).events).length,1);assert.equal(files.size,0);
});
