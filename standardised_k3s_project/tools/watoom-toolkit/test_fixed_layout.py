import unittest,copy
import fixed_layout
class FixedLayout(unittest.TestCase):
 def board(self):return {"cols":3,"rows":2,"cell_cm":200,"rock_cells":[[2,1]],"wall_edges":[[[0,0],[1,0]]],"door_edges":[[[0,0],[1,0]]]}
 def test_validation(self):
  self.assertEqual(fixed_layout.validate(self.board())["cell_cm"],200)
  for value in [{**self.board(),"cols":True},{**self.board(),"unknown":1},{**self.board(),"rock_cells":[[9,0]]},{**self.board(),"door_edges":[[[0,0],[2,0]]]},{**self.board(),"rock_cells":[[0,0],[0,0]]}]:
   with self.assertRaises(ValueError):fixed_layout.validate(value)
 def test_exact_repeatable_geometry(self):
  modules={role:[{"object_path":"/Game/"+role+"."+role,"pivot_offset_cm":[0,0,0]}] for role in ["floor","wall","doorway"]}
  base={"files":{},"portable_modules":[],"provenance":[],"qa":{}}
  a=fixed_layout.assemble(base,self.board(),[{"tile_cm":300,"modules":modules}])
  self.assertEqual(a,fixed_layout.assemble(base,self.board(),[{"tile_cm":300,"modules":modules}]))
  self.assertEqual(a["effective_options"]["board_cm"],[600,400])
  self.assertEqual(len([p for p in a["placements"] if p["role"]=="floor"]),5)
  self.assertEqual(len([p for p in a["placements"] if p["role"]=="doorway"]),1)
  self.assertEqual(a["layout"]["stairs"],[])
  self.assertEqual(len(base),4) # Original base plan not mutated.
