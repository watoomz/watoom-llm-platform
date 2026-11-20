import assert from 'node:assert/strict';
import {assertAllowed,godotInspectOnly} from '../../ansible/roles/watoom-code/files/coordinator-guard/index.js';
for(const command of ['godot --headless scene.tscn','timeout 90 xvfb-run -a godot --path . --headless scene.tscn 2>&1 | head -80','godot --headless --script res://capture.gd','godot --check-only --script test.gd; godot scene.tscn','/usr/local/bin/godot --headless --path .','godot --check-only --script test.gd --scene game.tscn'])assert.throws(()=>assertAllowed('shell',{command},{},false),/EXTERNAL_GODOT/);
for(const command of ['godot --version','/usr/local/bin/godot --help','timeout 20 godot --headless --check-only --script res://scripts/capture.gd'])assert(godotInspectOnly(command));
console.log('PASS all Godot scene/script launches rejected, headless/Xvfb bypass closed, standalone version/help/parser checks retained');

for(const command of ["which godot","command -v godot","rg -n godot scripts/scene.gd"])assert.doesNotThrow(()=>assertAllowed("shell",{command},{},false));
assert.throws(()=>assertAllowed("shell",{command:"flatpak run --system org.godotengine.Godot --headless scene.tscn"},{},false),/EXTERNAL_GODOT/);
// The forms agents actually type around a parse check are accepted; real bypasses are not.
for(const command of ['cd /data/ai/projects/games/magpie-flight-godot-candidate && godot --headless --check-only -s scripts/main.gd 2>&1','godot --headless --check-only -s scripts/main.gd 2>&1 | head -30','cd "/data/ai/projects/games/x y" && godot --headless --check-only --script res://scripts/main.gd 2>&1 | tail -n 20','godot --help 2>&1 | head -5']){assert(godotInspectOnly(command),command);assert.doesNotThrow(()=>assertAllowed("shell",{command},{},false));}
for(const command of ['cd /p && godot --headless scene.tscn 2>&1','cd /p; godot --check-only -s a.gd','cd $(pwd) && godot --check-only -s a.gd','godot --check-only -s a.gd 2>&1 | sh','cd /p && cd /q && godot --check-only -s a.gd','godot --check-only -s a.gd | head -5 | sh'])assert.throws(()=>assertAllowed("shell",{command},{},false),/EXTERNAL_GODOT/,command);
console.log('PASS cd/2>&1/head wrappers accepted around parse checks; chains, redirects and scene launches still rejected');

// T-0082: Godot hidden inside a Python/Node/shell wrapper (file or inline) is still a local Godot launch.
{
const {mkdtempSync,writeFileSync,mkdirSync}=await import('node:fs');const {join}=await import('node:path');const {tmpdir}=await import('node:os');
const {indirectGodotLaunch}=await import('../../ansible/roles/watoom-code/files/coordinator-guard/index.js');
const d=mkdtempSync(join(tmpdir(),'godot-wrap-'));mkdirSync(join(d,'w'));
writeFileSync(join(d,'w/run.py'),'import subprocess\ndef go():\n    cmd = [\n        "godot",\n        "--headless", "res://scenes/main.tscn",\n    ]\n    return subprocess.Popen(cmd)\n');
writeFileSync(join(d,'w/bin.py'),'import subprocess\nsubprocess.run([godot_bin, "--headless", "--editor", "--quit"])\n');
writeFileSync(join(d,'w/run.sh'),'#!/bin/sh\n# godot is external\ntimeout 60 godot --headless scene.tscn\n');
writeFileSync(join(d,'w/data.py'),'KEYWORDS = ["godot", "unity"]\nproj = "/games/magpie-godot"\nprint("Godot applies scale")\n');
writeFileSync(join(d,'w/export.py'),'import subprocess\nsubprocess.run(["blender","-b"])\nrun(preset="godot", objects=["Hero"])\n');
for(const [command,workdir] of [['TEST_ROOT="$(pwd)" python3 w/run.py',d],['cd '+d+' && python3 w/run.py 2>&1',undefined],['python3 w/bin.py',d],['sh w/run.sh',d],['./w/run.sh',d],
  [`python3 -c "import subprocess; subprocess.run(['godot','--headless'])"`,d],[`node -e "require('child_process').execSync('godot --headless x.tscn')"`,d],[`bash -c "godot --headless x.tscn"`,d]]) {
  assert(indirectGodotLaunch(command,workdir),command);
  assert.throws(()=>assertAllowed('shell',{command,workdir},{},false),/EXTERNAL_GODOT_WORKER_REQUIRED/,command);
}
for(const command of ['python3 w/data.py','python3 w/export.py','python3 w/missing.py','cat w/run.py','grep -n godot w/run.py','python3 -m unittest discover'])
  assert.doesNotThrow(()=>assertAllowed('shell',{command,workdir:d},{},false),command);
console.log('PASS Godot launched through Python/Node/shell wrappers (files or inline) is rejected; data mentioning godot is not');
}
