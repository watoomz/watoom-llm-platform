"""Typed settings and explicit, revision-scoped provenance."""
import re
# Language-model kinds: a GGUF model, or a GGUF LoRA adapter served on an installed GGUF base (llama-server --lora).
LLM_KINDS=("gguf","gguf-lora")
LLM={"context":131072,"context_auto":True,"output_tokens":4096,"cache_k":"turbo5","cache_v":"turbo4","flash_attention":True,"threads":8,"gpu_layers":-1,"cpu_ffn":0,"speculation":"none","draft_count":0,"parallel":1,"batch":2048,"ubatch":1024,"continuous_batching":True,"reasoning":"off","reasoning_effort":"low","chat_template":"none","jinja":True,"projector":None,"projector_gpu":False,"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":0.0,"repeat_penalty":1.0,"repeat_last_n":256}
IMAGE={"width":1024,"height":1024,"steps":30,"guidance":7.0,"scheduler":"euler","precision":"float16","seed":0,"strength":1.0,"base_model":None}
RANGES={"output_tokens":(128,4096),"context":(512,1048576),"threads":(1,256),"gpu_layers":(-1,999),"cpu_ffn":(0,999),"draft_count":(0,32),"parallel":(1,16),"batch":(1,8192),"ubatch":(1,8192),"temperature":(0,5),"top_p":(0,1),"top_k":(0,1000),"min_p":(0,1),"presence_penalty":(-2,2),"repeat_penalty":(0,3),"repeat_last_n":(-1,1048576),"width":(256,2048),"height":(256,2048),"steps":(1,100),"guidance":(0,30),"seed":(0,2**32-1),"strength":(0,2)}
ENUMS={"cache_k":["turbo5","turbo4","q4_0","q8_0","f16"],"cache_v":["turbo5","turbo4","q4_0","q8_0","f16"],"speculation":["none","draft-mtp"],"reasoning":["off","on"],"reasoning_effort":["low","medium","xhigh"],"chat_template":["none","qwen38"],"scheduler":["euler","dpm"],"precision":["float16","bfloat16","float32"]}
# 2026-11-19 (owner): 128K is the default context and smaller models get more. With context_auto the context is raised
# after download to what fits on the GPU (fit_context), never above the model's own maximum and never below the chosen
# value. Owner cap 2026-11-19: a model may use at most 18 GiB of the GPU's 20 GiB; the reserve inside that cap
# covers compute buffers, the recurrent state of hybrid models and CUDA overhead.
GPU_VRAM_BYTES=18*1024**3
# Measured 2026-11-19 fully on GPU: Ornith 9B 256K = weights + KV + 0.4 GiB, Defiant 9B 256K = weights + KV - 0.0 GiB.
VRAM_RESERVE_BYTES=1*1024**3
# turbo5/turbo4 are the llamAmpere KV types Swift runs (owner-adopted 2026-11-03, lower KLD than q4_0). Their sizes
# are taken HIGH on purpose (6 and 5 bits/value) so context_auto can only under-fill the GPU, never overflow it.
CACHE_BYTES={"f16":2.0,"q8_0":34/32,"q4_0":18/32,"turbo5":6/8,"turbo4":5/8}
def kv_bytes_per_token(header,cache_k="f16",cache_v="f16"):
    """KV-cache bytes per context token. Only full-attention layers grow with context: a hybrid model (Qwen3.5/3.8:
    full_attention_interval) has block_count/interval of them, a sliding-window model (Gemma) the layers whose pattern
    entry is False; an MTP head adds its layers."""
    blocks=header.get("block_count");heads=header.get("head_count_kv") or header.get("head_count")
    if not blocks or not heads:return None
    head_dim=(header.get("embedding_length") or 0)//(header.get("head_count") or 1) or None
    key=header.get("key_length") or head_dim;value=header.get("value_length") or head_dim
    if not key or not value:return None
    pattern=header.get("sliding_window_pattern")
    if pattern:full=sum(1 for sliding in pattern if not sliding)
    elif header.get("full_attention_interval"):full=blocks//header["full_attention_interval"]
    else:full=blocks
    full+=header.get("nextn_predict_layers") or 0
    return full*heads*(key*CACHE_BYTES.get(cache_k,2.0)+value*CACHE_BYTES.get(cache_v,2.0))
