#!/usr/bin/env python3
"""Bazzite worker access for the Unreal export: SSH command, rsync push/pull, detached bounded units.

Same access model as standardised_k3s_project/tools/bazzite-render-worker/remote.py: the server-held
credentials file and the pinned host key; credentials never appear in arguments or logs (SSH_ASKPASS
reads them from the root-only file). Bazzite cannot reach the homelab, so every transfer is driven
from here. Run as root.

  sudo python3 bazzite.py check            # reachability, free RAM/disk, staged runtime and image
  sudo python3 bazzite.py stage-runtime    # one-time: slimmed Unreal runtime + toolkit image to Bazzite
"""
import base64,contextlib,json,os,pathlib,shlex,subprocess,sys,tempfile,time
CREDENTIALS=pathlib.Path('/home/codex/game_render_host.txt')
KNOWN=pathlib.Path('/data/ai/helper-scripts/reports/game-render-host-audit-20261026/known_hosts')
PRIVATE=pathlib.Path('/data/ai/private')
HERE=pathlib.Path(__file__).resolve().parent
ENGINE=pathlib.Path('/data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653')
# remote layout (under the worker user's home, on Bazzite's NVMe)
R_ROOT='watoom-unreal'
R_ENGINE=R_ROOT+'/runtime/'+ENGINE.name
R_PACKS=R_ROOT+'/packs'
R_JOBS=R_ROOT+'/jobs'
R_IMAGE_MARK=R_ROOT+'/toolkit-image.json'
R_READY=R_ROOT+'/runtime/'+ENGINE.name+'.ready.json'
UNIT_LIMITS=['-p','MemoryMax=11G','-p','MemoryHigh=10G','-p','CPUQuota=600%','-p','Nice=10']

def connection():
    rows=CREDENTIALS.read_text().splitlines()
    return rows[0].strip(),next(l.split(':',1)[1].strip() for l in rows if l.startswith('username:'))

@contextlib.contextmanager
def _env():
    PRIVATE.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bazzite-ssh-',dir=str(PRIVATE)) as tmp:
        ask=pathlib.Path(tmp)/'askpass.py'
        ask.write_text("#!/usr/bin/python3\nfrom pathlib import Path\nfor l in Path(%r).read_text().splitlines():\n if l.startswith('password:'):print(l.split(':',1)[1].strip());break\n"%str(CREDENTIALS))
        ask.chmod(0o700)
        yield {**os.environ,'SSH_ASKPASS':str(ask),'SSH_ASKPASS_REQUIRE':'force','DISPLAY':':0'}

SSH_OPTS=['-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=4','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(KNOWN)]

def sh(command,timeout=900,check=False,sudo=False):
    """Run a shell command on Bazzite as the worker user (sudo=True: as root, password on stdin only)."""
    host,user=connection()
    stdin=None
    if sudo:
        command='sudo -S -p "" '+command
        stdin=next(l.split(':',1)[1].strip() for l in CREDENTIALS.read_text().splitlines() if l.startswith('password:'))+'\n'
    with _env() as env:
        r=subprocess.run(['ssh',*SSH_OPTS,user+'@'+host,command],env=env,capture_output=True,text=True,timeout=timeout,
                         input=stdin,stdin=None if sudo else subprocess.DEVNULL)
    if check and r.returncode:
        raise RuntimeError('bazzite: %s failed (%d): %s'%(command.split()[0],r.returncode,r.stderr[-500:]))
    return r

def _rsync(src,dst,extra,timeout):
    with _env() as env:
        cmd=['ionice','-c3','nice','-n','15','rsync','-a','--partial','--partial-dir=.rsync-partial','-e','ssh '+' '.join(shlex.quote(o) for o in SSH_OPTS),*extra,src,dst]
        return subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=timeout,stdin=subprocess.DEVNULL)

def _retry(src,dst,extra,timeout,attempts):
    # Wi-Fi link: a dropped connection resumes (--partial) instead of failing the whole copy
    end=time.time()+timeout
    for i in range(attempts):
        r=_rsync(src,dst,extra,max(60,end-time.time()))
        if r.returncode in (0,1,2,4) or time.time()>end:
            return r
        time.sleep(min(30*(i+1),300))
    return r

def push(local,remote,extra=(),timeout=4*3600,attempts=20):
    """rsync a local path to ~/<remote> on Bazzite (resumable, retried; idle I/O priority on this host)."""
    host,user=connection()
    return _retry(str(local),'%s@%s:%s'%(user,host,remote),list(extra),timeout,attempts)

def pull(remote,local,extra=(),timeout=4*3600,attempts=20):
    host,user=connection()
    return _retry('%s@%s:%s'%(user,host,remote),str(local),list(extra),timeout,attempts)

