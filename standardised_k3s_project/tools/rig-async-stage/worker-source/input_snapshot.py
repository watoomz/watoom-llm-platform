"""Socket-activated root reader for authorized asset snapshots; never executes input."""
import hashlib,json,os,pathlib,secrets,socket,sqlite3,stat,struct,sys,urllib.parse
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from package_inputs import unique,expand

STATE=pathlib.Path('/data/ai/helper-scripts/state/workstation-render-stage')
def copy_input(path,roots,folder,max_bytes=1024**3):
    path=pathlib.Path(path)
    if not path.is_absolute() or '..' in path.parts or not any(path.is_relative_to(pathlib.Path(r)) for r in roots):raise ValueError('Out-of-scope input')
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=child
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    finally:os.close(parent)
    temporary='.'+secrets.token_hex(16)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>max_bytes:raise ValueError('Input file budget')
        target=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=folder)
        digest=hashlib.sha256();size=0
        with os.fdopen(target,'wb') as dst:
            while data:=os.read(fd,1024*1024):dst.write(data);digest.update(data);size+=len(data)
            dst.flush();os.fsync(dst.fileno())
        if size!=info.st_size or os.fstat(fd).st_mtime_ns!=info.st_mtime_ns:raise ValueError('Input changed while snapshotting')
        sha=digest.hexdigest();os.replace(temporary,sha,src_dir_fd=folder,dst_dir_fd=folder)
        directory=hashlib.sha256(str(path.parent).encode()).hexdigest()[:24]
        return {'id':sha,'sha256':sha,'size':size,'original':str(path),'relative':'inputs/'+directory+'/'+path.name}
    finally:
        os.close(fd)
        try:os.unlink(temporary,dir_fd=folder)
        except FileNotFoundError:pass

def publish_inputs(items,source):
    import grp
    root=os.open('/data/ai/helper-scripts/workstation-transfer',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:destination=os.open('inputs',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root)
    finally:os.close(root)
    try:
        gid=grp.getgrnam('watoom-render-data').gr_gid
        for item in items:
            name=item['id']
            try:
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=destination)
            except FileNotFoundError:fd=None
            if fd is not None:
                with os.fdopen(fd,'rb') as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=name:raise ValueError('SFTP snapshot changed')
                continue
            temporary='.'+secrets.token_hex(16)
            src=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=source)
            target=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o640,dir_fd=destination)
            try:
                os.fchown(target,0,gid)
                with os.fdopen(target,'wb') as output:
                    while data:=os.read(src,1024*1024):output.write(data)
                    output.flush();os.fsync(output.fileno())
                os.replace(temporary,name,src_dir_fd=destination,dst_dir_fd=destination)
            finally:
                os.close(src)
                try:os.unlink(temporary,dir_fd=destination)
                except FileNotFoundError:pass
        return items
    finally:os.close(destination)

def operation(request):
    cfg=json.loads(pathlib.Path('/etc/watoom-asset-capture.json').read_text());roots=cfg['source_roots']+cfg['projects']
    stagepath=pathlib.Path('/etc/watoom-rig-async-stage.json')
    if stagepath.exists():
        stage=json.loads(stagepath.read_text())
        if stage.get('enabled'):roots+=stage['projects']
    top=os.open(STATE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:folder=os.open('blobs',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=top)
    finally:os.close(top)
    try:
        if request['op']=='initial':
            if request['manifest'].get('kind')=='godot':
                from game_contract import validate_game
                gamecfg=json.loads(pathlib.Path('/etc/watoom-rig-async-stage.json').read_text());spec=request['manifest']
                if not gamecfg.get('enabled'):raise ValueError('Game staging route disabled')
                validate_game(spec,gamecfg['projects']);result=[copy_input(spec['source'],gamecfg['projects'],folder,max_bytes=2*1024**3)]
                if result[0]['sha256']!=spec['source_sha256']:raise ValueError('Game snapshot hash mismatch')
                return publish_inputs(result,folder)
            from asset_capture_contract import manifest
            import asset_capture_contract
            asset_capture_contract.sha=lambda path:copy_input(path,roots,folder)['sha256']
            spec=request['manifest'];manifest(spec,roots)
            result=[copy_input(spec['source'],roots,folder)]
            if result[0]['sha256']!=spec['source_sha256']:raise ValueError('Source hash mismatch')
            if spec.get('preparation',{}).get('method')=='ts4-retarget':
                plan=spec['preparation']['plan'];item=copy_input(plan['clip'],roots,folder)
                if item['sha256']!=plan['clip_sha256']:raise ValueError('Clip hash mismatch')
                result.append(item)
            suffix=pathlib.Path(spec['source']).suffix.lower()
            if suffix in ('.gltf','.glb'):
                fd=os.open(result[0]['id'],os.O_RDONLY|os.O_NOFOLLOW,dir_fd=folder)
                with os.fdopen(fd,'rb') as stream:
                    if suffix=='.glb':
                        if stream.read(4)!=b'glTF':raise ValueError('Invalid GLB')
                        stream.read(8);size,kind=struct.unpack('<II',stream.read(8))
                        if kind!=0x4e4f534a or size>16*1024**2:raise ValueError('GLB metadata budget')
                        data=json.loads(stream.read(size))
                    else:
                        if result[0]['size']>16*1024**2:raise ValueError('glTF metadata budget')
                        data=json.load(stream)
                for item in data.get('buffers',[])+data.get('images',[]):
                    uri=item.get('uri','')
                    if not uri or uri.startswith('data:'):continue
                    value=urllib.parse.urlparse(uri)
                    if value.scheme not in ('','file'):raise ValueError('Network dependencies forbidden')
                    p=pathlib.Path(urllib.parse.unquote(value.path))
                    if not p.is_absolute():p=pathlib.Path(spec['source']).parent/p
                    result.append(copy_input(p.resolve(),roots,folder))
            return publish_inputs(unique(result),folder)
        if request['op']=='dependencies':
            with sqlite3.connect('file:'+str(STATE/'queue.sqlite')+'?mode=ro',uri=True) as db:
                if not db.execute("select 1 from jobs where id=? and state='CLAIMED'",(request['job'],)).fetchone():raise ValueError('Claim unavailable')
            if not isinstance(request['paths'],list) or len(request['paths'])>512:raise ValueError('Dependency budget')
            result=[]
            for item in request['paths']:
                if set(item)!={'path','kind'} or item['kind'] not in ('file','library','sequence','tiled'):raise ValueError('Invalid dependency')
                paths=expand(item['path'],item['kind'])
                if not paths:raise ValueError('Missing dependency')
                for path in paths:result.append(copy_input(path.resolve(),roots,folder))
            return publish_inputs(unique(result),folder)
        raise ValueError('Operation forbidden')
    finally:os.close(folder)

def main():
    channel=socket.socket(fileno=0)
    _,uid,_=struct.unpack('3i',channel.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
    import pwd
    if uid not in (0,pwd.getpwnam('watoom-render-stage').pw_uid):raise ValueError('Peer forbidden')
    channel.settimeout(120);stream=channel.makefile('rwb')
    try:
        raw=stream.readline(800000)
        if len(raw)>=800000:raise ValueError('Request budget')
        value={'ok':True,'inputs':operation(json.loads(raw))}
    except Exception as error:value={'ok':False,'error':str(error)[:500]}
    stream.write(json.dumps(value).encode()+b'\n');stream.flush()
if __name__=='__main__':main()