def fits_on_gpu(header,weights_bytes,context,cache_k,cache_v):
    """True when weights plus the KV cache at `context` stay inside the cap; None when the shape is unknown."""
    per_token=kv_bytes_per_token(header,cache_k,cache_v)
    if not per_token:return None
    return weights_bytes+per_token*context<=GPU_VRAM_BYTES-VRAM_RESERVE_BYTES
def fit_context(header,weights_bytes,cache_k,cache_v,minimum=4096):
    """Largest context (multiple of 8192) whose KV cache fits beside the weights, capped at the model's maximum;
    None when the header does not describe the attention shape."""
    per_token=kv_bytes_per_token(header,cache_k,cache_v)
    if not per_token:return None
    budget=GPU_VRAM_BYTES-VRAM_RESERVE_BYTES-weights_bytes
    fit=int(budget//per_token)//8192*8192 if budget>0 else 0
    native=header.get("context_length") or 1048576
    return max(minimum,min(fit,native))
def validate(values,kind,capabilities=None,max_context=None):
    baseline=LLM if kind in LLM_KINDS else IMAGE
    for k,v in values.items():
        if k not in baseline: raise ValueError("Unknown setting: "+k)
        default=baseline[k]
        if isinstance(default,bool) and not isinstance(v,bool): raise ValueError("Boolean required: "+k)
        if k in RANGES:
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not RANGES[k][0]<=v<=RANGES[k][1]: raise ValueError("Out of range: "+k)
            if isinstance(default,int) and not isinstance(v,int): raise ValueError("Integer required: "+k)
        if k in ENUMS and v not in ENUMS[k]: raise ValueError("Unsupported choice: "+k)
    if kind in LLM_KINDS:
        if max_context and values.get("context",0)>max_context: raise ValueError("Documented context exceeded")
        if values.get("output_tokens",128)>values.get("context",100000):raise ValueError("Output exceeds context budget")
        if values.get("ubatch",1)>values.get("batch",512): raise ValueError("ubatch exceeds batch")
        if values.get("speculation","none")!="none":
            # The draft head must be in the file: proven from the GGUF header (<arch>.nextn_predict_layers > 0) after
            # download; before download only a published MTP variant is accepted as a provisional claim.
            if not (capabilities or {}).get("mtp"): raise ValueError("MTP capability not verified")
            if not 1<=values.get("draft_count",0)<=32: raise ValueError("MTP speculation needs a draft count of 1-32")
        if values.get("projector") is not None:
            # A published mmproj file of the same revision; proven from both GGUF headers after download.
            if not isinstance(values["projector"],str) or not values["projector"].lower().endswith(".gguf") or "mmproj" not in values["projector"].lower(): raise ValueError("Projector must be a published mmproj GGUF")
            if not (capabilities or {}).get("vision"): raise ValueError("Vision capability not verified")
    else:
        if any(values.get(k,256)%8 for k in ("width","height")): raise ValueError("Dimensions must be multiples of eight")
    return values
def propose(metadata,overrides=None,swift=False,safe_only=False):
    kind=metadata["kind"]; baseline=dict(LLM if kind in LLM_KINDS else IMAGE)
    if kind not in LLM_KINDS: baseline["base_model"]=metadata.get("base_model")
    if swift: baseline.update(speculation="draft-mtp",draft_count=4)
    source={k:{"type":"Safe baseline","evidence":"128K default (owner 2026-11-19); context_auto raises it after download to what fits on the GPU, up to the model maximum" if kind in LLM_KINDS else "SDXL baseline; actual generation validation is separate"} for k in baseline}
    docs=metadata.get("documents",{}); cfg=docs.get("config.json",{}); gen=docs.get("generation_config.json",{})
    maximum=cfg.get("max_position_embeddings") if isinstance(cfg,dict) else None
    if isinstance(maximum,int) and "context" in baseline and maximum<baseline["context"]:
        baseline["context"]=maximum; source["context"]={"type":"Published recommendation","evidence":"config.json:max_position_embeddings (limit)","revision":metadata["revision"]}
    if kind in LLM_KINDS:baseline["output_tokens"]=min(baseline["output_tokens"],baseline["context"]//2)
    for k in baseline:
        if not safe_only and isinstance(gen,dict) and k in gen:
            try: validate({k:gen[k]},kind,max_context=maximum)
            except ValueError: continue
            baseline[k]=gen[k]; source[k]={"type":"Published recommendation","evidence":"generation_config.json:"+k,"revision":metadata["revision"]}
    presets=[]; card=docs.get("README.md","")
    if isinstance(card,str) and not safe_only:
        modes={}; mode="Published"
        for line_number,line in enumerate(card.splitlines(),1):
            if line.startswith("#"):
                mode=line.lstrip("#").strip()[:100] or "Published"
            match=re.fullmatch(r"\s*([A-Za-z_]+)\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)\s*[,;]?\s*",line)
            if not match or match.group(1) not in baseline:continue
            key=match.group(1); raw=match.group(2)
            value=float(raw) if "." in raw else int(raw)
            try:validate({key:value},kind,max_context=maximum)
            except ValueError:continue
            modes.setdefault(mode,{})[key]={"value":value,"line":line_number,"excerpt":line[:200]}
        seen={}
        for mode,fields in modes.items():
            for key,entry in fields.items():seen.setdefault(key,set()).add(entry["value"])
            presets.append({"name":mode,"fields":fields,"source":metadata.get("source"),"revision":metadata["revision"]})
        for preset in presets:
            for key,entry in preset["fields"].items():
                if len(seen[key])==1 and key not in gen:
                    baseline[key]=entry["value"];source[key]={"type":"Published recommendation","evidence":"README.md:"+str(entry["line"]),"excerpt":entry["excerpt"],"revision":metadata["revision"]}
    # Owner 2026-11-19: models get vision when the repository publishes a projector (T-0095).
    if kind in LLM_KINDS and metadata.get("projectors"):
        baseline["projector"]=metadata["projectors"][0]["path"];baseline["projector_gpu"]=True
        source["projector"]={"type":"Published recommendation","evidence":"published vision projector "+metadata["projectors"][0]["path"],"revision":metadata["revision"]}
        source["projector_gpu"]={"type":"Safe baseline","evidence":"on the GPU when it fits the 18 GiB cap; moved to the CPU at install otherwise"}
    for k,v in (overrides or {}).items():
        if k not in baseline: raise ValueError("Unknown override")
        baseline[k]=v; source[k]={"type":"Your override","revision":metadata["revision"]}
    options_extra={"projector":[None]+[f["path"] for f in metadata.get("projectors") or []]} if kind in LLM_KINDS else {}
    return {"values":baseline,"options":{**options_extra,**{k:([True,False] if isinstance(value,bool) else ENUMS[k] if k in ENUMS else sorted(set([value]+([4096,8192,32768,65536,100000] if k=="context" else [RANGES[k][0],RANGES[k][1]])))) for k,value in baseline.items() if isinstance(value,bool) or k in ENUMS or k in RANGES}},"sources":source,"max_context":maximum,"presets":presets,"uncertainty":"Conflicting published modes require explicit selection." if any(len({p["fields"][k]["value"] for p in presets if k in p["fields"]})>1 for k in baseline) else None}

def validate_negative_prompt(value):
 if not isinstance(value,str) or len(value)>4096:raise ValueError("Negative prompt must be a string of at most 4096 characters")
 return value
