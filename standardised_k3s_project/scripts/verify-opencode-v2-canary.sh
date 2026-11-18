#!/usr/bin/env bash
set -Eeuo pipefail

NS="${NS:-opencode}"
DEPLOY="${DEPLOY:-opencode-v2-canary}"

MODEL="${MODEL:-watoom/swift-qwen38-coder}"
AGENT="${AGENT:-watoom-builder}"

RUN_MODEL_SMOKE="${RUN_MODEL_SMOKE:-0}"
RUN_SKILL_SMOKE="${RUN_SKILL_SMOKE:-0}"

TMPROOT="$(mktemp -d /tmp/watoom-opencode-v2-verify.XXXXXX)"

cleanup() {
  rm -rf "$TMPROOT"
}
trap cleanup EXIT

section() {
  printf '\n======================================================================\n%s\n======================================================================\n' "$1"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

capture() {
  local outfile="$1"
  shift

  set +e
  "$@" >"$outfile" 2>&1
  local rc=$?
  set -e

  cat "$outfile"
  return "$rc"
}

###############################################################################
# 1. PRODUCTION SAFETY
###############################################################################

section "1. PRODUCTION SAFETY"

kubectl -n "$NS" get deployment "$DEPLOY"

READY="$(
  kubectl -n "$NS" get deployment "$DEPLOY" \
    -o jsonpath='{.status.readyReplicas}'
)"

[[ "${READY:-0}" -ge 1 ]] || fail "OpenCode V2 production deployment is not Ready"

echo "PRODUCTION_READY=PASS"

###############################################################################
# 2. VERSION
###############################################################################

section "2. CANARY VERSION"

VERSION="$(
  kubectl -n "$NS" exec "deployment/$DEPLOY" -- \
    opencode --version |
    tail -1 |
    tr -d '\r'
)"

echo "version=$VERSION"

[[ "$VERSION" =~ ^(opencode[[:space:]]+v)?2[.] ]] ||
  fail "expected OpenCode V2, got: $VERSION"

echo "V2_VERSION=PASS"

###############################################################################
# 3. RESOLVED CONFIG
###############################################################################

section "3. RESOLVED CONFIG"

CONFIG_OUT="$TMPROOT/config.txt"

if ! capture "$CONFIG_OUT" \
  kubectl -n "$NS" exec "deployment/$DEPLOY" -- \
    opencode debug config
then
  fail "opencode debug config failed"
fi

grep -Fq '"providerID": "watoom"' "$CONFIG_OUT" ||
  fail "resolved config does not contain providerID watoom"

grep -Fq '"model": "active-model"' "$CONFIG_OUT" ||
  fail "resolved config does not contain active-model"

grep -Fq '"default_agent": "watoom-workflow"' "$CONFIG_OUT" ||
  fail "resolved config does not contain default watoom-workflow"

echo "RESOLVED_CONFIG=PASS"

###############################################################################
# 4. AGENT CATALOG
###############################################################################

section "4. AGENT CATALOG"

AGENT_OUT="$TMPROOT/agents.txt"

if ! capture "$AGENT_OUT" \
  kubectl -n "$NS" exec "deployment/$DEPLOY" -- \
    opencode debug agents
then
  fail "opencode debug agents failed"
fi

for agent in \
  watoom-builder \
  watoom-investigator \
  watoom-reviewer
do
  grep -Fq "\"id\": \"$agent\"" "$AGENT_OUT" ||
    fail "missing V2 agent: $agent"
done

echo "AGENT_CATALOG=PASS"

###############################################################################
# 5. NATIVE SKILL FILES
###############################################################################

section "5. NATIVE SKILL FILES"

SKILL_OUT="$TMPROOT/skills.txt"

kubectl -n "$NS" exec "deployment/$DEPLOY" -- sh -lc '
  find "$HOME/.config/opencode/skills" \
    -mindepth 2 \
    -maxdepth 2 \
    -name SKILL.md \
    -print |
  sort
' | tee "$SKILL_OUT"

for skill in \
  ansible \
  kubernetes \
  bash \
  python \
  typescript \
  validation-recovery \
  web-smoke
do
  grep -Fq "/skills/${skill}/SKILL.md" "$SKILL_OUT" ||
    fail "missing native skill: $skill"
done

echo "NATIVE_SKILL_FILES=PASS"

###############################################################################
# 6. MODEL CATALOG
###############################################################################

section "6. MODEL CATALOG"

