"""Actual CPU-only Godot Sprite3D playback/capture using a verified installed binary."""
import argparse,pathlib,subprocess,os,select,json,hashlib
p=argparse.ArgumentParser();p.add_argument("--project",required=True,type=pathlib.Path);p.add_argument("--godot",required=True,type=pathlib.Path);a=p.parse_args()
root=a.project.resolve();binary=a.godot.resolve()
if not root.is_relative_to("/data/ai/projects") or not (root/"project.godot").is_file():raise SystemExit("Scoped existing project required")
with binary.open("rb") as f:assert hashlib.file_digest(f,"sha256").hexdigest()=="8d106cbe6144c2dc7e881d61d2429c1a8a76e6b22ef48bd5e48dcf934953f71e"
read_fd,write_fd=os.pipe();x=None
try:
 x=subprocess.Popen(["Xvfb","-displayfd",str(write_fd),"-screen","0","512x512x24","-nolisten","tcp"],pass_fds=(write_fd,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 os.close(write_fd);write_fd=None
 ready,_,_=select.select([read_fd],[],[],10)
 if not ready:raise RuntimeError("Owned Godot display timed out")
 display=os.read(read_fd,64).decode().strip();assert display.isdigit() and x.poll() is None
 env=dict(os.environ,DISPLAY=":"+display,LIBGL_ALWAYS_SOFTWARE="true",GALLIUM_DRIVER="llvmpipe",CUDA_VISIBLE_DEVICES="",NVIDIA_VISIBLE_DEVICES="void",HOME=str(root))
 prefix=["setpriv","--reuid=1009","--regid=1009","--clear-groups"]
 with (root/"godot-import.log").open("w") as log:
  subprocess.run(prefix+[str(binary),"--headless","--editor","--path",str(root),"--quit"],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
 with (root/"godot-play.log").open("w") as log:
  subprocess.run(prefix+[str(binary),"--path",str(root),"--rendering-method","gl_compatibility","--rendering-driver","opengl3","--resolution","512x512","--script","res://verify.gd"],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
 assert "llvmpipe" in (root/"godot-play.log").read_text().lower(),"Actual CPU renderer not proven"
 receipt=json.loads((root/"godot.json").read_text());assert receipt["status"]=="PASS_GODOT_SPRITE3D_PLAYBACK_RENDER";print(json.dumps({"status":"PASS","effects":len(receipt["effects"]),"renderer":"llvmpipe"}))
finally:
 os.close(read_fd)
 if write_fd is not None:os.close(write_fd)
 if x is not None and x.poll() is None:
  x.terminate()
  try:x.wait(timeout=5)
  except subprocess.TimeoutExpired:x.kill();x.wait()
