"""Short-lived fixed CPU jobs; controller has Jobs authority, workers have no API credential."""
import json, os, pathlib, re, ssl, time, urllib.request, urllib.error

def job_spec(jobid,argv,timeout,host_output,image,input_file=None,task='3d-generate',input_container=None,input_directory=False,host_assets=None,host_engine=None,host_catalog=None):
    if not re.fullmatch('[a-f0-9]{16}',jobid) or not re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}',image): raise ValueError('unverified worker identity/image')
    dungeon=task=='3d-creative' and len(argv)>=4 and argv[:3]==['python3','-B','/opt/watoom/dungeon_worker.py']
    engine=task=='3d-inspect' and len(argv)==4 and argv[:3]==['python3','-B','/opt/watoom/engine_validate_worker.py']
    native=dungeon or engine
    if not 1<=timeout<=(840 if dungeon else 420 if engine else 180) or not pathlib.Path(host_output).is_absolute():raise ValueError('invalid worker bounds')
    if task.startswith('3d-'):
        request=json.loads(argv[-1]);request['output']='/job/artifacts'
        if input_file:request['input']='/input/asset'+pathlib.Path(input_file).suffix.lower()
        command=argv[:-1]+[json.dumps(request,separators=(',',':'))]
        input_container=request.get('input')
    else:command=argv
    mounts=[{'name':'job','mountPath':'/job'},{'name':'tmp','mountPath':'/tmp'},{'name':'home','mountPath':'/home/toolkit'}]
    volumes=[{'name':'job','hostPath':{'path':host_output,'type':'Directory'}},{'name':'tmp','emptyDir':{'sizeLimit':'256Mi'}},{'name':'home','emptyDir':{'sizeLimit':'64Mi'}}]
    if host_assets is not None or task=='3d-creative':
        if host_assets!='/data/ai/assets':raise ValueError('Authoritative read-only asset root required')
        mounts.append({'name':'asset-library','mountPath':'/assets','readOnly':True})
        volumes.append({'name':'asset-library','hostPath':{'path':host_assets,'type':'Directory'}})
    if native:
        if not host_engine or not pathlib.Path(host_engine).is_absolute():raise ValueError('Validated native engine mount required')
        native_mounts=[('unreal-engine',host_engine,'/unreal-engine')]
        if dungeon:
            if not request.get('dungeon') or not host_catalog or not pathlib.Path(host_catalog).is_absolute():raise ValueError('Native dungeon and existing Catalog required')
            native_mounts.append(('catalog',host_catalog,'/catalog.json'))
        for name,host,target in native_mounts:
            mounts.append({'name':name,'mountPath':target,'readOnly':True})
            volumes.append({'name':name,'hostPath':{'path':host,'type':'File' if name=='catalog' else 'Directory'}})
    if input_file:
        mounts.append({'name':'input','mountPath':input_container,'readOnly':task!='godot-import'})
        volumes.append({'name':'input','hostPath':{'path':input_file,'type':'Directory' if input_directory else 'File'}})
    return {'apiVersion':'batch/v1','kind':'Job','metadata':{'name':'watoom-3d-'+jobid,'labels':{'app':'watoom-toolkit-worker','watoom-job':jobid}},
      'spec':{'backoffLimit':0,'activeDeadlineSeconds':timeout,'ttlSecondsAfterFinished':60,'template':{'metadata':{'labels':{'app':'watoom-toolkit-worker','watoom-job':jobid}},'spec':{
        'restartPolicy':'Never','automountServiceAccountToken':False,'enableServiceLinks':False,
        'securityContext':{'runAsUser':1000 if task=='godot-import' else 1009 if native else 1010,'runAsGroup':1000 if task=='godot-import' else 1009,'runAsNonRoot':True,'fsGroup':1009},
        'containers':[{'name':'worker','image':image,'imagePullPolicy':'IfNotPresent','command':command,
          'env':[{'name':'HOME','value':'/home/toolkit'},{'name':'PYTHONDONTWRITEBYTECODE','value':'1'}],
          'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']},'seccompProfile':{'type':'RuntimeDefault'}},
          'resources':{'requests':{'cpu':'1' if native else '100m','memory':'6Gi' if dungeon else '3Gi' if engine else '256Mi'},'limits':{'cpu':'2' if native else '1','memory':'6Gi' if dungeon else '3Gi' if engine else '2Gi','ephemeral-storage':'512Mi'}},'volumeMounts':mounts}], 'volumes':volumes}}}}

