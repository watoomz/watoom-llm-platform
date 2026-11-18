import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,rm,symlink} from 'node:fs/promises';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {gameSourceManifest,gameSourceFingerprint,executeGameWorker} from '../../ansible/roles/watoom-code/files/coordinator-guard/index.js';
const root=await mkdtemp('/data/ai/projects/games/.fingerprint-fixture-');
const tools=new URL('.',import.meta.url).pathname;
const stamp=(p,n)=>execFileSync('python3',['-c','import os,sys;os.utime(sys.argv[1],ns=(int(sys.argv[2]),int(sys.argv[2])))',p,String(n)]);
let checks=0;
const check=(v,label)=>{assert.ok(v,label);checks++;};
try {
 await writeFile(join(root,'project.godot'),'AAAA');stamp(join(root,'project.godot'),1700000000123456789n);
 const first=await gameSourceFingerprint(root);check(first===createHash('sha256').update('[[".watoom-worker-contract","cache-mount-v1","0"],["project.godot","4","1700000000123456789"]]').digest('hex'),'exact compact JSON and decimal nanoseconds');check(first===await gameSourceFingerprint(root),'identical manifests');
 await writeFile(join(root,'project.godot'),'AAAAA');stamp(join(root,'project.godot'),1700000000123456789n);check(first!==await gameSourceFingerprint(root),'size');
 await writeFile(join(root,'project.godot'),'AAAA');stamp(join(root,'project.godot'),1700000000123456789n);assert.equal(first,await gameSourceFingerprint(root));
 stamp(join(root,'project.godot'),1700000000123456790n);check(first!==await gameSourceFingerprint(root),'single nanosecond');stamp(join(root,'project.godot'),1700000000123456789n);
 await writeFile(join(root,'added.gd'),'');check(first!==await gameSourceFingerprint(root),'included addition');await rm(join(root,'added.gd'));
 for(const name of ['.godot','.git','.opencode','magpie-final']){await mkdir(join(root,name));await writeFile(join(root,name,'ignored'),'cache');}
 await writeFile(join(root,'ignored.import'),'x');check(first===await gameSourceFingerprint(root),'excluded dirs/extensions');
 for(const name of ['a','é','\uE000','😀','quote"line\n\\','separator\u2028']){await writeFile(join(root,name),'x');stamp(join(root,name),1700000000000000000n);}
 const manifest=await gameSourceManifest(root);check(manifest.every((row,i)=>!i || Buffer.compare(Buffer.from(manifest[i-1][0]),Buffer.from(row[0]))<=0),'UTF8 byte order');
 const python=execFileSync('python3',['-c',"import sys,pathlib;sys.path.insert(0,sys.argv[1]);from game_worker_bridge import fingerprint;print(fingerprint(pathlib.Path(sys.argv[2])))",tools,root],{encoding:'utf8'}).trim();check(python===await gameSourceFingerprint(root),'JSON unicode/control parity');
 await writeFile(join(root,'.watoom-worker-contract'),'real file');check((await gameSourceManifest(root)).filter(r=>r[0]==='.watoom-worker-contract').length===2,'historical duplicate sentinel ordering preserved');await rm(join(root,'.watoom-worker-contract'));
 const cap='.opencode/validation/p6-env-capture';await mkdir(join(root,cap),{recursive:true});await writeFile(join(root,cap,'p6_env_capture.gd'),'x');
 let rows=await gameSourceManifest(root);check(rows.filter(r=>r[0]===cap+'/p6_env_capture.gd').length===1,'explicit excluded validation source included once');
 check(rows.filter(r=>r[0]==='.watoom-worker-contract').length===1,'single contract sentinel');
 await symlink('/etc/hosts',join(root,'escape'));await assert.rejects(gameSourceFingerprint(root),/SYMLINK/);checks++;await rm(join(root,'escape'));
 await rm(join(root,cap),{recursive:true});await symlink('/tmp',join(root,cap));await assert.rejects(gameSourceFingerprint(root),/SYMLINK/);checks++;await rm(join(root,cap));
 const ctx={session:{get:async()=>({location:{directory:root}})}};const context={agent:'watoom-builder',sessionID:'ses_fixture',messageID:'msg_fixture',id:'call_1'};const input={action:'request',operation:'lmb-qualify',job:'one'};
 const one=await executeGameWorker(ctx,input,context);const retry=await executeGameWorker(ctx,input,{...context,id:'call_2'});check(one.metadata.request_id===retry.metadata.request_id,'same job retry');
 const two=await executeGameWorker(ctx,{...input,job:'two'},{...context,id:'call_3'});check(two.metadata.request_id!==one.metadata.request_id,'distinct job/call');
 const req=JSON.parse(await readFile(join(root,'.opencode/worker-requests',one.metadata.request_id+'.json'),'utf8'));
 const statusPath=join(root,'.opencode/worker-requests',req.request_id+'.status.json');
 await writeFile(statusPath,JSON.stringify({...req,status:'COMPLETED',job:'wrong'}),{mode:0o644});await assert.rejects(executeGameWorker(ctx,{...input,action:'status'},context),/identity mismatch/);checks++;
 await writeFile(statusPath,JSON.stringify({...req,status:'COMPLETED'}));check(JSON.parse((await executeGameWorker(ctx,{...input,action:'status'},context)).content).status==='COMPLETED','original completed readable');
 const old={...req,status:'COMPLETED'};delete old.job;await writeFile(statusPath,JSON.stringify(old));check(JSON.parse((await executeGameWorker(ctx,{...input,action:'status'},context)).content).status==='COMPLETED','legacy status job optional');
 await writeFile(join(root,'revision.gd'),'changed');const newer=await executeGameWorker(ctx,input,{...context,id:'call_4'});check(newer.metadata.request_id!==req.request_id,'new revision request');
 await rm(join(root,'.opencode/worker-requests',newer.metadata.request_id+'.json'));check((await executeGameWorker(ctx,{...input,action:'status'},context)).metadata.request_id===req.request_id,'historical status ignores current fingerprint');
 const raw=createHash('sha256').update(await readFile(join(root,'project.godot'))).digest('hex');check(raw!==await gameSourceFingerprint(root),'raw SHA not metadata digest');
 console.log(`PASS ${checks} fingerprint and request identity regression checks`);
} finally {if(!root.startsWith('/data/ai/projects/games/.fingerprint-fixture-'))throw Error('cleanup scope');await rm(root,{recursive:true,force:true});}
