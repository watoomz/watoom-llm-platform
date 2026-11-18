from pathlib import Path
import json,subprocess,sys
root=Path('/data/ai/game_templates/unreal/.downloads')
helper='/data/ai/helper-scripts/cache/megatools/unpacked/usr/bin/megatools'
for e in json.loads(Path(__file__).with_name('unreal-sources.json').read_text())['templates']:
 d=root/e['id'];d.mkdir(exist_ok=True)
 status=d/'download-status.json'
 if status.exists() and json.loads(status.read_text()).get('returncode')==0 and len(list(d.glob('*.zip')))==1:continue
 with (d/'download.log').open('w') as log:
  p=subprocess.run([helper,'dl','--ignore-config-file','--no-ask-password','--no-progress','--print-names','--path',str(d),e['download_url']],stdout=log,stderr=subprocess.STDOUT,timeout=3600)
 (d/'download-status.json').write_text(json.dumps({'returncode':p.returncode}))
 if p.returncode:sys.exit(p.returncode)
