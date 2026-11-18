"""Bounded metadata-only indexing of the existing read-only creative library."""
import contextlib,fcntl,hashlib,json,os,pathlib,re,time,zipfile
FORMATS={'.uasset','.umap','.uexp','.ubulk','.glb','.gltf','.fbx','.obj','.blend','.png','.jpg','.jpeg','.tif','.tiff','.exr','.wav','.ogg','.mp3','.stl','.mtl','.uproject','.uplugin','.zip','.rar','.mhpkg'}
EXCLUDE={'unreal-engine','.git','Intermediate','DerivedDataCache','Saved','node_modules','.godot','Binaries'}
CATEGORIES={'terrain':['terrain','landscape','heightmap'],'buildings':['building','architecture','house','castle'],'foliage':['foliage','forest','tree','grass','vegetation'],'rocks':['rock','stone','cliff'],'wildlife':['wildlife','bird','magpie','wombat','squirrel','creature'],'characters':['character','chars','knight','warrior','human','body'],'skeletons':['skeleton','rig','armature'],'animations':['animation','anim','walk','run','idle'],'materials':['material','shader','pbr'],'textures':['texture','texters','albedo','roughness','normal'],'audio':['audio','sound','music'],'props':['prop','furniture','weapon']}
def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.new')
    with tmp.open('w') as f:json.dump(value,f,separators=(',',':'));f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def safe(root,relative):
    if not isinstance(relative,str) or not relative or chr(92) in relative or pathlib.PurePosixPath(relative).is_absolute() or any(p in ('..','.') for p in relative.split('/')):raise ValueError('Invalid library reference')
    path=root/relative
    if not path.resolve(strict=True).is_relative_to(root.resolve()):raise ValueError('Library reference escapes asset root')
    return path
