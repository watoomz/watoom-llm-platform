import assert from "node:assert/strict";
import {mkdtemp,mkdir,writeFile,readFile,rm} from "node:fs/promises";
import {join} from "node:path";
import {createHash} from "node:crypto";
import {assertAllowed,assertWorkerProtocolAccess,validateWorkerRequestIdentity,executeGameWorker} from "../../ansible/roles/watoom-code/files/coordinator-guard/index.js";
for(const folder of ["worker-requests","rig-worker-requests","asset-capture-requests","esp32-requests"]) {
 for(const name of ["write","edit"])assert.throws(()=>assertWorkerProtocolAccess(name,{path:`/project/.opencode/${folder}/request.json`}),/WORKER_PROTOCOL_READ_ONLY/);
 assert.throws(()=>assertWorkerProtocolAccess("shell",{command:`python3 -c 'open(".opencode/${folder}/request.json","w").write("bad")'`}),/WORKER_PROTOCOL_READ_ONLY/);
}
assert.throws(()=>assertWorkerProtocolAccess("write",{path:"/project/scripts/../.opencode/worker-requests/request.json"}),/READ_ONLY/);
assert.doesNotThrow(()=>assertWorkerProtocolAccess("write",{path:"/project/.opencode/capture-jobs/job/request.json"}));
assert.doesNotThrow(()=>assertWorkerProtocolAccess("read",{path:"/project/.opencode/worker-requests/request.json"}));
assert.throws(()=>assertAllowed("shell",{command:'sleep 580; echo waited'},{pendingExternal:{status:'QUEUED'}},false),/EXTERNAL_JOB_PENDING/);
const root=await mkdtemp('/data/ai/projects/games/.worker-integrity-test-');
try {
 await mkdir(join(root,'scripts'));await writeFile(join(root,'project.godot'),'[application]');await writeFile(join(root,'scripts/test_runner.gd'),'extends SceneTree');
 const ctx={session:{get:async()=>({location:{directory:root}})}};
 const context={agent:'watoom-builder',sessionID:'ses_test',messageID:'msg_real',id:'call_real'};
 const input={action:'request',operation:'capture',job:'existing-job'};
 const result=await executeGameWorker(ctx,input,context);const path=join(root,'.opencode/worker-requests',result.metadata.request_id+'.json');
 const req=JSON.parse(await readFile(path,'utf8'));validateWorkerRequestIdentity(req,req.request_id+'.json');
 await writeFile(path,JSON.stringify({...req,message_id:'msg_invented',call_id:'cap_fake'}));
 for(const action of ['request','status'])await assert.rejects(executeGameWorker(ctx,{...input,action},context),/WORKER_REQUEST_CORRUPTED/);
 await writeFile(path,JSON.stringify(req));assert.equal((await executeGameWorker(ctx,{...input,action:'status'},context)).metadata.request_id,req.request_id);
 for(const worker_target of [undefined,'rig-stage']) {
  const r={...req,...(worker_target?{worker_target}: {})};r.request_id=createHash('sha256').update(JSON.stringify([r.project,r.operation,r.source_fingerprint,r.session_id,r.message_id,r.call_id,...(worker_target?['rig-stage']:[])])).digest('hex');validateWorkerRequestIdentity(r,r.request_id+'.json');
 }
 console.log('PASS runtime-owned protocol paths, capture manifests writable, pending sleep rejected, corrupted identities fail closed, same native identity recoverable');
}finally{assert(root.startsWith('/data/ai/projects/games/.worker-integrity-test-'));await rm(root,{recursive:true,force:true});}
