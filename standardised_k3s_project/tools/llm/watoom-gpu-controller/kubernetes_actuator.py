"""Offline-testable conditional Kubernetes actuator; no live CLI or kubeconfig.

All mutating methods require a caller-owned exclusive gateway lock. Adapter
users must provide KubernetesAPI.get/patch backed by a separately authorized
controller service. This module NEVER loads host credentials or performs
network requests on its own.
"""
import json
import os
from pathlib import Path
import uuid

class MutationUnsafe(RuntimeError): pass

FENCE = 'watoom.io/gpu-controller-intent'

class IntentJournal:
    def __init__(self, root):
        self.root=Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
    def _file(self, operation_id):
        return self.root / (operation_id+'.json')
    def write(self, data, exclusive=False):
        path=self._file(data['id'])
        tmp=self.root / ('.'+data['id']+'.'+uuid.uuid4().hex+'.tmp')
        with open(tmp, 'x', encoding='utf-8') as stream:
            json.dump(data,stream,sort_keys=True)
            stream.flush();os.fsync(stream.fileno())
        if exclusive and path.exists():
            tmp.unlink()
            raise MutationUnsafe('intent already exists')
        os.replace(tmp,path)
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    def pending(self):
        entries=[]
        for path in self.root.glob('*.json'):
            try:entries.append(json.loads(path.read_text()))
            except (ValueError,OSError) as exc:raise MutationUnsafe('unreadable intent record') from exc
        return [e for e in entries if e.get('status')=='pending']

class KubernetesActuator:
    """Namespace-qualified deployment client; all requests conditional.

    An optional deployment name mapping protects against mutating unexpected
    workloads. Set `allowed` explicitly in any future production adapter.
    """
    def __init__(self, api, journal, allowed=('qwen','mesh'), owner_generation=1):
        self.api=api
        self.journal=journal
        self.allowed=frozenset(allowed)
        self.generation=owner_generation
        self.unknown=False
    def _get(self,name):
        if name not in self.allowed:raise MutationUnsafe('unknown deployment')
        return self.api.get(name)
    def _patch(self,name,replicas):
        if self.unknown:raise MutationUnsafe('unknown mutation outcome; reconcile first')
        current=self._get(name)
        meta=current['metadata']
        operation={'id':uuid.uuid4().hex,'name':name,'uid':meta['uid'],
                   'version':meta['resourceVersion'],'replicas':replicas,
                   'generation':self.generation,'status':'pending'}
        self.journal.write(operation,exclusive=True)
        annotations=dict(meta.get('annotations') or {})
        annotations[FENCE]=operation['id']
        patch=[{'op':'test','path':'/metadata/uid','value':meta['uid']},
               {'op':'test','path':'/metadata/resourceVersion','value':meta['resourceVersion']},
               {'op':'add','path':'/metadata/annotations','value':annotations}]
        if replicas is not None:
            patch.append({'op':'replace','path':'/spec/replicas','value':replicas})
        try:
            result=self.api.patch(name,patch)
            good=(result['metadata']['uid']==meta['uid'] and
                  result['metadata']['resourceVersion']!=meta['resourceVersion'] and
                  result['metadata'].get('annotations',{}).get(FENCE)==operation['id'] and
                  (replicas is None or result['spec']['replicas']==replicas))
            if not good:raise MutationUnsafe('invalid acknowledgement')
            operation['status']='acknowledged'
            operation['ack_version']=result['metadata']['resourceVersion']
            self.journal.write(operation)
            return result
        except BaseException:
            self.unknown=True
            raise
    def scale(self,name,replicas,generation):
        if generation!=self.generation:raise MutationUnsafe('stale generation')
        if replicas not in (0,1):raise MutationUnsafe('unsupported replica count')
        return self._patch(name,replicas)
    def stopped(self,name):
        obj=self._get(name)
        return obj['spec'].get('replicas',0)==0 and obj.get('status',{}).get('replicas',0)==0
    def healthy(self,name):
        obj=self._get(name)
        return obj['spec'].get('replicas',0)==1 and obj.get('status',{}).get('readyReplicas',0)>=1
    def fence_and_reconcile(self,generation):
        if generation!=self.generation:raise MutationUnsafe('stale generation')
        pending=self.journal.pending()
        if any(e['generation']!=generation for e in pending):raise MutationUnsafe('unknown-owner pending intent')
        if not pending:
            self.unknown=False
            return True
        # The old operation and the barrier are both resourceVersion conditional.
        # No process-level lock can provide this guarantee to legacy writers.
        self.unknown=False
        for name in sorted({e['name'] for e in pending}):
            try:result=self._patch(name,None)
            except BaseException:
                self.unknown=True
                return False
            for operation in pending:
                if operation['name']!=name:continue
                if result['metadata']['uid']!=operation['uid']:
                    self.unknown=True;return False
                operation['status']='fenced'
                operation['fence_version']=result['metadata']['resourceVersion']
                self.journal.write(operation)
        return True
