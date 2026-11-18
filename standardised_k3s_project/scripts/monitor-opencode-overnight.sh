#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="${PROJECT:-/data/github/watoom-standardised-homelab/standardised_k3s_project}"
RUNNER="${OPENCODE_RUNNER:-$PROJECT/scripts/opencode-overnight}"
RUN_ROOT="${OPENCODE_RUN_ROOT:-/data/ai/projects/legacy-workspaces/opencode-workspace/.opencode-runs}"
NAMESPACE="${OPENCODE_NAMESPACE:-opencode}"
INTERVAL="${MONITOR_INTERVAL:-5}"
SHOW_GPU="${MONITOR_GPU:-1}"
SHOW_LLM="${MONITOR_LLM:-1}"
LLM_NAMESPACE="${MONITOR_LLM_NAMESPACE:-llama-cpp}"
LLM_SINCE="${MONITOR_LLM_SINCE:-15m}"
MODEL_ALIAS="${MONITOR_MODEL_ALIAS:-swift-qwen38-coder}"
QWEN_SELECTOR="${MONITOR_QWEN_SELECTOR:-app=llama-cpp-swift-qwen38-coder}"

usage() {
  cat <<'EOF'
Usage:
  monitor-opencode-overnight.sh [RUN_ID]
  monitor-opencode-overnight.sh --once [RUN_ID]

Environment:
  MONITOR_INTERVAL=5       refresh interval in seconds
  MONITOR_GPU=1            show compact GPU status (set 0 to disable)
  MONITOR_LLM=1            show router + Qwen activity (set 0 to disable)
  MONITOR_LLM_SINCE=15m    router/Qwen log lookback window
  MONITOR_LLM_NAMESPACE=llama-cpp
  MONITOR_MODEL_ALIAS=swift-qwen38-coder
  MONITOR_QWEN_SELECTOR=app=llama-cpp-swift-qwen38-coder
  OPENCODE_RUN_ROOT=...    override run directory root
  OPENCODE_NAMESPACE=...   default: opencode

Behaviour:
  - With no RUN_ID, automatically follows the newest run.
  - If a newer run appears while monitoring, it switches to it.
  - Ctrl-C stops only this monitor; it does not stop OpenCode or the runner.
EOF
}

once=0
case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  --once)
    once=1
    shift
    ;;
esac

requested_run="${1:-}"

latest_run() {
  find "$RUN_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null |
    sort |
    tail -1
}

compact_json_events() {
  local log="$1"
  [ -f "$log" ] || return 0

  python3 - "$log" <<'PY'
import json, sys
from collections import Counter

path = sys.argv[1]
events = []
tools = Counter()
last_tools = []

try:
    fh = open(path, "r", encoding="utf-8", errors="replace")
except OSError:
    raise SystemExit(0)

with fh:
    for line in fh:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue

        typ = ev.get("type")
        part = ev.get("part") or {}

        if typ == "tool_use":
            tool = part.get("tool", "?")
            state = part.get("state") or {}
            status = state.get("status", "?")
            inp = state.get("input")
            tools[tool] += 1
            last_tools.append((tool, status, inp))
            events.append(f"TOOL  {tool:<18} {status}")
        elif typ == "step_finish":
            reason = part.get("reason", "?")
            toks = part.get("tokens") or {}
            total = toks.get("total", "?")
            events.append(f"STEP  finish reason={reason} tokens={total}")
        elif typ == "text":
            text = part.get("text") or ""
            synthetic = (part.get("metadata") or {}).get("compaction_continue")
            if synthetic:
                events.append("TEXT  [synthetic compaction_continue]")
            elif text:
                first = " ".join(text.strip().split())
                if len(first) > 140:
                    first = first[:137] + "..."
                events.append("TEXT  " + first)

print("TOOL COUNTS")
if tools:
    for k, v in sorted(tools.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {k:<20} {v}")
else:
    print("  none")

print()
print("LAST TOOL CALLS")
if last_tools:
    for tool, status, inp in last_tools[-8:]:
        s = json.dumps(inp, sort_keys=True, ensure_ascii=False)
        if len(s) > 110:
            s = s[:107] + "..."
        print(f"  {tool:<18} {status:<10} {s}")
else:
    print("  none")

print()
print("LAST EVENTS")
for e in events[-12:]:
    print("  " + e)
PY
}

show_model_activity() {
  [ "$SHOW_LLM" = "1" ] || return 0

  echo "MODEL ROUTING"

  local router_line=""
  router_line="$(
    kubectl -n "$LLM_NAMESPACE" logs deploy/llm-router \
      --since="$LLM_SINCE" 2>/dev/null |
    grep '\[REQMETA\]' |
    grep "model=$MODEL_ALIAS" |
    tail -1 || true
  )"

  if [ -n "$router_line" ]; then
    echo "  $router_line"

    local tool_names tools messages message_chars stream
    tools="$(printf '%s\n' "$router_line" | sed -nE 's/.* tools=([0-9]+).*/\1/p')"
    tool_names="$(printf '%s\n' "$router_line" | sed -nE "s/.* tool_names=(\[[^]]*\]).*/\1/p")"
    messages="$(printf '%s\n' "$router_line" | sed -nE 's/.* messages=([0-9]+).*/\1/p')"
    message_chars="$(printf '%s\n' "$router_line" | sed -nE 's/.* message_chars=([0-9]+).*/\1/p')"
    stream="$(printf '%s\n' "$router_line" | sed -nE 's/.* stream=([^ ]+).*/\1/p')"

    echo "  summary: messages=${messages:-?} chars=${message_chars:-?} tools=${tools:-?} tool_names=${tool_names:-?} stream=${stream:-?}"
  else
    echo "  no matching REQMETA in last $LLM_SINCE"
  fi

  echo
  echo "QWEN ACTIVITY"

  local qpod=""
  qpod="$(
    kubectl -n "$LLM_NAMESPACE" get pod \
      -l "$QWEN_SELECTOR" \
      -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true
  )"

  if [ -z "$qpod" ]; then
    echo "  qwen pod not found for selector: $QWEN_SELECTOR"
    return 0
  fi

  echo "  pod=$qpod"

  local qlog=""
  qlog="$(
    kubectl -n "$LLM_NAMESPACE" logs "$qpod" \
      --since="$LLM_SINCE" 2>/dev/null |
    grep -E 'launch_slot_|processing task|prompt processing|n_gen|release:|error|ERROR|truncated' |
    tail -12 || true
  )"

  if [ -z "$qlog" ]; then
    echo "  no matching Qwen activity in last $LLM_SINCE"
    return 0
  fi

  printf '%s\n' "$qlog" | sed 's/^/  /'

  local last_line=""
  last_line="$(printf '%s\n' "$qlog" | tail -1)"

  if grep -q 'prompt processing' <<<"$last_line"; then
    local n_tokens progress estimate
    n_tokens="$(printf '%s\n' "$last_line" | sed -nE 's/.*n_tokens = *([0-9]+).*/\1/p')"
    progress="$(printf '%s\n' "$last_line" | sed -nE 's/.*progress = *([0-9.]+).*/\1/p')"
    estimate=""
    if [ -n "$n_tokens" ] && [ -n "$progress" ]; then
      estimate="$(
        python3 - "$n_tokens" "$progress" <<'PY'
