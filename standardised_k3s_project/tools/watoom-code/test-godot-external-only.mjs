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
