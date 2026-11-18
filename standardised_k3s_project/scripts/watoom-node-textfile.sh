#!/usr/bin/env bash
# Publish failed watoom-* systemd units and the GPU controller owner/phase for node-exporter's textfile collector.
set -euo pipefail
dir=/var/lib/node_exporter/textfile
tmp=$(mktemp "$dir/.watoom-systemd.XXXXXX")
trap 'rm -f "$tmp"' EXIT
{
  echo '# HELP watoom_systemd_unit_failed 1 when a watoom-* unit is in the failed state.'
  echo '# TYPE watoom_systemd_unit_failed gauge'
  systemctl list-units --all --plain --no-legend --no-pager --state=failed 'watoom-*' |
    awk '{print $1}' | while read -r unit; do
      printf 'watoom_systemd_unit_failed{unit="%s"} 1\n' "$unit"
    done
  # GPU ownership: llamacpp:* series vanish while a specialist (e.g. moss-image) owns the GPU,
  # so publish who has it. Absent/unreadable state emits nothing rather than guessing.
  python3 - <<'PY' || true
import json, pathlib
base = pathlib.Path('/data/ai/helper-scripts')
try:
    st = json.loads((base / 'state/gpu-controller/state.json').read_text())
    cfg = json.loads((base / 'config/gpu-controller.json').read_text())
    sel = json.loads((base / 'state/gpu-controller/selected-model.json').read_text()).get('deployment')
except (OSError, ValueError):
    raise SystemExit(0)
q = lambda v: str(v).replace('\\', '\\\\').replace('"', '\\"')
owner, phase = st.get('owner'), st.get('phase', 'unknown')
print('# HELP watoom_gpu_controller_info GPU controller phase and owner (1 = current).')
print('# TYPE watoom_gpu_controller_info gauge')
print('watoom_gpu_controller_info{phase="%s",owner="%s"} 1' % (q(phase), q(owner or '')))
print('# HELP watoom_gpu_controller_generation GPU controller ownership generation.')
print('# TYPE watoom_gpu_controller_generation gauge')
print('watoom_gpu_controller_generation %d' % int(st.get('generation', 0)))
print('# HELP watoom_gpu_controller_uncertain 1 when the controller outcome is uncertain (recovery required).')
print('# TYPE watoom_gpu_controller_uncertain gauge')
print('watoom_gpu_controller_uncertain %d' % (1 if st.get('uncertain') else 0))
print('# HELP watoom_gpu_workload_active Who holds the GPU: kind=specialist (owner job, e.g. moss-image) or llm (selected primary).')
print('# TYPE watoom_gpu_workload_active gauge')
if owner:
    print('watoom_gpu_workload_active{workload="%s",kind="specialist"} 1' % q(owner))
elif sel:
    print('watoom_gpu_workload_active{workload="%s",kind="llm"} 1' % q(cfg.get('aliases', {}).get(sel, sel)))
PY
  echo '# HELP watoom_node_textfile_timestamp_seconds Last successful refresh of WatooM host metrics.'
  echo '# TYPE watoom_node_textfile_timestamp_seconds gauge'
  printf 'watoom_node_textfile_timestamp_seconds %s\n' "$(date +%s)"
} > "$tmp"
chmod 0644 "$tmp"
mv -f "$tmp" "$dir/watoom-systemd.prom"
trap - EXIT
