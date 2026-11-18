#!/usr/bin/env python3
"""Run isolated development acceptance inside the deployed app as its runtime UID."""
import argparse,json,pathlib,subprocess,hashlib,os,struct,time
p=argparse.ArgumentParser();p.add_argument("--root",required=True);a=p.parse_args()
root=pathlib.Path(a.root)
if not root.is_absolute() or not str(root).startswith("/workspace/platform-acceptance-"):
    raise ValueError("Acceptance must use an isolated approved workspace")
root.mkdir(exist_ok=False)
checks={}
def run(name,args,timeout=90,cwd=None):
    result=subprocess.run(args,cwd=cwd or root,capture_output=True,text=True,timeout=timeout)
    (root/(name+".log")).write_text(result.stdout+result.stderr)
    checks[name]={"status":"PASS" if result.returncode==0 else "FAIL","exit_code":result.returncode}
    if result.returncode:raise RuntimeError(name+" failed; see isolated log")
    return result.stdout
try:
    run("ssh-client",["ssh","-V"])
    run("runtime-user",["python3","-c","import pwd,os; u=pwd.getpwuid(os.getuid()); assert u.pw_name=='opencode' and u.pw_dir=='/home/opencode'"])
    (root/"app.ts").write_text("export const value: number = 41;\n")
    (root/"app.ts").write_text((root/"app.ts").read_text().replace("41","42"))
    (root/"app.test.ts").write_text('import {test,expect} from "bun:test"; import {value} from "./app"; test("edited source",()=>expect(value).toBe(42));\n')
    run("typescript-tests",["bun","test","app.test.ts"])
    run("application-build",["bun","build","app.ts","--outdir","dist"])
    (root/"main.cpp").write_text('#include <iostream>\nint main(){std::cout << 42;return 0;}\n')
    (root/"CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.16)\nproject(platform_smoke LANGUAGES CXX)\nadd_executable(smoke main.cpp)\n")
    run("cmake-configure",["cmake","-S",".","-B","build","-G","Ninja"])
    run("cpp-build",["cmake","--build","build"])
    assert run("cpp-execute",[str(root/"build/smoke")]).strip()=="42"
    run("python-venv",["python3","-m","venv","venv"])
    run("python-pip",[str(root/"venv/bin/python"),"-m","pip","--version"])
    run("python-tests",[str(root/"venv/bin/python"),"-c","import unittest; t=unittest.FunctionTestCase(lambda: unittest.TestCase().assertEqual(6*7,42)); r=unittest.TextTestRunner().run(t); raise SystemExit(not r.wasSuccessful())"])
    (root/"source-assets").mkdir()
    (root/"source-assets/.gdignore").touch()
    (root/"asset.py").write_text("import bpy\nbpy.ops.wm.read_factory_settings(use_empty=True)\nbpy.ops.mesh.primitive_cube_add()\nbpy.ops.wm.save_as_mainfile(filepath="+repr(str(root/"source-assets/cube.blend"))+")\nbpy.ops.export_scene.gltf(filepath="+repr(str(root/"cube.glb"))+",export_format='GLB')\n")
    run("blender-asset",["blender","-b","--factory-startup","--threads","1","--python",str(root/"asset.py")],120)
    raw=(root/"cube.glb").read_bytes();magic,version,length=struct.unpack("<4sII",raw[:12])
    assert magic==b"glTF" and version==2 and length==len(raw)
    size,kind=struct.unpack("<II",raw[12:20]);gltf=json.loads(raw[20:20+size]);assert gltf["meshes"] and gltf["accessors"]
    checks["glb-structure"]={"status":"PASS","bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
    (root/"read-asset.py").write_text("import bpy\nbpy.ops.wm.read_factory_settings(use_empty=True)\nbpy.ops.import_scene.gltf(filepath="+repr(str(root/"cube.glb"))+")\nassert any(o.type=='MESH' for o in bpy.data.objects)\n")
    run("blender-readback",["blender","-b","--factory-startup","--threads","1","--python",str(root/"read-asset.py")],120)
    (root/"project.godot").write_text('config_version=5\n[application]\nconfig/name="WatooM Platform Acceptance"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    (root/"smoke.gd").write_text('extends SceneTree\nfunc _init():\n\tvar asset = load("res://cube.glb")\n\tif asset == null:\n\t\tquit(1)\n\telse:\n\t\tprint("PLATFORM_GODOT_ASSET_PASS")\n\t\tquit(0)\n')
    run("godot-import",["godot","--headless","--editor","--path",str(root),"--import"],120)
    assert "PLATFORM_GODOT_ASSET_PASS" in run("godot-smoke",["godot","--headless","--path",str(root),"-s","res://smoke.gd"],90)
    (root/"index.html").write_text('<!doctype html><title>Platform smoke</title><button id="run">Build verified</button><output id="result"></output><script>document.querySelector("#run").onclick=()=>document.querySelector("#result").textContent="42";</script>')
    (root/"browser.cjs").write_text("""const {chromium}=require('playwright');const http=require('http');const fs=require('fs');
(async()=>{const server=http.createServer((q,r)=>{r.writeHead(200,{'content-type':'text/html'});r.end(fs.readFileSync('index.html'));});await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
try{browser=await chromium.launch({headless:true,args:['--no-sandbox']});const page=await browser.newPage();await page.goto('http://127.0.0.1:'+server.address().port);await page.locator('#run').click();if(await page.locator('#result').textContent()!=='42')throw Error('browser interaction failed');await page.screenshot({path:'browser-smoke.png'});console.log('PLAYWRIGHT_INTERACTION_PASS');}
finally{if(browser)await browser.close();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1;});""")
    run("browser-smoke",["node","browser.cjs"],90)
    run("git-init",["git","init","-b","platform-smoke"])
    run("git-add",["git","add","app.ts","app.test.ts","main.cpp","CMakeLists.txt","project.godot","smoke.gd","index.html"])
    run("git-commit",["git","-c","user.name=Platform Acceptance","-c","user.email=platform-acceptance@localhost","commit","-m","test: isolated development platform smoke"])
    assert not run("git-tracked-diff",["git","diff","--exit-code"]).strip()
    approved=pathlib.Path("/data/ai/projects/llm")/root.name
    approved.mkdir();(approved/"persistence.txt").write_text("platform-persistence-marker")
    (root/"persistence.txt").write_text("platform-persistence-marker")
    checks["approved-project-writes"]={"status":"PASS","path":str(approved)}
    checks["runtime-identity"]={"status":"PASS" if os.getuid()==1001 else "FAIL","uid":os.getuid()}
except (OSError,RuntimeError,AssertionError,subprocess.TimeoutExpired) as error:
    checks["failure"]={"status":"FAIL","error":str(error)}
finally:
    report={"result":"PASS" if checks and all(x["status"]=="PASS" for x in checks.values()) else "FAIL","root":str(root),"checks":checks}
    (root/"acceptance.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
raise SystemExit(0 if report["result"]=="PASS" else 1)