def inhibit(name,seconds,why):
    """Block idle/sleep on Bazzite for at most `seconds` (root-owned, bounded unit; release() ends it early).
    The worker suspends when idle, which drops SSH and kills a running job's results."""
    unit=name+'-inhibit'
    cmd=['systemd-run','--quiet','--collect','--unit='+unit,'-p','RuntimeMaxSec=%d'%seconds,'--',
         '/usr/bin/systemd-inhibit','--what=idle:sleep','--mode=block','--who=watoom-homelab','--why='+why,'/usr/bin/sleep',str(seconds)]
    sh(' '.join(shlex.quote(x) for x in cmd),timeout=60,check=True,sudo=True)
    return unit

def release(unit):
    try:
        sh('systemctl stop '+shlex.quote(unit+'.service'),timeout=60,sudo=True)
    except Exception:
        pass # bounded by RuntimeMaxSec anyway

def free():
    """(available RAM bytes, free bytes in the worker home) on Bazzite."""
    r=sh("awk '/MemAvailable/{print $2*1024}' /proc/meminfo; df -B1 --output=avail ~ | tail -1",timeout=60,check=True)
    a,b=r.stdout.split()[:2]
    return int(a),int(b)

def require_reachable(r):
    """ssh exits 255 when it cannot connect/authenticate: that is 'Bazzite unreachable', never 'something is not staged'."""
    if r.returncode==255:
        last=([l for l in (r.stderr or '').strip().splitlines() if l.strip()] or ['no answer'])[-1]
        raise RuntimeError('Bazzite unreachable over SSH: '+last[:200])
    return r

def runtime_ready():
    r=require_reachable(sh('cat ~/%s ~/%s 2>/dev/null'%(R_READY,R_IMAGE_MARK),timeout=60))
    docs=[json.loads(x) for x in r.stdout.splitlines() if x.strip().startswith('{')]
    return docs if len(docs)==2 else None

def stage_runtime(image):
    """Copy the slimmed runtime (unreal-runtime-exclude.txt) and the toolkit image; verify and mark ready."""
    identity=json.loads((ENGINE/'runtime-identity.json').read_text())
    sh('mkdir -p ~/%s ~/%s ~/%s'%(R_ENGINE,R_PACKS,R_JOBS),timeout=60,check=True)
    held=inhibit('watoom-unreal-stage',6*3600,'Staging Unreal runtime from the homelab')
    try:
        return _stage(identity,image)
    finally:
        release(held)

def _stage(identity,image):
    r=push(str(ENGINE)+'/','%s/'%R_ENGINE,['--delete','--exclude-from='+str(HERE/'unreal-runtime-exclude.txt')],timeout=5*3600,attempts=40)
    if r.returncode:
        raise RuntimeError('runtime push failed: '+r.stderr[-800:])
    editor='Engine/Binaries/Linux/UnrealEditor'
    r=sh('sha256sum ~/%s/%s'%(R_ENGINE,editor),timeout=900,check=True)
    if r.stdout.split()[0]!=identity['editor_sha256']:
        raise RuntimeError('editor hash mismatch on Bazzite')
    # toolkit image: the homelab registry is not reachable from Bazzite, so ship an OCI archive
    digest=image.split('@',1)[1]
    with tempfile.TemporaryDirectory(prefix='bazzite-image-',dir='/app/ai/builds') as tmp:
        arch=pathlib.Path(tmp)/'toolkit.oci.tar'
        subprocess.run(['skopeo','copy','--src-tls-verify=false','docker://'+image,'oci-archive:%s:watoom-toolkit'%arch],check=True,stdout=subprocess.DEVNULL)
        r=push(arch,'%s/toolkit.oci.tar'%R_ROOT)
        if r.returncode:
            raise RuntimeError('image push failed: '+r.stderr[-800:])
    r=sh('cd ~/%s && podman load -q -i toolkit.oci.tar && podman tag watoom-toolkit localhost/watoom-toolkit:%s && rm -f toolkit.oci.tar && '
         'podman image inspect localhost/watoom-toolkit:%s --format "{{.Digest}}"'%(R_ROOT,digest[7:19],digest[7:19]),timeout=1800,check=True)
    mark={'image':image,'local_tag':'localhost/watoom-toolkit:'+digest[7:19],'digest_after_load':r.stdout.strip().splitlines()[-1]}
    sh("printf '%%s\\n' %s > ~/%s"%(shlex.quote(json.dumps(mark)),R_IMAGE_MARK),timeout=60,check=True)
    ready={'engine':ENGINE.name,'editor_sha256':identity['editor_sha256'],'version':identity['version'],'exclude':[l.strip() for l in (HERE/'unreal-runtime-exclude.txt').read_text().splitlines() if l.strip() and not l.lstrip().startswith('#')]}
    sh("printf '%%s\\n' %s > ~/%s"%(shlex.quote(json.dumps(ready)),R_READY),timeout=60,check=True)
    return ready,mark

CAPTURE_PACKAGES='xorg-x11-server-Xvfb xorg-x11-xauth mesa-libEGL mesa-libGL libglvnd-egl'
def capture_image_tag(base_tag):
    """Godot captures need Xvfb + Mesa EGL, which the production toolkit image lacks: they live in a derived image built once on Bazzite."""
    return 'localhost/watoom-toolkit-xvfb:'+base_tag.rsplit(':',1)[-1]