MODEL_OUT="$TMPROOT/models.txt"

if ! capture "$MODEL_OUT" \
  kubectl -n "$NS" exec "deployment/$DEPLOY" -- \
    opencode models
then
  fail "opencode models failed"
fi

grep -Fq 'watoom/active-model' "$MODEL_OUT" ||
  fail "active-model alias is not visible"

grep -Fq 'watoom/swift-qwen38-coder' "$MODEL_OUT" ||
  fail "Swift Qwen alias is not visible"

echo "MODEL_CATALOG=PASS"

###############################################################################
# 7. V2 SESSION API
###############################################################################

section "7. V2 SESSION API"

API_OUT="$TMPROOT/api-session.json"

if ! capture "$API_OUT" \
  kubectl -n "$NS" exec "deployment/$DEPLOY" -- \
    opencode api \
      --server http://127.0.0.1:4096 \
      -H 'accept:application/json' \
      GET /api/session
then
  fail "V2 session API request failed"
fi

python3 - "$API_OUT" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    obj = json.load(f)

if not isinstance(obj, dict):
    raise SystemExit("ERROR: /api/session response is not a JSON object")

if "data" not in obj or not isinstance(obj["data"], list):
    raise SystemExit("ERROR: /api/session response missing list field: data")

cursor = obj.get("cursor")
if cursor is not None and not isinstance(cursor, dict):
    raise SystemExit("ERROR: /api/session cursor is not an object/null")

print(f"session_count={len(obj['data'])}")
print("V2_SESSION_API_JSON=PASS")
PY

echo "V2_SESSION_API=PASS"

###############################################################################
# 8. OPTIONAL MODEL SMOKE
###############################################################################

section "8. OPTIONAL MODEL SMOKE"

if [[ "$RUN_MODEL_SMOKE" == "1" ]]; then
  MODEL_SMOKE_OUT="$TMPROOT/model-smoke.log"

  set +e
  timeout 1200 \
    kubectl -n "$NS" exec "deployment/$DEPLOY" -- \
      opencode run \
        --server http://127.0.0.1:4096 \
        --agent "$AGENT" \
        --model "$MODEL" \
        --format json \
        "Do not use tools. Reply with exactly V2_CANARY_OK." \
      >"$MODEL_SMOKE_OUT" 2>&1
  RC=$?
  set -e

  cat "$MODEL_SMOKE_OUT"

  [[ "$RC" -eq 0 ]] || fail "model smoke returned rc=$RC"

  grep -Fq 'V2_CANARY_OK' "$MODEL_SMOKE_OUT" ||
    fail "model smoke did not return V2_CANARY_OK"

  echo "MODEL_SMOKE=PASS"
else
  echo "MODEL_SMOKE=SKIPPED"
fi

###############################################################################
# 9. OPTIONAL NATIVE SKILL SMOKE
###############################################################################

section "9. OPTIONAL NATIVE SKILL SMOKE"

if [[ "$RUN_SKILL_SMOKE" == "1" ]]; then
  SKILL_SMOKE_OUT="$TMPROOT/skill-smoke.log"

  set +e
  timeout 1200 \
    kubectl -n "$NS" exec "deployment/$DEPLOY" -- \
      opencode run \
        --server http://127.0.0.1:4096 \
        --agent "$AGENT" \
        --model "$MODEL" \
        --format json \
        "Load the native typescript skill. After it loads, reply with exactly V2_SKILL_OK and do not use any other tool." \
      >"$SKILL_SMOKE_OUT" 2>&1
  RC=$?
  set -e

  cat "$SKILL_SMOKE_OUT"

  [[ "$RC" -eq 0 ]] || fail "native skill smoke returned rc=$RC"

  grep -Fq 'V2_SKILL_OK' "$SKILL_SMOKE_OUT" ||
    fail "native skill smoke did not return V2_SKILL_OK"

  echo "NATIVE_SKILL_SMOKE=PASS"
else
  echo "NATIVE_SKILL_SMOKE=SKIPPED"
fi

###############################################################################
# 10. CANARY HEALTH
###############################################################################

section "10. CANARY HEALTH"

kubectl -n "$NS" get pod \
  -l app="$DEPLOY" \
  -o wide

kubectl -n "$NS" logs \
  "deployment/$DEPLOY" \
  --tail=100

echo
echo "WATOOM_OPENCODE_V2_CANARY_VERIFY=PASS"
