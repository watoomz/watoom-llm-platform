#!/usr/bin/env bash
# One-time live cutover for the "plain watoom-code" rename. Run on the homelab after the rename branch is merged to main
# and checked out at /data/github/watoom-standardised-homelab. Default is a DRY RUN that only prints what it would do.
#
#   scripts/cutover-watoom-code-rename.sh            # dry run
#   scripts/cutover-watoom-code-rename.sh --apply     # take the GUI offline, move data, redeploy under the new names
#   scripts/cutover-watoom-code-rename.sh --finalize  # after you have checked the new deployment: delete the old namespaces
#
# Names:  opencode-watoom-stage -> watoom-code            /data/ai/watoom-code-stage -> /data/ai/watoom-code
#         opencode-rig-jobs-stage -> watoom-code-rig-jobs  /data/ai/watoom-code-rig-jobs-stage -> /data/ai/watoom-code-rig-jobs
#         opencode-learning-20261023 / opencode-learning-repair-20261025 -> watoom-code-learning-20261023 / watoom-code-learning-repair-20261025
# Secrets are copied cluster-to-cluster through a pipe; they are never written to disk.
# Rollback before --finalize: scale the new deployments to 0, move the data folders back, scale the old deployments back up.
set -euo pipefail
MODE=dry; [[ "${1:-}" == "--apply" ]] && MODE=apply; [[ "${1:-}" == "--finalize" ]] && MODE=finalize
PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLD_NS=opencode-watoom-stage;   NEW_NS=watoom-code
OLD_RIG=opencode-rig-jobs-stage; NEW_RIG=watoom-code-rig-jobs
OLD_DIR=/data/ai/watoom-code-stage;           NEW_DIR=/data/ai/watoom-code
OLD_RIGDIR=/data/ai/watoom-code-rig-jobs-stage; NEW_RIGDIR=/data/ai/watoom-code-rig-jobs
LOG=/root/watoom-code-rename-$(date +%Y%m%d-%H%M%S).log
run() { echo "+ $*" | tee -a "$LOG"; [[ $MODE == apply || $MODE == finalize ]] && "$@" || true; }
say() { echo "== $*" | tee -a "$LOG"; }
die() { echo "REFUSE: $*" >&2; exit 1; }

say "mode=$MODE log=$LOG"
if [[ $MODE == finalize ]]; then
  kubectl -n "$NEW_NS" get deploy watoom-code -o jsonpath='{.status.readyReplicas}' | grep -q '^1$' || die "new watoom-code is not ready"
  run kubectl delete namespace "$OLD_NS" "$OLD_RIG" opencode-learning-20261023 opencode-learning-repair-20261025 --wait=false
  say "done; old namespaces are deleting"; exit 0
fi

say "preflight"
grep -q 'watoom_code_namespace: watoom-code' "$PROJECT/ansible/vars/watoom-code.yml" "$PROJECT/ansible/roles/watoom-code/defaults/main.yml" 2>/dev/null || die "checkout does not contain the rename (merge the rename-watoom-code branch first)"
[[ -f "$PROJECT/ansible/playbooks/watoom-code.yml" ]] || die "ansible/playbooks/watoom-code.yml missing"
kubectl get ns "$OLD_NS" >/dev/null || die "$OLD_NS does not exist"
kubectl get ns "$NEW_NS" >/dev/null 2>&1 && die "$NEW_NS already exists"
[[ -d $OLD_DIR ]] || die "$OLD_DIR missing"; [[ ! -e $NEW_DIR ]] || die "$NEW_DIR already exists"
[[ ! -e $NEW_RIGDIR ]] || die "$NEW_RIGDIR already exists"
RIG_PRESENT=0; kubectl get ns "$OLD_RIG" >/dev/null 2>&1 && RIG_PRESENT=1

say "1. record and stop the old workloads"
kubectl -n "$OLD_NS" get deploy -o custom-columns=NAME:.metadata.name,REPLICAS:.spec.replicas --no-headers | tee -a "$LOG" >/dev/null
for d in $(kubectl -n "$OLD_NS" get deploy --no-headers | awk '$3>0{print $1}'); do run kubectl -n "$OLD_NS" scale deploy/"$d" --replicas=0; done
if [[ $RIG_PRESENT == 1 ]]; then for d in $(kubectl -n "$OLD_RIG" get deploy --no-headers | awk '$3>0{print $1}'); do run kubectl -n "$OLD_RIG" scale deploy/"$d" --replicas=0; done; fi
run sleep 20

