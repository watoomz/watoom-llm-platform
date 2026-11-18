"""Publish already-validated artifacts into a new immutable asset version directory."""
import hashlib,os,pathlib
def publish(jobid,evidence,read):
    root=pathlib.Path(os.environ['WATOOM_3D_PUBLISH'])
    temporary=root/('.pending-'+jobid);destination=root/jobid
    temporary.mkdir(mode=0o755)
    files=[]
    for artifact in evidence:
        name=pathlib.PurePosixPath(artifact['path']).name
        data=read(artifact['path'])
        if hashlib.sha256(data).hexdigest()!=artifact['sha256'] or len(data)!=artifact['bytes']:raise ValueError('artifact changed before publication')
        descriptor=os.open(temporary/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
        with os.fdopen(descriptor,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        files.append({'path':name,'sha256':artifact['sha256'],'bytes':artifact['bytes']})
    if destination.exists():raise ValueError('publication version already exists')
    temporary.rename(destination)
    return {'root':'assets','path':os.environ['WATOOM_3D_PUBLIC_REFERENCE'].rstrip('/')+'/'+jobid,'files':files}