def checksum(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
class Catalog:
    def __init__(self,root,state):
        self.root=pathlib.Path(root);self.state=pathlib.Path(state)
    def load(self):
        if not self.state.exists():return {'schema':1,'root':str(self.root),'cursor':'','records':{},'scan':0}
        if self.state.stat().st_size>128*1024**2:raise ValueError('Catalog metadata limit reached')
        result=json.loads(self.state.read_text())
        if result['schema']!=1 or result['root']!=str(self.root):raise ValueError('Catalog root/schema mismatch')
        return result
    def metadata(self,relative,path):
        name=relative.lower();suffix=path.suffix.lower();parts=pathlib.PurePosixPath(relative).parts
        stat=path.stat();result={'metadata_version':2,'sidecar_mtime_ns':0,'id':'ast_'+hashlib.sha256(relative.encode()).hexdigest()[:24],'path':relative,'source_pack':'/'.join(parts[:2]),'format':suffix[1:],'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns,'categories':[category for category,words in CATEGORIES.items() if any(word in name for word in words)] or ['props'],'sha256':None,'checksum_state':'DEFERRED','dependencies':[],'dependency_state':'NOT_INSPECTED','engine_compatibility':{'unreal':'UNVERIFIED','godot':'UNVERIFIED'},'license':{'status':'UNVERIFIED','restriction':'Internal authorized project use only; review source license before distribution'},'preview':relative if suffix in {'.png','.jpg','.jpeg'} else None}
        if suffix in {'.glb','.gltf'}:result['engine_compatibility']['format']='glTF 2.0; import acceptance required'
        if suffix=='.mhpkg':
            result['categories']=sorted(set(result['categories']+['characters']))
            result['engine_compatibility']['format']='MetaHuman package; import through installed MetaHuman workflow; acceptance required'
            result['engine_compatibility']['godot']='SOURCE_PACKAGE_NOT_DIRECTLY_IMPORTABLE'
        pack=self.root.joinpath(*parts[:2])
        for filename in ['LICENSE','LICENSE.txt','LICENSE.md','SOURCE_AND_LICENSE.md']:
            candidate=pack/filename
            if candidate.is_file() and candidate.stat().st_size<65536 and candidate.resolve().is_relative_to(self.root.resolve()):
                result['license']={'status':'SOURCE_TEXT_AVAILABLE','path':str(candidate.relative_to(self.root)),'excerpt':candidate.read_text(errors='replace')[:1500]};break
        if suffix=='.gltf' and stat.st_size<2*1024**2:
            try:
                document=json.loads(path.read_text())
                references=[x['uri'] for k in ['buffers','images'] for x in document.get(k,[]) if isinstance(x.get('uri'),str) and not x['uri'].startswith('data:')]
                result['dependencies']=[value[:512] for value in references[:64]]
                result['dependency_references_truncated']=len(references)>64 or any(len(value)>512 for value in references[:64])
                result['dependency_state']='REFERENCES_ONLY'
            except (ValueError,UnicodeError):result['dependency_state']='INVALID_JSON'
        if suffix in {'.uproject','.uplugin'} and stat.st_size<65536:
            try:result['engine_compatibility']['unreal']=json.loads(path.read_text()).get('EngineAssociation','UNVERIFIED')
            except (ValueError,UnicodeError):pass
        manifest=path.parent/'manifest.json'
        if suffix in {'.glb','.gltf','.blend','.fbx','.obj'} and manifest.is_file() and manifest.stat().st_size<=1024*1024 and manifest.resolve().is_relative_to(self.root.resolve()):
            result['sidecar_mtime_ns']=manifest.stat().st_mtime_ns
            try:
                info=json.loads(manifest.read_text())
                generator=info.get('generator_id','')
                clips=info.get('animations',[])
                if isinstance(generator,str) and isinstance(clips,list):
                    result['source_metadata']={'manifest':str(manifest.relative_to(self.root)),'manifest_mtime_ns':manifest.stat().st_mtime_ns,'generator':generator[:256],'animations':[value[:128] for value in clips[:64] if isinstance(value,str)],'evidence':'source annotations; current import/rig validation still required'}
                    style=info.get('input_manifest',{}).get('style') if isinstance(info.get('input_manifest'),dict) else None
                    if isinstance(style,str):result['source_metadata']['style']=style[:128]
                    words=(generator+' '+str(style or '')+' '+' '.join(value for value in clips if isinstance(value,str))).lower()
                    result['categories']=sorted(set(result['categories']+[category for category,tags in CATEGORIES.items() if any(tag in words for tag in tags)]))
                    if isinstance(info.get('skin_count'),int) and info['skin_count']>0:result['categories']=sorted(set(result['categories']+['characters','skeletons']))
                    if clips:result['categories']=sorted(set(result['categories']+['animations']))
                    preview=path.parent/'perspective.png'
                    if preview.is_file() and preview.resolve().is_relative_to(self.root.resolve()):result['preview']=str(preview.relative_to(self.root))
            except (OSError,ValueError,UnicodeError):result['source_metadata_state']='UNREADABLE'
        return result
    def index(self,limit=256,hash_budget=32*1024**2,seconds=4):
        if type(limit) is not int or not 1<=limit<=1024:raise ValueError('Index limit must be 1..1024')
        self.state.parent.mkdir(parents=True,exist_ok=True)
        with (self.state.parent/'asset-catalog.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            data=self.load();start=time.monotonic();used=0;processed=0;errors=[];paths=[]
            def error(e):errors.append({'path':e.filename,'error':type(e).__name__})
            for directory,dirs,files in os.walk(self.root,followlinks=False,onerror=error):
                dirs[:]=sorted(d for d in dirs if d not in EXCLUDE)
                for filename in sorted(files):
                    path=pathlib.Path(directory)/filename
                    if path.suffix.lower() in FORMATS:paths.append(str(path.relative_to(self.root)))
                if len(paths)>100000:raise ValueError('Library scan metadata budget reached')
            paths.sort();remaining=[x for x in paths if x>data['cursor']]
            for relative in remaining:
                if processed>=limit or time.monotonic()-start>seconds:break
                try:
                    path=safe(self.root,relative);stat=path.stat();key='ast_'+hashlib.sha256(relative.encode()).hexdigest()[:24]
                    old=data['records'].get(key)
                    unchanged=old and old['mtime_ns']==stat.st_mtime_ns and old['bytes']==stat.st_size
                    manifest=path.parent/'manifest.json'
                    sidecar_mtime=manifest.stat().st_mtime_ns if path.suffix.lower() in {'.glb','.gltf','.blend','.fbx','.obj'} and manifest.is_file() and manifest.stat().st_size<=1024*1024 and manifest.resolve().is_relative_to(self.root.resolve()) else 0
                    annotation_current=not old or old.get('sidecar_mtime_ns',0)==sidecar_mtime
                    if unchanged and old.get('metadata_version')==2 and annotation_current:record=old
                    else:
                        record=self.metadata(relative,path)
                        if unchanged and old.get('sha256') is not None:record['sha256']=old['sha256'];record['checksum_state']=old['checksum_state']
                    if record['sha256'] is None and stat.st_size<=hash_budget-used:
                        record['sha256']=checksum(path);record['checksum_state']='VERIFIED';used+=stat.st_size
                    data['records'][key]=record
                except (OSError,ValueError) as e:errors.append({'path':relative,'error':type(e).__name__})
                data['cursor']=relative;processed+=1
            complete=not remaining or processed==len(remaining)
            if complete:
                current=set(paths);data['records']={k:v for k,v in data['records'].items() if v['path'] in current}
                data['cursor']='';data['scan']+=1
            if self.state.exists():
                # Preserve exact prior metadata before replacement; source assets are never changed.
                atomic(self.state.with_suffix('.previous.json'),self.load())
            atomic(self.state,data)
            return {'status':'PASS' if not errors else 'WARN','indexed':len(data['records']),'processed':processed,'scan_complete':complete,'scan':data['scan'],'hashed_bytes':used,'deferred_checksums':sum(v['sha256'] is None for v in data['records'].values()),'errors':errors[:32]}
    def index_selected(self,relatives,hash_budget=512*1024**2):
        """Register a bounded inspected dependency closure in this same global catalog."""
        if not isinstance(relatives,list) or not 1<=len(relatives)<=256 or len(set(relatives))!=len(relatives):
            raise ValueError("Select1..256unique library paths")
        if type(hash_budget) is not int or not 0<=hash_budget<=1024**3:
            raise ValueError("Selected checksum budget exceeded")
        self.state.parent.mkdir(parents=True,exist_ok=True)
        with (self.state.parent/'asset-catalog.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            data=self.load();selected=[];used=0
            for relative in relatives:
                path=safe(self.root,relative);stat=path.stat()
                if path.suffix.lower() not in FORMATS:raise ValueError("Unsupported selected format")
                key='ast_'+hashlib.sha256(relative.encode()).hexdigest()[:24]
                old=data["records"].get(key)
                unchanged=old and old["mtime_ns"]==stat.st_mtime_ns and old["bytes"]==stat.st_size
                record=old.copy() if unchanged and old.get("metadata_version")==2 else self.metadata(relative,path)
                if record.get("sha256") is None:
                    if stat.st_size>hash_budget-used:raise ValueError("Selected checksum budget exceeded")
                    record["sha256"]=checksum(path);record["checksum_state"]="VERIFIED";used+=stat.st_size
                    after=path.stat()
                    if (after.st_size,after.st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):raise ValueError("Selected source changed during inspection")
                data["records"][key]=record;selected.append(key)
            if self.state.exists():atomic(self.state.with_suffix(".previous.json"),self.load())
            atomic(self.state,data)
            return {"status":"PASS","ids":selected,"hashed_bytes":used,"indexed":len(data["records"])}
    def search(self,query='',category=None,format=None,limit=32):
        if not isinstance(query,str) or len(query)>256 or not 1<=limit<=64:raise ValueError('Invalid catalog search')
        records=self.load()['records'].values();terms=query.casefold().split()
        return [v for v in sorted(records,key=lambda x:x['path']) if all(t in (v['path']+' '+' '.join(v['categories'])+' '+json.dumps(v.get('source_metadata',{}),sort_keys=True)).casefold() for t in terms) and (not category or category in v['categories']) and (not format or format.lower().lstrip('.')==v['format'])][:limit]
    def resolve(self,asset_id):
        if not isinstance(asset_id,str) or not re.fullmatch('ast_[a-f0-9]{24}',asset_id):raise ValueError('Catalog asset ID required')
        record=self.load()['records'].get(asset_id)
        if not record:raise ValueError('Asset not indexed')
        source=safe(self.root,record['path']);stat=source.stat()
        if stat.st_mtime_ns!=record['mtime_ns'] or stat.st_size!=record['bytes']:raise ValueError('Asset changed; reindex before use')
        return source,{**record,'sha256':checksum(source),'checksum_state':'VERIFIED'}
