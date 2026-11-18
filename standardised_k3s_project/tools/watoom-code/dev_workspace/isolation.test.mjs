import { test } from 'node:test';
import assert from 'node:assert/strict';
import { assertTool, install, saveRecipe } from './index.js';
test('dev leaf enforcement denies every ordinary and privileged route', () => {
 for (const tool of ['bash','read','write','edit','apply_patch','task','codemode','watoom_specialist','kubectl','watoom_memory_remember']) assert.throws(()=>assertTool('watoom-dev',tool),/DEV_ISOLATION/);
 for (const tool of ['watoom_dev_workspace','watoom_memory_recall']) assert.doesNotThrow(()=>assertTool('watoom-dev',tool));
 assert.doesNotThrow(()=>assertTool('watoom-builder','bash'));
});
test('wrapping blocks an attempted direct leaf execution before side effects', async () => {
 let called=false;
 const tools=[{id:'shell',name:'bash',execute(){called=true;}}];
 const ctx={location:{directory:'/data/github/watoom-homelab-dev'},options:{},tool:{async transform(fn){fn({add(x){tools.push({...x,id:x.name});},list(){return tools;},update(id,fn){fn(tools.find(x=>x.id===id));}});}}};
 await install(ctx);
 assert.throws(()=>tools[0].execute({}, {agent:'watoom-dev'}), /DEV_ISOLATION/);
 assert.equal(called,false);
 tools[0].execute({}, {agent:'watoom-builder'}); assert.equal(called,true);
 const dev=tools.find(x=>x.name==='watoom_dev_workspace');
 await assert.rejects(()=>dev.execute({op:'status',job:'owned'}, {agent:'watoom-builder'}),/DEV_ISOLATION/);
 ctx.location.directory='/workspace';
 await assert.rejects(()=>dev.execute({op:'status',job:'owned'}, {agent:'watoom-dev'}),/DEV_ISOLATION/);
});

test('only verified pushed reports invoke the existing scoped native remember command', async () => {
 const calls=[]; const ctx={session:{async command(...args){calls.push(args);}}};
 const context={sessionID:'owned-native-session'};
 await saveRecipe(ctx,{op:'report'},context,{task:{phase:'COMMITTED'}});
 assert.equal(calls.length,0);
 await saveRecipe(ctx,{op:'report'},context,{task:{phase:'PUSHED',job:'owned-recipe',commit:'a'.repeat(40),files:['test.py'],validated_command:'python3 -m unittest'}});
 assert.equal(calls.length,1);assert.equal(calls[0][0].name,'remember');
 assert.equal(calls[0][0].sessionID,context.sessionID);
 assert.match(calls[0][0].text,/python3 -m unittest/);
});
