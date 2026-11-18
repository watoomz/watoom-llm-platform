import json,pathlib
ROOT=pathlib.Path('/data/ai/assets/catalog')
def build():
 c=json.loads((ROOT/'fab-owned.json').read_text());profiles=json.loads((pathlib.Path(__file__).parent/'pipeline_profiles.json').read_text());groups=[]
 for name,g in profiles.items():
  hits=[x for x in c['assets'] if any(t.casefold() in x['title'].casefold() for t in g['terms'])]
  groups.append({'group':name,'pipelines':['watoom-prompt-'+x for x in g['pipelines']],'reason':g['reason'],'candidates':[{'id':x['id'],'title':x['title'],'type':x['type'],'status':'OWNED_CANDIDATE_NOT_QUALIFIED'} for x in hits]})
 report={'schema':1,'basis':'owned titles/types; relevance candidates, not compatibility acceptance','inventory_timestamp':c['refreshed_at'],'groups':groups,'no_direct_fab_runtime_claim':['iac','kali','models','writing','research','development','image'],'catalog_pipelines':['asset-index','asset-search','inspect','fab-acquire']}
 (ROOT/'fab-pipeline-candidates.json').write_text(json.dumps(report,indent=2));lines=['# Fab candidates by pipeline','','Title-based owned-library candidates; approval and qualification required.','']
 for g in groups:
  lines+=['## '+g['group'],'',', '.join(g['pipelines']),'',g['reason'],'']+['- '+x['title']+' — `'+x['id']+'` ('+x['type']+')' for x in g['candidates']]+['']
 lines+=['No direct Fab runtime integration established for IaC, Kali, LLM serving, writing, research, development or image inference. Catalog/search/inspection/acquisition pipelines use the full owned catalog.']
 (ROOT/'fab-pipeline-candidates.md').write_text('\n'.join(lines)+'\n');return sum(len(g['candidates']) for g in groups)
if __name__=='__main__':print(build())
