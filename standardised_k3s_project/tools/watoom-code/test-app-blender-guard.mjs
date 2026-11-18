import assert from "node:assert/strict";
import {appBlenderLaunch,assertAllowed} from "../../ansible/roles/watoom-code/files/coordinator-guard/index.js";
const blocked=[
 "blender --background bench.blend --python render.py",
 "/opt/blender/blender -b bench.blend",
 "OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 /opt/blender/blender --background bench.blend",
 "cd /project && /opt/blender/blender -b bench.blend",
 "timeout 300 /opt/blender/blender --background bench.blend",
 "env OMP_NUM_THREADS=2 /opt/blender/blender -b bench.blend",
 '"/path with spaces/blender" --background bench.blend',
 "exec /opt/blender/blender -b bench.blend",
 "bash -lc 'blender -b bench.blend'",
 "blender --python-expr 'print(1)'",
 "blender --version",
 "blender"
];
for(const command of blocked){assert(appBlenderLaunch(command),command);assert.throws(()=>assertAllowed('shell',{command},{},false),/EXTERNAL_BLENDER_WORKER_REQUIRED/,command);}
for(const command of ['cat /project/render.py','sha256sum /opt/blender/blender','echo "blender --background bench.blend"','python3 -m json.tool runtime.json']){assert(!appBlenderLaunch(command),command);assert.doesNotThrow(()=>assertAllowed('shell',{command},{},false));}
assert.doesNotThrow(()=>assertAllowed('write',{path:'render.sh',content:'blender -b bench.blend'},{},false));
console.log('APP_BLENDER_GUARD=PASS; blocked='+blocked.length+'; neutral reads/writes preserved; no engine launched');

const continuedHash = "sha256sum " + String.fromCharCode(92,10) + " /opt/blender/blender " + String.fromCharCode(92,10) + " /project/source.blend";
assert(!appBlenderLaunch(continuedHash));
assert.doesNotThrow(()=>assertAllowed("shell",{command:continuedHash},{},false));
assert(appBlenderLaunch("echo checked\n/opt/blender/blender -b scene.blend"));
assert(appBlenderLaunch("env OMP_NUM_THREADS=2 " + String.fromCharCode(92,10) + " /opt/blender/blender -b scene.blend"));
console.log("PASS continued checksum arguments permitted; real multiline launches remain blocked");
