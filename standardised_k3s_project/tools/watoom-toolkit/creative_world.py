"""Seeded editable environment composition from indexed portable library props."""
import bpy,math,random,json,hashlib
from mathutils import Vector,Matrix
from creative_blender_common import load,uv,cube,material
def prepare(request,work):
 params=request.get('parameters',{});seed=request.get('seed',0);rng=random.Random(seed)
 size=params.get('size',12);resolution=params.get('resolution',16);height=params.get('height',.4);count=int(params.get('instances',12)*params.get('density',1))
 def elevation(x,y):
  if abs(x)<.65 or abs(y)<.4:return 0
  return height*math.sin((x+size/2)/size*resolution*.37+seed)*math.cos((y+size/2)/size*resolution*.31-seed)
 vertices=[(-size/2+size*x/resolution,-size/2+size*y/resolution,elevation(-size/2+size*x/resolution,-size/2+size*y/resolution)) for y in range(resolution+1) for x in range(resolution+1)]
 faces=[(y*(resolution+1)+x,y*(resolution+1)+x+1,(y+1)*(resolution+1)+x+1,(y+1)*(resolution+1)+x) for y in range(resolution) for x in range(resolution)]
 mesh=bpy.data.meshes.new('SeededTerrain');mesh.from_pydata(vertices,[],faces)
 terrain=bpy.data.objects.new('EditableTerrain',mesh);bpy.context.collection.objects.link(terrain);terrain.data.materials.append(material('Biome ground',(.16,.27,.09)));uv(terrain)
 group=bpy.data.node_groups.new('WatooM Seeded Terrain','GeometryNodeTree')
 group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
 incoming=group.nodes.new('NodeGroupInput');position=group.nodes.new('GeometryNodeSetPosition');outgoing=group.nodes.new('NodeGroupOutput')
 noise=group.nodes.new('ShaderNodeTexNoise');noise.noise_dimensions='4D';noise.inputs['Scale'].default_value=2;noise.inputs['W'].default_value=seed
 offset=group.nodes.new('ShaderNodeCombineXYZ');scale=group.nodes.new('ShaderNodeMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=height*.02
 group.links.new(noise.outputs['Fac'],scale.inputs[0]);group.links.new(scale.outputs[0],offset.inputs['Z']);group.links.new(offset.outputs[0],position.inputs['Offset'])
 group.links.new(incoming.outputs['Geometry'],position.inputs['Geometry']);group.links.new(position.outputs['Geometry'],outgoing.inputs['Geometry'])
 modifier=terrain.modifiers.new('Editable seeded Geometry Nodes','NODES');modifier.node_group=group
 bpy.context.view_layer.update()
 baked=terrain.copy();baked.data=bpy.data.meshes.new_from_object(terrain.evaluated_get(bpy.context.evaluated_depsgraph_get()));baked.modifiers.clear();baked.name='Terrain';bpy.context.collection.objects.link(baked)
 terrain['watoom_editor_only']=True;terrain.hide_render=True;terrain.hide_set(True)
 prototypes=[]
 for source in request['sources']:
  if source['path'].lower().endswith('.blend'):raise ValueError('Select portable GLB/FBX/OBJ world props; retain linked Blender source independently')
  previous=set(bpy.context.scene.objects);load(source['path'])
  fresh=[o for o in bpy.context.scene.objects if o not in previous]
  if any(o.type=='ARMATURE' for o in fresh):raise ValueError('Animated actors require character placement support; select static world props')
  meshes=[(o,o.matrix_world.copy()) for o in fresh if o.type=='MESH']
  if not meshes:raise ValueError('Library prop has no geometry')
  for obj in fresh:obj['watoom_editor_only']=True;obj.hide_render=True;obj.hide_set(True)
  prototypes.append((source['reference']['id'],meshes))
 layout=[]
 for i in range(count):
  for attempt in range(64):
   x=rng.uniform(-size*.43,size*.43);y=rng.uniform(-size*.43,size*.43)
   if abs(x)>.9 and abs(y)>.65 and all((x-p['position'][0])**2+(y-p['position'][1])**2>.5 for p in layout):break
  else:continue
  ref,parts=prototypes[i%len(prototypes)];angle=rng.random()*math.tau;factor=.25+rng.random()*.35;z=elevation(x,y)+height*.01
  transform=Matrix.Translation(Vector((x,y,z)))@Matrix.Rotation(angle,4,'Z')@Matrix.Scale(factor,4)
  for part_index,(template,matrix) in enumerate(parts):
   obj=template.copy();obj.data=template.data;obj.parent=None;obj.name='Placed_'+str(i)+'_'+str(part_index);bpy.context.collection.objects.link(obj)
   obj.hide_render=False;obj.hide_set(False);obj['watoom_editor_only']=False;obj.matrix_world=transform@matrix
  layout.append({'source':ref,'position':[round(x,6),round(y,6),round(z,6)],'rotation':round(angle,6),'scale':round(factor,6)})
 cube('Road',(0,0,.015),(.9,size,.03),material('Road',(.23,.2,.16)))
 cube('River',(0,0,.025),(size,.5,.025),material('River',(.04,.17,.28)))
 cube('ProceduralBuilding',(size*.31,size*.31,.7),(1,1,1.4),material('Building',(.42,.31,.21)))
 collision=baked.copy();collision.data=baked.data.copy();collision.name='Terrain-colonly';collision.hide_render=True;bpy.context.collection.objects.link(collision)
 (work/'world-layout.json').write_text(json.dumps(layout,indent=2))
 return {'world_layout':layout,'layout_sha256':hashlib.sha256(json.dumps(layout,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'geometry_nodes':group.name,'editable_source':'Hidden EditableTerrain retains live Geometry Nodes; GLB contains evaluated copy','fallback_building_reason':'No portable building selected; Unreal source buildings require verified editor access','boundaries':[-size/2,size/2],'placement_constraints':'Road/river exclusion, bounded spacing and count','_files':['world-layout.json']}
