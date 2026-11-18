#!/usr/bin/env python3
"""Native cold-location Skill readiness without model requests or production changes."""
import argparse,pathlib,sys,json,time,os,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from native_readiness import wait
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',type=pathlib.Path,required=True);a=p.parse_args();root=a.evidence.resolve();source=pathlib.Path(__file__).resolve().parent;stage=root/'staging';location='/workspace/readiness-'+str(time.time_ns());host=stage/'workspace'/location.split('/')[-1];host.mkdir(mode=0o700);os.chown(host,1001,1001)
m=Maintenance(json.loads((stage/'prepared.json').read_text())['namespace'],'learning-app',stage,True,True);baseline=[x['id'] for x in json.loads((root/'existing-skills/native-inventory.json').read_text())['data']];start=time.monotonic();info,skills,attempts=wait(m,baseline,location);report={'status':'PASS','original_skills':len(baseline),'registered_skills':len(skills),'fresh_native_location':location,'attempts':attempts,'seconds':time.monotonic()-start,'source_sha256':hashlib.sha256((source/'native_readiness.py').read_bytes()).hexdigest(),'model_requests':0,'production_modified':False};atomic(root/'native-tests/native-readiness.json',report);print(json.dumps(report))
