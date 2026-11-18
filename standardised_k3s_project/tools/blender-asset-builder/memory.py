"""Existing AgentMemory HTTP contract inspected from installed v0.9.29 source."""
import os,json,pathlib,sys,urllib.request,hashlib,subprocess
r=pathlib.Path(sys.argv[1]);mode=sys.argv[2] if len(sys.argv)>2 else 'recall';key='watoom-blender-static-recipe-4.2.23-godot-20261020'
def call(path,data):
 req=urllib.request.Request(os.environ['AGENTMEMORY_URL'].rstrip('/')+'/agentmemory/'+path,json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['AGENTMEMORY_SECRET']})
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
try:
 if mode=='save':
  q=json.loads((r/'reports/quality.json').read_text());g=json.loads((r/'engine-validation/result.json').read_text());assert q['technical_pass'] and g['status']=='PASS','cannot save unverified recipe'
  recipe={'key':key,'category':'static Blender to Godot','blender':'4.2.23','godot':g['godot'],'environment':'opencode-v2-canary CPU four threads','inputs':'versioned directory, reviewed scripts, local anatomy references','tested_command':'python3 scripts/pipeline.py --root '+str(r)+' --resume','expected_output':'blend, packed texture PNGs, GLB, FBX, contact sheet, quality.json, Godot instantiated meshes','validation':{'technical':'PASS','godot':'PASS','visual':'see separate visual-review.json','rig':'NOT TESTED','unreal':'NOT TESTED'},'failures':['zero-area UV end caps','triangle budget','disabled subdivision level zero'],'provenance':json.loads((r/'upstream-manifest.json').read_text())[0]['commit'],'script_sha256':hashlib.sha256((r/'scripts/magpie.py').read_bytes()).hexdigest()}
  result=call('remember',{'content':json.dumps(recipe),'type':'workflow','concepts':['blender','godot',key],'project':'watoom-blender-asset-builder'});(r/'reports/memory-save.json').write_text(json.dumps(result,indent=2));print(json.dumps({'status':'PASS','operation':'save'}))
 else:
  result=call('search',{'query':key,'limit':3,'format':'full','project':'watoom-blender-asset-builder'});found=key in json.dumps(result);assert found,'verified recipe not retrieved'
  if mode=='reuse':
   assert hashlib.sha256((r/'scripts/magpie.py').read_bytes()).hexdigest() in json.dumps(result),'recipe environment/script provenance mismatch'
   # Execute the locally known adapter, never arbitrary command text from memory.
   q=subprocess.run([sys.executable,str(r/'scripts/pipeline.py'),'--root',str(r),'--dry-run'],capture_output=True,text=True,timeout=15);assert q.returncode==0;json.loads(q.stdout)
  (r/'reports'/('memory-'+mode+'.json')).write_text(json.dumps({'status':'PASS' if found else 'FAIL','result':result,'reuse':'local runner dry-run with matching script hash' if mode=='reuse' else None},indent=2));print(json.dumps({'status':'PASS','operation':mode,'recipe':key}))
except Exception as e:print(json.dumps({'status':'BLOCKED','error':type(e).__name__,'reason':str(e)[:180]}));sys.exit(2)
