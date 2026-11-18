import assert from "node:assert/strict";
import {shellReadOnly,readShellPermission,install,assertWorkerProtocolAccess} from "../../ansible/roles/watoom-code/files/coordinator-guard/index.js";
for(const command of ["cat /data/receipt.json","ls -la /data/github","head -n 20 /data/a.log","tail -n 30 /data/a.log","rg -n 'FAIL' /data/logs | head -n 20","/usr/bin/cat '/data/file with spaces'","sha256sum /data/a.blend","stat /data/receipt.json"]){assert.equal(shellReadOnly(command),true,command);}
for(const command of ["cat a > b","cat a >> b","cat a; touch b","cat $(touch b)","cat `touch b`","rg --pre=sh x a","rg --hostname-bin /tmp/evil x","rg -z x a","tail -f a","find /data -exec rm {} +","sed -i s/a/b/ a","python3 -c 'print(1)'","sh -c 'cat a'","/tmp/cat a","cat a\nrm b","cat <(touch b)","cat a | tee b","cat $SECRET"]){assert.equal(shellReadOnly(command),false,command);}
const bindings=new Map(),key=JSON.stringify(["s","m","c"]);bindings.set(key,{agent:"watoom-critic",command:"cat /data/receipt.json"});
const event=()=>({sessionID:"s",agent:"watoom-critic",action:"shell",source:{type:"tool",messageID:"m",id:"c"},effect:"ask"});
let e=event();readShellPermission(e,bindings);assert.equal(e.effect,"allow");
for(const change of [{agent:"watoom-builder"},{sessionID:"other"},{source:{type:"tool",messageID:"m",id:"wrong"}},{action:"write"}]){e={...event(),...change};readShellPermission(e,bindings);assert.equal(e.effect,"ask");}
bindings.set(key,{agent:"watoom-critic",command:"cat a > b"});e=event();readShellPermission(e,bindings);assert.equal(e.effect,"ask");
// Exercise the actual executor wrapper and native permission hook binding/cleanup.
const store=new Map(),tools=new Map();let permissionHook;
tools.set("shell",{id:"shell",name:"shell",execute:async(input,context)=>{
 const e={sessionID:context.sessionID,agent:context.agent,action:"shell",source:{type:"tool",messageID:context.messageID,id:context.id},resources:["cat a"],effect:"ask"};
 await permissionHook(e);return {content:[],metadata:{permissionEffect:e.effect}};
}});
const ctx={options:{},permission:{hook:async(name,fn)=>{assert.equal(name,"evaluate");permissionHook=fn;}},storage:{get:async k=>structuredClone(store.get(k)),set:async(k,v)=>store.set(k,structuredClone(v))},session:{get:async()=>({}),hook:async()=>{}},tool:{hook:async()=>{},transform:async fn=>fn({list:()=>[...tools.values()],add:x=>tools.set(x.name,{...x,id:x.name}),update:(id,fn)=>fn(tools.get(id))})}};
await install(ctx);
for(const agent of ["watoom-critic","watoom-investigator","watoom-reviewer","watoom-builder","watoom-workflow","watoom-creative-writer","watoom-kali"]){
 const context={agent,sessionID:agent,messageID:"m",id:"c"};
 let result=await tools.get("shell").execute({command:"cat /data/receipt.json"},context);assert.equal(result.metadata.permissionEffect,"allow",agent);
 result=await tools.get("shell").execute({command:"cat a > b"},context);assert.equal(result.metadata.permissionEffect,"ask",agent);
 const stale={sessionID:agent,agent,action:"shell",source:{type:"tool",messageID:"m",id:"c"},effect:"ask"};await permissionHook(stale);assert.equal(stale.effect,"ask");
}
console.log("PASS full-command reads, unsafe options/redirects, exact source/agent binding, all-role native permission hook and cleanup");

for(const name of ["md5sum","sha1sum","sha224sum","sha256sum","sha384sum","sha512sum","b2sum","cksum"]){assert.equal(shellReadOnly(name+" -c /data/checksums.txt"),true);assert.equal(shellReadOnly(name+" /data/a > /data/checksums.txt"),false);}
assert.doesNotThrow(()=>assertWorkerProtocolAccess("shell",{command:"sha256sum /data/.opencode/worker-requests/existing.status.json"}));
assert.throws(()=>assertWorkerProtocolAccess("shell",{command:"sha256sum a > /data/.opencode/worker-requests/existing.status.json"}),/WORKER_PROTOCOL_READ_ONLY/);
console.log("PASS checksum generation/check mode and immutable worker protocol read/write distinction");
