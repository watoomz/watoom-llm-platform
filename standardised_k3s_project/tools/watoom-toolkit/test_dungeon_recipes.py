import unittest,math
from dungeon_recipes import inspected_modules
class Recipes(unittest.TestCase):
 def receipt(self):
  return {"version":"5.8.3-0+UE5","meshes":[{"path":"/Game/Test/"+name+"."+name,"min_cm":minimum,"max_cm":maximum,"simple_collision_count":1,"materials":["/Game/Test/Material"]} for name,minimum,maximum in [("SM_Stone_Floor_01a",[-.2,.36,-.45],[60.24,60.15,5.36]),("SM_Stone_01a",[-.65,-.74,-.72],[32.21,27.41,65.65])]]}
 def boxes(self,module,receipt):
  rows={m["path"]:m for m in receipt["meshes"]}
  return [([part["position_cm"][i]+rows[part["object_path"]]["min_cm"][i]*part["scale"][i] for i in range(3)],[part["position_cm"][i]+rows[part["object_path"]]["max_cm"][i]*part["scale"][i] for i in range(3)]) for part in module["parts"]]
 def test_forge_exact_grid_and_walkable_door_opening(self):
  receipt=self.receipt();modules=inspected_modules("dungeon-forge",receipt)
  self.assertEqual([len(modules[k][0]["parts"]) for k in ("floor","wall","doorway")],[25,52,30])
  for role in ("floor","wall","doorway"):
   boxes=self.boxes(modules[role][0],receipt)
   self.assertAlmostEqual(min(a[0] for a,b in boxes),0)
   self.assertAlmostEqual(max(b[0] for a,b in boxes),300)
   if role=="floor":
    self.assertAlmostEqual(max(b[1] for a,b in boxes),300)
    self.assertAlmostEqual(max(b[2] for a,b in boxes),0)
   else:self.assertAlmostEqual(max(b[2] for a,b in boxes),300)
  for a,b in self.boxes(modules["doorway"][0],receipt):
   self.assertTrue(b[0]<=60.00001 or a[0]>=239.99999 or a[2]>=239.99999)
 def test_forge_stairs_are_solid_twenty_cm_risers_with_protected_bay(self):
  from dungeon_recipes import inspected_features
  receipt=self.receipt();modules=inspected_features("dungeon-forge",receipt)
  stair=modules["stairs"][0];boxes=self.boxes(stair,receipt)
  self.assertEqual(stair["stairwell"],"east-bay-v1");self.assertEqual(len(boxes),20)
  for i,(a,b) in enumerate(boxes):
   self.assertAlmostEqual(a[0],150);self.assertAlmostEqual(b[0],450)
   self.assertAlmostEqual(a[2],0);self.assertAlmostEqual(b[2],20*(i+1))
  self.assertAlmostEqual(min(a[1] for a,b in boxes),-300)
  self.assertAlmostEqual(max(b[1] for a,b in boxes),300)
  rail=self.boxes(modules["railing"][0],receipt)
  self.assertAlmostEqual(max(b[2] for a,b in rail),100)
 def test_rejects_changed_family_and_missing_native_collision(self):
  receipt=self.receipt();receipt["meshes"][0]["max_cm"][0]=100
  with self.assertRaises(ValueError):inspected_modules("dungeon-forge",receipt)
  receipt=self.receipt();receipt["meshes"][1]["simple_collision_count"]=0
  with self.assertRaises(ValueError):inspected_modules("dungeon-forge",receipt)
 def test_recipes_do_not_claim_verification(self):
  for entries in inspected_modules("dungeon-forge",self.receipt()).values():
   for module in entries:
    self.assertNotIn("collision_verified",module);self.assertNotIn("materials_verified",module)
if __name__=="__main__":unittest.main()
