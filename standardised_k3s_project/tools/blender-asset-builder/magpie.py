import bpy, bmesh, math, json, sys, random, shutil
from pathlib import Path
from mathutils import Vector
import numpy as np

ROOT=Path(sys.argv[sys.argv.index('--')+1]); ROOT.mkdir(parents=True,exist_ok=True)
for folder in ['source','textures','renders','game-ready','reports']: (ROOT/folder).mkdir(exist_ok=True)
shutil.copyfile(__file__,ROOT/'source'/'build_script.py')
STATE=ROOT/'reports'; STATE.mkdir(exist_ok=True)
random.seed(71)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.unit_settings.system='METRIC'
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8
scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=4
scene.render.resolution_x=384;scene.render.resolution_y=384;scene.render.resolution_percentage=100
scene.world.color=(.16,.16,.16)
scene.view_settings.view_transform='AgX'
collections={}
for name in ['01_Anatomy','02_Face','03_Wing_L','04_Wing_R','05_Tail','06_Legs_Feet','07_Contour_Plumage','90_Studio']:
    c=bpy.data.collections.new(name);scene.collection.children.link(c);collections[name]=c
def move(o,c):
    for old in list(o.users_collection):old.objects.unlink(o)
    collections[c].objects.link(o)
def material(name,color,rough=.5,metal=0):
    m=bpy.data.materials.new(name);m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal
    return m
black=material('Plumage | charcoal satin',(.018,.024,.03),.48)
white=material('Plumage | ivory',(.78,.79,.75),.62)
silver=material('Bill | cool bone-grey',(.41,.49,.53),.36)
tip=material('Bill tip | charcoal',(.025,.029,.032),.38)
skin=material('Tarsus | graphite scales',(.012,.016,.017),.68)
claw=material('Claws | horn',(.019,.022,.024),.42)
iris=material('Iris | deep chestnut',(.13,.037,.012),.27)
pupil=material('Pupil | obsidian',(.002,.003,.004),.12)
def finish(o,name,mat,c):
    o.name=name;move(o,c);o.data.materials.append(mat)
    if o.type=='MESH':
        for p in o.data.polygons:p.use_smooth=True
    return o
def ellipsoid(name,loc,scale,mat,c='01_Anatomy',segments=24,rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments,ring_count=rings,location=loc)
    o=bpy.context.object;o.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(o,name,mat,c)
def mesh(name,verts,faces,mat,c,uv=None):
    d=bpy.data.meshes.new(name);d.from_pydata(verts,[],faces);d.update()
    o=bpy.data.objects.new(name,d);collections[c].objects.link(o);d.materials.append(mat)
    for p in d.polygons:p.use_smooth=True
    bm=bmesh.new();bm.from_mesh(d);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(d);bm.free()
    if uv:
        layer=d.uv_layers.new(name='FeatherUV')
        for p in d.polygons:
            for li in p.loop_indices:layer.data[li].uv=uv[d.loops[li].vertex_index]
    return o
def tube(name,points,radii,mat,c='06_Legs_Feet',sides=10):
    ps=[Vector(p) for p in points];v=[];f=[]
    for i,p in enumerate(ps):
        tangent=(ps[min(i+1,len(ps)-1)]-ps[max(0,i-1)]).normalized()
        u=tangent.cross(Vector((1,0,0)))
        if u.length<.1:u=tangent.cross(Vector((0,1,0)))
        u.normalize();w=tangent.cross(u).normalized()
        for j in range(sides):v.append(p+radii[i]*(math.cos(j*2*math.pi/sides)*u+math.sin(j*2*math.pi/sides)*w))
    for i in range(len(ps)-1):
        for j in range(sides):a=i*sides+j;b=i*sides+(j+1)%sides;f.append((a,b,b+sides,a+sides))
    f.append(tuple(range(sides-1,-1,-1)));f.append(tuple((len(ps)-1)*sides+j for j in range(sides)))
    return mesh(name,v,f,mat,c)
