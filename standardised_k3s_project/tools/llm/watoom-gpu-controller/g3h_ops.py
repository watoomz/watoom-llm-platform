"""Bounded offline/live operator checks and fail-closed recovery.

Never scales deployments directly and never restores legacy write permissions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import copy
from client import GPUClient
from g3h_service import atomic, process_identity

BASE = Path('/data/ai/helper-scripts')
PRIVATE = BASE / 'state/gpu-controller-private/worker.sock'
MARKER = BASE / 'state/gpu-controller-maintenance'
AGENTS = Path('/app/ai/services/opencode/home/.config/opencode/agent')
MISSING={'__gpu_missing__':True}


def restore_timeout(document, before, after):
    result=copy.deepcopy(document)
    server=result['mcp'].get('servers', result['mcp'])['watoom-llama-mesh']
    value=server.get('timeout',MISSING)
    if value==before:return result
    if value!=after:raise RuntimeError('MCP timeout changed independently; restoration conflict')
    if before==MISSING:server.pop('timeout',None)
    else:server['timeout']=before
    return result


def opencode_config(root, restore=False):
    path=Path(root)/'opencode-timeout.json'
    raw=subprocess.check_output(['kubectl','-n','opencode','get','cm','opencode-v2-canary-config','-o','json'])
    cm=json.loads(raw)
    current=cm['data']['opencode.json']
    document=json.loads(current)
    if not path.exists():
        if restore:raise RuntimeError('missing timeout restoration record')
        atomic(path,{'before':document['mcp'].get('servers', document['mcp'])['watoom-llama-mesh'].get('timeout',MISSING),'after':{'startup':30000,'catalog':30000,'execution':3600000}})
    record=json.loads(path.read_text())
    updated=restore_timeout(document,record['before'] if restore else record['after'],record['after'] if restore else record['before'])
    if updated==document:return
    ops=[{'op':'test','path':'/metadata/uid','value':cm['metadata']['uid']},
         {'op':'test','path':'/metadata/resourceVersion','value':cm['metadata']['resourceVersion']},
         {'op':'test','path':'/data/opencode.json','value':current},
         {'op':'replace','path':'/data/opencode.json','value':json.dumps(updated,indent=2)+'\n'}]
    # One conditional attempt. A concurrent ConfigMap edit fails without overwriting it.
    subprocess.run(['kubectl','-n','opencode','patch','cm','opencode-v2-canary-config','--type=json','-p',json.dumps(ops)],check=True,capture_output=True)


def restore_model(current, before, after):
    """Restore only the owned frontmatter field, preserving all unrelated text."""
    match = re.search(r'\A---\r?\n(?P<front>.*?)\r?\n---(?:\r?\n|$)', current, re.S)
    if not match:
        raise RuntimeError('missing agent frontmatter')
    model = re.search(r'^model:.*$', match['front'], re.M)
    if not model:
        raise RuntimeError('missing model field')
    value = model.group()
    if value == before:
        return current
    if value != after:
        raise RuntimeError('model field changed independently; restoration conflict')
    start = match.start('front') + model.start()
    end = match.start('front') + model.end()
    return current[:start] + before + current[end:]


def opencode_patch(root, restore=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = root / 'opencode-fields.json'
    if not record.exists():
        if restore:
            raise RuntimeError('missing OpenCode restoration record')
        changes = []
        for name in ('watoom-workflow.md', 'watoom-investigator.md'):
            path = AGENTS / name
            text = path.read_text()
            match = re.search(r'\A---\n.*?^model:([^\n]*)$', text, re.S | re.M)
            if not match:
                raise RuntimeError('missing model frontmatter: ' + name)
            before = 'model:' + match[1]
            (root / name).write_text(text)
            changes.append({'name': name, 'before': before, 'after': 'model: watoom/swift-qwen38-coder'})
        atomic(record, changes)
    changes = json.loads(record.read_text())
    # Precompute all replacements before writing any file (conflict fails closed).
    replacements = []
    for change in changes:
        path = AGENTS / change['name']
        text = path.read_text()
        before, after = change['before'], change['after']
        result = restore_model(text, before if restore else after, after if restore else before)
        replacements.append((path, result))
    for path, result in replacements:
        temp = path.with_name(path.name + '.gpu-controller-new')
        metadata = path.stat()
        with temp.open('w') as stream:
            stream.write(result); stream.flush(); os.fsync(stream.fileno())
        os.chown(temp, metadata.st_uid, metadata.st_gid)
        os.chmod(temp, metadata.st_mode & 0o777)
        os.replace(temp, path)
    opencode_config(root, restore=restore)
    print('RESULT=OPENCODE_FIELDS_' + ('RESTORED' if restore else 'PATCHED'))


def rollback_decision(status, live):
    if status['owner']:
        return 'DEFER_LIVE_OWNER' if live else 'RECOVER_ENDED_OWNER'
    if status['phase']=='model-ready' and not status['uncertain']:
        return 'RESTORE_PRIMARY'
    if status['phase'] != 'qwen-ready' or status['uncertain']:
        return 'BLOCKED_UNOWNED_UNSAFE_STATE'
    return 'VERIFY_QWEN'


def rollback(client, owner_live, health, restore):
    status = client.call('status')
    decision = rollback_decision(status, owner_live(status['owner']) if status['owner'] else False)
    if decision.startswith(('DEFER', 'BLOCKED')):
        return decision
    if decision == 'RECOVER_ENDED_OWNER':
        client.call('recover', job=status['owner'], generation=status['generation'])
    elif decision == 'RESTORE_PRIMARY':
        client.call('request-model',deployment=status['primary'],allow_switch=True)
    # No retries. Restoration is gated on actual Qwen inference.
    health()
    restore()
    return 'QWEN_SAFE_MESH_SUBMISSIONS_PAUSED'


def emergency(root):
    MARKER.touch(mode=0o600, exist_ok=True)
    client = GPUClient(PRIVATE, timeout=1500)
    def live(job):
        owner=json.loads((BASE/'state/gpu-controller/worker.json').read_text())
        if owner['job']!=job:raise RuntimeError('owner identity does not match durable registry')
        if owner.get('kind') in ('router','operator'):return process_identity(owner['pid'])==owner['start']
        result = subprocess.run(['systemctl', 'show', 'llama-mesh-' + job,
                                 '--property=ActiveState', '--value'], capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError('worker liveness unverifiable')
        return result.stdout.strip() in ('active', 'activating', 'deactivating')
    def health():
        subprocess.run(['/usr/bin/python3', str(BASE / 'llama_mesh_pipeline.py'), 'health'], check=True, timeout=800)
    result = rollback(client, live, health, lambda: opencode_patch(root, restore=True))
    print('RESULT=' + result)


def router_restore_plan(current_cm, current_deployment, before_cm, candidate_cm):
    cm=copy.deepcopy(current_cm)
    for key in ('router.py','client.py'):
        before=before_cm['data'].get(key,MISSING)
        after=candidate_cm['data'].get(key,MISSING)
        present=cm['data'].get(key,MISSING)
        if present==before:continue
        if present!=after:raise RuntimeError('router ConfigMap field edited independently: '+key)
        if before==MISSING:cm['data'].pop(key,None)
        else:cm['data'][key]=before
    deployment=copy.deepcopy(current_deployment)
    pod=deployment['spec']['template']['spec']
    expected_volume={'name':'gpu-controller','hostPath':{'path':'/data/ai/helper-scripts/state/gpu-controller-router','type':'Directory'}}
    for volume in list(pod['volumes']):
        if volume['name']=='gpu-controller':
            if volume!=expected_volume:raise RuntimeError('router controller mount changed independently')
            pod['volumes'].remove(volume)
    for container in pod['containers']:
        for mount in list(container.get('volumeMounts',[])):
            if mount['name']=='gpu-controller':
                if mount!={'name':'gpu-controller','mountPath':'/gpu-controller','readOnly':True}:
                    raise RuntimeError('router controller mount changed independently')
                container['volumeMounts'].remove(mount)
    return cm,deployment


def router_rollback(snapshot, candidate):
    status=GPUClient(PRIVATE,timeout=30).call('status')
    if status['owner'] or status['phase']!='qwen-ready' or status['uncertain']:
        raise RuntimeError('router rollback deferred until ownership is safely released')
    MARKER.touch(mode=0o600,exist_ok=True)
    root=Path(snapshot)
    before=json.loads((root/'router-cm.json').read_text())
    import yaml
    proposed=next(yaml.safe_load_all(Path(candidate).read_text()))
    current_cm=json.loads(subprocess.check_output(['kubectl','-n','llama-cpp','get','cm','llm-router-app','-o','json']))
    current_deploy=json.loads(subprocess.check_output(['kubectl','-n','llama-cpp','get','deploy','llm-router','-o','json']))
    cm,deployment=router_restore_plan(current_cm,current_deploy,before,proposed)
    # Restore only owned fields with fresh UID/RV tests; unrelated edits survive.
    for kind,name,current,ops in [
        ('cm','llm-router-app',current_cm,[{'op':'replace','path':'/data','value':cm['data']}]),
        ('deployment','llm-router',current_deploy,[{'op':'replace','path':'/spec/template/spec/volumes','value':deployment['spec']['template']['spec']['volumes']},
            {'op':'replace','path':'/spec/template/spec/containers','value':deployment['spec']['template']['spec']['containers']}])]:
        tests=[{'op':'test','path':'/metadata/uid','value':current['metadata']['uid']},
               {'op':'test','path':'/metadata/resourceVersion','value':current['metadata']['resourceVersion']}]
        subprocess.run(['kubectl','-n','llama-cpp','patch',kind,name,'--type=json','-p',json.dumps(tests+ops)],check=True,capture_output=True)
    # Never apply the baseline Role: keep narrow read permissions and admission fence.
    print('RESULT=ROUTER_BASELINE_CODE_RESTORED_LEGACY_SCALING_DENIED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('opencode-patch', 'opencode-rollback', 'emergency-recovery','router-rollback'))
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--candidate')
    args = parser.parse_args()
    if args.action == 'router-rollback':
        router_rollback(args.snapshot,args.candidate)
    elif args.action == 'emergency-recovery':
        emergency(args.snapshot)
    else:
        opencode_patch(args.snapshot, restore=args.action.endswith('rollback'))
