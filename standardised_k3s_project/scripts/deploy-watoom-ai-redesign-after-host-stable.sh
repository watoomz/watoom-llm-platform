#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT="${PROJECT_ROOT:-/data/github/watoom-standardised-homelab/standardised_k3s_project}"
if [[ "${WATOOM_DEPLOY_AFTER_HOST_STABLE:-}" != "YES" ]]; then
  echo 'REFUSED: set WATOOM_DEPLOY_AFTER_HOST_STABLE=YES only after reviewing the host stability audit.' >&2
  exit 20
fi
cd "$PROJECT"
grep -Fq 'watoom_execution_stage: "A"' ansible/roles/pi-kali-agent/defaults/main.yml || { echo 'REFUSE: Stage A is not configured' >&2; exit 21; }
scripts/tool-knowledge verify
ANSIBLE_ROLES_PATH="$PROJECT/ansible/roles" ansible-playbook -i ansible/inventories/homelab/hosts.yml ansible/playbooks/pi-kali-agent.yml --syntax-check
ANSIBLE_ROLES_PATH="$PROJECT/ansible/roles" ansible-playbook -i ansible/inventories/homelab/hosts.yml ansible/playbooks/pi-kali-agent.yml --tags grounding-stage-a
kubectl -n pi-agent rollout status deployment/pi-agent --timeout=180s
kubectl -n pi-agent get pods -o wide
