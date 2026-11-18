import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,utimesSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {loadLearnedLessons,learnedLessonsNote,learnedApiWarnings,withLearnedWarning} from '../../ansible/roles/watoom-code/files/coordinator-guard/index.js';

const engine=[
 {engine:'godot',version:'4.7.2',kind:'set',class:'ProceduralSkyMaterial',member:'sun_elevation',value_type:'float'},
 {engine:'godot',version:'4.7.2',kind:'call',class:'FileAccess',member:'store_text',value_type:''},
 {engine:'godot',version:'4.7.2',kind:'set',class:'MeshInstance3D',member:'material',value_type:'Material'},
 {engine:'godot',version:'4.7.2',kind:'get',class:'Animation',member:'track_count',value_type:''},
];
const data={version:1,generated_utc:1,engine,owner:[{problem:'owner lesson',rule:'Never fix engine API errors from memory;\nverify them first.'}]};

// standing note: names the engine, lists the rejected members, carries owner rules, stays small
const note=learnedLessonsNote(data);
assert.match(note,/godot 4\.7\.2/);
for(const needle of ['ProceduralSkyMaterial.sun_elevation (assignment)','FileAccess.store_text()','Animation.track_count','OWNER LESSONS','Never fix engine API errors from memory; verify them first.'])assert.ok(note.includes(needle),needle);
assert.ok(note.length<3200,'note stays compact');
assert.equal(learnedLessonsNote({version:1,engine:[],owner:[]}),null);
assert.equal(learnedLessonsNote(null),null);

// targeted warnings at the moment a script uses a rejected name
const w=t=>learnedApiWarnings(t,data);
assert.deepEqual(w('sky_mat.sun_elevation = 35.0'),['ProceduralSkyMaterial.sun_elevation (assignment) (godot 4.7.2)']);
assert.equal(w('var sun_elevation = 35.0').length,0,'a local name is not a member access');
assert.equal(w('sky_mat.sun_elevation == 3').length,0,'comparison is not an assignment');
assert.equal(w('f.store_text("x")').length,1);
assert.equal(w('f.store_string("x")').length,0,'the valid method is not flagged');
assert.equal(w('mesh.material = m').length,0,'a common word needs its class named');
assert.equal(w('var m := MeshInstance3D.new()\nm.material = mat').length,1);
assert.equal(w('anim.track_count').length,1);
assert.deepEqual(w(''),[]);assert.deepEqual(learnedApiWarnings('x.sun_elevation = 1',null),[]);
// hostile lesson data cannot inject a regex or break matching
const evil={version:1,owner:[],engine:[{engine:'godot',version:'4.7.2',kind:'call',class:'A',member:'a.*b(',value_type:''},{engine:'godot',version:'4.7.2',kind:'call',class:'X Y',member:'ok_name',value_type:''}]};
assert.deepEqual(learnedApiWarnings('a.b(',evil),[]);assert.equal(learnedLessonsNote(evil),null);

// the warning lands in the tool result without breaking either result shape
let r=withLearnedWarning({content:'wrote'},w('f.store_text("x")'));
assert.match(r.content,/LEARNED_API_WARNING.*FileAccess\.store_text\(\)/s);assert.equal(r.metadata.learned_api_warning.length,1);
r=withLearnedWarning({output:'wrote'},w('f.store_text("x")'));assert.match(r.output,/LEARNED_API_WARNING/);
assert.deepEqual(withLearnedWarning({content:'x'},[]),{content:'x'});assert.equal(withLearnedWarning(null,['a']),null);

// file loader: missing, malformed, wrong shape and oversize give null; edits are picked up by mtime
const dir=mkdtempSync(join(tmpdir(),'learned-'));const f=join(dir,'learned-lessons.json');
assert.equal(loadLearnedLessons(f),null);
writeFileSync(f,'not json');assert.equal(loadLearnedLessons(f),null);
writeFileSync(f,JSON.stringify({version:2,engine:[],owner:[]}));utimesSync(f,1,2);assert.equal(loadLearnedLessons(f),null);
writeFileSync(f,JSON.stringify(data));utimesSync(f,3,4);assert.equal(loadLearnedLessons(f).engine.length,4);
writeFileSync(f,JSON.stringify({...data,engine:engine.slice(0,1)}));utimesSync(f,5,6);assert.equal(loadLearnedLessons(f).engine.length,1);
writeFileSync(f,'x'.repeat(1048577));utimesSync(f,7,8);assert.equal(loadLearnedLessons(f),null);
console.log('PASS learned lessons: note, targeted warnings, hostile data, result shapes and file loader');
