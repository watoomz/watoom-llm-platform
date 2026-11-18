"""Bounded software-only Unreal renderer; private RO mounts, no GPU-controller changes."""
import argparse,pathlib,os,subprocess,sys,select,shutil,json
p=argparse.ArgumentParser()
for n in ["project","engine","content","script"]:p.add_argument("--"+n,required=True,type=pathlib.Path)
p.add_argument("--inside",action="store_true");a=p.parse_args()
root=a.project.resolve();engine=a.engine.resolve();content=a.content.resolve();script=a.script.resolve()
if not root.is_relative_to("/data/ai/projects") or not (engine/"Engine/Binaries/Linux/UnrealEditor").is_file() or not content.is_relative_to("/data/ai/assets/fab"):raise SystemExit("Explicit scoped project/accepted runtime/source paths required")
if os.geteuid()!=0:raise SystemExit("Private read-only bind setup requires administrative runner")
if not a.inside:
 ram=int(next(x.split()[1] for x in pathlib.Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:")))*1024
 if ram<7*1024**3:raise SystemExit("7GiB actual headroom required (5GiB hard limit plus2GiB host reserve); active work preserved")
 if shutil.disk_usage("/data/ai").free<300*1024**3:raise SystemExit("300GiB disk floor")
 command=["unshare","--mount","--propagation","private",sys.executable,__file__,*sys.argv[1:],"--inside"]
 raise SystemExit(subprocess.call(command))
(root/"Content").mkdir(exist_ok=True)
for source,target in [(content,root/"Content"),(engine,engine)]:
 subprocess.run(["mount","--bind",str(source),str(target)],check=True)
 subprocess.run(["mount","-o","remount,bind,ro",str(target)],check=True)
for n in ["home","runtime"]:
 d=root/("."+n);d.mkdir(exist_ok=True);os.chown(d,1009,1009);d.chmod(0o700)
icd=pathlib.Path("/usr/share/vulkan/icd.d/lvp_icd.x86_64.json")
if not icd.is_file():raise SystemExit("Existing software Vulkan ICD unavailable")
env=dict(os.environ,HOME=str(root/".home"),XDG_RUNTIME_DIR=str(root/".runtime"),VK_DRIVER_FILES=str(icd),VK_ICD_FILENAMES=str(icd),CUDA_VISIBLE_DEVICES="",NVIDIA_VISIBLE_DEVICES="void",LIBGL_ALWAYS_SOFTWARE="true")
read_fd,write_fd=os.pipe();x=None;editor=None
try:
 x=subprocess.Popen(["Xvfb","-displayfd",str(write_fd),"-screen","0","640x480x24","-nolisten","tcp"],pass_fds=(write_fd,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 os.close(write_fd);write_fd=None
 ready,_,_=select.select([read_fd],[],[],10)
 if not ready:raise RuntimeError("Owned display allocation failed")
 display=os.read(read_fd,64).decode().strip()
 if not display.isdigit() or x.poll() is not None:raise RuntimeError("Owned display unavailable")
 env["DISPLAY"]=":"+display
 argv=["setpriv","--reuid=1009","--regid=1009","--clear-groups",str(engine/"Engine/Binaries/Linux/UnrealEditor"),str(root/"BloodFx.uproject"),"-vulkan","-AllowSoftwareRendering","-sm5","-unattended","-nosound","-nosplash","-nop4","-stdout","-FullStdOutLogOutput","-ddc=NoZenLocalFallback","-LocalDataCachePath="+str(root/"DerivedDataCache"),"-ExecutePythonScript="+str(script)]
 with (root/"software-render.log").open("w") as log:
  editor=subprocess.Popen(argv,env=env,stdout=log,stderr=subprocess.STDOUT)
  try:rc=editor.wait(timeout=1500)
  except subprocess.TimeoutExpired:editor.terminate();raise RuntimeError("Bounded software render timed out")
 text=(root/"software-render.log").read_text(errors="replace")
 if "llvmpipe" not in text.lower():raise RuntimeError("Actual software device not proven")
 result=json.loads((root/"bloodfx-render.json").read_text());result.update(actual_software_device=True,exit_code=rc)
 (root/"software-render-receipt.json").write_text(json.dumps(result,indent=2))
 if rc or result["status"]!="PASS_NATIVE_SAMPLED_RENDER":raise RuntimeError("Native render gate failed; inspect retained log/receipt")
finally:
 os.close(read_fd)
 if write_fd is not None:os.close(write_fd)
 if editor is not None and editor.poll() is None:
  editor.terminate()
  try:editor.wait(timeout=10)
  except subprocess.TimeoutExpired:editor.kill();editor.wait()
 if x is not None and x.poll() is None:
  x.terminate()
  try:x.wait(timeout=5)
  except subprocess.TimeoutExpired:x.kill();x.wait()
