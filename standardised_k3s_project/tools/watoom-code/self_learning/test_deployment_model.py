import unittest
from deployment_model import validate_idle_model
class SelectedModel(unittest.TestCase):
 def test_selected_alternate_passes_without_primary_switch(self):
  validate_idle_model(self.gpu(), 'alternate','alternate',self.deployment())
 def gpu(self):return dict(owner=None,phase='model-ready',uncertain=False,active_requests=0)
 def deployment(self):return dict(metadata=dict(name='alternate',generation=3),spec=dict(replicas=1),status=dict(readyReplicas=1,observedGeneration=3))
 def test_unsafe_states_rejected(self):
  for change in [dict(owner='job'),dict(phase='switching-model'),dict(uncertain=True),dict(active_requests=1)]:
   with self.subTest(change=change),self.assertRaises(RuntimeError):validate_idle_model({**self.gpu(),**change},'alternate','alternate',self.deployment())
 def test_different_or_unready_model_rejected(self):
  with self.assertRaises(RuntimeError):validate_idle_model(self.gpu(),'primary','alternate',self.deployment())
  dep=self.deployment();dep['status']['readyReplicas']=0
  with self.assertRaises(RuntimeError):validate_idle_model(self.gpu(),'alternate','alternate',dep)
