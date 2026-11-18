"""Typed settings and explicit, revision-scoped provenance."""
import re
LLM={"context":100000,"output_tokens":4096,"cache_k":"q4_0","cache_v":"q4_0","flash_attention":True,"threads":8,"gpu_layers":-1,"cpu_ffn":0,"speculation":"none","draft_count":0,"parallel":1,"batch":512,"ubatch":128,"continuous_batching":True,"reasoning":"off","jinja":True,"projector":None,"projector_gpu":False,"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":0.0,"repeat_penalty":1.0,"repeat_last_n":256}
IMAGE={"width":1024,"height":1024,"steps":30,"guidance":7.0,"scheduler":"euler","precision":"float16","seed":0,"strength":1.0,"base_model":None}
RANGES={"output_tokens":(128,4096),"context":(512,1048576),"threads":(1,256),"gpu_layers":(-1,999),"cpu_ffn":(0,999),"draft_count":(0,32),"parallel":(1,16),"batch":(1,8192),"ubatch":(1,8192),"temperature":(0,5),"top_p":(0,1),"top_k":(0,1000),"min_p":(0,1),"presence_penalty":(-2,2),"repeat_penalty":(0,3),"repeat_last_n":(-1,1048576),"width":(256,2048),"height":(256,2048),"steps":(1,100),"guidance":(0,30),"seed":(0,2**32-1),"strength":(0,2)}
ENUMS={"cache_k":["q4_0","q8_0","f16"],"cache_v":["q4_0","q8_0","f16"],"speculation":["none","draft-mtp"],"reasoning":["off","on"],"scheduler":["euler","dpm"],"precision":["float16","bfloat16","float32"]}
def validate(values,kind,capabilities=None,max_context=None):
    baseline=LLM if kind=="gguf" else IMAGE
    for k,v in values.items():
        if k not in baseline: raise ValueError("Unknown setting: "+k)
        default=baseline[k]
        if isinstance(default,bool) and not isinstance(v,bool): raise ValueError("Boolean required: "+k)
        if k in RANGES:
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not RANGES[k][0]<=v<=RANGES[k][1]: raise ValueError("Out of range: "+k)
            if isinstance(default,int) and not isinstance(v,int): raise ValueError("Integer required: "+k)
        if k in ENUMS and v not in ENUMS[k]: raise ValueError("Unsupported choice: "+k)
    if kind=="gguf":
        if max_context and values.get("context",0)>max_context: raise ValueError("Documented context exceeded")
        if values.get("output_tokens",128)>values.get("context",100000):raise ValueError("Output exceeds context budget")
        if values.get("ubatch",1)>values.get("batch",512): raise ValueError("ubatch exceeds batch")
        if values.get("speculation","none")!="none" and not (capabilities or {}).get("mtp"): raise ValueError("MTP capability not verified")
        if values.get("projector") and not (capabilities or {}).get("vision"): raise ValueError("Vision capability not verified")
    else:
        if any(values.get(k,256)%8 for k in ("width","height")): raise ValueError("Dimensions must be multiples of eight")
    return values
def propose(metadata,overrides=None,swift=False,safe_only=False):
    kind=metadata["kind"]; baseline=dict(LLM if kind=="gguf" else IMAGE)
    if kind!="gguf": baseline["base_model"]=metadata.get("base_model")
    if swift: baseline.update(speculation="draft-mtp",draft_count=4)
    source={k:{"type":"Safe baseline","evidence":"User-confirmed 100K/4096; capability checks still apply" if kind=="gguf" else "SDXL baseline; actual generation validation is separate"} for k in baseline}
    docs=metadata.get("documents",{}); cfg=docs.get("config.json",{}); gen=docs.get("generation_config.json",{})
    maximum=cfg.get("max_position_embeddings") if isinstance(cfg,dict) else None
    if isinstance(maximum,int) and "context" in baseline and maximum<baseline["context"]:
        baseline["context"]=maximum; source["context"]={"type":"Published recommendation","evidence":"config.json:max_position_embeddings (limit)","revision":metadata["revision"]}
    if kind=="gguf":baseline["output_tokens"]=min(baseline["output_tokens"],baseline["context"]//2)
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
    for k,v in (overrides or {}).items():
        if k not in baseline: raise ValueError("Unknown override")
        baseline[k]=v; source[k]={"type":"Your override","revision":metadata["revision"]}
    return {"values":baseline,"options":{k:([True,False] if isinstance(value,bool) else ENUMS[k] if k in ENUMS else sorted(set([value]+([4096,8192,32768,65536,100000] if k=="context" else [RANGES[k][0],RANGES[k][1]])))) for k,value in baseline.items() if isinstance(value,bool) or k in ENUMS or k in RANGES},"sources":source,"max_context":maximum,"presets":presets,"uncertainty":"Conflicting published modes require explicit selection." if any(len({p["fields"][k]["value"] for p in presets if k in p["fields"]})>1 for k in baseline) else None}

def validate_negative_prompt(value):
 if not isinstance(value,str) or len(value)>4096:raise ValueError("Negative prompt must be a string of at most 4096 characters")
 return value
