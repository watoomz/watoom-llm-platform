import unittest,copy,sys
from pathlib import Path
from retarget_contract import validate
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'watoom-code'))
from asset_capture_contract import manifest
PLAN={'schema':'watoom.ts4.retarget.v1','armature':'Shadowheart','clip':'/data/ai/projects/images/neutral.clip','clip_sha256':'a'*64,'profile':'ts4-af-shadowheart-mhx-v1','start_tick':0,'end_tick':30,'root_motion':'in-place'}
class Tests(unittest.TestCase):
 def test_valid(self):self.assertEqual(validate(PLAN),PLAN)
 def test_reject_unknowns(self):
  for key,value in [('profile','other'),('armature','other'),('clip_sha256','bad'),('clip','relative.clip'),('end_tick',120),('end_tick',0),('start_tick',True),('root_motion','execute')]:
   p=copy.deepcopy(PLAN);p[key]=value
   with self.assertRaises(ValueError):validate(p)
 def test_scripts_rejected(self):
  p=copy.deepcopy(PLAN);p['script']='/tmp/anything.py'
  with self.assertRaises(ValueError):validate(p)
 def test_input_outside_roots(self):
  from tempfile import TemporaryDirectory
  import hashlib
  with TemporaryDirectory() as t:
   p=Path(t);source=p/'a.blend';source.write_bytes(b'fixture');clip=p/'a.clip';clip.write_bytes(b'fixture');plan=dict(PLAN,clip=str(clip),clip_sha256=hashlib.sha256(b'fixture').hexdigest())
   spec={'schema':1,'mode':'pose-prepare','source':str(source),'source_sha256':'a'*64,'preparation':{'method':'ts4-retarget','plan':plan}}
   self.assertEqual(manifest(spec,[t]),spec)
   plan['clip_sha256']='b'*64
   with self.assertRaises(ValueError):manifest(spec,[t])

class ProfileTests(unittest.TestCase):
 def test_quin_subset(self):
  from retarget_contract import load_profile
  profile=load_profile('ts4-af-shadowheart-mhx-v2-quin','Shadowheart')
  self.assertEqual(set(profile['retarget']['mapping'].values()),{'hip','spine','chest','neckhead'})
  self.assertEqual(validate(dict(PLAN,profile=profile['id']))['profile'],profile['id'])
 def test_profile_paths_rejected(self):
  for name in ['../escape','/tmp/profile','bad.py','OTHER','']:
   with self.assertRaises(ValueError):validate(dict(PLAN,profile=name))
 def test_new_runtime_profile_and_invalid_data(self):
  import json,retarget_contract as c
  from tempfile import TemporaryDirectory
  from unittest.mock import patch
  template=c.load_profile('ts4-af-shadowheart-mhx-v2-quin','Shadowheart')
  with TemporaryDirectory() as t, TemporaryDirectory() as source:
   with patch.object(c,'PROFILE_DIR',Path(source)),patch.object(c,'RUNTIME_PROFILE_DIR',Path(t)):
    profile=copy.deepcopy(template);profile['id']='ts4-af-new-profile'
    p=Path(t)/(profile['id']+'.json')
    p.write_text(json.dumps(profile))
    self.assertEqual(c.validate(dict(PLAN,profile=profile['id']))['profile'],profile['id'])
    for field,value in [('armature','Wrong'),('retarget',{}),('bone_count',True)]:
     bad=copy.deepcopy(profile);bad[field]=value;p.write_text(json.dumps(bad))
     with self.assertRaises(ValueError):c.validate(dict(PLAN,profile=profile['id']))
    bad=copy.deepcopy(profile);bad['retarget']['mapping']['b__Head__']='not-a-control';p.write_text(json.dumps(bad))
    with self.assertRaises(ValueError):c.validate(dict(PLAN,profile=profile['id']))
    p.unlink();p.symlink_to(Path(t)/'missing')
    with self.assertRaises(ValueError):c.validate(dict(PLAN,profile=profile['id']))
if __name__=='__main__':unittest.main()

