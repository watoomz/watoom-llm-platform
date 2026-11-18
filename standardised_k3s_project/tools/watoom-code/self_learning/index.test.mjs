import test from "node:test";import assert from "node:assert/strict";import {mkdtemp,rm} from "node:fs/promises";import {tmpdir} from "node:os";import path from "node:path";import {install} from "./index.mjs";
test("learning storage failures preserve the original model context and successful tool result",async()=>{
 const root=await mkdtemp(path.join(tmpdir(),"watoom-learning-hook-"));let unavailable=false,cleanup;const hooks={},values=new Map();const editor={list:()=>[],get:()=>undefined,add:()=>{},update:()=>{}};
 const ctx={options:{root,agent:"build",policies:[]},location:{project:{id:"p"},directory:"/isolated"},storage:{get:async k=>{if(unavailable)throw Error("fixture storage unavailable");return values.get(k);},set:async(k,v)=>{if(unavailable)throw Error("fixture storage unavailable");values.set(k,structuredClone(v));}},skill:{list:async()=>({data:[]}),transform:async f=>{f(editor);},reload:async()=>{}},tool:{transform:async f=>f(editor),hook:async(name,f)=>{hooks[name]=f;}},session:{hook:async(name,f)=>{hooks[name]=f;}}};
 try{cleanup=await install(ctx);unavailable=true;const e={agent:"build",sessionID:"s",messages:[],system:[{type:"text",text:"Preserve user preference"}]};await assert.doesNotReject(hooks.context(e));assert.deepEqual(e.system,[{type:"text",text:"Preserve user preference"}]);const outcome={agent:"build",sessionID:"s",messageID:"m",id:"c",tool:"safe-task",input:{},status:"completed",result:{content:"Verified task output"}};await assert.doesNotReject(hooks["execute.after"](outcome));assert.equal(outcome.result.content,"Verified task output");}finally{cleanup?.();assert(root.startsWith(path.join(tmpdir(),"watoom-learning-hook-")));await rm(root,{recursive:true,force:true});}
});

import {publishArtifact} from "./index.mjs";
import {readFile,readdir} from "node:fs/promises";
test("concurrent project writers publish one immutable body without shared temp collisions",async()=>{
 const root=await mkdtemp(path.join(tmpdir(),"watoom-artifact-race-"));
 try{const target=path.join(root,"same.md");await Promise.all(Array.from({length:40},()=>publishArtifact(root,target,"unchanged")));assert.equal(await readFile(target,"utf8"),"unchanged");await assert.rejects(publishArtifact(root,target,"different"),/collision/);assert.deepEqual(await readdir(root),["same.md"]);}finally{await rm(root,{recursive:true,force:true});}
});