def aim(o,at):o.rotation_euler=(Vector(at)-o.location).to_track_quat('-Z','Y').to_euler()
def checkpoint(wp):
    p=ROOT/'source'/f'{wp}.blend';bpy.ops.wm.save_as_mainfile(filepath=str(p))
    with (STATE/'progress.md').open('a') as out:out.write(f'\n{wp} saved: {p}\n')
    (STATE/'handoff.md').write_text(f'# Handoff\nLast saved {wp}: {p}\nBuild script /data/ai/helper-scripts/build_magpie_character.py. Check live task process and reports before resuming. CPU only. Game and inference unchanged.\n')
    return p

# Continuous torso and neck with a unioned head. Z up, forward -Y, real metres.
body=ellipsoid('Torso',(0,.015,.191),(.047,.085,.072),black)
body.rotation_euler.x=math.radians(-24)
neck=ellipsoid('Neck',(0,-.035,.260),(.034,.041,.046),black)
head=ellipsoid('Head',(0,-.073,.305),(.032,.042,.029),black)
chest=ellipsoid('Chest transition',(0,-.029,.232),(.040,.052,.056),black)
bpy.ops.object.select_all(action='DESELECT')
for o in [body,neck,head,chest]:o.select_set(True)
bpy.context.view_layer.objects.active=body;bpy.ops.object.join()
body.name='Torso_Neck_Head | continuous skin'
mod=body.modifiers.new('Anatomical union','REMESH');mod.mode='VOXEL';mod.voxel_size=.002
bpy.ops.object.modifier_apply(modifier=mod.name)
mod=body.modifiers.new('Smooth anatomical transitions','SMOOTH');mod.factor=.8;mod.iterations=16
bpy.ops.object.modifier_apply(modifier=mod.name)
mod=body.modifiers.new('Final surface','SUBSURF');mod.levels=1
bpy.ops.object.modifier_apply(modifier=mod.name)
body.data.materials.clear();body.data.materials.append(black);body.data.materials.append(white)
for p in body.data.polygons:
    co=body.matrix_world@p.center
    # White nape behind crown, and white rump, retaining the black saddle.
    if (co.z>.263 and co.y>-.044+max(0,co.z-.302)*.9) or (co.y>.068 and .178<co.z<.237):p.material_index=1
    p.use_smooth=True
bpy.context.view_layer.objects.active=body;body.select_set(True)
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.sphere_project();bpy.ops.object.mode_set(mode='OBJECT')

def bill(name,upper):
    v=[];f=[];uv=[];N=20;S=16
    for i in range(N+1):
        t=i/N;y=-.104-.065*t
        width=.013*(1-t)**.75+.00015
        height=(.016 if upper else .006)*(1-t)**.8+.00015
        z=.300-.009*t+.002*math.sin(t*math.pi)
        if not upper:z-=.001
        for j in range(S):
            a=j/S*2*math.pi;sn=math.sin(a)
            dz=(max(sn,0)*height+min(sn,0)*.0004) if upper else (min(sn,0)*height+max(sn,0)*.0003)
            v.append((width*math.cos(a),y,z+dz));uv.append((j/S,t))
    for i in range(N):
        for j in range(S):a=i*S+j;b=i*S+(j+1)%S;f.append((a,b,b+S,a+S))
    f.extend([tuple(range(S-1,-1,-1)),tuple(N*S+j for j in range(S))])
    o=mesh(name,v,f,silver,'02_Face',uv);o.data.materials.append(tip)
    for p in o.data.polygons:
        if p.center.y<-.151:p.material_index=1
    return o
bill('Beak_Upper',True);bill('Beak_Lower',False)
for s,side in [(-1,'L'),(1,'R')]:
    tube('Leg_'+side,[(s*.023,.031,.145),(s*.024,.034,.099),(s*.024,.010,.031),(s*.024,.007,.019)],[.005,.0042,.0033,.0041],skin)
    for k,spread in enumerate([-.018,0,.018]):
        x=s*.024;end=(x+spread,-.040-(.009 if k==1 else 0),.007)
        tube(f'Toe_{side}_{k+1}',[(x,.007,.018),(x+spread*.48,-.016,.010),end],[.0032,.0026,.0015],skin)
    tube('Hallux_'+side,[(s*.024,.011,.018),(s*.024-s*.008,.038,.010),(s*.024-s*.012,.049,.007)],[.0026,.002,.0014],skin)

