#!/usr/bin/env python3
"""Index only receipt-verified acquired resources through the installed Catalog API."""
import argparse,pathlib,json,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--evidence',type=pathlib.Path,required=True);a=p.parse_args();r=a.evidence.resolve();assert r.is_relative_to('/data/ai/helper-scripts/reports')
d=json.loads((r/'download-status.json').read_text());assert d['status']=='PASS'
paths=[]
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'watoom-toolkit'));from asset_catalog import FORMATS
for item in d['completed']:
 receipt=json.loads(pathlib.Path(item['receipt']).read_text());assert receipt['asset']['id']==item['id']
 for name in receipt['files']:
  f=pathlib.Path(name);assert f.is_file() and not f.is_symlink() and f.resolve().is_relative_to('/data/ai/assets')
  if f.suffix.lower() in FORMATS:paths.append(str(f.relative_to('/data/ai/assets')))
paths=sorted(set(paths));assert paths
results=[]
code="import sys,json;sys.path.insert(0,'/opt/watoom');from asset_catalog import Catalog;c=Catalog('/assets','/state/asset-catalog/catalog.json');print(json.dumps(c.index_selected(json.loads(sys.argv[1]))))"
for offset in range(0,len(paths),256):
 value=json.loads(subprocess.check_output(['kubectl','-n','watoom-code','exec','deploy/watoom-toolkit','--','python3','-c',code,json.dumps(paths[offset:offset+256])],timeout=90));assert value['status']=='PASS';results.append(value)
result={'status':'PASS','method':'installed Catalog.index_selected under existing global catalog lock','selected_files':len(paths),'batches':results};(r/'selected-catalog-reconciliation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
