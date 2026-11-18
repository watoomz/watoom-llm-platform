import argparse,json,hashlib,pathlib,os,tempfile
p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--session-id',required=True);p.add_argument('--asset-id',required=True);p.add_argument('--reason',required=True);p.add_argument('--preparation-plan',required=True);p.add_argument('--format-selection-json',required=True);a=p.parse_args();selection=json.loads(a.format_selection_json)
if not all(selection.get(k) for k in ['target_engine','available_formats','selected_format','source_evidence','rationale','engine_version']) or selection['selected_format'] not in selection['available_formats']:raise ValueError('Verified available and selected format/version required')
base=pathlib.Path(a.project).resolve(strict=True)
if not base.is_relative_to('/data/ai/projects') or base==pathlib.Path('/data/ai/projects'):raise ValueError('Existing project required')
items={x['id']:x for x in json.loads(pathlib.Path('/data/ai/assets/catalog/fab-owned.json').read_text())['assets']};item=items[a.asset_id]
v={'schema':1,'project':str(base),'asset_id':a.asset_id,'title':item['title'],'reason':a.reason,'preparation_plan':a.preparation_plan,'session_id':a.session_id,'format_selection':selection,'status':'AWAITING_OWNER_APPROVAL','cost':'owned item; no purchase authorized'}
h=hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest();folder=base/'.opencode/asset-requests';folder.mkdir(parents=True,exist_ok=True)
if not folder.resolve().is_relative_to(base):raise ValueError('Request path escapes project')
f=folder/(h+'.json')
if f.exists() and json.loads(f.read_text())!=v:raise ValueError('Conflicting request')
with f.open('w') as o:json.dump(v,o,indent=2)
question='FAB_APPROVAL:'+h+' Download owned Fab asset '+v['title']+' ('+a.asset_id+') for project '+str(base)+'? Reason: '+a.reason+'. Preparation: '+a.preparation_plan+'. Format selection: '+json.dumps(selection,sort_keys=True,separators=(',',':'))+'. Size unknown unless separately verified. This authorizes the download and described data preparation, not automatic execution of acquired code.'
print(json.dumps({'request':str(f),'request_hash':h,'native_question':{'questions':[{'header':'Fab asset download','question':question,'options':[{'label':'Approve download','description':'Download this exact owned asset and prepare it for this project.'},{'label':'Decline','description':'Do not download this asset.'}]}]}}))