floor=material('Studio | warm slate',(.095,.12,.13),.83)
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,0));finish(bpy.context.object,'Ground',floor,'90_Studio')
world=scene.world;world.use_nodes=True;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.16,.19,.23,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.5
for name,loc,power,size,color in [('Key',(.35,-.4,.7),35,.4,(1,.89,.76)),('Fill',(-.4,-.2,.4),18,.4,(.72,.84,1)),('Rim',(.15,.4,.55),45,.3,(.87,.94,1))]:
    d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='DISK';d.size=size;d.color=color
    o=bpy.data.objects.new(name,d);collections['90_Studio'].objects.link(o);o.location=loc;aim(o,(0,0,.19))
d=bpy.data.cameras.new('AssetCamera');camera=bpy.data.objects.new('AssetCamera',d);collections['90_Studio'].objects.link(camera);scene.camera=camera
camera.location=(.6,-.8,.43);aim(camera,(0,.045,.185));d.type='ORTHO';d.ortho_scale=.49
checkpoint('WP1_base_anatomy')
scene.render.resolution_x=512;scene.render.resolution_y=512;scene.cycles.samples=16
scene.render.filepath=str(ROOT/'renders'/'WP1_silhouette.png');bpy.ops.render.render(write_still=True)

# Closed feather blades. Their UVs encode vane direction; thin lens cross-section.
def feather(name,start,end,width,mat,c,normal=(1,0,0),white_base=False):
    start=Vector(start);end=Vector(end);axis=(end-start).normalized();norm=Vector(normal).normalized()
    across=axis.cross(norm).normalized();norm=across.cross(axis).normalized()
    small=(end-start).length<.024
    verts=[];faces=[];uv=[];N=12 if small else 22;S=8 if small else 12
    for i in range(N+1):
        t=i/N;ctr=start.lerp(end,t)+norm*((.00045 if small else .0025)*math.sin(math.pi*t))
        profile=(math.sin(math.pi*(.045+.935*t))**.65)*(.85+.15*t)
        if i in [0,N]:profile=.045
        for j in range(S):
            a=j/S*math.tau;u=math.cos(a)
            w=width*profile*(.86 if u<0 else 1)
            verts.append(ctr+across*u*w+norm*math.sin(a)*((.00010+.0001*profile) if small else (.00042+.0006*profile)))
            uv.append(((u+1)/2,t))
    for i in range(N):
        for j in range(S):a=i*S+j;b=i*S+(j+1)%S;faces.append((a,b,b+S,a+S))
    faces +=[tuple(range(S-1,-1,-1)),tuple(N*S+j for j in range(S))]
    o=mesh(name,verts,faces,mat,c,uv)
    if white_base:
        o.data.materials.append(white)
        for p in o.data.polygons:
            if sum(uv[k][1] for k in p.vertices)/len(p.vertices)<.72:p.material_index=1
    return o
for s,side in [(-1,'L'),(1,'R')]:
    c='03_Wing_L' if s==-1 else '04_Wing_R'
    o=ellipsoid('Wing_'+side+' | folded foundation',(s*.039,.033,.216),(.008,.058,.045),black,c)
    o.rotation_euler.x=math.radians(-28)
    for i in range(9):
        feather(f'{side}_Primary_{i+1:02}',(s*(.042+.0005*i),-.002+i*.005,.226-i*.004),(s*(.055+.0003*i),.130+i*.0015,.132+i*.004),.007,black,c,(s,0,0))
    for i in range(8):
        feather(f'{side}_Secondary_{i+1:02}',(s*.035,-.005+i*.008,.249-i*.003),(s*.057,.063+i*.007,.179+i*.001),.008,black,c,(s,0,0))
    for i in range(8):
        feather(f'{side}_Median_{i+1:02}',(s*.042,-.022+i*.006,.222-i*.002),(s*.060,.025+i*.006,.173+i*.001),.006,black,c,(s,0,0))
    for row in range(3):
        for i in range(9-row):
            start=(s*(.028+row*.004),-.018+i*.009,.266-row*.014-i*.002)
            end=(s*(.050+row*.002),start[1]+.035,start[2]-.025)
            feather(f'{side}_Covert_{row}_{i:02}',start,end,.0055,white if row<2 else black,c,(s,0,0))
    for i in range(5):
        feather(f'{side}_Scapular_{i:02}',(s*(.022+i*.005),.006,.275),(s*(.033+i*.005),.061,.244-i*.002),.005,black,c,(s,0,.8))
    for o in collections[c].objects:o.location.z-=.009
