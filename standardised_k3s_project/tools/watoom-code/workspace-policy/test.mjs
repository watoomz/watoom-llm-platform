import assert from "node:assert/strict";import fs from "node:fs";import os from "node:os";import path from "node:path";
import {assess,resolveBoundary,install} from "./guard.mjs";
const root=fs.mkdtempSync(path.join(os.tmpdir(),"workspace-policy-"));fs.mkdirSync(root+"/.opencode/work",{recursive:true});fs.symlinkSync("/etc",root+"/escape");
assert(assess("write",{filePath:root+"/new.yml"},root));assert(assess("write",{filePath:root+"/.opencode/work/checkpoint.md"},root));
for(const file of ["../escape.yml","escape/passwd",".git/config","opencode.json",".opencode/plugins/evil.js"])assert(!assess("write",{path:file},root));
for(const name of ["shell","execute","apply_patch","watoom_game_worker","mcp_unreviewed"])assert(!assess(name,{command:"true"},root));
const sessions={old:{time:{created:1},location:{directory:root}},fresh:{time:{created:3},location:{directory:root}},child:{parentID:"fresh",location:{directory:root}},escape:{parentID:"fresh",location:{directory:"/tmp"}},idx:{time:{created:3},location:{directory:"/workspace"}}};
const lookup=async id=>sessions[id],policy={root,enrollAfter:2};assert.equal(await resolveBoundary("old",lookup,policy),null);assert.equal(await resolveBoundary("idx",lookup,policy),null);assert.equal((await resolveBoundary("child",lookup,policy)).root,root);await assert.rejects(resolveBoundary("escape",lookup,policy));console.log("PASS: allow/deny, symlinks, runtime config, old sessions, child inheritance, unrelated IDX");

const policyFile=root+"/policy.json";fs.writeFileSync(policyFile,JSON.stringify({version:2,root,enrollAfter:2}));let before;
await install({options:{policy:policyFile},session:{get:async({sessionID})=>sessions[sessionID],hook:async()=>{}},tool:{hook:async(name,handler)=>{assert.equal(name,"execute.before");before=handler;}}});
await assert.rejects(before({sessionID:"fresh",tool:"late_registered_executor",input:{}}));await before({sessionID:"idx",tool:"late_registered_executor",input:{}});console.log("PASS: native hook covers late tools without enrolling IDX");
