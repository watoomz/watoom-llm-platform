#!/usr/bin/env python3
"""Safely extract owner-requested archives without executing their code."""
import hashlib,json,os,re
from pathlib import Path,PurePosixPath
from archive import extract,sha
ROOT=Path('/data/ai/game_templates/unreal')
def install(e):
 source=ROOT/'.downloads'/e['id'];status=json.loads((source/'download-status.json').read_text());assert status['returncode']==0
 archives=[p for p in source.iterdir() if p.suffix.lower()=='.zip'];assert len(archives)==1
 archive=archives[0];digest=sha(archive);target=ROOT/e['category']/e['id'];record=ROOT/'.catalogue/records'/f"{e['id']}.json"
 if target.exists():
  old=json.loads(record.read_text());assert old['archive_sha256']==digest;return old
 stage=ROOT/'.incoming'/e['id'];stage.mkdir(parents=True,exist_ok=False)
 manifest=extract(archive,stage)
 projects=sorted(str(p.relative_to(stage)) for p in stage.rglob('*.uproject'))
 plugins=sorted(str(p.relative_to(stage)) for p in stage.rglob('*.uplugin'))
 assert projects or plugins or any(p.suffix in ['.uasset','.umap'] for p in stage.rglob('*')),'No Unreal source content'
 versions=[]
 for project in projects:
  try:versions.append(json.loads((stage/project).read_text(encoding='utf-8-sig')).get('EngineAssociation','UNSPECIFIED'))
  except (ValueError,UnicodeError):versions.append('UNREADABLE_DESCRIPTOR')
 notices=sorted(str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file() and re.search(r'licen[cs]e|copyright|terms|readme',p.name,re.I))
 target.parent.mkdir(parents=True,exist_ok=True);stage.rename(target)
 result=dict(e,path=str(target),project_files=projects,plugin_files=plugins,project_root=str(target/str(PurePosixPath(projects[0]).parent)) if len(projects)==1 else None,engine_declared=versions or 'Archive label: UE4.26; unqualified',archive_name=archive.name,archive_sha256=digest,archive_bytes=archive.stat().st_size,license='UNKNOWN; user-provided mirror, preserve bundled notices; no Fab entitlement established',license_files=notices,file_count=len(manifest),bytes=sum(x['bytes'] for x in manifest),tree_manifest_sha256=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),runtime_validation='NOT_TESTED',validation='Archive integrity, contained paths, complete extraction and hashes checked. No editor, plugin, installer or template code executed. UE5 compatibility unqualified.')
 record.parent.mkdir(parents=True,exist_ok=True);record.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2));record.write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 entries=[install(e) for e in json.loads(Path(__file__).with_name('unreal-sources.json').read_text())['templates']]
 (ROOT/'catalogue.json').write_text(json.dumps({'schema':'watoom.game-template-catalogue.v1','root':str(ROOT),'templates':entries},indent=2)+'\n')
 print(json.dumps({'installed':len(entries),'entries':[{k:e[k] for k in ['id','file_count','engine_declared','project_files']} for e in entries]}))