def capture_image_ready(base_tag):
    r=require_reachable(sh('podman image exists %s && echo yes'%shlex.quote(capture_image_tag(base_tag)),timeout=60))
    return r.stdout.strip()=='yes'

def build_capture_image(base_tag):
    """Additive: adds localhost/watoom-toolkit-xvfb:<tag> on top of the staged toolkit image; nothing existing is modified."""
    tag=capture_image_tag(base_tag)
    user=sh('podman image inspect %s --format "{{.Config.User}}"'%shlex.quote(base_tag),timeout=60,check=True).stdout.strip() or 'root'
    containerfile='FROM %s\nUSER root\nRUN dnf -y install --setopt=install_weak_deps=False %s && dnf clean all\nUSER %s\n'%(base_tag,CAPTURE_PACKAGES,user)
    b64=base64.b64encode(containerfile.encode()).decode()
    sh("mkdir -p ~/watoom-godot/capture-image && printf %%s %s | base64 -d > ~/watoom-godot/capture-image/Containerfile"%b64,timeout=60,check=True)
    held=inhibit('watoom-capture-image',3600,'Building the Xvfb capture image')
    try:
        r=sh('cd ~/watoom-godot/capture-image && podman build -q -t %s -f Containerfile . 2>&1 | tail -5'%shlex.quote(tag),timeout=1800,check=True)
        probe=sh("podman run --rm --network none --entrypoint /bin/sh %s -c 'command -v xvfb-run && command -v Xvfb && command -v xauth && command -v setpriv && test -f /usr/share/glvnd/egl_vendor.d/50_mesa.json && echo CAPTURE-TOOLS-OK'"%shlex.quote(tag),timeout=120)
        if 'CAPTURE-TOOLS-OK' not in probe.stdout:
            raise RuntimeError('built image still lacks capture tools: '+(probe.stdout+probe.stderr)[-300:])
        return {'image':tag,'build':r.stdout.strip()[-200:]}
    finally:
        release(held)

KEEP_AWAKE='watoom-keep-awake'
KEEP_AWAKE_UNIT="""[Unit]
Description=Keep Bazzite available as the homelab build/export worker (blocks automatic idle suspend only)
After=systemd-logind.service
[Service]
ExecStart=/usr/bin/systemd-inhibit --what=idle --mode=block --who=watoom-homelab --why=Homelab-worker-stays-available /usr/bin/sleep infinity
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
"""

def keep_awake(enable=True):
    """Owner-approved 2026-11-04: Bazzite must not auto-suspend while it serves homelab jobs. Idle-only, so the
    owner can still suspend it manually; allow-sleep removes it."""
    if enable:
        # content travels base64 in the argument: stdin carries only the sudo password
        b64=base64.b64encode(KEEP_AWAKE_UNIT.encode()).decode()
        sh("sh -c %s"%shlex.quote("printf %%s %s | base64 -d > /etc/systemd/system/%s.service"%(b64,KEEP_AWAKE)),timeout=60,check=True,sudo=True)
        sh('sh -c %s'%shlex.quote('systemctl daemon-reload && systemctl enable --now %s.service'%KEEP_AWAKE),timeout=60,check=True,sudo=True)
    else:
        sh('sh -c %s'%shlex.quote('systemctl disable --now %s.service; rm -f /etc/systemd/system/%s.service; systemctl daemon-reload'%(KEEP_AWAKE,KEEP_AWAKE)),timeout=60,sudo=True)
    return sh('systemctl is-active %s.service; systemd-inhibit --list --no-pager | grep -c watoom-homelab'%KEEP_AWAKE,timeout=60).stdout.split()

if __name__=='__main__':
    if os.geteuid()!=0:
        raise SystemExit('Run as root: the credentials file is root-only')
    op=sys.argv[1] if len(sys.argv)>1 else 'check'
    if op=='check':
        ram,disk=free()
        print(json.dumps({'reachable':True,'available_ram_gib':round(ram/2**30,1),'free_disk_gib':round(disk/2**30,1),'staged':runtime_ready()},indent=1))
    elif op=='stage-runtime':
        image=subprocess.check_output(['kubectl','-n','watoom-code','get','deploy','watoom-toolkit','-o','jsonpath={.spec.template.spec.containers[0].image}'],text=True).strip()
        print(json.dumps(stage_runtime(image),indent=1))
    elif op=='build-capture-image':
        print(json.dumps(build_capture_image(runtime_ready()[1]['local_tag']),indent=1))
    elif op in ('keep-awake','allow-sleep'):
        print(json.dumps({'keep_awake':keep_awake(op=='keep-awake')}))
    else:
        raise SystemExit('usage: bazzite.py check|stage-runtime|build-capture-image|keep-awake|allow-sleep')
