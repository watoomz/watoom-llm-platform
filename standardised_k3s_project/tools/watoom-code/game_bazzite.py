#!/usr/bin/env python3
"""Operator-only Godot import/regression/capture on the Bazzite worker (keeps big game jobs off the homelab server).

Same contract and receipts as game_import.py / game_validation.py, with more room: 8 GiB, 6 CPUs, 600 s.
The project (without .opencode/.git) is mirrored to Bazzite and verified file by file against the source
manifest; the pinned Godot runs headless in rootless podman (toolkit image, no network, read-only root, all
capabilities dropped) inside a bounded user unit while a root-owned sleep inhibitor is held.
  import     - only Godot's caches (.godot/, *.import) come back, applied only if the live source is unchanged.
  regression - res://scripts/test_runner.gd on the mirror; the live project is never written.
  capture    - bounded Xvfb/llvmpipe rendering on the mirror; only PNG evidence and receipts return.
Exit 75 with status NOT_STARTED = nothing was launched (the bridge may then use the local worker); after the
launch there is no fallback and no replay.
"""
import argparse,hashlib,json,os,pathlib,re,shlex,shutil,struct,subprocess,sys,time
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent.parent/'ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts/unreal-export'))
from game_validation import GODOT,GODOT_SHA,manifest,atomic,publish_receipt,regression_failure_reason,godot_errors,import_failure_reason,godot_hints,godot_output_tail
from capture_profiles import PROFILES,exit_evidence,frame_evidence_errors
import bazzite as bz
NOT_STARTED=75
MEMORY_GIB=8;CPUS=6;DEADLINE=600
# Free RAM Bazzite must report before a job starts. Owner-set 2026-11-07: 8 GiB (was job size + 2 GiB reserve = 10 GiB, which a
# 15 GiB desktop host with two logged-in sessions rarely met: it reported 9.2-9.3 GiB and every capture was NOT_STARTED).
MIN_FREE_GIB=8
R_GODOT='watoom-godot/bin/godot-'+GODOT_SHA[:12]
EXCLUDE_SYNC=['--exclude=/.opencode/','--exclude=/.git/','--exclude=/magpie-final/']

REMOTE_MANIFEST=r"""
import hashlib,json,os,pathlib,sys
root=pathlib.Path.home()/sys.argv[1];out={}
for d,dirs,files in os.walk(root,followlinks=False):
    dirs[:]=[x for x in dirs if x not in {'.godot','.opencode','.git','magpie-final'}]
    for n in files:
        p=pathlib.Path(d)/n
        if p.is_symlink():raise SystemExit('symlink in mirror: '+str(p))
        with p.open('rb') as f:out[str(p.relative_to(root))]=hashlib.file_digest(f,'sha256').hexdigest()
json.dump(out,sys.stdout)
"""

def remote_manifest(r_project):
    # exactly game_validation.manifest(): the same directories skipped at any depth, no shell filename escaping
    r=bz.sh('python3 -c %s %s'%(shlex.quote(REMOTE_MANIFEST),shlex.quote(r_project)),timeout=600,check=True)
    return json.loads(r.stdout)

def failure_fields(receipt):
    if receipt.get('source_changes_by_import'): return 'reconcile','source_changed'
    text=' '.join(str(x or '') for x in (receipt.get('failure_reason'), receipt.get('errors'), receipt.get('log_tail'))).lower()
    if receipt.get('timed_out') or 'deadline exceeded' in text or 'timeout' in text or receipt.get('exit') is None: return 'run','timeout'
    if receipt.get('exit') == 137 or 'out of memory' in text or 'memory limit' in text or 'oom' in text: return 'run','oom'
    if 'read-only file system' in text or 'script error' in text or 'godot errors' in text or 'script raised' in text: return 'run','script_error'
    if receipt.get('status') not in ('PASS','CAPTURED_VISUAL_REVIEW_PENDING'):
        return 'run', 'worker_error' if receipt.get('exit') not in (None,0) else 'unknown'
    return None,None

def annotate_failure(receipt):
    stage,code=failure_fields(receipt)
    if stage: receipt['failure_stage'],receipt['failure_code']=stage,code
    return receipt