for i in range(12):
    x=(i-5.5)*.0042
    feather(f'Tail_Rectrix_{i+1:02}',(x*.62,.076,.191),(x*1.2,.246-.017*abs(i-5.5)/5.5,.105),.0057,black,'05_Tail',(0,0,1),False)
for s,side in [(-1,'L'),(1,'R')]:
    ellipsoid('Thigh_'+side,(s*.023,.026,.132),(.014,.021,.023),black)
    # Iris sits in a small dark orbital rim, natural size rather than cartoon eyes.
    ellipsoid('Orbital_rim_'+side,(s*.0283,-.080,.312),(.0048,.0058,.0056),black,'02_Face')
    ellipsoid('Eye_'+side,(s*.0314,-.081,.312),(.0025,.0041,.0041),iris,'02_Face')
    ellipsoid('Pupil_'+side,(s*.0334,-.0818,.312),(.0009,.0023,.0025),pupil,'02_Face')
    ellipsoid('Nostril_'+side,(s*.0095,-.117,.306),(.0008,.0022,.001),tip,'02_Face',24,12)
    for k,spread in enumerate([-.018,0,.018]):
        end=Vector((s*.024+spread,-.040-(.009 if k==1 else 0),.007))
        tube(f'Claw_{side}_{k+1}',[end,end+Vector((0,-.004,.002)),end+Vector((0,-.010,-.003))],[.0017,.0013,.00015],claw)
    end=Vector((s*.024-s*.012,.049,.007));tube('Hallux_claw_'+side,[end,end+Vector((-s*.002,.005,.001)),end+Vector((-s*.003,.010,-.003))],[.0014,.001,.00015],claw)
    # Overlapping tarsal plates retain silhouette and catch soft light.
    for i in range(11):
        t=i/11;z=.037+t*.057;y=.010+t*.022
        ellipsoid(f'Scale_{side}_{i:02}',(s*.024,y-.0032,z),(.0035,.001,.0019),skin,'06_Legs_Feet',16,8)
# Small overlapping contour feather tips break the smooth toy-like breast and nape.
polys=list(body.data.polygons)
centers=np.array([tuple(body.matrix_world@p.center) for p in polys],dtype=np.float32)
normals=np.array([tuple((body.matrix_world.to_3x3()@p.normal).normalized()) for p in polys],dtype=np.float32)
seen=set();candidates=[]
for i,(co,n) in enumerate(zip(centers,normals)):
    exposed=((n[1]<-.4 and .145<co[2]<.272) or (co[1]>-.035 and co[2]>.266) or (co[1]>.068 and co[2]>.178))
    if not exposed:continue
    key=tuple(np.floor(co/.008).astype(int))
    if key in seen:continue
    seen.add(key);candidates.append(i)
candidates=[] # Surface-tip experiment rejected in run 05; keep the continuous contour texture.
for count,i in enumerate(candidates):
    co=Vector(centers[i]);n=Vector(normals[i]);direction=Vector((0,.004,-.012))
    direction-=n*direction.dot(n)
    if direction.length<.004:continue
    direction.normalize();target=co+direction*.012
    j=int(np.argmin(np.sum((centers-np.array(target))**2,axis=1)))
    end=Vector(centers[j])+Vector(normals[j])*.0005
    start=co+n*.0005
    if (end-start).length<.006:continue
    mat=white if polys[i].material_index==1 else black
    feather('Contour_'+str(count),start,end,.0034,mat,'07_Contour_Plumage',n)
