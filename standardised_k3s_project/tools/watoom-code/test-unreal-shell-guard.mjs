import assert from "node:assert/strict";
import {assertAllowed} from "../../ansible/roles/watoom-code/files/coordinator-guard/index.js";
for(const command of ["UnrealEditor -version","/unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd -run=PythonScript","ls /tmp; /path/UnrealEditor -version","timeout 120 /path/UnrealEditor -version","nice -n 19 /path/ShaderCompileWorker"])
 assert.throws(()=>assertAllowed("shell",{command},{errors:0},false),/EXTERNAL_UNREAL_WORKER_REQUIRED/);
for(const command of ["cat /engine/Engine/Build/Build.version","ls /engine/Engine/Binaries/Linux/UnrealEditor","grep UnrealEditor manifest.json"])
 assert.doesNotThrow(()=>assertAllowed("shell",{command},{errors:0},false));
console.log("PASS Unreal launch rejection, timeout/nice wrappers, and read-only inspection");
