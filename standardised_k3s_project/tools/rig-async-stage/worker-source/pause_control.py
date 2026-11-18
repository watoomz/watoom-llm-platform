import json,pathlib
class PauseRequested(RuntimeError):pass
def control(config):
 p=pathlib.Path(config.get('control_file',str(pathlib.Path(config['root']).parent/'worker-control.json')))
 if not p.exists():return None
 try:
  d=json.loads(p.read_text(encoding='utf-8-sig'))
  return d if d.get('paused') is True else None
 except (OSError,ValueError):return {'paused':True,'mode':'finish','reason':'Invalid control file; no new jobs until operator repair'}
def check(config):
 d=control(config)
 if d and d.get('mode')=='now':raise PauseRequested('Operator paused RIG jobs to release resources; explicit local resume required')
