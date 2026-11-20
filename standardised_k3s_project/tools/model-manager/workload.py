"""Fixed owned workloads at replicas zero; no replica writer in this module."""
import re
from pathlib import Path
from settings import validate
from download import safe_path
LLAMA_IMAGE="ghcr.io/ggml-org/llama.cpp@sha256:150b59966fb5b2cb1a8fa9d226267c56ebd22c520c7b3640331cde87f3c4fb01"
def build(record,artifacts,images,namespace="llama-cpp"):
 identity=record["id"]
 if not re.fullmatch("[a-f0-9]{64}",identity):raise ValueError("Invalid managed identity")
 name="llama-cpp-mm-"+identity[:16];alias="mm-"+identity[:16];kind=record["kind"];settings=record["settings"]
 validate(settings,kind,capabilities=record.get("capabilities"),max_context=record.get("max_context"))
 labels={"app":name,"watoom.io/model-manager":"owned","watoom.io/model-id":identity[:32]}
 auth=images.get("backend_auth_file")
 if auth!="/data/ai/private/model-manager/backend-key":raise ValueError("Managed backend authentication file required")
 volumes=[{"name":"backend-auth","hostPath":{"path":auth,"type":"File"}}]
 mounts=[{"name":"backend-auth","mountPath":"/private/backend-key","readOnly":True}]
 for index,artifact in enumerate(artifacts):
  if kind=="diffusion-pipeline" or (kind in ("lora","diffusion-checkpoint") and index>0):continue
  path=Path(artifact["path"])
  if not path.is_absolute() or not str(path).startswith("/data/ai/models/"):raise ValueError("Model mount outside managed model root")
  vol="artifact-"+str(index)
  volumes.append({"name":vol,"hostPath":{"path":str(path),"type":"File"}})
  mounts.append({"name":vol,"mountPath":"/models/"+path.name,"readOnly":True})
 if kind in ("gguf","gguf-lora"):
  image=images.get("gguf",LLAMA_IMAGE)
  projector=settings.get("projector")
  projector_mount="/models/"+Path(artifacts[-1]["path"]).name if projector else None
  if projector and Path(artifacts[-1]["path"]).name!=Path(projector).name:raise ValueError("Projector must be the last artifact")
  models=[m["mountPath"] for m in mounts if m["mountPath"].endswith(".gguf") and m["mountPath"]!=projector_mount]
  # gguf-lora artifacts are [adapter, base...]: the base is served and the adapter applied with --lora.
  if kind=="gguf-lora" and len(models)<2:raise ValueError("GGUF LoRA needs the adapter and its base model")
  if not models:raise ValueError("GGUF model absent")
  args=["--host","0.0.0.0","--port","8080","--api-key-file","/private/backend-key","--metrics","--alias",alias,"--model",models[1 if kind=="gguf-lora" else 0]]
  if kind=="gguf-lora":args.extend(("--lora",models[0]))
  flags={"context":"--ctx-size","threads":"--threads","gpu_layers":"--gpu-layers","cache_k":"--cache-type-k","cache_v":"--cache-type-v","parallel":"--parallel","batch":"--batch-size","ubatch":"--ubatch-size","cpu_ffn":"--n-cpu-ffn","reasoning":"--reasoning","temperature":"--temp","top_p":"--top-p","top_k":"--top-k","min_p":"--min-p","presence_penalty":"--presence-penalty","repeat_penalty":"--repeat-penalty","repeat_last_n":"--repeat-last-n"}
  for k,flag in flags.items():
   if k in settings:args.extend((flag,str(settings[k])))
  args.extend(("--flash-attn","on" if settings.get("flash_attention",True) else "off"))
  if settings.get("jinja",True):args.append("--jinja")
  if projector:
   # Proven at install from both GGUF headers (mmproj vision encoder, projection_dim == embedding_length).
   if not (record.get("capabilities") or {}).get("vision"):raise ValueError("Vision projector not proven")
   args.extend(("--mmproj",projector_mount,"--image-max-tokens","1024"))
   if not settings.get("projector_gpu"):args.append("--no-mmproj-offload")
  speculation=settings.get("speculation","none")
  if speculation=="draft-mtp":
   # Proven at install from the GGUF header (<arch>.nextn_predict_layers > 0), never from a file name.
   if not (record.get("capabilities") or {}).get("mtp"):raise ValueError("MTP head not proven in the GGUF header")
   args.extend(("--spec-type","draft-mtp","--spec-draft-n-max",str(settings["draft_count"])))
  elif speculation!="none":raise ValueError("Unsupported speculation")
  else:args.extend(("--spec-type","none"))
  command=["/app/llama-server"]
 else:
  image=images.get("sdxl")
  if not image:raise ValueError("Validated SDXL image digest is required")
  # Full directory mounts are derived only from a verified immutable base install.
  base=record.get("base_path")
  root=Path("/data/ai/models/diffusion/model-manager")
  if not base or not Path(base).is_relative_to(root):raise ValueError("Verified diffusion base directory required")
  safe_path(root,str(Path(base).relative_to(root)))
  volumes.append({"name":"base","hostPath":{"path":base,"type":"Directory"}});mounts.append({"name":"base","mountPath":"/base","readOnly":True})
  volumes.append({"name":"output","emptyDir":{}});mounts.append({"name":"output","mountPath":"/output"})
  runtime=images.get("sdxl_runtime")
  if not isinstance(runtime,dict) or runtime.get("format")!="read-only-conda-v1":raise ValueError("Publish immutable SDXL runtime on /data before enrollment")
  root=Path("/data/ai/toolchains/model-manager-sdxl");payload=Path(runtime["path"])
  if not payload.is_relative_to(root):raise ValueError("Runtime outside managed toolchain")
  safe_path(root,str(payload.relative_to(root)))
  volumes.append({"name":"sdxl-runtime","hostPath":{"path":str(payload),"type":"Directory"}})
  mounts.append({"name":"sdxl-runtime","mountPath":"/app/runtime","readOnly":True})
  command=["/app/runtime/bin/python","/app/model-manager/sdxl_backend.py"]
  args=["--base","/base","--alias",alias,"--output","/output","--precision",settings.get("precision","float16"),"--key-file","/private/backend-key"]
  if kind in ("lora","diffusion-checkpoint"):
   adapter=next((m["mountPath"] for m in mounts if m["mountPath"].endswith(".safetensors")),None)
   if not adapter:raise ValueError("Adapter missing")
   args.extend(("--adapter" if kind=="lora" else "--checkpoint",adapter))
 if not re.fullmatch(r"[A-Za-z0-9_./:-]+@sha256:[a-f0-9]{64}",image):raise ValueError("Digest-pinned backend image required")
 container={"name":"model","image":image,"command":command,"args":args,"ports":[{"containerPort":8080}],"volumeMounts":mounts,"resources":{"requests":{"cpu":"1","memory":"1Gi","ephemeral-storage":"64Mi","nvidia.com/gpu":1},"limits":{"cpu":"8","memory":"16Gi","ephemeral-storage":"1Gi","nvidia.com/gpu":1}},"securityContext":{"allowPrivilegeEscalation":False,"capabilities":{"drop":["ALL"]},"runAsUser":1009,"runAsGroup":1009},"readinessProbe":{"httpGet":{"path":"/health","port":8080},"periodSeconds":5},"startupProbe":{"httpGet":{"path":"/health","port":8080},"periodSeconds":10,"failureThreshold":120},"env":[{"name":"LD_LIBRARY_PATH","value":"/app/runtime/lib:/usr/local/nvidia/lib:/usr/local/nvidia/lib64"},{"name":"HF_HUB_OFFLINE","value":"1"},{"name":"TRANSFORMERS_OFFLINE","value":"1"},{"name":"HF_HOME","value":"/tmp/huggingface"},{"name":"HOME","value":"/tmp"},{"name":"XDG_CACHE_HOME","value":"/tmp/.cache"},{"name":"GGML_CUDA_DISABLE_GRAPHS","value":"1"},{"name":"LLAMA_ARG_CONT_BATCHING","value":"true" if settings.get("continuous_batching",True) else "false"}]}
 deployment={"apiVersion":"apps/v1","kind":"Deployment","metadata":{"name":name,"namespace":namespace,"labels":labels,"annotations":{"watoom.io/model-id":identity}},"spec":{"replicas":0,"selector":{"matchLabels":{"app":name}},"template":{"metadata":{"labels":labels},"spec":{"runtimeClassName":"nvidia","automountServiceAccountToken":False,"securityContext":{"fsGroup":1009},"containers":[container],"volumes":volumes}}}}
 service={"apiVersion":"v1","kind":"Service","metadata":{"name":name,"namespace":namespace,"labels":labels,"annotations":{"watoom.io/model-id":identity}},"spec":{"selector":{"app":name},"ports":[{"port":8080,"targetPort":8080}]}}
 return deployment,service,alias
