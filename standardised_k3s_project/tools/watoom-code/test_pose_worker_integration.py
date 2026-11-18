"""Operator-only real-worker regression using an unconstrained synthetic FK fixture."""
import argparse,copy,json,pathlib,re
from asset_capture import run
from asset_capture_contract import sha

def main():
 a=argparse.ArgumentParser();a.add_argument('--source',required=True,type=pathlib.Path);a.add_argument('--plan',required=True,type=pathlib.Path);a.add_argument('--evidence',required=True,type=pathlib.Path);a.add_argument('--prefix',required=True);v=a.parse_args()
 assert re.fullmatch('[a-z0-9-]{1,42}',v.prefix)
 project=pathlib.Path('/data/ai/projects/images');source_hash=sha(v.source);plan=json.loads(v.plan.read_text());bad=copy.deepcopy(plan)
 for target in bad['targets'].values():target['point']=[900,900,900]
 cases=[('inspect',{'mode':'pose-inspect'},True),('auto',{'mode':'pose-prepare','preparation':{'method':'auto','plan':plan}},True),('unreachable',{'mode':'pose-prepare','preparation':{'method':'auto','plan':bad}},False)]
 results=[]
 for suffix,extra,success in cases:
  job=v.prefix+'-'+suffix;folder=project/'.opencode/capture-jobs'/job;folder.mkdir(exist_ok=False)
  manifest={'schema':1,'source':str(v.source),'source_sha256':source_hash,**extra};(folder/'request.json').write_text(json.dumps(manifest))
  rc=run(str(project),job,v.evidence/suffix);receipt=json.loads((v.evidence/suffix/'result.json').read_text());out=pathlib.Path(receipt['output'])
  assert (rc==0)==success and receipt['source_unchanged'] and receipt['cgroup_limit_verified']
  assert not receipt.get('images'), 'Preparation cannot claim rendered pixels'
  if suffix=='auto':assert (out/'posed.blend').is_file() and receipt['status']=='PREPARED_REVIEW_PENDING' and receipt['requires_visual_review'] and receipt['adapter_sha256']
  if not success:assert not (out/'posed.blend').exists() and (out/'pose-validation.json').is_file()
  assert sha(v.source)==source_hash
  results.append({'case':suffix,'status':'PASS','receipt':str(v.evidence/suffix/'result.json')})
 # A retry may not overwrite or replay this identity, even after failure.
 try:run(str(project),v.prefix+'-unreachable',v.evidence/'no-replay')
 except ValueError as error:assert 'Output already exists' in str(error)
 else:raise AssertionError('Failed job was replayed')
 (v.evidence/'acceptance.json').write_text(json.dumps({'status':'PASS','cases':results,'replay_rejected':True,'scope':'synthetic FK worker routing; not real character visual qualification'},indent=2))
if __name__=='__main__':main()