checkpoint('WP2_geometry_detail')

# Portable image-backed PBR maps, created from scratch. No procedural-only GLB shaders.
N=256
u,v=np.meshgrid(np.linspace(0,1,N,dtype=np.float32),np.linspace(0,1,N,dtype=np.float32))
rng=np.random.default_rng(71)
phase=(v*160+np.abs(u-.5)*80)*math.tau
barbs=np.sin(phase)*.5+.5
shaft=np.exp(-((u-.5)/.018)**2)
noise=rng.random((N,N),dtype=np.float32)
variation=.78+.12*barbs+.10*noise+.09*shaft
def image_file(name,rgb,noncolor=False):
    im=bpy.data.images.new(name,width=N,height=N,alpha=True)
    if noncolor:im.colorspace_settings.name='Non-Color'
    rgba=np.ones((N,N,4),dtype=np.float32);rgba[:,:,:3]=rgb
    im.pixels.foreach_set(rgba.ravel());im.filepath_raw=str(ROOT/'textures'/(name+'.png'));im.file_format='PNG'
    im.save();im.pack();return im
dark_img=image_file('feather_charcoal_basecolor',variation[:,:,None]*np.array([.065,.080,.095],dtype=np.float32)[None,None,:])
white_img=image_file('feather_ivory_basecolor',variation[:,:,None]*np.array([.88,.87,.82],dtype=np.float32)[None,None,:])
h=.018*np.sin(phase)+.02*shaft
dy,dx=np.gradient(h);norm=np.stack([-dx*28,-dy*28,np.ones_like(h)],axis=-1);norm/=np.linalg.norm(norm,axis=-1,keepdims=True)
normal_img=image_file('feather_vane_normal',norm*.5+.5,True)
rough_img=image_file('feather_roughness',np.repeat((.5+.12*noise+.06*barbs)[:,:,None],3,axis=2),True)
for mat,im in [(black,dark_img),(white,white_img)]:
    nt=mat.node_tree;p=nt.nodes.get('Principled BSDF')
    tex=nt.nodes.new('ShaderNodeTexImage');tex.image=im;nt.links.new(tex.outputs['Color'],p.inputs['Base Color'])
    tex=nt.nodes.new('ShaderNodeTexImage');tex.image=rough_img;nt.links.new(tex.outputs['Color'],p.inputs['Roughness'])
    tex=nt.nodes.new('ShaderNodeTexImage');tex.image=normal_img
    nm=nt.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.12;nt.links.new(tex.outputs['Color'],nm.inputs['Color']);nt.links.new(nm.outputs['Normal'],p.inputs['Normal'])
    p.inputs['Specular IOR Level'].default_value=.22
# Body contour plumage has many small feather tips, distinct from long flight-feather vanes.
row=np.floor(v*32);col=u*22+((row%2)*.5)
fx=col%1-.5;fy=(v*32)%1
curve=.63-.50*(np.abs(fx)*2)**1.7
edge=np.exp(-((fy-curve)/.028)**2)
body_var=.85+.035*noise-.065*edge
body_img=image_file('body_charcoal_basecolor',body_var[:,:,None]*np.array([.047,.057,.067],dtype=np.float32)[None,None,:])
body_h=.004*edge
dy,dx=np.gradient(body_h);bn=np.stack([-dx*10,-dy*10,np.ones_like(body_h)],axis=-1);bn/=np.linalg.norm(bn,axis=-1,keepdims=True)
body_normal=image_file('body_contour_normal',bn*.5+.5,True)
bodymat=black.copy();bodymat.name='Body | soft contour plumage'
for node in bodymat.node_tree.nodes:
    if node.type=='TEX_IMAGE' and node.image==dark_img:node.image=body_img
    elif node.type=='TEX_IMAGE' and node.image==normal_img:node.image=body_normal
    elif node.type=='NORMAL_MAP':node.inputs['Strength'].default_value=.3
body.data.materials[0]=bodymat
napemat=white.copy();napemat.name='Nape | soft ivory contour'
for node in napemat.node_tree.nodes:
    if node.type=='TEX_IMAGE' and node.image==normal_img:node.image=body_normal
