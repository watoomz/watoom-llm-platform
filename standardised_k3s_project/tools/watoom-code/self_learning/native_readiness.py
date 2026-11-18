"""Wait for the native asynchronous filesystem Skill registry, then enforce coverage."""
import time,urllib.parse,urllib.error
def wait(m,baseline,directory='/workspace',seconds=45):
 deadline=time.monotonic()+seconds;attempts=0;missing=set(baseline)
 while True:
  attempts+=1
  try:
   info=m.request('/api/info');skills=m.request('/api/skill?'+urllib.parse.urlencode({'location[directory]':directory}))['data'];missing=set(baseline)-{x['id'] for x in skills}
   if info.get('version') and not missing:return info,skills,attempts
  except urllib.error.HTTPError as error:
   if error.code!=503:raise
  if time.monotonic()>=deadline:raise RuntimeError('Native Skill readiness deadline expired; missing: '+','.join(sorted(missing)))
  time.sleep(.5)
