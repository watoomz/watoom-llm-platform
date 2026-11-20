import assert from "node:assert/strict";
import {mkdtemp,mkdir,writeFile,readFile,rm,symlink,chown} from "node:fs/promises";
import {join} from "node:path";
import {execFileSync} from "node:child_process";
import {executeGameWorker,gameSourceFingerprint,validateGameWorkerInput} from "../../ansible/roles/watoom-code/files/coordinator-guard/index.js";
const root=await mkdtemp('/data/ai/projects/games/.worker-bridge-test-');
try {
 await mkdir(join(root,'scripts'));await writeFile(join(root,'project.godot'),'[application]');await writeFile(join(root,'scripts/test_runner.gd'),'extends SceneTree');
 const ctx={session:{get:async()=>({location:{directory:root}})}};const context={agent:'watoom-workflow',sessionID:'ses_test',messageID:'msg_test',id:'call_test'};const input={action:'request',operation:'regression',job:'stable-job'};
 const first=await executeGameWorker(ctx,input,context),value=JSON.parse(first.content);assert.equal(value.status,'QUEUED');const id=first.metadata.request_id;
 const second=await executeGameWorker(ctx,input,{...context,id:'second'});assert.equal(second.metadata.request_id,id,'same source cannot create duplicate job');
 assert.equal((await executeGameWorker(ctx,{...input,action:'status'},context)).metadata.request_id,id);
 for(const role of ['watoom-critic','watoom-reviewer','watoom-investigator','general'])assert.throws(()=>validateGameWorkerInput(input,role),/ROLE_DENIED/);
 for(const bad of [{...input,command:'touch /etc/test'},{...input,operation:'shell'},{...input,job:'../escape'},{...input,project:'/etc'}])assert.throws(()=>validateGameWorkerInput(bad,'watoom-builder'),/INVALID/);
 await assert.rejects(executeGameWorker({session:{get:async()=>({location:{directory:'/tmp'}})}},input,context),/PROJECT_DENIED/);
 const before=await gameSourceFingerprint(root);await mkdir(join(root,'.godot'));await writeFile(join(root,'.godot/cache'),'generated');await writeFile(join(root,'scripts/generated.import'),'generated');assert.equal(before,await gameSourceFingerprint(root));
 const python=execFileSync('python3',['-c',"import sys;sys.path.insert(0,sys.argv[1]);from game_worker_bridge import fingerprint;from pathlib import Path;print(fingerprint(Path(sys.argv[2])))",'/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/watoom-code/',root],{encoding:'utf8'}).trim();assert.equal(python,before,'native and operator fingerprints agree');
 await writeFile(join(root,'scripts/test_runner.gd'),'extends SceneTree\n# changed');assert.notEqual(before,await gameSourceFingerprint(root));
 await symlink('/etc/hosts',join(root,'scripts/escape'));await assert.rejects(gameSourceFingerprint(root),/SYMLINK/);await rm(join(root,'scripts/escape'));
 const status=join(root,'.opencode/worker-requests',id+'.status.json');const req=JSON.parse(await readFile(join(root,'.opencode/worker-requests',id+'.json'),'utf8'));
 await writeFile(status,JSON.stringify({request_id:id,project:root,operation:'regression',source_fingerprint:req.source_fingerprint,status:'TEST_FIXTURE_COMPLETED'}),{mode:0o644});
 assert.equal(JSON.parse((await executeGameWorker(ctx,{...input,action:'status'},context)).content).status,'TEST_FIXTURE_COMPLETED');
 await chown(status,1001,1001);await assert.rejects(executeGameWorker(ctx,{...input,action:'status'},context),/Untrusted/);
 console.log('PASS typed role/project boundary, duplicate prevention, revision fingerprints/parity, symlink refusal and forged-status rejection');
} finally {if(!root.startsWith('/data/ai/projects/games/.worker-bridge-test-'))throw Error('test cleanup scope');await rm(root,{recursive:true,force:true});}

assert.doesNotThrow(()=>validateGameWorkerInput({action:"request",operation:"poo-vfx-inspect",job:"owned-vfx"},"watoom-builder"));
assert.throws(()=>validateGameWorkerInput({action:"request",operation:"poo-vfx-inspect",job:"owned-vfx"},"watoom-investigator"));

assert.doesNotThrow(()=>validateGameWorkerInput({action:"request",operation:"capture-p7",job:"p7"},"watoom-builder"));
