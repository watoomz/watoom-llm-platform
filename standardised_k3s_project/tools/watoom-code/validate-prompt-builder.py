#!/usr/bin/env python3
"""Validate the published prompt page without submitting work, under the existing native fence."""
import argparse,base64,hashlib,json,os,pathlib,subprocess
from maintenance_guard import Maintenance
import release_guard
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);a=p.parse_args();a.evidence.mkdir(parents=True,exist_ok=False)
m=Maintenance('watoom-code','watoom-code',a.evidence,True,True)
release_guard.validate(m.request('/api/session/deployment-guard'),True)
tls=m.kub('get','secret','watoom-code-lan-tls')['data']
pem=subprocess.check_output(['openssl','x509','-pubkey','-noout'],input=base64.b64decode(tls['tls.crt']))
der=subprocess.check_output(['openssl','pkey','-pubin','-outform','DER'],input=pem)
env={**os.environ,'PLAYWRIGHT_MODULE':'/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/source/node_modules/.bun/playwright@1.59.1/node_modules/playwright','CANDIDATE_PASSWORD':m.password,'CANDIDATE_BASE':'https://watoom-code.internal.homelab.example','EVIDENCE':str(a.evidence),'TRUSTED_TLS_SPKI':base64.b64encode(hashlib.sha256(der).digest()).decode()}
q=subprocess.run(['node',str(pathlib.Path(__file__).with_name('prompt-builder-browser.cjs'))],env=env,capture_output=True,text=True,timeout=150)
(a.evidence/'runner.log').write_text(q.stdout+q.stderr)
if q.returncode:raise RuntimeError('Published prompt builder failed; see retained browser evidence')
release_guard.validate(m.request('/api/session/deployment-guard'),True)
print('PASS published prompt builder, safe defaults and clipboard without submitting work')
