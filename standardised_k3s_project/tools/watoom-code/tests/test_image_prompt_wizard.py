"""Deterministic CPU-only acceptance of the shared image wizard; no image jobs."""
import sys
sys.dont_write_bytecode=True
import copy,importlib.util,json,pathlib,tempfile,unittest,socket
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[3]
SKILL=ROOT/'ansible/roles/watoom-code/files/skills/watoom-explicit-image-creator'
spec=importlib.util.spec_from_file_location('image_wizard',SKILL/'scripts/wizard.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
MODEL=dict(id='a'*64,revision='b'*40,kind='diffusion-pipeline',registered=True,repository='fixture/sdxl')
def reviewed(state):
 for action in ['approve_positive','approve_negative','continue']:state=w.transition(state,action)
 return state
class Wizard(unittest.TestCase):
 def test_short_idea_initial_positive(self):
  state=w.new('A lighthouse during a storm');self.assertIn('lighthouse',w.positive_prompt(state));self.assertEqual(state['phase'],'POSITIVE_REVIEW');self.assertIsNone(state['negative'])
 def test_positive_edit_and_approval(self):
  state=w.transition(w.new('A lighthouse'),'edit_positive',dict(description='A red lighthouse',tags=['coast','coast']));self.assertIn('red lighthouse',w.positive_prompt(state));self.assertEqual(state['positive']['tags'],['coast']);state=w.transition(state,'approve_positive');self.assertEqual(state['phase'],'NEGATIVE_REVIEW');self.assertIsInstance(state['negative'],str)
 def test_negative_review_exact(self):
  state=w.transition(w.new('A lighthouse'),'approve_positive');text='  blur, unwanted lettering\n';state=w.transition(state,'edit_negative',dict(text=text));state=w.transition(state,'approve_negative');self.assertEqual(state['negative'],text);self.assertEqual(state['phase'],'DETAILS')
 def test_additional_details_only_after_reviews(self):
  state=w.new('A lighthouse')
  with self.assertRaises(ValueError):w.transition(state,'details',dict(lighting=dict(color_temperature='warm')))
  state=w.transition(w.transition(state,'approve_positive'),'approve_negative');state=w.transition(state,'details',dict(lighting=dict(color_temperature='warm')));self.assertEqual(state['details']['lighting']['color_temperature'],'warm')
 def test_prefilled_details(self):
  state=w.new('A quiet snowy forest',analysis=dict(details=dict(environment=dict(weather='snowy',location='forest'))));self.assertEqual(state['details']['environment']['weather'],'snowy');self.assertEqual(state['idea'],'A quiet snowy forest')
 def test_skip_optional_details(self):self.assertEqual(reviewed(w.new('An old tree'))['phase'],'FINAL_REVIEW')
 def test_default_appearance_and_adult(self):
  state=w.new('A fictional explorer',analysis={'human':True});self.assertEqual(state['details']['subject']['age'],'adult');self.assertIn('Caucasian/European',state['details']['subject']['appearance'])
 def test_explicit_appearance_overrides_default(self):
  state=w.new('An adult Japanese explorer',analysis=dict(human=True,details=dict(subject=dict(appearance='Japanese facial characteristics',age='adult'))));self.assertEqual(state['details']['subject']['appearance'],'Japanese facial characteristics');self.assertNotIn('Caucasian',w.positive_prompt(state))
 def test_character_and_reference_preserved(self):
  for analysis in [dict(human=True,character_identity='established character'),dict(human=True,reference='supplied portrait'),dict(human=True,appearance_specified=True)]:
   state=w.new('The same character',analysis=analysis);self.assertEqual(state['details']['subject']['appearance'],'')
 def test_nonhuman_no_appearance_default(self):self.assertNotIn('Caucasian',w.positive_prompt(w.new('A forest fox')))
 def test_pony_only_verified_revision(self):
  model={**MODEL,'prompt_profile':dict(family='pony',verified=True,revision=MODEL['revision'],source='fixture-only model-card evidence')};state=reviewed(w.new('A painted lighthouse',model=model));self.assertIn('score_9',w.preview(state)['positive_prompt']);self.assertIn('score_6',state['negative'])
  model['prompt_profile']['revision']='c'*40;self.assertNotIn('score_9',w.positive_prompt(w.new('A lighthouse',model=model)))
 def test_sdxl_and_unknown_no_pony(self):
  for family in ['sdxl','unknown']:
   model={**MODEL,'prompt_profile':dict(family=family,verified=True,revision=MODEL['revision'],source='fixture')};state=reviewed(w.new('A lighthouse',model=model));self.assertNotIn('score_',w.preview(state)['positive_prompt']);self.assertNotIn('score_',state['negative'])
 def test_field_edit_preserves_other_fields(self):
  state=reviewed(w.new('A lighthouse',analysis=dict(details=dict(camera=dict(angle='low'),lighting=dict(color_temperature='cool')))));state=w.transition(state,'details',dict(lighting=dict(color_temperature='warm')));state=w.transition(state,'continue');out=w.preview(state)['positive_prompt'];self.assertIn('warm',out);self.assertNotIn('cool',out);self.assertEqual(state['details']['camera']['angle'],'low')
 def test_approved_original_and_negative_preserved(self):
  state=reviewed(w.new('A lighthouse in a storm',negative='no captions'));out=w.preview(state);self.assertIn('A lighthouse in a storm',out['positive_prompt']);self.assertEqual(out['negative_prompt'],'no captions')
 def test_prompt_only_without_gpu_or_network(self):
  with patch.object(socket,'socket',side_effect=AssertionError('No network allowed')):
   state=w.transition(reviewed(w.new('A lighthouse')),'save_prompts');self.assertEqual(state['phase'],'SAVED');self.assertNotIn('request_plan',state)
 def test_generate_requires_final_approval(self):
  state=reviewed(w.new('A lighthouse',model=MODEL))
  with self.assertRaises(ValueError):w.transition(state,'generate',dict(current_model=MODEL))
  state=w.transition(state,'generate',dict(current_model=MODEL,preview_id=w.preview(state)['preview_id']));self.assertEqual(state['phase'],'PLAN_READY');self.assertEqual(state['request_plan']['negative_prompt'],state['negative'])
 def test_stale_preview_rejected(self):
  state=reviewed(w.new('A lighthouse',model=MODEL));old=w.preview(state)['preview_id'];state=w.transition(state,'edit_settings',dict(seed=8))
  with self.assertRaises(ValueError):w.transition(state,'generate',dict(current_model=MODEL,preview_id=old))
 def test_stale_model_rejected(self):
  state=reviewed(w.new('A lighthouse',model=MODEL))
  with self.assertRaises(ValueError):w.transition(state,'generate',dict(current_model={**MODEL,'revision':'c'*40},preview_id=w.preview(state)['preview_id']))
 def test_limits_and_unsupported_controls(self):
  for settings in [dict(width=2048),dict(steps=51),dict(guidance=float('nan')),dict(seed=-1),dict(scheduler='guessed'),dict(lora_scale=1)]:
   with self.assertRaises(ValueError):w.settings(settings)
 def test_receipts_and_history_retained(self):
  state=reviewed(w.new('A lighthouse',model=MODEL));state=w.transition(state,'generate',dict(current_model=MODEL,preview_id=w.preview(state)['preview_id']));plan=copy.deepcopy(state['request_plan']);receipt=dict(request_id=plan['request_id'],job_id='d'*64,receipt={'published':'/generated/fixture/image.png','generation_settings':plan['settings']});state=w.transition(state,'record_receipt',receipt);state=w.transition(state,'refine',dict(description='A lighthouse with warmer light'));self.assertEqual(state['receipts'][0],receipt);self.assertEqual(state['history'][0]['positive_prompt'],plan['prompt']);self.assertEqual(state['revision'],2)
 def test_retry_stable_edit_new_revision(self):
  state=reviewed(w.new('A lighthouse',model=MODEL));data=dict(current_model=MODEL,preview_id=w.preview(state)['preview_id']);state=w.transition(state,'generate',data);first=state['request_plan'];self.assertEqual(w.transition(state,'generate',data)['request_plan'],first);state=w.transition(state,'edit_settings',dict(seed=9));state=w.transition(state,'generate',dict(current_model=MODEL,preview_id=w.preview(state)['preview_id']));self.assertNotEqual(state['request_plan']['request_id'],first['request_id'])
 def test_demographics_not_auto_negative(self):
  state=w.transition(w.new('An explorer',analysis={'human':True}),'approve_positive');self.assertEqual(state['negative'],'compression artifacts, unintentional blur')
 def test_preference_persistence_and_request_override(self):
  with tempfile.TemporaryDirectory() as folder:
   path=pathlib.Path(folder)/'preferences.json';saved=w.save_preset(path,'warm',dict(positive_tags=['painterly'],camera={'angle':'high'},lighting={'color_temperature':'warm'},generation_settings={'steps':35}));reloaded=json.loads(path.read_text());self.assertEqual(reloaded,saved);self.assertEqual(path.stat().st_mode&0o777,0o600)
   state=reviewed(w.new('A lighthouse',prefs=reloaded,analysis=dict(details=dict(camera=dict(angle='low')))));state=w.transition(state,'apply_preset',{'name':'warm'});self.assertEqual(state['details']['camera']['angle'],'low');self.assertEqual(state['details']['lighting']['color_temperature'],'warm');self.assertEqual(state['settings']['steps'],35);self.assertEqual(state['phase'],'POSITIVE_REVIEW')
 def test_preferences_explicit_override(self):
  state=w.new('An explorer',analysis={'human':True},prefs={'default_human_appearance':'custom user appearance'});self.assertEqual(state['details']['subject']['appearance'],'custom user appearance')
 def test_incompatible_explicit_scores_block_generation(self):
  state=reviewed(w.new('A lighthouse',model=MODEL,positive={'description':'A lighthouse','tags':['score_9']}))
  with self.assertRaises(ValueError):w.transition(state,'generate',dict(current_model=MODEL,preview_id=w.preview(state)['preview_id']))
 def test_both_entrypoints_use_shared_resource(self):
  prompt=(SKILL.parent/'watoom-prompt-image/SKILL.md').read_text();self.assertIn('watoom-explicit-image-creator',prompt);self.assertIn('final Generate choice',prompt)
if __name__=='__main__':unittest.main()
