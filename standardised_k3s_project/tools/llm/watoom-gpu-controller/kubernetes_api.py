"""Restricted Kubernetes API transport for the WatooM actuator.

No deployment executable, no auto-discovery of secrets, and no live actions.
An authorized future controller may inject a bearer token and CA file.
The API is scoped to a fixed namespace and exact deployment allowlist.
"""
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

class APIError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status

class DeploymentAPI:
    def __init__(self, *, base_url, namespace, token, ca_file, allowed, timeout=15, opener=None):
        if not base_url.startswith('https://') or not namespace or not token or not ca_file:
            raise ValueError('HTTPS, namespace, bearer token and CA required')
        if not re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', namespace):
            raise ValueError('invalid namespace')
        self.allowed=frozenset(allowed)
        if not self.allowed or any(not re.fullmatch(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', n) for n in self.allowed):
            raise ValueError('invalid deployment allowlist')
        self.base_url=base_url.rstrip('/')
        self.namespace=namespace
        self.token=token
        self.ca_file=ca_file
        self.timeout=timeout
        self.opener=opener

    def _call(self, name, method, patch=None, resource="deployments"):
        if name not in self.allowed:
            raise APIError('deployment not in allowed set')
        if resource not in ("deployments","services") or (resource=="services" and (method!="GET" or patch is not None)):raise APIError("Unsupported resource operation")
        prefix="/apis/apps/v1" if resource=="deployments" else "/api/v1"
        path=prefix+'/namespaces/{}/{}/{}'.format(self.namespace,resource,name)
        url=self.base_url+path
        data=None if patch is None else json.dumps(patch, separators=(',',':')).encode('utf-8')
        req=urllib.request.Request(url, data=data, method=method)
        req.add_header('Authorization','Bearer '+self.token)
        req.add_header('Accept','application/json')
        if patch is not None: req.add_header('Content-Type','application/json-patch+json')
        try:
            if self.opener:
                response=self.opener(req,self.timeout)
            else:
                ctx=ssl.create_default_context(cafile=self.ca_file)
                response=urllib.request.urlopen(req, timeout=self.timeout, context=ctx)
            with response as r:
                raw=r.read(1024*1024+1)
                if len(raw)>1024*1024:raise APIError('oversized response')
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            # Do not expose response body: may contain sensitive details.
            raise APIError('Kubernetes API rejected request',exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # A network failure on PATCH does not establish whether it committed.
            raise APIError('Kubernetes API outcome unknown') from exc

    def get(self,name):
        return self._call(name,'GET')

    def get_service(self,name):
        return self._call(name,'GET',resource='services')

    def patch(self,name,ops):
        if not isinstance(ops,list) or not ops:
            raise ValueError('nonempty JSON Patch list required')
        paths={op.get('path') for op in ops if isinstance(op,dict)}
        if '/metadata/uid' not in paths or '/metadata/resourceVersion' not in paths:
            raise ValueError('missing UID or resourceVersion precondition')
        if any(not isinstance(op,dict) or op.get('op') not in ('test','add','replace') or op.get('path') not in
               ('/metadata/uid','/metadata/resourceVersion','/metadata/annotations','/spec/replicas') for op in ops):
            raise ValueError('unsupported JSON Patch operation')
        if not any(op.get('op')=='test' and op.get('path')=='/metadata/uid' for op in ops):
            raise ValueError('UID must be tested')
        if not any(op.get('op')=='test' and op.get('path')=='/metadata/resourceVersion' for op in ops):
            raise ValueError('resourceVersion must be tested')
        return self._call(name,'PATCH',ops)
