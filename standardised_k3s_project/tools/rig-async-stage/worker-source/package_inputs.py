"""Bounded input snapshots shared by staging and native-authorized admissions."""
import base64, hashlib, json, os, pathlib, posixpath, re, secrets, shutil, struct, urllib.parse

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def snapshot(root, path, roots, name=None, max_bytes=1024**3):
    path=pathlib.Path(path)
    if not path.is_absolute() or path.is_symlink() or path.resolve()!=path or not any(path.is_relative_to(pathlib.Path(r)) for r in roots) or not path.is_file():raise ValueError('Dependency outside authorized roots')
    if path.stat().st_size>max_bytes:raise ValueError('Input file exceeds configured budget')
    sha=digest(path);target=root/'blobs'/sha
    if not target.exists():
        temp=target.with_name('.'+sha+'.'+secrets.token_hex(6))
        with path.open('rb') as src,temp.open('xb') as dst:shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
        if digest(temp)!=sha:raise ValueError('Dependency changed while snapshotting')
        os.replace(temp,target)
    parent=hashlib.sha256(str(path.parent).encode()).hexdigest()[:24]
    return {'id':sha,'original':str(path),'relative':name or 'inputs/'+parent+'/'+path.name,'sha256':sha,'size':target.stat().st_size}

def gltf_dependencies(path):
    path=pathlib.Path(path)
    if path.suffix.lower()=='.gltf':data=json.loads(path.read_text())
    elif path.suffix.lower()=='.glb':
        with path.open('rb') as stream:
            if stream.read(4)!=b'glTF':raise ValueError('Invalid GLB')
            stream.read(8);size,kind=struct.unpack('<II',stream.read(8))
            if kind!=0x4e4f534a or size>16*1024**2:raise ValueError('Invalid GLB JSON budget')
            data=json.loads(stream.read(size))
    else:return []
    result=[]
    for item in data.get('buffers',[])+data.get('images',[]):
        uri=item.get('uri','')
        if not uri or uri.startswith('data:'):continue
        parsed=urllib.parse.urlparse(uri)
        if parsed.scheme not in ('','file'):raise ValueError('Network glTF dependencies are unsupported')
        value=urllib.parse.unquote(parsed.path)
        result.append(pathlib.Path(value) if value.startswith('/') else (path.parent/value).resolve())
    return result

def initial(root,spec,roots):
    source=pathlib.Path(spec['source']);result=[snapshot(root,source,roots,max_bytes=2*1024**3 if spec.get('kind')=='godot' else 1024**3)]
    if result[0]['sha256']!=spec['source_sha256']:raise ValueError('Source hash mismatch')
    if spec.get('preparation',{}).get('method')=='ts4-retarget':
        clip=spec['preparation']['plan'];item=snapshot(root,pathlib.Path(clip['clip']),roots)
        if item['sha256']!=clip['clip_sha256']:raise ValueError('TS4 clip hash mismatch')
        result.append(item)
    for path in gltf_dependencies(source):result.append(snapshot(root,path,roots))
    return unique(result)

def unique(items):
    result=list({item['original']:item for item in items}.values())
    if len(result)>512 or sum(item['size'] for item in result)>2*1024**3:raise ValueError('Dependency package budget: 512 files / 2GiB')
    return result

def expand(path,kind):
    p=pathlib.Path(path)
    if kind=='tiled' and '<UDIM>' in p.name:
        return sorted(p.parent.glob(p.name.replace('<UDIM>','[0-9][0-9][0-9][0-9]')))
    if kind=='sequence':
        match=re.fullmatch(r'(.*?)([0-9]+)(\.[^.]+)',p.name)
        if match:return sorted(q for q in p.parent.iterdir() if re.fullmatch(re.escape(match[1])+r'[0-9]{'+str(len(match[2]))+'}'+re.escape(match[3]),q.name))
    return [p]
