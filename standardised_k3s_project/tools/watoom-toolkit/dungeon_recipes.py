"""Pure bounded recipes from native inspection rows; these do not register or verify adapters."""
import math
def _mesh(receipt,name):
 rows=[m for m in receipt.get("meshes",[]) if m.get("path","").split(".")[-1]==name]
 if len(rows)!=1:raise ValueError("Exactly one inspected module required: "+name)
 row=rows[0]
 if not receipt.get("version","").startswith("5.8.3") or row.get("simple_collision_count",0)<1 or not row.get("materials"):
  raise ValueError("Native collision/material inspection required")
 for values in (row["min_cm"],row["max_cm"]):
  if len(values)!=3 or not all(type(x) in (int,float) and math.isfinite(x) for x in values):raise ValueError("Invalid measured bounds")
 if any(row["max_cm"][i]<=row["min_cm"][i] for i in range(3)):raise ValueError("Empty measured module")
 return row
def inspected_modules(style,receipt):
 def module(row,pivot,lod=0,parts=None):
  return {"object_path":row["path"],"span_cm":300,"pivot_offset_cm":pivot,"lod":lod,"collision_configured":True,"materials_resolved":True,**({"parts":parts} if parts else {})}
 if style=="dungeon-builder":
  floor=_mesh(receipt,"SM_Floor_Stone_Square_Tiles_A");wall=_mesh(receipt,"SM_Wall_A");door=_mesh(receipt,"SM_Wall_A_Flat_Entrance_A")
  if any(abs((floor["max_cm"][i]-floor["min_cm"][i])-300)>1 for i in (0,1)):raise ValueError("Builder grid changed")
  return {"floor":[module(floor,[-150,150,-floor["max_cm"][2]])],"wall":[module(wall,[-150,0,0])],"doorway":[module(door,[-150,0,0])]}
 if style!="dungeon-forge":raise ValueError("Unsupported inspected kit style")
 floor=_mesh(receipt,"SM_Stone_Floor_01a");stone=_mesh(receipt,"SM_Stone_01a")
 fspan=[floor["max_cm"][i]-floor["min_cm"][i] for i in range(3)]
 span=[stone["max_cm"][i]-stone["min_cm"][i] for i in range(3)]
 if not all(55<=fspan[i]<=65 for i in (0,1)) or not 25<=span[0]<=35 or not 55<=span[2]<=70:
  raise ValueError("Forge measured module family changed")
 floor_parts=[]
 for x in range(5):
  for y in range(5):
   sx,sy=60/fspan[0],60/fspan[1]
   floor_parts.append({"object_path":floor["path"],"position_cm":[x*60-floor["min_cm"][0]*sx,y*60-floor["min_cm"][1]*sy,-floor["max_cm"][2]],"rotation":[0,0,0],"scale":[sx,sy,1]})
 def brick(x,z,width=30):
  sx=width/span[0];sz=60/span[2]
  return {"object_path":stone["path"],"position_cm":[x-stone["min_cm"][0]*sx,-stone["min_cm"][1],z-stone["min_cm"][2]*sz],"rotation":[0,0,0],"scale":[sx,1,sz]}
 wall_parts=[];door_parts=[]
 for row in range(5):
  for start,width in ([(x*30,30) for x in range(10)] if row%2==0 else [(0,15)]+[(15+x*30,30) for x in range(9)]+[(285,15)]):
   wall_parts.append(brick(start,row*60,width))
  for base in (0,240):
   entries=[(base+x*30,30) for x in range(2)] if row%2==0 else [(base,15),(base+15,30),(base+45,15)]
   door_parts.extend(brick(x,row*60,width) for x,width in entries)
  if row==4:door_parts.extend(brick(x,240) for x in (60,90,120,150,180,210))
 return {"floor":[module(floor,[-150,-150,0],3,floor_parts)],"wall":[module(stone,[-150,-span[1],0],5,wall_parts)],"doorway":[module(stone,[-150,-span[1],0],5,door_parts)]}

def inspected_features(style,receipt):
 """Optional source-inspected features; still require native candidate acceptance."""
 modules=inspected_modules(style,receipt)
 def entry(row,pivot,lod=0,**extra):
  return {"object_path":row["path"],"span_cm":300,"pivot_offset_cm":pivot,"lod":lod,"collision_configured":True,"materials_resolved":True,**extra}
 if style=="dungeon-builder":
  brick=_mesh(receipt,"SM_Stone_Wall_Brick_A");candle=_mesh(receipt,"SM_Wallcandlestick_A")
  modules["prop"]=[entry(brick,[0,0,-brick["min_cm"][2]],attachment="floor"),
                    entry(candle,[-sum((candle["min_cm"][0],candle["max_cm"][0]))/2,-candle["min_cm"][1],180-sum((candle["min_cm"][2],candle["max_cm"][2]))/2],attachment="south-wall")]
  stair=_mesh(receipt,"SM_Stairs_A_300");span=[stair["max_cm"][i]-stair["min_cm"][i] for i in range(3)]
  if not 280<=span[0]<=320 or not 280<=span[1]<=320 or not 140<=span[2]<=160:raise ValueError("Inspected stair family changed")
  scale=[300/span[0],300/span[1],200/span[2]]
  modules["stairs"]=[entry(stair,[150-stair["min_cm"][0]*scale[0],300-stair["max_cm"][1]*scale[1],-stair["min_cm"][2]*scale[2]],rise_cm=400,run_cm=600,stairwell="east-bay-v1",parts=[{"object_path":stair["path"],"position_cm":[0,-300*i,200*i],"rotation":[0,0,0],"scale":scale} for i in range(2)])]
  wall=modules["wall"][0]
  modules["railing"]=[{**wall,"parts":[{"object_path":wall["object_path"],"position_cm":[0,0,0],"rotation":[0,0,0],"scale":[1,1,.25]}]}]
 elif style=="dungeon-forge":
  stone=_mesh(receipt,"SM_Stone_01a")
  modules["prop"]=[entry(stone,[-sum((stone["min_cm"][0],stone["max_cm"][0]))/4,-sum((stone["min_cm"][1],stone["max_cm"][1]))/4,-stone["min_cm"][2]/2],5,attachment="floor",parts=[{"object_path":stone["path"],"position_cm":[0,0,0],"rotation":[0,0,0],"scale":[.5,.5,.5]}])]
  span=[stone["max_cm"][i]-stone["min_cm"][i] for i in range(3)]
  parts=[]
  for step in range(20):
   scale=[300/span[0],30/span[1],20*(step+1)/span[2]]
   parts.append({"object_path":stone["path"],"position_cm":[150-stone["min_cm"][0]*scale[0],300-(step+1)*30-stone["min_cm"][1]*scale[1],-stone["min_cm"][2]*scale[2]],"rotation":[0,0,0],"scale":scale})
  modules["stairs"]=[entry(stone,[0,0,0],5,rise_cm=400,run_cm=600,stairwell="east-bay-v1",parts=parts)]
  wall=modules["wall"][0]
  modules["railing"]=[{**wall,"parts":[{**part,"position_cm":[part["position_cm"][0],part["position_cm"][1],part["position_cm"][2]/3],"scale":[part["scale"][0],part["scale"][1],part["scale"][2]/3]} for part in wall["parts"]]}]
 return modules
