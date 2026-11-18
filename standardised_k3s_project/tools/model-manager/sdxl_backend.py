"""Local-files-only SDXL backend; controller grants exclusive GPU ownership.

No Hub fetches, remote code or chat-shaped health. Loading requires an explicit
base directory and adapter file already verified by the manager.
"""
import argparse,hashlib,json,threading,hmac
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
def pretrained_variant(base):
 weights=list(Path(base).rglob("*.safetensors"))
 fp16=[p for p in weights if p.name.endswith(".fp16.safetensors")]
 if fp16 and len(fp16)!=len(weights):raise ValueError("Mixed pipeline variants are not supported")
 return {"variant":"fp16"} if fp16 else {}
class Engine:
 def __init__(self,base,adapter=None,precision="float16",checkpoint=None):
  self.base=Path(base).resolve(strict=True);self.adapter=Path(adapter).resolve(strict=True) if adapter else None
  self.checkpoint=Path(checkpoint).resolve(strict=True) if checkpoint else None
  self.precision=precision;self.pipeline=None;self.lock=threading.Lock()
 def load(self):
  import torch
  from diffusers import StableDiffusionXLPipeline
  dtype={"float16":torch.float16,"bfloat16":torch.bfloat16,"float32":torch.float32}[self.precision]
  if self.checkpoint:
   self.pipeline=StableDiffusionXLPipeline.from_single_file(str(self.checkpoint),config=str(self.base),torch_dtype=dtype,local_files_only=True,use_safetensors=True)
  else:
   self.pipeline=StableDiffusionXLPipeline.from_pretrained(str(self.base),torch_dtype=dtype,local_files_only=True,use_safetensors=True,**pretrained_variant(self.base))
  if self.adapter:self.pipeline.load_lora_weights(str(self.adapter.parent),weight_name=self.adapter.name,adapter_name="managed",local_files_only=True)
  self.pipeline.to("cuda")
 def generate(self,request,output):
  import torch
  from diffusers import EulerDiscreteScheduler,DPMSolverMultistepScheduler
  from settings import validate,validate_negative_prompt
  negative_prompt=validate_negative_prompt(request.get("negative_prompt",""))
  settings={k:v for k,v in request.items() if k not in ("prompt","negative_prompt")}
  validate(settings,"lora" if self.adapter else "diffusion-pipeline")
  prompt=request.get("prompt")
  if not isinstance(prompt,str) or not 1<=len(prompt)<=4096:raise ValueError("Bounded prompt required")
  with self.lock:
   scheduler=settings.get("scheduler","euler")
   cls=EulerDiscreteScheduler if scheduler=="euler" else DPMSolverMultistepScheduler
   self.pipeline.scheduler=cls.from_config(self.pipeline.scheduler.config)
   if self.adapter:self.pipeline.set_adapters(["managed"],adapter_weights=[settings.get("strength",1.0)])
   seed=settings.get("seed",0)
   image=self.pipeline(prompt=prompt,negative_prompt=negative_prompt,width=settings.get("width",1024),height=settings.get("height",1024),num_inference_steps=settings.get("steps",30),guidance_scale=settings.get("guidance",7.0),generator=torch.Generator("cuda").manual_seed(seed)).images[0]
   image.save(output)
   return {"status":"generated","seed":seed,"width":image.width,"height":image.height,"sha256":hashlib.sha256(Path(output).read_bytes()).hexdigest()}
def main():
 parser=argparse.ArgumentParser();parser.add_argument("--base",required=True);parser.add_argument("--adapter");parser.add_argument("--checkpoint");parser.add_argument("--alias",required=True);parser.add_argument("--precision",choices=("float16","bfloat16","float32"),default="float16");parser.add_argument("--output",required=True);parser.add_argument("--key-file",required=True)
 args=parser.parse_args();key=Path(args.key_file).read_text().strip();engine=Engine(args.base,args.adapter,args.precision,args.checkpoint);engine.load()
 output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def reply(self,status,body):
   raw=json.dumps(body).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
  def do_GET(self):
   if self.path.startswith("/artifacts/"):
    if not hmac.compare_digest(self.headers.get("Authorization",""),"Bearer "+key):return self.reply(401,{"error":"Unauthorized"})
    import re
    name=self.path[len("/artifacts/"):]
    if not re.fullmatch("[a-f0-9]{32}"+r"\.png",name):return self.reply(404,{"error":"Not found"})
    file=output/name
    if not file.is_file() or file.is_symlink():return self.reply(404,{"error":"Not found"})
    raw=file.read_bytes();self.send_response(200);self.send_header("Content-Type","image/png");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw);return
   if self.path=="/status":return self.reply(200,{"active":1 if engine.lock.locked() else 0})
   if self.path=="/health":return self.reply(200,{"status":"ok","backend":"sdxl","model":args.alias})
   self.reply(404,{"error":"Not found"})
  def do_POST(self):
   if not hmac.compare_digest(self.headers.get("Authorization",""),"Bearer "+key):return self.reply(401,{"error":"Unauthorized"})
   if self.path not in ("/generate","/validate"):return self.reply(404,{"error":"Not found"})
   try:
    count=int(self.headers.get("Content-Length","0"))
    if not 0<count<=65536:raise ValueError("Invalid payload")
    request=json.loads(self.rfile.read(count))
    if self.path=="/validate":request={"prompt":"A blue cube on a plain background","width":512,"height":512,"steps":2,"seed":42}
    import uuid
    name=uuid.uuid4().hex+".png"
    result=engine.generate(request,output/name);result.update(model=args.alias,artifact=name)
    self.reply(200,result)
   except (ValueError,KeyError):self.reply(400,{"error":"Invalid generation settings"})
   except Exception:self.reply(503,{"error":"Generation failed"})
 ThreadingHTTPServer(("0.0.0.0",8080),Handler).serve_forever()
if __name__=="__main__":main()