body.data.materials[1]=napemat
# Join by functional feather group for browser draw-call efficiency; individual blades remain disconnected editable islands.
for c in ['03_Wing_L','04_Wing_R','05_Tail','06_Legs_Feet','07_Contour_Plumage']:
    keys=['Primary','Secondary','Median','Covert','Scapular'] if 'Wing' in c else (['Rectrix'] if 'Tail' in c else (['Contour'] if 'Contour' in c else ['Scale']))
    for key in keys:
        group=[o for o in list(collections[c].objects) if key in o.name and o.type=='MESH']
        if len(group)>1:
            bpy.ops.object.select_all(action='DESELECT')
            for o in group:o.select_set(True)
            bpy.context.view_layer.objects.active=group[0];bpy.ops.object.join();group[0].name=c+'_'+key+'_group'
checkpoint('WP3_materials')

asset=[o for o in scene.objects if o.type=='MESH' and collections['90_Studio'] not in o.users_collection]
# Put origin of every runtime component on the ground-centred character origin and apply transforms.
bpy.ops.object.select_all(action='DESELECT')
for o in asset:o.select_set(True)
bpy.context.view_layer.objects.active=body
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
scene.cursor.location=(0,0,0);bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
for o in asset:o['rigging_note']='Neutral folded pose; unrigged. Bind continuous skin and feather groups separately; split islands for feather controls if needed.'
def stats(objs):
    r={'objects':len(objs),'vertices':0,'triangles':0,'nonmanifold_edges':0,'zero_area_faces':0,'nonfinite_coordinates':0,'missing_uv_objects':[],'negative_volume_objects':[]}
    for o in objs:
        d=o.data;d.calc_loop_triangles();r['vertices']+=len(d.vertices);r['triangles']+=len(d.loop_triangles)
        r['nonfinite_coordinates']+=sum(not all(math.isfinite(x) for x in v.co) for v in d.vertices)
        bm=bmesh.new();bm.from_mesh(d);r['nonmanifold_edges']+=sum(not e.is_manifold for e in bm.edges);r['zero_area_faces']+=sum(f.calc_area()<1e-12 for f in bm.faces)
        if bm.calc_volume(signed=True)<0:r['negative_volume_objects'].append(o.name)
        bm.free()
        if not d.uv_layers:r['missing_uv_objects'].append(o.name)
    coords=[o.matrix_world@v.co for o in objs for v in o.data.vertices]
    r['bounds']=[[min(p[i] for p in coords),max(p[i] for p in coords)] for i in range(3)]
    return r
# All remaining meshes get UVs for future painting; constant materials don't need textures.
for o in asset:
    if not o.data.uv_layers:
        bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project();bpy.ops.object.mode_set(mode='OBJECT')
# WatooM repair: reduce body mesh budget and give closed end-caps real UV area.
bpy.ops.object.select_all(action='DESELECT')
bpy.context.view_layer.objects.active=body;body.select_set(True)
mod=body.modifiers.new('Runtime budget','DECIMATE');mod.ratio=.55
bpy.ops.object.modifier_apply(modifier=mod.name)
for ob in asset:
    me=ob.data
    uv=me.uv_layers.active
    if uv is None:continue
    for poly in me.polygons:
        loops=list(poly.loop_indices);points=[uv.data[i].uv for i in loops]
        area=abs(sum(points[i].x*points[(i+1)%len(points)].y-points[(i+1)%len(points)].x*points[i].y for i in range(len(points))))
        if area<1e-12:
            axis=max(range(3),key=lambda i:abs(poly.normal[i]));axes=[i for i in range(3) if i!=axis]
            for li in loops:
                co=me.vertices[me.loops[li].vertex_index].co
                uv.data[li].uv=(.5+co[axes[0]],.5+co[axes[1]])