def api(method,path,body=None,raw=False,missing_ok=False):
    directory=pathlib.Path('/var/run/secrets/kubernetes.io/serviceaccount')
    token=(directory/'token').read_text().strip()
    context=ssl.create_default_context(cafile=str(directory/'ca.crt'))
    host=os.environ.get('KUBERNETES_SERVICE_HOST','kubernetes.default.svc');port=os.environ.get('KUBERNETES_SERVICE_PORT_HTTPS','443')
    request=urllib.request.Request('https://'+host+':'+port+path,data=json.dumps(body).encode() if body is not None else None,
      method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,context=context,timeout=5) as response:
            content=response.read(65537)
            if len(content)>65536:raise ValueError('worker API response exceeds budget')
            return content.decode(errors='replace') if raw else json.loads(content)
    except urllib.error.HTTPError as error:
        if error.code==404 and (method=='DELETE' or missing_ok):return {}
        raise RuntimeError('worker Kubernetes API rejected '+method+' status '+str(error.code)) from None

def task_native(argv,payload):
    return (payload.get("task")=="3d-creative" and "dungeon" in payload and argv[:3]==["python3","-B","/opt/watoom/dungeon_worker.py"]) or (payload.get("task")=="3d-inspect" and argv[:3]==["python3","-B","/opt/watoom/engine_validate_worker.py"])

