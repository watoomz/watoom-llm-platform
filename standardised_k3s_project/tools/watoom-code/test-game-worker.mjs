import assert from "node:assert/strict";
import {mkdtemp,mkdir,writeFile,readFile,rm,symlink,chown} from "node:fs/promises";
import {join} from "node:path";
import {execFileSync} from "node:child_process";
import {executeGameWorker,gameSourceFingerprint,validateGameWorkerInput,gameWorkerGuidance,gameWorkerResultWhere,godotEditorToolDenied,rearmAfterPrompt,recordToolFailure} from "../../ansible/roles/watoom-code/files/coordinator-guard/index.js";
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
 await assert.rejects(executeGameWorker({session:{get:async()=>({location:{directory:'/workspace/projects'}})}},input,context),e=>/PROJECT_DENIED/.test(e.message) && e.message.includes('"/workspace/projects"') && /not a worker allowlist/.test(e.message));
 await assert.rejects(executeGameWorker({session:{get:async()=>({location:{directory:'/data/ai/projects/games/does-not-exist-x'}})}},input,context),/PROJECT_DENIED/);
 const before=await gameSourceFingerprint(root);await mkdir(join(root,'.godot'));await writeFile(join(root,'.godot/cache'),'generated');await writeFile(join(root,'scripts/generated.import'),'generated');assert.equal(before,await gameSourceFingerprint(root));
 const python=execFileSync('python3',['-c',"import sys;sys.path.insert(0,sys.argv[1]);from game_worker_bridge import fingerprint;from pathlib import Path;print(fingerprint(Path(sys.argv[2])))",new URL('.',import.meta.url).pathname,root],{encoding:'utf8'}).trim();assert.equal(python,before,'native and operator fingerprints agree');
 await writeFile(join(root,'scripts/test_runner.gd'),'extends SceneTree\n# changed');assert.notEqual(before,await gameSourceFingerprint(root));
 await symlink('/etc/hosts',join(root,'scripts/escape'));await assert.rejects(gameSourceFingerprint(root),/SYMLINK/);await rm(join(root,'scripts/escape'));
 const status=join(root,'.opencode/worker-requests',id+'.status.json');const req=JSON.parse(await readFile(join(root,'.opencode/worker-requests',id+'.json'),'utf8'));
 await writeFile(status,JSON.stringify({request_id:id,project:root,operation:'regression',source_fingerprint:req.source_fingerprint,status:'TEST_FIXTURE_COMPLETED'}),{mode:0o644});
 assert.equal(JSON.parse((await executeGameWorker(ctx,{...input,action:'status'},context)).content).status,'TEST_FIXTURE_COMPLETED');
 await chown(status,1001,1001);await assert.rejects(executeGameWorker(ctx,{...input,action:'status'},context),/Untrusted/);
 assert.throws(()=>validateGameWorkerInput({action:'status',operation:'godot-game',job:'a'.repeat(64)},'watoom-builder'),/JOB_IS_REQUEST_ID/);
 assert.doesNotThrow(()=>validateGameWorkerInput({action:'request',operation:'godot-game',job:'test-run3'},'watoom-builder'));
 await writeFile(join(root,'gg_ui.json'),'{}');
 for(const op of ['regression','import','capture','capture-scene','capture-p7'])await assert.rejects(executeGameWorker(ctx,{...input,operation:op},context),/WRONG_OPERATION/);
 await rm(join(root,'gg_ui.json'));
 const mine={session_id:'s1',job:'j',created_at:Date.now()-5*60000},old={session_id:'s0',job:'j',created_at:Date.now()-40*60000};
 assert.equal(gameWorkerGuidance('FAILED',mine,'s1',{operation:'godot-game'}).own_session,true);
 assert.match(gameWorkerGuidance('FAILED',mine,'s1',{operation:'godot-game'}).next,/FINISHED.*NEW job name.*not a blocker/);
 assert.match(gameWorkerGuidance('RECONCILIATION_REQUIRED',mine,'s1',{operation:'godot-game'}).next,/NEW job name/);
 assert.match(gameWorkerGuidance('QUEUED',old,'s1',{operation:'godot-game'}).next,/Queued 40 min.*operator/);
 assert.match(gameWorkerGuidance('QUEUED',old,'s1',{operation:'godot-game'}).warning,/another session/);
 assert.equal(gameWorkerGuidance('QUEUED',mine,'s1',{operation:'godot-game'}).warning,undefined);
 assert.match(gameWorkerGuidance('FAILED',mine,'s1',{operation:'unreal-export'}).next,/unreal-exports\/j\//);
 assert.match(gameWorkerGuidance('FAILED',mine,'s1',{operation:'blender'}).next,/blender-out\/j\/result.json/);
 assert.match(gameWorkerGuidance('FAILED',mine,'s1',{operation:'godot-game'}).next,/godot-game-out\/j\/result.json/);
 assert.doesNotMatch(gameWorkerGuidance('FAILED',mine,'s1',{operation:'regression'}).next,/-out\//);
 assert.match(gameWorkerResultWhere('terrain-export','j'),/output\//);
 await writeFile(join(root,'gg_ui.json'),'{}');assert.match(await godotEditorToolDenied(root),/NOT_FOR_THIS_PROJECT/);await rm(join(root,'gg_ui.json'));
 assert.equal(await godotEditorToolDenied(root),null);assert.equal(await godotEditorToolDenied('/tmp/x'),null);assert.equal(await godotEditorToolDenied(undefined),null);
// BLOCKED lock-in: a stuck top-level builder is re-armed by a new prompt; coordinators, children and critics are left alone
 {const st={isChild:false,callingAgent:'watoom-builder',errors:3,guardRejections:2,terminalReport:true,criticConsulted:true,lastExecutionError:{tool:'shell'}};
  assert.equal(rearmAfterPrompt(st),true);assert.deepEqual([st.errors,st.guardRejections,st.terminalReport,st.criticConsulted,st.lastExecutionError],[0,0,false,false,null]);
  assert.equal(rearmAfterPrompt(st),false);
  for(const o of [{isChild:true,callingAgent:'watoom-builder'},{isChild:false,callingAgent:'watoom-workflow'},{isChild:false,callingAgent:'watoom-critic'}]){const z={...o,errors:3,terminalReport:true};assert.equal(rearmAfterPrompt(z),false);assert.equal(z.errors,3);}
  const f={errors:0};recordToolFailure(f,'watoom-builder','watoom_game_worker',{},'x');assert.equal(f.errors,1);
  const e={errors:0};recordToolFailure(e,'watoom-builder','shell',{command:'rg needle /p'},'x');assert.equal(e.errors,0,'a read-only search miss is information, not a failed repair');
  const b={errors:0};recordToolFailure(b,'watoom-builder','shell',{command:'godot --headless --script run_tests.gd'},'x');assert.equal(b.errors,1,'builder validation exits still count');}
 // statuses the dispatcher really publishes: COMPLETED is a pass, STALE_RESULT is finished
 assert.match(gameWorkerGuidance('COMPLETED',{session_id:'s',job:'j'},'s',{operation:'godot-game'}).next||'',/Passed/);
 assert.match(gameWorkerGuidance('STALE_RESULT',{session_id:'s',job:'j'},'s',{operation:'godot-game'}).next||'',/FINISHED/);
 assert.match(gameWorkerGuidance('RUNNING',mine,'s1',{operation:'godot-game'}).next,/Do not poll/);
 console.log('PASS typed role/project boundary, duplicate prevention, revision fingerprints/parity, symlink refusal and forged-status rejection');
} finally {if(!root.startsWith('/data/ai/projects/games/.worker-bridge-test-'))throw Error('test cleanup scope');await rm(root,{recursive:true,force:true});}

assert.doesNotThrow(()=>validateGameWorkerInput({action:"request",operation:"poo-vfx-inspect",job:"owned-vfx"},"watoom-builder"));
assert.throws(()=>validateGameWorkerInput({action:"request",operation:"poo-vfx-inspect",job:"owned-vfx"},"watoom-investigator"));

assert.doesNotThrow(()=>validateGameWorkerInput({action:"request",operation:"capture-p7",job:"p7"},"watoom-builder"));