# WatooM final repair: union intersecting wing layers; transfer plumage materials.
from mathutils.kdtree import KDTree
for coll in ['03_Wing_L','04_Wing_R']:
    group=[o for o in collections[coll].objects if o.type=='MESH']
    points=[];mats=[]
    for ob in group:
        for poly in ob.data.polygons:
            points.append((ob.matrix_world@poly.center,ob.data.materials[poly.material_index]))
    kd=KDTree(len(points))
    for i,(co,ma) in enumerate(points):kd.insert(co,i)
    kd.balance()
    bpy.ops.object.select_all(action='DESELECT')
    for ob in group:ob.select_set(True)
    ob=group[0];bpy.context.view_layer.objects.active=ob;bpy.ops.object.join();ob.name=coll+'_unified_feathers'
    mod=ob.modifiers.new('Feather layer union','REMESH');mod.mode='VOXEL';mod.voxel_size=.00055
    bpy.ops.object.modifier_apply(modifier=mod.name)
    mod=ob.modifiers.new('Wing budget','DECIMATE');mod.ratio=.12;bpy.ops.object.modifier_apply(modifier=mod.name)
    ob.data.materials.clear()
    for ma in [black,white]:ob.data.materials.append(ma)
    for poly in ob.data.polygons:
        _,i,_=kd.find(ob.matrix_world@poly.center);poly.material_index=1 if points[i][1]==white else 0;poly.use_smooth=True
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project();bpy.ops.object.mode_set(mode='OBJECT')
asset=[o for o in scene.objects if o.type=='MESH' and collections['90_Studio'] not in o.users_collection]
bpy.ops.object.select_all(action='DESELECT')
for ob in asset:ob.select_set(True)
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
source_stats=stats(asset)
bpy.ops.object.select_all(action='DESELECT')
for o in asset:o.select_set(True)
glb=ROOT/'game-ready'/'australian_magpie.glb'
bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',use_selection=True,export_yup=True,export_apply=True)
final=checkpoint('WP4_export')
(ROOT/'reports'/'source-stats.json').write_text(json.dumps(source_stats,indent=2))
# Reimport in a distinct scene; do not replace the authoring scene.
original_scene=scene
bpy.ops.scene.new(type='NEW');test_scene=bpy.context.scene
bpy.ops.import_scene.gltf(filepath=str(glb));imported=[o for o in test_scene.objects if o.type=='MESH']
reimport_stats=stats(imported)
report={'source':source_stats,'reimport':reimport_stats,'glb_bytes':glb.stat().st_size,'blender':bpy.app.version_string,'glb_reimport':'PASS' if imported and not reimport_stats['nonfinite_coordinates'] else 'FAIL','rigged':False,'animated':False,'orientation':'Source Z up, forward -Y; glTF Y up, forward +Z','texture_files':[p.name for p in (ROOT/'textures').glob('*.png')],'missing_image_files':[im.filepath for im in bpy.data.images if im.source=='FILE' and not im.packed_file and not Path(bpy.path.abspath(im.filepath)).exists()]}
(ROOT/'reports'/'validation.json').write_text(json.dumps(report,indent=2))
bpy.context.window.scene=original_scene;bpy.data.scenes.remove(test_scene)
bpy.ops.outliner.orphans_purge(do_recursive=True)
scene=original_scene
checkpoint('WP4_validated')
scene.render.resolution_x=384;scene.render.resolution_y=384;scene.cycles.samples=8
views={'front':(0,-1,.21),'side':(1,.045,.21),'rear':(0,1,.21),'top':(0,.045,1),'three_quarter':(.7,-1,.46)}
for name,loc in views.items():
    camera.location=loc;aim(camera,(0,.045,.18));camera.data.ortho_scale=.48
    scene.render.filepath=str(ROOT/'renders'/(name+'.png'));bpy.ops.render.render(write_still=True)
camera.location=(.65,-1,.46);aim(camera,(0,.045,.185));camera.data.ortho_scale=.46
scene.render.resolution_x=512;scene.render.resolution_y=512;scene.cycles.samples=16
scene.render.filepath=str(ROOT/'renders'/'beauty.png');bpy.ops.render.render(write_still=True)
checkpoint('WP5_rendered')
(ROOT/'reports'/'COMPLETE').write_text('Rendering complete; visual acceptance pending human/model image review.\n')
print('ASSET_BUILD_COMPLETE',ROOT,flush=True)