import sys
n = int(sys.argv[1])
p = float(sys.argv[2])
print(round(n / p) if p > 0 else "?")
PY
      )"
    fi
    echo "  state=prompt-processing progress=${progress:-?} n_tokens=${n_tokens:-?} estimated_prompt_tokens=${estimate:-?}"
  elif grep -q 'n_gen' <<<"$last_line"; then
    local n_gen rate
    n_gen="$(printf '%s\n' "$last_line" | sed -nE 's/.*n_gen = *([0-9]+).*/\1/p')"
    rate="$(printf '%s\n' "$last_line" | sed -nE 's/.*tg = *([0-9.]+) t\/s.*/\1/p')"
    echo "  state=generating n_gen=${n_gen:-?} rate=${rate:-?} tok/s"
  elif grep -q 'release:' <<<"$last_line"; then
    echo "  state=turn-released"
  elif grep -q 'launch_slot_' <<<"$last_line"; then
    echo "  state=starting-next-turn"
  fi
}

show_processes() {
  echo "PROCESS STATE"
  ps -eo pid,ppid,stat,etime,cmd |
    grep -E 'opencode-overnight|opencode run|ansible-playbook|watoom-opencode-overnight-v3' |
    grep -v grep |
    sed 's/^/  /' || echo "  none"
}

show_gpu() {
  [ "$SHOW_GPU" = "1" ] || return 0
  command -v nvidia-smi >/dev/null 2>&1 || return 0

  echo "GPU"
  nvidia-smi \
    --query-gpu=name,utilization.gpu,memory.used,memory.total,pstate,power.draw,temperature.gpu \
    --format=csv,noheader,nounits 2>/dev/null |
    awk -F', *' '{
      printf "  %s | util=%s%% | vram=%s/%s MiB | %s | %s W | %s C\n",
             $1,$2,$3,$4,$5,$6,$7
    }'
}

show_once() {
  local run_id="$1"
  local run_dir="$RUN_ROOT/$run_id"

  clear 2>/dev/null || true
  echo "======================================================================"
  echo " OpenCode Overnight Monitor"
  echo "======================================================================"
  echo "time=$(date -Is)"
  echo "run_id=$run_id"
  echo "run_dir=$run_dir"
  echo

  if [ ! -d "$run_dir" ]; then
    echo "Run directory does not exist."
    return 1
  fi

  echo "RUNNER STATUS"
  if [ -x "$RUNNER" ]; then
    "$RUNNER" status "$run_id" 2>&1 |
      sed -n '1,18p' |
      sed 's/^/  /'
  else
    echo "  runner not executable/found: $RUNNER"
  fi
  echo

  local result exit_code watchdog duplicate
  result="$(cat "$run_dir/result" 2>/dev/null || true)"
  exit_code="$(cat "$run_dir/exit-code" 2>/dev/null || true)"
  watchdog="$(cat "$run_dir/watchdog-reason" 2>/dev/null || true)"
  duplicate="$(cat "$run_dir/duplicate-tool-signature" 2>/dev/null || true)"

  echo "RUN OUTCOME"
  echo "  result=${result:-running/unknown}"
  echo "  exit_code=${exit_code:-not-set}"
  echo "  watchdog=${watchdog:-none}"
  [ -z "$duplicate" ] || echo "  duplicate_tool_signature=$duplicate"
  echo

  show_model_activity
  echo

  compact_json_events "$run_dir/output.log"
  echo

  show_processes
  echo

  show_gpu
  echo
  echo "Ctrl-C stops only this monitor."
}

while :; do
  if [ -n "$requested_run" ]; then
    run_id="$requested_run"
  else
    run_id="$(latest_run)"
  fi

  if [ -z "${run_id:-}" ]; then
    clear 2>/dev/null || true
    echo "No OpenCode runs found under $RUN_ROOT"
  else
    show_once "$run_id" || true
  fi

  [ "$once" -eq 0 ] || break
  sleep "$INTERVAL"
done
