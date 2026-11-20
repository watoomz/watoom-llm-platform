#!/usr/bin/env python3
"""Accumulate lifetime per-model performance counters for Grafana's all-time comparison panel.

Prometheus counters reset on process restart and its own retention window (30d) rolls off
raw history, so neither can answer "which model is the best performer, all time". This script
polls the current counter values on a timer, tracks deltas in a durable state file (handling
counter resets as a restart, not a loss), and republishes the running lifetime totals as
node-exporter textfile gauges -- the same pattern watoom-node-textfile.sh uses for GPU
ownership, just with delta accumulation added.
"""
import json
import pathlib
import sys
import urllib.request
import urllib.parse

LIFETIME_COUNTERS = {
    "prompt_tokens": 'sum by (model) (llamacpp:prompt_tokens_total{job="llama-cpp",service!~".*test.*"})',
    "generated_tokens": 'sum by (model) (llamacpp:tokens_predicted_total{job="llama-cpp",service!~".*test.*"})',
    "prompt_seconds": 'sum by (model) (llamacpp:prompt_seconds_total{job="llama-cpp",service!~".*test.*"})',
    "generation_seconds": 'sum by (model) (llamacpp:tokens_predicted_seconds_total{job="llama-cpp",service!~".*test.*"})',
}

MOSS_COUNTERS = {
    "images": "watoom_moss_jobs_total",
    "pixels": "watoom_moss_pixels_total",
    "generation_seconds": "watoom_moss_generation_seconds_sum",
}

MOSS_MODEL_LABEL = "moss-image"


def prom_query(base_url: str, expr: str) -> dict:
    url = base_url.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    with urllib.request.urlopen(url, timeout=10) as resp:
        payload = json.load(resp)
    if payload.get("status") != "success":
        raise RuntimeError(f"prometheus query failed: {expr!r}: {payload}")
    out = {}
    for item in payload["data"]["result"]:
        model = item["metric"].get("model") or MOSS_MODEL_LABEL
        out[model] = float(item["value"][1])
    return out


def load_state(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_state(path: pathlib.Path, state: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(path)


def accumulate(state: dict, model: str, field: str, raw_value: float) -> float:
    """Add the delta since the last observed raw value for (model, field) into the
    durable lifetime total, treating a decrease as a counter reset (process restart) rather
    than a loss -- the whole post-reset value is counted rather than a negative delta."""
    bucket = state.setdefault(model, {})
    last_raw = bucket.get(f"_raw_{field}", 0.0)
    lifetime = bucket.get(field, 0.0)
    delta = raw_value - last_raw if raw_value >= last_raw else raw_value
    bucket[field] = lifetime + delta
    bucket[f"_raw_{field}"] = raw_value
    return bucket[field]


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--prometheus-url", default="http://10.243.64.210:9090")
    ap.add_argument("--state-file", default="/var/lib/node_exporter/textfile/.watoom-model-perf-state.json")
    ap.add_argument("--output", default=None, help="write metrics here atomically instead of stdout")
    args = ap.parse_args()

    state_path = pathlib.Path(args.state_file)
    state = load_state(state_path)

    out_lines = []
    models_seen = set()

    for field, expr in LIFETIME_COUNTERS.items():
        try:
            values = prom_query(args.prometheus_url, expr)
        except Exception as exc:
            print(f"warn: query failed for {field}: {exc}", file=sys.stderr)
            continue
        for model, raw in values.items():
            accumulate(state, model, field, raw)
            models_seen.add(model)

    try:
        moss_values = {k: prom_query(args.prometheus_url, expr) for k, expr in MOSS_COUNTERS.items()}
    except Exception as exc:
        print(f"warn: moss query failed: {exc}", file=sys.stderr)
        moss_values = {}
    for field, per_model in moss_values.items():
        for model, raw in per_model.items():
            accumulate(state, model, field, raw)
            models_seen.add(model)

    save_state(state_path, state)

    def emit(name: str, help_text: str, field: str):
        out_lines.append(f"# HELP {name} {help_text}")
        out_lines.append(f"# TYPE {name} gauge")
        for model in sorted(models_seen):
            value = state.get(model, {}).get(field)
            if value is not None:
                out_lines.append(f'{name}{{model="{model}"}} {value}')

    emit("watoom_model_perf_lifetime_generated_tokens_total", "Lifetime generated tokens, by model.", "generated_tokens")
    emit("watoom_model_perf_lifetime_prompt_tokens_total", "Lifetime prompt tokens processed, by model.", "prompt_tokens")
    emit("watoom_model_perf_lifetime_generation_seconds_total", "Lifetime generation wall-time, by model.", "generation_seconds")
    emit("watoom_model_perf_lifetime_prompt_seconds_total", "Lifetime prompt-eval wall-time, by model.", "prompt_seconds")
    emit("watoom_model_perf_lifetime_images_total", "Lifetime images generated (MOSS image studio only).", "images")
    emit("watoom_model_perf_lifetime_pixels_total", "Lifetime pixels generated (MOSS image studio only).", "pixels")

    out_lines.append("# HELP watoom_model_perf_lifetime_timestamp_seconds Last successful refresh of the lifetime model performance accumulator.")
    out_lines.append("# TYPE watoom_model_perf_lifetime_timestamp_seconds gauge")
    import time
    out_lines.append(f"watoom_model_perf_lifetime_timestamp_seconds {time.time()}")

    text = "\n".join(out_lines) + "\n"
    if args.output:
        out_path = pathlib.Path(args.output)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(text)
        tmp.replace(out_path)
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
