"""Reference HTTP client; stdlib only, no automatic mutation retries.
Run as a script for authenticated read-only server identity, never a prompt.
"""
import base64,json,os,urllib.request,urllib.error,urllib.parse

class APIError(RuntimeError):
    def __init__(self,status):
        self.status=status
        super().__init__("WatooM HTTP status "+str(status)+"; reconcile state before retrying a mutation")

class NativeClient:
    def __init__(self,base_url,password,username="opencode",timeout=30):
        parsed=urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http","https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use an HTTP(S) base URL without embedded credentials/query/fragment")
        self.base_url=base_url.rstrip("/");self.timeout=timeout
        self.authorization="Basic "+base64.b64encode((username+":"+password).encode()).decode()
    def request(self,method,path,body=None):
        if not path.startswith("/api/"):raise ValueError("Expected native /api/ path")
        req=urllib.request.Request(self.base_url+path,method=method,
            headers={"Authorization":self.authorization,"Content-Type":"application/json","Accept":"application/json"},
            data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req,timeout=self.timeout) as response:
                raw=response.read();return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:raise APIError(exc.code) from None
    def info(self):return self.request("GET","/api/info")
    def sessions(self,limit=20,cursor=None):
        params={"limit":str(limit),"order":"desc"}
        if cursor is not None:params["cursor"]=cursor
        return self.request("GET","/api/session?"+urllib.parse.urlencode(params))
    def create_session(self,directory,title,agent="watoom-workflow",session_id=None):
        body={"location":{"directory":directory},"title":title,"agent":agent,
              "model":{"providerID":"watoom","id":"swift-qwen38-coder"}}
        if session_id is not None:body["id"]=session_id
        return self.request("POST","/api/session",body)
    def prompt(self,session_id,text,message_id=None,resume=True):
        body={"text":text,"resume":resume}
        if message_id is not None:body["id"]=message_id
        safe=urllib.parse.quote(session_id,safe="")
        return self.request("POST","/api/session/"+safe+"/prompt",body)

if __name__=="__main__":
    client=NativeClient(os.environ["WATOOM_BASE_URL"],os.environ["WATOOM_PASSWORD"])
    info=client.info();print(json.dumps({"version":info.get("version"),"reachable":True}))
