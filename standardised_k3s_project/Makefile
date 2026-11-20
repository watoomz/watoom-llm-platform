# One entry point for repository checks (T-0115). Run from standardised_k3s_project/.
#   make check        fast, deterministic gate (generated files, drift checks, all unit tests, JS tests)
#   make lint         ansible-lint + yamllint + shellcheck (slower; shellcheck skipped if not installed)
#   make all-checks   both
# Nothing here deploys or touches the live cluster.

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
PY := python3
export ANSIBLE_CONFIG := $(CURDIR)/ansible/ansible.cfg
export ANSIBLE_ROLES_PATH := $(CURDIR)/ansible/roles

PY_SUITES := tools/recovery tools/tickets tools/watoom-code/tests tools/watoom-code/self_learning \
             tools/language-knowledge/tests tools/moss-image/tests tools/creation-studio/tests \
             tools/writing-studio/tests tools/rig-async-stage/worker-source
NODE_TESTS := $(wildcard tools/watoom-code/test-*.mjs) $(wildcard tools/rig-async-stage/test-*.mjs)

.PHONY: check generated pytests gpu-controller-tests nodetests links lint all-checks

check: generated pytests gpu-controller-tests nodetests links
	@echo "make check: OK"

generated:
	$(PY) scripts/render-native-agents.py --check
	$(PY) scripts/sync-skill-shared.py --check
	$(PY) scripts/render-server-catalogue.py --check >/dev/null && echo 'OK: server catalogue up to date'
	$(PY) scripts/render-glance-guide.py --check >/dev/null && echo 'OK: Glance guide up to date'
	cd tools/rig-async-stage && $(PY) -c 'import json,hashlib,pathlib,sys; m=json.load(open("source-manifest.json")); bad=[n for n,s in m["files"].items() if hashlib.sha256(pathlib.Path(n).read_bytes()).hexdigest()!=s]; print("FAIL: rig source-manifest stale for", bad) if bad else print("OK: rig source-manifest matches"); sys.exit(1 if bad else 0)'

pytests:
	@for d in $(PY_SUITES); do echo "== $$d"; (cd $$d && $(PY) -m unittest discover -q 2>&1 | tail -n 3); \
	  (cd $$d && $(PY) -m unittest discover -q >/dev/null 2>&1) || { echo "FAIL: $$d"; exit 1; }; done

gpu-controller-tests:
	cd tools/llm/watoom-gpu-controller && $(PY) -m unittest discover -q -s tests

nodetests:
	@for t in $(NODE_TESTS); do node $$t >/dev/null 2>&1 || { echo "FAIL: $$t"; node $$t; exit 1; }; done
	@echo "node tests: $(words $(NODE_TESTS)) passed"

links:
	$(PY) scripts/check-md-links.py

lint:
	cd ansible && ansible-lint -q playbooks/
	yamllint -c ansible/.yamllint ansible
	@if command -v shellcheck >/dev/null; then git ls-files '*.sh' | xargs shellcheck -S error; else echo "shellcheck not installed; skipped"; fi

all-checks: check lint
