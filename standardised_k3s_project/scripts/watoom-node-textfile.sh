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
  # Readable LLM names for Grafana. Model Manager models are labelled by install ID (model="mm-2befb4fc7156646b");
  # their router catalog carries "<repository> (<file>.gguf) · MTP", so the GGUF file stem (or a LoRA's adapter
  # repository) is the short, distinctive label. Other models keep their ID, so every model has exactly one name.
  python3 - <<'PY' || true
import json, pathlib, re
base = pathlib.Path('/data/ai/helper-scripts')
names = {}
try:
    for d in json.loads((base / 'config/gpu-controller.json').read_text()).get('aliases', {}):
        names[d.removeprefix('llama-cpp-')] = d.removeprefix('llama-cpp-')
except (OSError, ValueError):
    pass
try:
    # Every installed Model Manager LLM, registered or not: the GGUF file stem (a LoRA's adapter repository).
    import sqlite3
    db = sqlite3.connect('file:/data/ai/model-manager/catalog.sqlite?mode=ro', uri=True, timeout=2)
    paths = dict(db.execute('SELECT id, path FROM artifacts'))
    for ident, raw in db.execute('SELECT id, record FROM models'):
        rec = json.loads(raw)
        if rec.get('kind') == 'gguf-lora':
            names['mm-' + ident[:16]] = (rec.get('repository') or '').split('/')[-1].removesuffix('-GGUF')[:65] + ' (LoRA)'
        elif rec.get('kind') == 'gguf' and rec.get('artifacts'):
            names['mm-' + ident[:16]] = pathlib.Path(paths.get(rec['artifacts'][0], '')).stem[:72] or 'mm-' + ident[:16]
except Exception:
    pass
try:
    routes = json.loads((base / 'state/model-manager-router/catalog.json').read_text()).get('models', {})
except (OSError, ValueError):
    routes = {}
for alias, r in routes.items():
    if r.get('backend') not in (None, 'gguf'):
        continue  # image backends are not LLMs
    full = r.get('name') or alias
    lora = re.match(r'^[^/ ]+/([^ ]+?)(?:-GGUF)? on ', full)
    stem = re.search(r'\(([^()]+?)\.gguf\)', full)
    label = (lora.group(1) + ' (LoRA)') if lora else stem.group(1) if stem else full.split(' ')[0].split('/')[-1]
    names[alias] = label[:72]
# Remember names: re-registration (retire + register) or a failed registration briefly drops a model from the router
# catalog, and its panels then showed the bare mm-<id>. A model keeps its last known name until it is removed.
memo = base / 'state/llm-model-names.json'
try:
    known = json.loads(memo.read_text())
except (OSError, ValueError):
    known = {}
known.update({k: v for k, v in names.items() if v != k})
try:
    tmp = memo.with_suffix('.tmp'); tmp.write_text(json.dumps(known, sort_keys=True)); tmp.replace(memo)
except OSError:
    pass
names = {**{k: v for k, v in known.items() if k.startswith('mm-')}, **{k: v for k, v in names.items() if v != k or k not in known}}
if names:
    q = lambda v: str(v).replace('\\', '\\\\').replace('"', '\\"')
    print('# HELP watoom_llm_model_info Readable name for each LLM model label (1 = known).')
    print('# TYPE watoom_llm_model_info gauge')
    for model, label in sorted(names.items()):
        print('watoom_llm_model_info{model="%s",name="%s"} 1' % (q(model), q(label)))
PY
  echo '# HELP watoom_node_textfile_timestamp_seconds Last successful refresh of WatooM host metrics.'
  echo '# TYPE watoom_node_textfile_timestamp_seconds gauge'
  printf 'watoom_node_textfile_timestamp_seconds %s\n' "$(date +%s)"
} > "$tmp"
chmod 0644 "$tmp"
mv -f "$tmp" "$dir/watoom-systemd.prom"
trap - EXIT
