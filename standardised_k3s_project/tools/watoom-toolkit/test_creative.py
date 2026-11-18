import unittest,creative
class CreativeContract(unittest.TestCase):
 def test_bounded_references_and_contract(self):
  payload={'task':'3d-creative','operation':'world','asset_id':'ast_'+'a'*24,'seed':42,'parameters':{'instances':8}}
  creative.validate(payload)
  for change in [{'asset_id':'/assets/private'},{'seed':-1},{'operation':'unknown'},{'parameters':{'instances':65}},{'parameters':{'texture_resolution':64.5}}]:
   with self.assertRaises(ValueError):creative.validate({**payload,**change})
  self.assertIn('world-layout.json',creative.names(payload))
  self.assertEqual(len(creative.names({**payload,'operation':'character'})),21)
 def test_catalog_budgets(self):
  creative.validate({'task':'asset-search','query':'tree','limit':16})
  for payload in [{'task':'asset-search','limit':17},{'task':'asset-index','limit':1025},{'task':'asset-index','path':'/secret'}]:
   with self.assertRaises(ValueError):creative.validate(payload)
if __name__=='__main__':unittest.main()
