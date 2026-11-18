#!/usr/bin/env python3
"""Fixed owned-Poo VFX native inspection; source read-only, no generation/export."""
import pathlib,json,subprocess,hashlib,time,os,argparse,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'watoom-code'))
from game_validation import atomic,publish_receipt
p=argparse.ArgumentParser();p.add_argument('--project',type=pathlib.Path,required=True);p.add_argument('--evidence',type=pathlib.Path,required=True);p.add_argument('--i-approve',action='store_true');a=p.parse_args()
assert os.geteuid()==0 and a.i_approve
project=a.project.resolve(strict=True);out=a.evidence.resolve();assert not a.project.is_symlink() and project.parent==pathlib.Path('/data/ai/projects/games')
assert out.is_relative_to('/data/ai/helper-scripts/reports') and not out.exists()
source=pathlib.Path('/data/ai/assets/fab/poo-vfx-0e2a097a');assert (source/'Content/Vefects/VFX_Poo').is_dir()
mem=int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert mem>=5*1024**3,'3GiB plus2GiB reserve unavailable'
def hashes():return {str(x.relative_to(source)):hashlib.sha256(x.read_bytes()).hexdigest() for x in source.rglob('*') if x.is_file()}
before=hashes();out.mkdir(mode=0o770);atomic(out/'source-hashes.json',before)
atomic(out/'Inspection.uproject',{'FileVersion':3,'EngineAssociation':'','Plugins':[{'Name':'PythonScriptPlugin','Enabled':True},{'Name':'Niagara','Enabled':True}]})
probe="""import unreal,json,pathlib,traceback,collections
r={'status':'FAIL','scope':'Native owned-source class/load inspection only. No export, playback, conversion or Godot adaptation acceptance.'}
try:
 registry=unreal.AssetRegistryHelpers.get_asset_registry();registry.scan_paths_synchronous(['/Game/Vefects/VFX_Poo'],True)
 rows=[{'path':str(x.package_name),'class':str(x.asset_class_path.asset_name)} for x in registry.get_assets_by_path('/Game/Vefects/VFX_Poo',True)]
 assert rows,'No asset registry rows'
 selected=[];counts=collections.Counter()
 for row in sorted(rows,key=lambda x:x['path']):
  kind=row['class']
  if '/Demo/' in row['path'] or kind not in ['NiagaraSystem','Material','MaterialInstanceConstant','Texture2D','StaticMesh'] or counts[kind]>=3:continue
  asset=unreal.load_asset(row['path']);assert asset is not None,'Load failed: '+row['path']
  selected.append({'path':row['path'],'loaded_class':asset.get_class().get_name()});counts[kind]+=1
 assert counts['NiagaraSystem']>0,'No NiagaraSystem loaded'
 r.update(status='NATIVE_INSPECTION_PASS',engine=unreal.SystemLibrary.get_engine_version(),assets=rows,loaded=selected,class_counts=dict(collections.Counter(x['class'] for x in rows)),godot_adaptation_confirmed=False)
except Exception:r['error']=traceback.format_exc()
pathlib.Path('/job/native-result.json').write_text(json.dumps(r,indent=2))
if r['status']=='FAIL':raise RuntimeError(r.get('error','failed'))
"""
(out/'probe.py').write_text(probe)
base=pathlib.Path('/data/ai/helper-scripts/reports/remaining-acceptance-20261017T202822Z/pack-9cdd1f83/job.json');job=json.loads(base.read_text());name='watoom-poo-inspect-'+hashlib.sha256(str(out).encode()).hexdigest()[:12]
job['metadata']={'name':name,'namespace':'watoom-code','labels':{'watoom-test-owner':'owned-vfx-inspection'}};job['spec'].update(ttlSecondsAfterFinished=3600,backoffLimit=0,activeDeadlineSeconds=300)
spec=job['spec']['template']['spec'];spec['activeDeadlineSeconds']=300
for v in spec['volumes']:
 if v['name']=='engine':v['hostPath']['path']='/data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653'
 if v['name']=='content':v['hostPath']['path']=str(source/'Content')
 if v['name']=='job':v['hostPath']['path']=str(out)
c=spec['containers'][0];c['resources']={'requests':{'cpu':'100m','memory':'512Mi'},'limits':{'cpu':'2','memory':'3Gi'}}
c['command']=['python3','-c',"import pathlib,subprocess,sys;pathlib.Path('/tmp/home').mkdir(exist_ok=True);sys.exit(subprocess.run(sys.argv[1:],timeout=240).returncode)",'/unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd','/job/Inspection.uproject','-run=PythonScript','-script=/job/probe.py','-NullRHI','-unattended','-nosound','-nop4','-stdout','-ddc=NoZenLocalFallback','-LocalDataCachePath=/job/DerivedDataCache']
for f in [out,*out.iterdir()]:os.chown(f,1009,1009)
atomic(out/'job.json',job);subprocess.run(['kubectl','create','-f',str(out/'job.json')],check=True,stdout=subprocess.DEVNULL)
for _ in range(65):
 j=json.loads(subprocess.check_output(['kubectl','-n','watoom-code','get','job',name,'-o','json']))
 if j.get('status',{}).get('succeeded') or j.get('status',{}).get('failed'):break
 time.sleep(5)
logs=subprocess.run(['kubectl','-n','watoom-code','logs','job/'+name],capture_output=True,text=True);(out/'native.private.log').write_text(logs.stdout+logs.stderr);os.chmod(out/'native.private.log',0o600)
assert hashes()==before,'Purchased source changed'
result=json.loads((out/'native-result.json').read_text()) if (out/'native-result.json').exists() else {'status':'FAIL','reason':'Worker produced no native inspection receipt'}
if not j.get('status',{}).get('succeeded'):result.update(status='FAIL',reason='Unreal worker did not terminate successfully')
result.update(source_unchanged=True,job=name,memory_limit='3GiB',worker_succeeded=bool(j.get('status',{}).get('succeeded')));publish_receipt(project,out,result,log_name='native.private.log',receipt_folder='operator-unreal');atomic(out/'result.json',result);print(json.dumps(result));raise SystemExit(0 if result['status']=='NATIVE_INSPECTION_PASS' else 1)
