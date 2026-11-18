"""Fixed-origin Hugging Face metadata inspection. Repository text is data."""
import json, re, urllib.request, urllib.parse
ORIGIN="https://huggingface.co"
class MetadataError(ValueError): pass
def parse_url(value):
    u=urllib.parse.urlsplit(value)
    if u.scheme!="https" or u.hostname!="huggingface.co" or u.username or u.password or u.port not in (None,443):
        raise MetadataError("Only HTTPS huggingface.co repository URLs are supported")
    parts=[urllib.parse.unquote(x) for x in u.path.strip("/").split("/")]
    if len(parts)<2 or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*",x) or x in (".","..") for x in parts[:2]):
        raise MetadataError("Invalid repository")
    revision="main"; selected=None
    if len(parts)>2:
        if parts[2] not in ("tree","blob","resolve") or len(parts)<4: raise MetadataError("Unsupported link")
        revision=parts[3]
        selected="/".join(parts[4:]) or None
    for i,x in enumerate(parts):
        segments=x.split("/") if i==3 and len(parts)>3 else [x]
        if any(part in ("",".","..") for part in segments) or "\\" in x or "%" in x or ("/" in x and i!=3): raise MetadataError("Unsafe path")
    return "/".join(parts[:2]),revision,selected
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
class Hub:
    def __init__(self,token=None):
        self.token=token; self.open=urllib.request.build_opener(NoRedirect)
    def get(self,path,text=False):
        if not path.startswith("/") or path.startswith("//"): raise MetadataError("Invalid API path")
        headers={"User-Agent":"WatooM-model-manager/1"}
        if self.token: headers["Authorization"]="Bearer "+self.token
        try:
            with self.open.open(urllib.request.Request(ORIGIN+path,headers=headers),timeout=30) as res:
                raw=res.read(8*1024*1024+1)
                if len(raw)>8*1024*1024: raise MetadataError("Metadata exceeds bound")
                return (raw.decode("utf-8"),dict(res.headers)) if text else (json.loads(raw),dict(res.headers))
        except urllib.error.HTTPError as e:
            raise MetadataError("Hub metadata HTTP "+str(e.code)) from None
    def inspect(self,url):
        repo,rev,selected=parse_url(url); q=lambda s:urllib.parse.quote(s,safe="")
        meta,_=self.get("/api/models/"+repo+"/revision/"+q(rev))
        sha=meta.get("sha","")
        if not re.fullmatch("[0-9a-f]{40}",sha): raise MetadataError("Missing immutable commit")
        refs,_=self.get("/api/models/"+repo+"/refs")
        path="/api/models/"+repo+"/tree/"+sha+"?recursive=true&expand=true"; files=[]
        for page in range(100):
            data,headers=self.get(path)
            for f in data:
                if f.get("type")!="file": continue
                name=f["path"]
                if name.startswith("/") or any(x in ("",".","..") for x in name.split("/")) or "\\" in name: raise MetadataError("Unsafe remote file")
                lfs=f.get("lfs") or {}
                files.append({"path":name,"size":lfs.get("size",f.get("size")),"sha256":lfs.get("oid"),"git_oid":f.get("oid")})
            link=headers.get("Link",headers.get("link",""))
            match=re.search(r'<([^>]+)>;\s*rel="next"',link)
            if not match: break
            nxt=urllib.parse.urlsplit(match[1])
            if nxt.scheme!="https" or nxt.netloc!="huggingface.co" or not nxt.path.startswith("/api/models/"+repo+"/tree/"+sha): raise MetadataError("Unsafe pagination")
            path=nxt.path+("?"+nxt.query if nxt.query else "")
        else: raise MetadataError("File tree exceeds pagination bound")
        docs={}
        names={f["path"] for f in files}
        for name in ("README.md","config.json","generation_config.json","model_index.json","adapter_config.json"):
            if name in names:
                try:
                    raw,_=self.get("/"+repo+"/raw/"+sha+"/"+name,text=True)
                    docs[name]=raw if name.endswith(".md") else json.loads(raw)
                except (MetadataError,ValueError): docs[name]={"unavailable":True}
        card=meta.get("cardData") or {}; tags=meta.get("tags") or []
        base=card.get("base_model")
        if isinstance(base,list): base=base[0] if len(base)==1 else base
        lora="lora" in tags or card.get("base_model_relation")=="adapter" or "adapter_config.json" in names
        kind="lora" if lora else "diffusion-pipeline" if "model_index.json" in names else "gguf" if any(n.lower().endswith(".gguf") for n in names) else "diffusion-checkpoint" if meta.get("pipeline_tag")=="text-to-image" or ("sdxl" in tags and any(n.lower().endswith(".safetensors") for n in names)) else "unsupported"
        variants=[]; grouped={}
        for f in files:
            n=f["path"]; lower=n.lower()
            eligible=(kind=="gguf" and lower.endswith(".gguf") and "mmproj" not in lower) or (kind in ("lora","diffusion-checkpoint") and lower.endswith(".safetensors"))
            if not eligible: continue
            m=re.search(r"-(\d{5})-of-(\d{5})\.gguf$",n,re.I)
            key=re.sub(r"-\d{5}-of-\d{5}\.gguf$",".gguf",n,flags=re.I) if m else n
            grouped.setdefault(key,[]).append(f)
        for key,items in grouped.items():
            items.sort(key=lambda item:item["path"])
            parts=[re.search(r"-(\d{5})-of-(\d{5})\.gguf$",x["path"],re.I) for x in items]
            if parts[0]:
                total=int(parts[0].group(2))
                if sorted(int(m.group(1)) for m in parts)!=list(range(1,total+1)): continue
            quant=re.search(r"(?:^|[-_.])(IQ\d[^./-]*|Q\d[^./-]*|BF16|F16|F32)(?:[-_.]|$)",key,re.I) if kind=="gguf" else None
            variants.append({"id":key,"files":items,"bytes":sum(x["size"] for x in items) if all(isinstance(x["size"],int) for x in items) else None,"precision":quant.group(1) if quant else None})
        if kind=="diffusion-pipeline":
            index=docs.get("model_index.json",{})
            components={k for k,v in index.items() if not k.startswith("_") and isinstance(v,list) and len(v)==2 and all(v)}
            for precision in ("default","fp16"):
                items=[f for f in files if f["path"]=="model_index.json"];complete=True
                for component in sorted(components):
                    entries=[f for f in files if f["path"].startswith(component+"/") and "/" not in f["path"][len(component)+1:]]
                    weights=[f for f in entries if f["path"].endswith(".safetensors") and ((".fp16." in f["path"])==(precision=="fp16"))]
                    has_weights=any(f["path"].endswith((".safetensors",".bin")) for f in entries)
                    if has_weights and not weights:complete=False;break
                    auxiliary=[f for f in entries if f["path"].endswith((".json",".txt",".model")) and (not f["path"].endswith(".index.json") or (".fp16." in f["path"])==(precision=="fp16"))]
                    items.extend(weights+auxiliary)
                if not complete or not components or not any(f["path"].endswith(".safetensors") for f in items):continue
                variants.append({"id":precision,"precision":"float16" if precision=="fp16" else None,"files":items,"bytes":sum(x["size"] for x in items) if all(isinstance(x["size"],int) for x in items) else None})
        return {"repository":repo,"revision":sha,"refs":refs,"kind":kind,"base_model":base,"variants":variants,"files":files,"documents":docs,"gated":meta.get("gated",False),"license":card.get("license"),"source":ORIGIN+"/"+repo+"/tree/"+sha}