REMOTE_IMAGES=r"""
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);started=float(pathlib.Path(sys.argv[2]).read_text());out={}
for name in json.loads(sys.argv[3]):
    f=root/name
    if not f.exists():continue
    if f.is_symlink() or f.resolve()!=f or not f.is_file() or f.stat().st_size>128*1024**2:raise ValueError('Unsafe/oversize capture output')
    out[name]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'fresh':f.stat().st_mtime>=started}
print(json.dumps(out))
"""

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--operation',choices=['import','regression','capture','capture-scene','capture-p7'],required=True)
    p.add_argument('--project',type=pathlib.Path,required=True);p.add_argument('--evidence',type=pathlib.Path,required=True)
    p.add_argument('--i-approve',action='store_true')
    p.add_argument('--profile',choices=sorted(PROFILES),default='p6');p.add_argument('--capture-job')
    a=p.parse_args()
    capture=a.operation in ('capture','capture-scene','capture-p7')
    if a.operation=='capture-p7':a.profile='p7'
    if a.operation=='capture-scene' and not a.capture_job:raise ValueError('capture-scene requires --capture-job')
    if os.geteuid()!=0:raise PermissionError('Trusted operator required')
    project=a.project.resolve(strict=True)
    if not a.i_approve or a.project.is_symlink() or not project.is_relative_to('/data/ai/projects/games') or not (project/'project.godot').is_file():
        raise ValueError('Approved existing game project required')
    if a.operation=='regression' and not (project/'scripts/test_runner.gd').is_file():raise ValueError('Existing canonical game/test project required')
    if a.operation=='import' and '[editor]' in (project/'project.godot').read_text():raise ValueError('Existing editor settings require explicit merge before import')
    profile=None;capture_inputs={}
    if capture:
        profile=PROFILES[a.profile]
        if a.capture_job:
            from capture_spec import load
            profile=load(project,a.capture_job)
            inputs=[*profile['inputs'],'.opencode/capture-jobs/'+a.capture_job+'/request.json']
        else:
            scene=project/profile['scene']
            if not scene.is_file() or scene.is_symlink():raise ValueError('Existing capture scene required: '+profile['scene'])
            inputs=[str(f.relative_to(project)) for f in scene.parent.rglob('*') if not f.is_dir()]
        for name in inputs:
            f=project/name
            if f.is_symlink() or f.resolve()!=f or not f.is_file() or f.stat().st_size>64*1024**2:raise ValueError('Unsafe capture input')
            capture_inputs[name]=hashlib.sha256(f.read_bytes()).hexdigest()
    # The module default (600s) is "more room" than the local worker's, but a declarative capture-scene
    # request can set its own deadline_sec (60-1080, validated by capture_spec.load()); honor it here instead
    # of always falling back to the fixed 600s, which silently ignored every request that raised it.
    deadline=profile.get('deadline_sec',DEADLINE) if profile else DEADLINE
    with GODOT.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=GODOT_SHA:raise ValueError('Pinned Godot input changed')
    directory=a.evidence.resolve();directory.mkdir(parents=True,exist_ok=False,mode=0o750);os.chown(directory,0,1009)
    before=manifest(project)
    if a.operation=='import':before={k:v for k,v in before.items() if not k.endswith('.import')}
    atomic(directory/'source-manifest.json',before)
    unit='watoom-godot-'+('capture' if capture else 'import' if a.operation=='import' else 'check')+'-'+str(time.time_ns())
    r_project='watoom-godot/projects/'+project.name;r_job='watoom-godot/jobs/'+unit
    held=None

    def not_started(reason):
        if held:bz.release(held)
        shutil.rmtree(directory,ignore_errors=True) # nothing ran: leave no evidence that would block the local route
        text=str(reason);lower=text.lower()
        code='unreachable' if '255' in lower or 'ssh' in lower and ('timeout' in lower or 'timed out' in lower) else 'not_staged' if 'not staged' in lower or 'missing' in lower else 'worker_error'
        safe='Bazzite access command failed (%s).' % code if text.startswith("Command '[") else text[:300]
        print(json.dumps({'status':'NOT_STARTED','worker':'bazzite','reason':safe,'failure_stage':'stage','failure_code':code}));raise SystemExit(NOT_STARTED)

    # ---- preparation: any failure here is NOT_STARTED ----
    try:
        staged=bz.runtime_ready()
        if not staged:raise RuntimeError('Bazzite toolkit not staged (bazzite.py stage-runtime)')
        tag=staged[1]['local_tag']
        if capture:
            # the production toolkit image has no Xvfb/EGL; captures use the derived image built by `bazzite.py build-capture-image`
            if not bz.capture_image_ready(tag):raise RuntimeError('Bazzite capture image missing (Xvfb + Mesa EGL): run bazzite.py build-capture-image')
            tag=bz.capture_image_tag(tag)
        ram,disk=bz.free()
        if ram<MIN_FREE_GIB*1024**3:raise RuntimeError('Bazzite has %.1f GiB free RAM'%(ram/1024**3))
        if disk<20*1024**3:raise RuntimeError('Bazzite has %.1f GiB free disk'%(disk/1024**3))
        held=bz.inhibit(unit,deadline+1800,'Godot '+a.operation+' '+project.name)
        home=bz.sh('printf %s "$HOME"',timeout=60,check=True).stdout.strip()
        bz.sh('mkdir -p ~/watoom-godot/bin ~/%s ~/%s/home ~/%s/cache'%(r_project,r_job,r_job),timeout=60,check=True)
        r=bz.sh('sha256sum ~/%s 2>/dev/null'%R_GODOT,timeout=120)
        if not r.stdout.startswith(GODOT_SHA):
            r=bz.push(str(GODOT),R_GODOT,timeout=900)
            if r.returncode:raise RuntimeError('Godot push failed: '+r.stderr[-300:])
            if not bz.sh('sha256sum ~/%s'%R_GODOT,timeout=120,check=True).stdout.startswith(GODOT_SHA):raise RuntimeError('Godot hash mismatch on Bazzite')
            bz.sh('chmod 0755 ~/%s'%R_GODOT,timeout=60,check=True)
        r=bz.push(str(project)+'/','%s/'%r_project,['--delete',*EXCLUDE_SYNC],timeout=900,attempts=3)
        if r.returncode:raise RuntimeError('project sync failed: '+r.stderr[-300:])
        remote=remote_manifest(r_project)
        if a.operation=='import':remote={k:v for k,v in remote.items() if not k.endswith('.import')}
        if remote!=before:raise RuntimeError('Bazzite mirror does not match the source manifest')
        if manifest_now(project,a.operation)!=before:raise RuntimeError('Live source changed during sync')
        if capture:
            # .opencode is deliberately excluded by the normal mirror sync. Stage only checked inputs;
            # remove previous outputs so a pulled PNG cannot be mistaken for a fresh render (no clock skew).
            bz.sh('rm -rf ~/%s/.opencode && mkdir -p ~/%s/.godot ~/%s/.opencode/validation ~/%s/%s'%
                  (r_project,r_project,r_project,r_project,profile['directory']),timeout=60,check=True)
            for name,digest in capture_inputs.items():
                remote_file=r_project+'/'+name
                bz.sh('mkdir -p '+shlex.quote(home+'/'+str(pathlib.PurePosixPath(remote_file).parent)),timeout=60,check=True)
                r=bz.push(str(project/name),remote_file,timeout=120,attempts=3)
                if r.returncode or not bz.sh('sha256sum '+shlex.quote(home+'/'+remote_file),timeout=60,check=True).stdout.startswith(digest):
                    raise RuntimeError('Capture input sync mismatch: '+name)
            if any(hashlib.sha256((project/n).read_bytes()).hexdigest()!=h for n,h in capture_inputs.items()):raise RuntimeError('Capture inputs changed during sync')
        args=['--headless','--path','/project']+(['--editor','--import'] if a.operation=='import' else ['--script','res://scripts/test_runner.gd'])
        podman=['podman','run','--rm','--name',unit,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--userns','keep-id:uid=1009,gid=1009','--memory','%dg'%MEMORY_GIB,'--memory-swap','%dg'%MEMORY_GIB,'--cpus',str(CPUS),'--pids-limit','512',
            '--timeout',str(deadline),'--tmpfs','/tmp:rw,size=1g,mode=1777',
            '-e','HOME=/job/home','-e','XDG_CACHE_HOME=/job/cache','-e','USER=watoom-worker','-e','LOGNAME=watoom-worker',
            '-v','%s/%s:/godot:ro,z'%(home,R_GODOT),'-v','%s/%s:/project:z'%(home,r_project),'-v','%s/%s:/job:z'%(home,r_job),
            '--workdir','/project','--entrypoint','/godot',tag,*args]
        if capture:
            # Rootless podman supplies a private /dev with no GPU devices. Source is read-only;
            # only the mirror's caches and capture area are writable, as in game_capture.py.
            source_mount=podman.index('%s/%s:/project:z'%(home,r_project))
            podman[source_mount]='%s/%s:/project:ro,z'%(home,r_project)
            podman=podman[:podman.index('--entrypoint')]+[
                '-v','%s/%s/.godot:/project/.godot:z'%(home,r_project),
                '-v','%s/%s/.opencode:/project/.opencode:z'%(home,r_project),
                '-e','LIBGL_ALWAYS_SOFTWARE=1','-e','GALLIUM_DRIVER=llvmpipe','-e','LP_NUM_THREADS=6',
                '-e','__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json','-e','__GLX_VENDOR_LIBRARY_NAME=mesa',
                # no setpriv: the container already runs as the unprivileged uid 1009 (keep-id) with --cap-drop ALL, so there is nothing to drop and setpriv itself
                # fails ("setgroups failed: Operation not permitted") without CAP_SETGID. It was carried over from the server flow, which starts as root.
                '--entrypoint','xvfb-run',tag,
                '-e','/project/.opencode/validation/xvfb-worker.log','-a','-s','-screen 0 800x800x24',
                '/godot','--path','/project','--audio-driver','Dummy','--rendering-driver','opengl3','res://'+profile['scene']]
        job_dir=home+'/'+r_job
        script='%s > %s 2>&1; echo $? > %s'%(' '.join(shlex.quote(x) for x in podman),shlex.quote(job_dir+'/godot.log'),shlex.quote(job_dir+'/exit_code'))
        if capture:script='date +%s.%N > '+shlex.quote(job_dir+'/started_at')+'; '+script
        launch=['systemd-run','--user','--unit='+unit,'--collect','-p','MemoryMax=%dG'%(MEMORY_GIB+1),'-p','CPUQuota=%d%%'%(CPUS*100),'-p','Nice=10',
                '-p','RuntimeMaxSec=%d'%(deadline+60),'/bin/bash','-c',script]
        if capture:
            # No PrivateDevices=yes and no NoNewPrivileges=yes on this systemd USER unit: either one stops podman's setuid/file-capability newuidmap
            # from creating its helper process whenever none exists yet ("unable to create a new pause process ... Operation not permitted"),
            # so captures failed NOT_STARTED intermittently. Bisected on Bazzite. The container itself keeps --cap-drop ALL, --security-opt
            # no-new-privileges, a read-only root and podman's private /dev, so nothing is weakened for the workload.
            launch[launch.index('/bin/bash'):launch.index('/bin/bash')]=['-p','MemorySwapMax=0','-p','TimeoutStopSec=10','-p','KillMode=control-group']
        if capture:
            # Probe tools under the same isolation and user mapping, without starting Godot. Unsupported
            # user-unit namespaces or a missing display stack must be NOT_STARTED, never a replay.
            probe=podman[:podman.index('--entrypoint')]+['--entrypoint','/bin/sh',tag,'-c',
                'm=; for t in xvfb-run Xvfb xauth; do command -v $t >/dev/null || m="$m $t"; done; test -f /usr/share/glvnd/egl_vendor.d/50_mesa.json || m="$m mesa-egl-vendor-file"; test -z "$m" || { echo "capture image lacks:$m" >&2; exit 3; }']
            probe[probe.index(unit)]=unit+'-prepare'
            preflight=launch[:launch.index('/bin/bash')]+['--wait','--pipe','--',*probe]
            preflight[preflight.index('--unit='+unit)]='--unit='+unit+'-prepare'
            bz.sh(' '.join(shlex.quote(x) for x in preflight),timeout=120,check=True)
        atomic(directory/'prepared.json',{'unit':unit,'project':str(project),'source_files':len(before),'godot_sha256':GODOT_SHA,'worker':'bazzite',
                                         'memory_limit':'%dGiB'%MEMORY_GIB,'cpus':CPUS,'deadline_seconds':deadline,'image':staged[1]['image']})
    except SystemExit:
        raise
    except Exception as e:
        not_started(e)

    # ---- launch: from here on there is no fallback ----
    started=time.time()
    try:
        r=bz.sh(' '.join(shlex.quote(x) for x in launch),timeout=120)
        launch_state='ok' if r.returncode==0 else 'error: '+r.stderr[-300:]
    except Exception as e:
        launch_state='uncertain: '+str(e)[:300]
    code=None
    while time.time()-started<deadline+120:
        try:
            r=bz.sh('cat ~/%s/exit_code 2>/dev/null; systemctl --user is-active %s.service'%(r_job,unit),timeout=60)
            out=r.stdout.split()
            if out and out[0].lstrip('-').isdigit():code=int(out[0]);break
            if out and out[-1] in ('inactive','failed'):break
        except Exception:
            pass
        time.sleep(10)
    elapsed=round(time.time()-started,1)
    log=directory/('capture.log' if capture else 'godot.log')
    log_error=None
    if capture:
        try:
            r=bz.pull('%s/godot.log'%r_job,str(log),timeout=120,attempts=1)
            if r.returncode:log_error='CAPTURE_LOG_PULL_FAILED: '+r.stderr[-300:]
        except Exception as e:log_error='CAPTURE_LOG_PULL_FAILED: '+str(e)[:300]
    else:r=bz.pull('%s/godot.log'%r_job,str(log),timeout=300)
    if not log.exists():log.write_text('')
    os.chmod(log,0o600)
    text=log.read_text(errors='replace')
    errors=godot_errors(text)
    if log_error:errors.append(log_error)
    common={'unit':unit,'worker':'bazzite','launch':launch_state,'exit':code,'elapsed_seconds':elapsed,'memory_limit':'%dGiB'%MEMORY_GIB,
            'cpus':CPUS,'deadline_seconds':deadline,'failure_reason':None if code==0 else ('timeout' if code in (124,255) or code is None else 'worker-exit')}

    if capture:
        images=[]
        try:
            metadata=json.loads(bz.sh(' '.join(shlex.quote(x) for x in ['python3','-c',REMOTE_IMAGES,
                home+'/'+r_project+'/'+profile['directory'],home+'/'+r_job+'/started_at',json.dumps(profile['names'])]),timeout=120,check=True).stdout)
            output=directory/'images';output.mkdir()
            r=bz.pull(r_project+'/'+profile['directory']+'/',str(output)+'/',
                      ['--no-links','--no-specials','--no-devices',*['--include=/'+n for n in profile['names']],'--exclude=*'],timeout=120,attempts=1)
            if r.returncode:errors.append('CAPTURE_PULL_FAILED: '+r.stderr[-300:])
            for name in profile['names']:
                f=output/name
                if not f.is_file():continue
                if f.is_symlink() or f.resolve()!=f or f.stat().st_size>128*1024**2:raise ValueError('Unsafe/oversize capture output')
                with f.open('rb') as image:header=image.read(24)
                if len(header)!=24 or header[:8]!=bytes([137,80,78,71,13,10,26,10]) or any(not 16<=x<=8192 for x in struct.unpack('>II',header[16:24])):raise ValueError('Invalid rendered PNG')
                digest=hashlib.sha256(f.read_bytes()).hexdigest()
                if metadata.get(name,{}).get('sha256')!=digest:raise ValueError('Capture changed during pull: '+name)
                images.append({'path':str(f),'sha256':digest,'fresh':metadata[name]['fresh']})
            if manifest_now(project,a.operation)!=before or remote_manifest(r_project)!=before:errors.append('Capture source changed during execution')
            if any(hashlib.sha256((project/n).read_bytes()).hexdigest()!=h for n,h in capture_inputs.items()):errors.append('Capture inputs changed during execution')
        except Exception as e:
            errors.append(str(e)[:500])
        timed_out,exit_errors=exit_evidence(code,text,elapsed,deadline,errors);errors=exit_errors+errors
        errors+=frame_evidence_errors(a.profile,images)
        receipt={'profile':'declarative' if a.capture_job else a.profile,'scene':profile['scene'],'capture_spec_sha256':profile.get('capture_spec_sha256'),
                 'status':'CAPTURED_VISUAL_REVIEW_PENDING' if code==0 and len(images)==len(profile['names']) and all(x['fresh'] for x in images) and not errors else 'FAIL',
                 'unit':unit,'exit':code,'timed_out':timed_out,'elapsed_sec':elapsed,'deadline_sec':deadline,'images':images,
                 'errors':errors[:20],'hints':godot_hints(errors),'output_tail':godot_output_tail(text),'gpu_used':False,'memory_limit':str(MEMORY_GIB)+'GiB'}
        annotate_failure(receipt);atomic(directory/'result.json',receipt)
        target=project/'.opencode/validation/operator-godot';target.mkdir(parents=True,exist_ok=True)
        out=target/(unit+'.json');out.write_text(json.dumps(receipt,indent=2));os.chmod(out,0o644)
    elif a.operation=='import':
        applied=False;after=None
        if code==0:
            # bring back only Godot's caches, then apply them only if the live source is still the imported one
            cache=directory/'caches';cache.mkdir()
            r=bz.pull('%s/'%r_project,str(cache)+'/',['--prune-empty-dirs','--include=/.godot/***','--include=*/','--include=*.import','--exclude=*'],timeout=1500)
            after=remote_manifest(r_project);after={k:v for k,v in after.items() if not k.endswith('.import')}
            if r.returncode==0 and after==before and manifest_now(project,'import')==before:
                subprocess.run(['rsync','-a','--chown=1009:1009','--chmod=D2770,F660',str(cache)+'/',str(project)+'/'],check=True,timeout=900)  # group-writable: the project ACL mask follows these bits and the app user needs rw
                applied=True
            shutil.rmtree(cache,ignore_errors=True)
        live=manifest_now(project,'import')==before
        # an import may only produce caches; name any source files it created or rewrote (e.g. Godot .uid files,
        # resources re-saved by import settings) so the cause is actionable. Nothing is applied in that case.
        changes=None
        if after is not None and after!=before:
            changes={'created':sorted(set(after)-set(before))[:50],'rewritten':sorted(k for k in before if k in after and after[k]!=before[k])[:50],
                     'removed':sorted(set(before)-set(after))[:50],
                     'note':'import changed source files; caches were not applied. Commit or fix these, then request a new import.'}
        receipt={**common,'status':'PASS' if code==0 and applied and not errors and live else 'FAIL','log_tail':text.splitlines()[-40:],
                 'source_unchanged':live and (after is None or after==before),'source_changes_by_import':changes,'errors':errors[:20],'hints':godot_hints(errors),
                 'import_threads':'multiple','caches_applied':applied,'scope':'import only; no rendering or gameplay acceptance'}
        if receipt['status']!='PASS' and code==0:receipt['failure_reason']=import_failure_reason(errors,changes,live,applied)
        annotate_failure(receipt);atomic(directory/'result.json',receipt)
        target=project/'.opencode/validation/operator-godot';target.mkdir(parents=True,exist_ok=True)
        out=target/(unit+'.json');out.write_text(json.dumps(receipt,indent=2));os.chmod(out,0o644)
        receipt['app_receipt']=str(out);annotate_failure(receipt);atomic(directory/'result.json',receipt)
    else:
        matches=re.findall(r'^passed=(\d+) failed=(\d+) total=(\d+)$',text,re.M)
        summary=tuple(map(int,matches[-1])) if matches else None
        receipt={**common,'status':'PASS' if code==0 and summary and summary[1]==0 and summary[0]==summary[2] and summary[2]>0 and not errors else 'FAIL',
                 'runtime_error_count':len(errors),'service_result':'success' if code==0 else 'failure','exit_status':str(code),
                 'summary':{'passed':summary[0],'failed':summary[1],'total':summary[2]} if summary else None,
                 'source_manifest':'source-manifest.json','log':str(log),'original_project_untouched':True}
        if receipt['status']!='PASS' and code==0:receipt['failure_reason']=regression_failure_reason(summary,len(errors))
        receipt['live_source_still_matches_snapshot']=manifest_now(project,'regression')==before
        publish_receipt(project,directory,receipt)
        annotate_failure(receipt);atomic(directory/'result.json',receipt)
    try:
        bz.sh('rm -rf ~/%s'%r_job,timeout=120)
    finally:
        bz.release(held)
    print(json.dumps(receipt if capture else {k:receipt.get(k) for k in ('status','worker','unit','exit','elapsed_seconds','summary','caches_applied','failure_reason')}))
    raise SystemExit(0 if receipt['status'] in ('PASS','CAPTURED_VISUAL_REVIEW_PENDING') else 1)

def manifest_now(project,operation):
    m=manifest(project)
    return {k:v for k,v in m.items() if not k.endswith('.import')} if operation=='import' else m

if __name__=='__main__':
    main()
