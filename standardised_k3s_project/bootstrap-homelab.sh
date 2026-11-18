#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-${1:-}}"
REPO_BRANCH="${REPO_BRANCH:-}"
REPO_PARENT="${REPO_PARENT:-/data/github}"
REPO_NAME="${REPO_NAME:-watoom-standardised-homelab}"
REPO_ROOT="${REPO_PARENT}/${REPO_NAME}"
PROJECT_ROOT="${REPO_ROOT}/standardised_k3s_project"

log() {
    printf '\n== %s ==\n' "$*"
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    die "Run this bootstrap as root."
fi

log "Install bootstrap dependencies"

if command -v dnf >/dev/null 2>&1; then
    dnf install -y \
        ansible-core \
        git \
        python3 \
        python3-kubernetes \
        python3-jmespath \
        rsync \
        curl \
        unzip \
        jq
else
    die "This bootstrap currently supports Fedora/RHEL-family hosts using dnf."
fi

log "Verify required executables"

for cmd in ansible-playbook ansible-galaxy git python3; do
    command -v "$cmd" >/dev/null 2>&1 || die "Missing required executable: $cmd"
done

mkdir -p "$REPO_PARENT"

if [[ -d "$REPO_ROOT/.git" ]]; then
    log "Existing repository detected"

    cd "$REPO_ROOT"

    CURRENT_REMOTE="$(git remote get-url origin 2>/dev/null || true)"

    if [[ -n "$REPO_URL" && -n "$CURRENT_REMOTE" && "$CURRENT_REMOTE" != "$REPO_URL" ]]; then
        die "Existing origin differs from requested REPO_URL:
existing: $CURRENT_REMOTE
requested: $REPO_URL"
    fi

    git fetch --prune origin

    if [[ -n "$REPO_BRANCH" ]]; then
        git checkout "$REPO_BRANCH"
        git pull --ff-only origin "$REPO_BRANCH"
    else
        git pull --ff-only
    fi
else
    [[ -n "$REPO_URL" ]] || die \
        "REPO_URL is required when the repository has not yet been cloned."

    log "Clone repository"

    if [[ -n "$REPO_BRANCH" ]]; then
        git clone \
            --branch "$REPO_BRANCH" \
            --single-branch \
            "$REPO_URL" \
            "$REPO_ROOT"
    else
        git clone "$REPO_URL" "$REPO_ROOT"
    fi
fi

[[ -d "$PROJECT_ROOT/ansible" ]] || die \
    "Ansible directory not found: $PROJECT_ROOT/ansible"

cd "$PROJECT_ROOT"

log "Install Ansible collections"

ansible-galaxy collection install \
    -r ansible/requirements.yml

log "Validate Python Kubernetes client"

python3 - <<'PY'
import kubernetes
print("kubernetes python client:", kubernetes.__version__)
PY

log "Validate Ansible syntax"

ANSIBLE_CONFIG=ansible/ansible.cfg \
ansible-playbook \
    --syntax-check \
    ansible/playbooks/site.yml

if [[ -r /etc/rancher/k3s/k3s.yaml ]]; then
    log "Configure root kubeconfig"

    install -d -m 0700 /root/.kube
    install \
        -m 0600 \
        -o root \
        -g root \
        /etc/rancher/k3s/k3s.yaml \
        /root/.kube/config
fi

if [[ -x "$PROJECT_ROOT/ansible-run" ]] &&
   [[ -r /etc/rancher/k3s/k3s.yaml ]]; then

    log "Run homelab validation"

    "$PROJECT_ROOT/ansible-run" playbooks/validate.yml
else
    log "Runtime validation skipped"
    echo "k3s may not be installed yet; run validation after site deployment."
fi

cat <<EOF2

Bootstrap complete.

Repository:
  $REPO_ROOT

Project:
  $PROJECT_ROOT

Full reconciliation:
  cd $PROJECT_ROOT
  ./ansible-run playbooks/site.yml

Validation:
  ./ansible-run playbooks/validate.yml
EOF2