say "2. move the data folders (the state lives on the SSD and is bind-mounted at /data/ai/<name>, see scripts/move-state-to-ssd.sh)"
move_dir() {  # old new : handles a bind-mounted directory as well as a plain one
  local old=$1 new=$2 ssd_old=/app/ai/$(basename "$1") ssd_new=/app/ai/$(basename "$2")
  if mountpoint -q "$old"; then
    run umount "$old"
    run mv "$ssd_old" "$ssd_new"
    run mkdir "$new"
    if [[ $MODE == apply ]]; then
      sed -i "s#^$ssd_old $old #$ssd_new $new #" /etc/fstab
      rmdir "$old" 2>/dev/null || true
      systemctl daemon-reload
    else echo "+ (would repoint the fstab bind mount to $ssd_new -> $new)" | tee -a "$LOG"; fi
    run mount "$new"
  else
    run mv "$old" "$new"
  fi
}
move_dir "$OLD_DIR" "$NEW_DIR"
[[ -d $OLD_RIGDIR ]] && move_dir "$OLD_RIGDIR" "$NEW_RIGDIR"

say "3. create the new namespaces with the old labels, copy secrets"
copy_ns() {  # old new
  local old=$1 new=$2
  if [[ $MODE == apply ]]; then
    kubectl get ns "$old" -o json | python3 -c "
import sys,json
d=json.load(sys.stdin); l={k:v for k,v in d['metadata'].get('labels',{}).items() if not k.startswith('kubernetes.io/')}
print(json.dumps({'apiVersion':'v1','kind':'Namespace','metadata':{'name':'$new','labels':l}}))" | kubectl apply -f -
    for s in $(kubectl -n "$old" get secret -o json | python3 -c "
import sys,json
print(' '.join(s['metadata']['name'] for s in json.load(sys.stdin)['items'] if s['type'] not in ('kubernetes.io/service-account-token',)))"); do
      kubectl -n "$old" get secret "$s" -o json | python3 -c "
import sys,json
d=json.load(sys.stdin); m=d['metadata']; d['metadata']={'name':m['name'],'namespace':'$new','labels':m.get('labels',{}),'annotations':{k:v for k,v in m.get('annotations',{}).items() if not k.startswith('kubectl.kubernetes.io/')}}
print(json.dumps(d))" | kubectl apply -f - >/dev/null && echo "copied secret $s -> $new" | tee -a "$LOG"
    done
  else echo "+ (would create namespace $new with the labels of $old and copy its secrets)" | tee -a "$LOG"; fi
}
copy_ns "$OLD_NS" "$NEW_NS"; [[ $RIG_PRESENT == 1 ]] && copy_ns "$OLD_RIG" "$NEW_RIG"

say "3b. recreate the dormant self-learning sandbox namespaces under the new prefix (objects only; their data lives in /data/ai/helper-scripts)"
recreate_learning() {  # old
  local old=$1 new=${1/opencode-learning-/watoom-code-learning-}
  kubectl get ns "$old" >/dev/null 2>&1 || { echo "(skip $old: not present)" | tee -a "$LOG"; return; }
  if [[ $MODE == apply ]]; then
    local owner; owner=$(kubectl get ns "$old" -o jsonpath='{.metadata.labels.watoom-owner}')
    kubectl create ns "$new" 2>/dev/null || true
    kubectl label ns "$new" "watoom-owner=$owner" --overwrite >/dev/null
    kubectl -n "$old" get deploy,svc,cm -o json | python3 -c "
import sys,json
d=json.load(sys.stdin); out=[]
for i in d['items']:
    if i['metadata']['name']=='kube-root-ca.crt': continue
    m=i['metadata']; i['metadata']={k:v for k,v in {'name':m['name'],'namespace':'$new','labels':m.get('labels'),'annotations':{a:b for a,b in (m.get('annotations') or {}).items() if not a.startswith(('kubectl.kubernetes.io/','deployment.kubernetes.io/'))} or None}.items() if v}
    i.pop('status',None)
    if i['kind']=='Service':
        for k in ('clusterIP','clusterIPs'): i['spec'].pop(k,None)
    out.append(i)
print(json.dumps({'apiVersion':'v1','kind':'List','items':out}).replace('opencode-learning-','watoom-code-learning-'))" | kubectl apply -f - && echo "recreated $old as $new" | tee -a "$LOG"
  else echo "+ (would recreate $old as $new with its deployments, services and configmaps)" | tee -a "$LOG"; fi
}
recreate_learning opencode-learning-20261023; recreate_learning opencode-learning-repair-20261025

say "4. apply namespace allow-lists, then redeploy from the renamed IaC"
run kubectl apply -f "$PROJECT/manifests/10-infrastructure/llm/llama-cpp-network-policy.yml"
run env ANSIBLE_CONFIG="$PROJECT/ansible/ansible.cfg" ANSIBLE_ROLES_PATH="$PROJECT/ansible/roles" ansible-playbook -i "$PROJECT/ansible/inventories/homelab/hosts.yml" "$PROJECT/ansible/playbooks/watoom-code.yml"
run env ANSIBLE_CONFIG="$PROJECT/ansible/ansible.cfg" ANSIBLE_ROLES_PATH="$PROJECT/ansible/roles" ansible-playbook -i "$PROJECT/ansible/inventories/homelab/hosts.yml" "$PROJECT/ansible/playbooks/watoom-code-lan-route.yml" -e watoom_code_lan_route_approved=true

say "4b. recreate the isolated RIG-jobs app (provision-app.py only creates it once) from the old objects, and repoint the dispatcher config"
# The old app was running before the cutover; copy its ServiceAccount/Service/Deployment into the new namespace with the names rewritten.
run python3 - <<'PYEOF'
import json,subprocess
O="opencode-rig-jobs-stage"
def rw(t):
    for a,b in (("opencode-watoom-stage","watoom-code"),(O,"watoom-code-rig-jobs"),("watoom-code-rig-jobs-stage","watoom-code-rig-jobs"),("watoom-code-stage","watoom-code")):t=t.replace(a,b)
    return t
items=[]
for kind in ("serviceaccount/watoom-code","service/watoom-code","deployment/watoom-code"):
    d=json.loads(subprocess.check_output(["kubectl","-n",O,"get",kind,"-o","json"]))
    m=d["metadata"]
    for k in ("uid","resourceVersion","creationTimestamp","generation","managedFields","ownerReferences"):m.pop(k,None)
    m.get("annotations",{}).pop("kubectl.kubernetes.io/last-applied-configuration",None);m.get("annotations",{}).pop("deployment.kubernetes.io/revision",None)
    d.pop("status",None)
    if d["kind"]=="Service":d["spec"].pop("clusterIP",None);d["spec"].pop("clusterIPs",None)
    if d["kind"]=="Deployment":d["spec"]["replicas"]=1
    items.append(json.loads(rw(json.dumps(d))))
subprocess.run(["kubectl","apply","-f","-"],input=json.dumps({"apiVersion":"v1","kind":"List","items":items}).encode(),check=True)
PYEOF
run sed -i 's#"namespace": "opencode-rig-jobs-stage"#"namespace": "watoom-code-rig-jobs"#; s#/data/ai/watoom-code-rig-jobs-stage/#/data/ai/watoom-code-rig-jobs/#g' /etc/watoom-rig-async-stage.json

say "5. verify"
run kubectl -n "$NEW_NS" rollout status deploy/watoom-code --timeout=300s
run kubectl -n "$NEW_NS" get pods
say "6. installed copies that still embed the old names (systemd units, /usr/local/libexec, frozen controllers). Re-run the playbook that installed each one"
grep -l -E "opencode-watoom-stage|opencode-rig-jobs-stage|watoom-code-stage|opencode-learning-" /etc/systemd/system/*.service /etc/systemd/system/*.timer /usr/local/libexec/watoom/* /data/ai/helper-scripts/watoom-self-learning-*/production/recovery-state.json 2>/dev/null | tee -a "$LOG" || true
say "   known: ansible/playbooks/worker-status.yml refreshes worker_status.py and bazzite.py; the self-learning recovery state points at namespace opencode-watoom-stage and its frozen recover.py only accepts that exact name, so redeploy the self-learning controller (watoom-code-self-learning-controller.yml) or edit recovery-state.json before the recovery timer runs again"
say "Check https://watoom-code.internal.homelab.example in a browser, then run: $0 --finalize"
