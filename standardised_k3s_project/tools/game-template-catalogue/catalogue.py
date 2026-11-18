#!/usr/bin/env python3
"""Combine installed records and publish short, searchable native skill entries."""
import argparse,json,os,shutil
from pathlib import Path
ROOT=Path('/data/ai/game_templates')
def build(root=ROOT):
 entries=[]
 for engine in ('godot','unreal'):
  p=root/engine/'catalogue.json'
  if not p.exists():continue
  for item in json.loads(p.read_text())['templates']:
   e=dict(item,engine=engine)
   if not Path(e['path']).resolve().is_relative_to((root/engine).resolve()):raise ValueError('Template outside engine root')
   entries.append(e)
 if len({e['id'] for e in entries})!=len(entries):raise ValueError('Duplicate template id')
 result={'schema':'watoom.game-template-catalogue.v1','root':str(root),'templates':entries}
 (root/'catalogue.json').write_text(json.dumps(result,indent=2)+'\n')
 lines=['# Installed game templates','', 'Search with the native watoom_skill_search tool using engine, genre or feature intent. Load the returned game-template skill for its exact local path, source revision and limitations.', '', 'Source installation and static checks do not establish runtime compatibility. Copy selected material into an approved project; preserve library originals and licence notices.','']
 for e in entries:
  lines += ['## '+e['name'], '', e['description'], '', '- Engine/category: '+e['engine']+'/'+e['category'], '- Path: `'+e['path']+'`', '- Source: '+e['source_url'], '- Runtime: '+e['runtime_validation'], '']
 (root/'CATALOGUE.md').write_text('\n'.join(lines))
 return entries

def skills(entries,destination):
 destination.mkdir(parents=True,exist_ok=True)
 for e in entries:
  name='game-template-'+e['id'];d=destination/name;d.mkdir(exist_ok=True)
  version=e.get('godot_declared') or e.get('engine_declared','UNKNOWN')
  description=f"{e['engine'].title()} {e['category']} template: {e['name']}. {e['description']}"
  meta={'aliases':e['tags']+[e['name'],'game template','starter project'], 'requires':[]}
  text='---\nname: '+name+'\ndescription: '+json.dumps(description)+'\nmetadata:\n  opencode/autoinvoke: false\n---\n\n# '+e['name']+'\n\n'+e['description']+'\n\n```skill-routing\n'+json.dumps(meta)+'\n```\n\n'
  text+='- Engine/category: '+e['engine']+'/'+e['category']+'\n- Declared version: '+str(version)+'\n- Library source: `'+e['path']+'`\n- Project root: `'+str(e.get('project_root') or 'Inspect project_files; component pack may have no standalone project')+'`\n- Upstream: '+e['source_url']+'\n- Source revision/hash: '+str(e.get('commit') or e.get('archive_sha256'))+'\n- Licence: '+e['license']+'\n- Runtime qualification: '+e['runtime_validation']+'\n\n'
  text+='Use when creating a new project or explicitly reusing a suitable component. Inspect the exact README, licence and dependency notices first. Compare engine versions and relevant feature scope. Do not claim source installation proves runtime support. For an existing game, propose selective reuse; never replace it with a starter without owner approval. Preserve this library source unchanged. Copy only selected material into the approved project, excluding `.git`, `.godot`, generated caches and downloads; retain author attribution, bundled third-party terms and engine content namespaces. Do not execute downloaded editor plugins, scripts, installers or engine code during discovery. Qualification uses the verified bounded external worker and normal technical/visual gates. No new download is needed for this installed source.\n\nFull searchable catalogue: `/data/ai/game_templates/catalogue.json`; human index: `/data/ai/game_templates/CATALOGUE.md`.\n'
  (d/'SKILL.md').write_text(text)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--skills',type=Path);a=p.parse_args();entries=build(a.root)
 if a.skills:skills(entries,a.skills)
 print(json.dumps({'templates':len(entries),'catalogue':str(a.root/'catalogue.json')}))
