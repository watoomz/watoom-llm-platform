#!/usr/bin/env python3
import argparse, json, sys, urllib.request

TOOL = {
    "type": "function",
    "function": {
        "name": "watoom_probe",
        "description": "Synthetic compatibility probe. No external action is performed.",
        "parameters": {
            "type": "object",
            "properties": {"marker": {"type": "string"}},
            "required": ["marker"],
            "additionalProperties": False,
        },
    },
}


def request(url, model, marker):
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": f"Call the watoom_probe tool exactly once with marker {marker!r}. Do not answer in normal text.",
            }
        ],
        "tools": [TOOL],
        "tool_choice": "auto",
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
    }
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def validate(resp, marker):
    choices = resp.get("choices") or []
    if not choices:
        return False, "no choices"
    msg = choices[0].get("message") or {}
    calls = msg.get("tool_calls") or []
    if len(calls) != 1:
        return False, f"tool_calls={len(calls)}"
    fn = calls[0].get("function") or {}
    if fn.get("name") != "watoom_probe":
        return False, f"tool_name={fn.get('name')!r}"
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except Exception as e:
        return False, f"arguments_json_error={e}"
    if args != {"marker": marker}:
        return False, f"arguments={args!r}"
    return True, "exact OpenAI tool_calls contract"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--model", required=True)
    ap.add_argument("--marker", default="WATOOM_TOOL_COMPAT")
    ap.add_argument("--json-out")
    a = ap.parse_args()
    try:
        resp = request(a.url, a.model, a.marker)
    except Exception as e:
        print(f"FAIL request: {e}", file=sys.stderr)
        return 2
    ok, detail = validate(resp, a.marker)
    report = {
        "model": a.model,
        "ok": ok,
        "detail": detail,
        "request_shape": {"stream": False, "tool_choice": "auto", "tool_count": 1},
        "response": resp,
    }
    if a.json_out:
        open(a.json_out, "w").write(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("model", "ok", "detail")}, indent=2))
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
