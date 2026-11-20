"""Bounded, immutable downloads; credentials never accompany CDN redirects."""
import os,json,hashlib,shutil,urllib.request,urllib.parse,urllib.error
from pathlib import Path
class DownloadError(ValueError): pass
def safe_path(root,name):
    root=Path(root).absolute()
    if any(parent.is_symlink() for parent in [root,*root.parents]):raise DownloadError("Symlink storage root")
    root=root.resolve()
    if not name or name.startswith("/") or "\\" in name or any(x in ("",".","..") for x in name.split("/")): raise DownloadError("Unsafe artifact path")
    dest=root/name
    current=root
    for part in name.split("/"):
        current=current/part
        if current.is_symlink(): raise DownloadError("Symlink artifact path")
    if not dest.resolve().is_relative_to(root): raise DownloadError("Artifact escapes storage")
    return dest
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urllib.parse.urlsplit(newurl); host=u.hostname or ""
        if u.scheme!="https" or u.username or u.password or u.port not in (None,443) or not (host=="huggingface.co" or host.endswith(".huggingface.co") or host.endswith(".hf.co") or host.endswith(".xethub.hf.co")):
            raise DownloadError("Unapproved download redirect")
        nxt=super().redirect_request(req,fp,code,msg,headers,newurl)
        if nxt and host!="huggingface.co":
            nxt.remove_header("Authorization")
            nxt.remove_header("authorization")
        return nxt
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()
def git_digest(path):
    h=hashlib.sha1()
    h.update(("blob "+str(Path(path).stat().st_size)+"\0").encode())
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def fetch(root,repo,revision,item,token=None,reserve=3*1024**3,progress=lambda n:None,cancel=lambda:False,opener=None):
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*",repo) or not re.fullmatch("[a-f0-9]{40}",revision): raise DownloadError("Immutable repository selection required")
    size=item.get("size"); remote=item.get("sha256"); git_oid=item.get("git_oid") if not remote else None
    if not isinstance(size,int) or size<0: raise DownloadError("Exact size required")
    if git_oid and not re.fullmatch("[a-f0-9]{40}",git_oid): raise DownloadError("Invalid Git blob digest")
    if remote and not re.fullmatch("[a-f0-9]{64}",remote): raise DownloadError("Invalid remote digest")
    dest=safe_path(root,item["path"]); dest.parent.mkdir(parents=True,exist_ok=True)
    partial=safe_path(root,item["path"]+".partial"); receipt=safe_path(root,item["path"]+".receipt.json")
    if dest.exists():
        local=digest(dest)
        if dest.stat().st_size==size and ((remote and local==remote) or (git_oid and git_digest(dest)==git_oid) or (not git_oid and receipt.exists() and json.loads(receipt.read_text()).get("sha256")==local)):
            return {"path":str(dest),"bytes":size,"sha256":local,"verification":"remote-sha256" if remote else "remote-git-blob-sha1" if git_oid else "local-only"}
        raise DownloadError("Existing artifact differs; refusing overwrite")
    offset=partial.stat().st_size if partial.exists() else 0
    if offset>size: raise DownloadError("Partial exceeds expected size")
    if shutil.disk_usage(dest.parent).free<size-offset+reserve: raise DownloadError("Disk reserve insufficient")
    headers={"User-Agent":"WatooM-model-manager/1","Accept-Encoding":"identity"}
    if token: headers["Authorization"]="Bearer "+token
    validator=safe_path(root,item["path"]+".partial-validator.json")
    if offset:
        headers["Range"]="bytes="+str(offset)+"-"
        if validator.exists():
            saved=json.loads(validator.read_text())
            if saved.get("revision")!=revision or saved.get("path")!=item["path"]:raise DownloadError("Partial belongs to another immutable selection")
            if saved.get("etag"):headers["If-Range"]=saved["etag"]
    url="https://huggingface.co/"+repo+"/resolve/"+revision+"/"+urllib.parse.quote(item["path"],safe="/")
    op=opener or urllib.request.build_opener(Redirect)
    try:
        response=op.open(urllib.request.Request(url,headers=headers),timeout=60)
    except urllib.error.HTTPError as e: raise DownloadError("Download HTTP "+str(e.code)) from None
    with response as res:
        if offset and res.status==206:
            expected="bytes "+str(offset)+"-"
            if not res.headers.get("Content-Range","").startswith(expected): raise DownloadError("Invalid resumed range")
        elif res.status==200: offset=0
        else: raise DownloadError("Unexpected download status")
        if offset and validator.exists():
            saved=json.loads(validator.read_text())
            if saved.get("etag") and res.headers.get("ETag")!=saved["etag"]:raise DownloadError("Remote validator changed; partial retained")
        validator.write_text(json.dumps({"revision":revision,"path":item["path"],"etag":res.headers.get("ETag")}))
        flags=os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|(os.O_APPEND if offset else os.O_TRUNC)
        with os.fdopen(os.open(partial,flags,0o600),"ab" if offset else "wb") as out:
            while True:
                if cancel():
                    partial.unlink(missing_ok=True); validator.unlink(missing_ok=True)
                    raise DownloadError("Cancelled; partial removed")
                data=res.read(1024*1024)
                if not data: break
                offset+=len(data)
                if offset>size: raise DownloadError("Download exceeds expected size")
                if shutil.disk_usage(dest.parent).free<reserve: raise DownloadError("Disk reserve reached")
                out.write(data); progress(offset)
            out.flush(); os.fsync(out.fileno())
    if offset!=size: raise DownloadError("Incomplete download; partial retained")
    local=digest(partial)
    if remote and local!=remote: raise DownloadError("SHA256 mismatch; partial retained")
    if git_oid and git_digest(partial)!=git_oid: raise DownloadError("Git blob SHA1 mismatch; partial retained")
    result={"repository":repo,"revision":revision,"path":str(dest),"bytes":size,"sha256":local,"verification":"remote-sha256" if remote else "remote-git-blob-sha1" if git_oid else "local-only","etag":response.headers.get("ETag")}
    # Hard link atomically refuses a destination created by a concurrent actor.
    os.link(partial,dest,follow_symlinks=False); partial.unlink();validator.unlink(missing_ok=True)
    temp=receipt.with_name(receipt.name+".tmp")
    temp.write_text(json.dumps(result,sort_keys=True)); os.replace(temp,receipt)
    return result
