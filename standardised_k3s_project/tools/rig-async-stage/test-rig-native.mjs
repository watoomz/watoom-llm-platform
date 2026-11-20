import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,readdir,rm} from 'node:fs/promises';
import {executeGameWorker,assetCaptureProject} from '../../ansible/roles/watoom-code/files/coordinator-guard/index.js';
const root=await mkdtemp('/data/ai/projects/games/.rig-stage-test-');
try {
 await mkdir(root+'/scripts');await writeFile(root+'/project.godot','config_version=5');await writeFile(root+'/scripts/test_runner.gd','extends SceneTree');
 const ctx={options:{rigAsyncStage:true,rigGameProjects:[root]},session:{get:async()=>({data:{location:{directory:root}}})}};
 const context={sessionID:'ses_fixture',messageID:'msg_fixture',id:'call_fixture',agent:'watoom-workflow'};
 const a=await executeGameWorker(ctx,{action:'request',operation:'regression',job:'background-a'},context,'rig-stage');const av=JSON.parse(a.content);assert.equal(av.status,'QUEUED');assert.equal(av.inputs_frozen,false);assert.match(av.note,/Continue independent work/);
 await writeFile(root+'/.opencode/independent-note.md','Independent work completed while the external request is queued.');
 const b=await executeGameWorker(ctx,{action:'request',operation:'import',job:'background-b'},{...context,id:'call_other'},'rig-stage');assert.notEqual(a.metadata.request_id,b.metadata.request_id);
 await writeFile(root+'/scripts/test_runner.gd','extends SceneTree\n# changed source');
 const again=await executeGameWorker(ctx,{action:'request',operation:'regression',job:'background-a'},{...context,id:'new_call'},'rig-stage');assert.equal(again.metadata.request_id,a.metadata.request_id);assert.equal(JSON.parse(again.content).source_matches,false,'same job never silently becomes a second revision');
 assert.equal((await readdir(root+'/.opencode/rig-worker-requests')).length,2);
 await assert.rejects(executeGameWorker(ctx,{action:'request',operation:'regression',job:'denied'},{...context,agent:'watoom-reviewer'},'rig-stage'),/ROLE_DENIED/);
 await assert.rejects(executeGameWorker(ctx,{action:'request',operation:'lmb-qualify',job:'unsupported'},context,'rig-stage'),/UNSUPPORTED/);
 assert.equal(assetCaptureProject(root),false);assert.equal(assetCaptureProject(root,[root]),true);assert.equal(assetCaptureProject('/etc',[root]),false);
 await mkdir(root+'/scenes',{recursive:true});await writeFile(root+'/scenes/fixture.tscn','[gd_scene load_steps=1 format=3]');
 await mkdir(root+'/.opencode/capture-jobs/rig-capture-fixture',{recursive:true});
 await writeFile(root+'/.opencode/capture-jobs/rig-capture-fixture/request.json',JSON.stringify({schema:1,scene:'scenes/fixture.tscn',inputs:['scenes/fixture.tscn'],output_directory:'.opencode/captures/rig-fixture',images:['shot.png']}));
 const captureScene=await executeGameWorker(ctx,{action:'request',operation:'capture-scene',job:'rig-capture-fixture'},{...context,id:'call_capture_scene'},'rig-stage');
 assert.equal(JSON.parse(captureScene.content).status,'QUEUED','capture-scene is now enrolled on the rig, not RIG_CAPTURE_CAPABILITY_NOT_ENROLLED');
 await assert.rejects(executeGameWorker(ctx,{action:'request',operation:'capture-scene',job:'missing-manifest'},{...context,id:'call_missing_manifest'},'rig-stage'),(e)=>!/RIG_CAPTURE_CAPABILITY_NOT_ENROLLED/.test(String(e)),'a missing manifest still fails closed, on its own missing-manifest grounds -- never the old enrollment message');
 console.log('PASS staged role/scope, immediate queue, independent work, distinct jobs, immutable revision identity and rig-enrolled capture-scene');
} finally {if(!root.startsWith('/data/ai/projects/games/.rig-stage-test-'))throw Error('cleanup scope');await rm(root,{recursive:true,force:true});}
