"""Privileged issuer is separate from the controller; never print a token."""
import json,os,subprocess
from pathlib import Path
from g3h_service import atomic
root=Path('/data/ai/helper-scripts/state/gpu-controller-credentials')
root.mkdir(mode=0o700,parents=True,exist_ok=True)
token=subprocess.check_output(['kubectl','-n','llama-cpp','create','token','watoom-gpu-controller','--duration=1h'],text=True).strip()
raw=json.loads(subprocess.check_output(['kubectl','config','view','--raw','-o','json']))
cluster=raw['clusters'][0]['cluster']
import base64
ca=base64.b64decode(cluster['certificate-authority-data'])
for name,data in [('token',token+'\n'),('ca.crt',ca)]:
 path=root/name;tmp=root/(name+'.new')
 with tmp.open('wb') as stream:stream.write(data.encode() if isinstance(data,str) else data);stream.flush();os.fsync(stream.fileno())
 os.replace(tmp,path)
config={'apiVersion':'v1','kind':'Config','clusters':[{'name':'cluster','cluster':{'server':'https://127.0.0.1:6443','certificate-authority':str(root/'ca.crt')}}],
 'users':[{'name':'controller','user':{'tokenFile':str(root/'token')}}],
 'contexts':[{'name':'controller','context':{'cluster':'cluster','user':'controller','namespace':'llama-cpp'}}],'current-context':'controller'}
atomic(root/'kubeconfig',config)
print('RESULT=CREDENTIALS_REFRESHED TOKEN_EXPOSED=no')