def execute(argv,timeout,root,state,workspace,payload):
    image=os.environ.get('WATOOM_WORKER_IMAGE','')
    host_state=pathlib.Path(os.environ.get('WATOOM_HOST_STATE',''))
    host_workspace=pathlib.Path(os.environ.get('WATOOM_HOST_WORKSPACE',''))
    namespace=os.environ.get('WATOOM_WORKER_NAMESPACE','opencode')
    if not image or not host_state.is_absolute() or not re.fullmatch('[a-z0-9-]+',namespace):raise ValueError('isolated 3D worker is not configured')
    if task_native(argv,payload):
        available=int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
        reserve=5 if payload.get('task')=='3d-inspect' else 8
        if available<reserve*1024**3:raise ValueError('Native worker memory plus2GiB host reserve unavailable')
    relative=root.relative_to(state)
    local=root/'worker';local.mkdir(mode=0o770)
    os.chmod(local,0o770)
    task=payload['task']
    request=json.loads(argv[-1]) if task.startswith('3d-') else {}
    if task.startswith('3d-') and request.get('expected_engine_sha256'):
        import three_d
        three_d.stage_registry_seed(local,request['expected_engine_sha256'])
    input_container=request.get('input')
    if not task.startswith('3d-') and task!='probe':
        input_container=str(workspace/payload['path'])
        if task=='ansible-syntax':input_container=str(pathlib.Path(input_container).parent)
    input_file=None
    if input_container and task!="3d-creative":
        source=pathlib.Path(input_container)
        published=pathlib.Path(os.environ.get('WATOOM_3D_PUBLISH','/generated'))
        if task.startswith('3d-') and source.is_relative_to(published):
            host_published=pathlib.Path(os.environ.get('WATOOM_HOST_PUBLISH',''))
            if not host_published.is_absolute():raise ValueError('published worker input root is not configured')
            input_file=str(host_published/source.relative_to(published))
        elif source.is_relative_to(pathlib.Path('/data/ai/projects/llm/pipelines')):
            input_file=str(source)
        else:input_file=str(host_workspace/source.relative_to(workspace))
    command=argv if task.startswith('3d-') else [str(arg).replace(str(root)+'/','/job/') for arg in argv]
    specification=job_spec(root.name,command,timeout,str(host_state/relative/'worker'),image,input_file,task,input_container,task in ('godot-import','ansible-syntax'),os.environ.get('WATOOM_HOST_ASSETS','/data/ai/assets'),os.environ.get('WATOOM_HOST_UNREAL_ENGINE'),str(host_state/'asset-catalog/catalog.json'))
    prefix='/apis/batch/v1/namespaces/'+namespace+'/jobs'
    name=specification['metadata']['name'];created=False;started=time.monotonic()
    operation=payload.get('operation_id')
    def cancelled():
        return (root/'cancel.requested').exists() or (isinstance(operation,str) and re.fullmatch('[a-f0-9]{64}',operation) and (state/'jobs'/('.cancel-'+operation)).exists())
    try:
        if cancelled():return {'status':'CANCELLED','exit_code':None,'seconds':0,'output':'cancelled before worker launch'}
        result=api('POST',prefix,specification);created=True
        if result.get('metadata',{}).get('name')!=name:raise ValueError('worker creation identity mismatch')
        while time.monotonic()-started<timeout+15:
            if cancelled():return {'status':'CANCELLED','exit_code':None,'seconds':round(time.monotonic()-started,2),'output':'worker cancellation requested'}
            status=api('GET',prefix+'/'+name).get('status',{})
            complete=status.get('succeeded',0)==1
            failed=status.get('failed',0)>0 or any(c.get('type')=='Failed' and c.get('status')=='True' for c in status.get('conditions',[]))
            if complete or failed:
                pods=api('GET','/api/v1/namespaces/'+namespace+'/pods?labelSelector=watoom-job%3D'+root.name).get('items',[])
                logs=''
                if len(pods)==1:
                    if not any(owner.get('uid')==result['metadata']['uid'] for owner in pods[0]['metadata'].get('ownerReferences',[])):raise ValueError('worker owner identity mismatch')
                    pod=pods[0]['metadata']['name']
                    logs=api('GET','/api/v1/namespaces/'+namespace+'/pods/'+pod+'/log?container=worker&limitBytes=12000',raw=True)
                    if pods[0]['spec'].get('automountServiceAccountToken') is not False:raise ValueError('worker credential boundary changed')
                else:raise ValueError('worker pod identity ambiguous')
                return {'status':'PASS' if complete else 'FAIL','exit_code':0 if complete else 1,'seconds':round(time.monotonic()-started,2),'output':logs,'worker':{'name':name,'uid':result['metadata']['uid'],'identity':pods[0]['spec']['securityContext']['runAsUser'],'gpu':0,'service_account_token':False,'image_id':pods[0].get('status',{}).get('containerStatuses',[{}])[0].get('imageID')}}
            time.sleep(0.5)
        return {'status':'TIMEOUT','exit_code':None,'seconds':round(time.monotonic()-started,2),'output':'bounded CPU worker exceeded deadline'}
    finally:
        if created:api('DELETE',prefix+'/'+name,{'propagationPolicy':'Foreground'})

def cancel(jobid):
    if not re.fullmatch('[a-f0-9]{16}',jobid):raise ValueError('invalid worker job identity')
    namespace=os.environ.get('WATOOM_WORKER_NAMESPACE','opencode')
    return api('DELETE','/apis/batch/v1/namespaces/'+namespace+'/jobs/watoom-3d-'+jobid,{'propagationPolicy':'Foreground'})

def worker_stopped(jobid,seconds=0):
    """Observe the exact owned Job and Pods gone; deletion acceptance alone is insufficient."""
    if not re.fullmatch('[a-f0-9]{16}',jobid):raise ValueError('invalid worker identity')
    namespace=os.environ.get('WATOOM_WORKER_NAMESPACE','opencode')
    if not re.fullmatch('[a-z0-9-]+',namespace):raise ValueError('invalid worker namespace')
    deadline=time.monotonic()+seconds
    while True:
        job=api('GET','/apis/batch/v1/namespaces/'+namespace+'/jobs/watoom-3d-'+jobid,missing_ok=True)
        pods=api('GET','/api/v1/namespaces/'+namespace+'/pods?labelSelector=watoom-job%3D'+jobid).get('items',[])
        if not job and not pods:return True
        if time.monotonic()>=deadline:return False
        time.sleep(.5)
