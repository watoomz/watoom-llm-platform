import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {assertAllowed} from "../../ansible/roles/watoom-code/files/coordinator-guard/index.js";
for(const role of ["watoom-critic","watoom-investigator"]){
 const state={callingAgent:role,direct:0,errors:0,reviews:[],calls:[]};
 for(const tool of ["read","glob","grep","question","shell","watoom_skill_search"])assert.doesNotThrow(()=>assertAllowed(tool,{command:"stat /data/github"},state,false));
 for(const tool of ["write","edit"])assert.throws(()=>assertAllowed(tool,{path:"/data/test"},state,false),/READ_ONLY/);
 assert.throws(()=>assertAllowed("shell",{command:"blender -b scene.blend"},state,false),/EXTERNAL_BLENDER/);
 const text=await readFile(new URL("../../ansible/roles/opencode-agent/files/v2-native/agents/"+role+".md",import.meta.url),"utf8");
 assert.match(text,/action: "shell"\n    resource: "\*"\n    effect: ask/);
 assert.match(text,/action: "external_directory"\n    resource: "\*"\n    effect: allow/);
 assert.match(text,/action: "read"\n    resource: "\*"\n    effect: allow/);
}
console.log("PASS broad read/search, native shell ask policy, write denial and engine guard retained");
