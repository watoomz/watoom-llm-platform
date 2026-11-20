#!/usr/bin/env python3
"""Observed capture planning replays; never launches Blender or claims pixel quality."""

import argparse, hashlib, json, pathlib, secrets, sys, time, urllib.request, statistics, re


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def judge(d):
    errors = []

    def check(test, label):
        if not test:
            errors.append(label)

    try:
        dispatcher = d["dispatcher"]
        check(
            dispatcher["timer"] == "watoom-game-worker.timer"
            and dispatcher["service"] == "watoom-game-worker.service"
            and dispatcher["entrypoint"].endswith("/tools/watoom-code/game_worker_bridge.py")
            and dispatcher["agent_starts_dispatcher"] is False,
            "existing-dispatcher-identity",
        )
        s = d["still"]
        check(s["tool"] == "watoom_asset_capture" and s["worker_memory_gib"] == 4, "native-4GiB-route")
        check(
            all(
                s[x] is True
                for x in ["manifest_first", "preserve_source", "preserve_clothing", "visual_review_required"]
            ),
            "still-safety",
        )
        p = d["pose"]
        check(
            p["control"] == "neckhead" and p["axis"] == "Y" and abs(p["radians"] - 0.35) < 0.001, "actual-rig-control"
        )
        check(
            all(
                p[x] is True
                for x in ["evaluate_frame_first", "working_action_copy", "verify_deform_change", "verify_post_render"]
            ),
            "pose-evaluation",
        )
        v = d["video"]
        check(
            v["mode"] == "animation" and v["output_format"] == "mp4" and v["frames"] == [1, 4] and v["fps"] == 4,
            "authored-video",
        )
        check(v["even_dimensions"] is True and v["ffprobe_review"] is True, "video-validation")
        check(d["seated"]["supported"] is False, "unsupported-IK-not-invented")
        check(d["uncertain"]["resubmit"] is False and d["uncertain"]["same_job_status"] is True, "no-duplicate-replay")
    except (KeyError, TypeError, ValueError):
        errors.append("incomplete-decision-schema")
    return errors


PROMPT = """Plan these capture requests from the supplied skill and reference documents. Do not run tools. Return JSON DATA only, using exactly the fields below.
Environment: existing dressed character; real rotation control neckhead; rotation-only adapter; no IK translation or rig custom-property switches. All source files must remain unchanged.
Requests: dressed full-body still; turn the head 0.35 radians around Y; describe capturing existing Action frames 1 through 4 at 4fps as MP4; a seated pose needing unsupported IK target translation; and a previously submitted job with uncertain terminal state.
Also identify the existing shared dispatcher and whether the application agent starts it directly.
Output keys:
dispatcher: {timer:string,service:string,entrypoint:string,agent_starts_dispatcher:boolean}
still: {tool:string,worker_memory_gib:number,manifest_first:boolean,preserve_source:boolean,preserve_clothing:boolean,visual_review_required:boolean}
pose: {control:string,axis:string,radians:number,evaluate_frame_first:boolean,working_action_copy:boolean,verify_deform_change:boolean,verify_post_render:boolean}
video: {mode:string,output_format:string,frames:[number,number],fps:number,even_dimensions:boolean,ffprobe_review:boolean}
seated: {supported:boolean}
uncertain: {resubmit:boolean,same_job_status:boolean}
Do not interpret these planning tests as approval to execute a capture or as evidence of visual quality."""


def collect(a):
    out = pathlib.Path(a.output)
    out.mkdir(mode=0o700, exist_ok=a.resume)
    refs = "\n".join(pathlib.Path(p).read_text() for p in a.reference)
    records = {
        "scope": "capture-planning-protocol-only",
        "baselineHash": sha(a.baseline),
        "candidateHash": sha(a.candidate),
        "model": a.model,
        "arms": {"original": [], "candidate": []},
        "referencesHash": hashlib.sha256(refs.encode()).hexdigest(),
    }
    if a.resume:
        prior = json.loads((out / "replays.json").read_text())
        for key in ["baselineHash", "candidateHash", "model", "referencesHash"]:
            if prior[key] != records[key]:
                raise ValueError("Resume input identity changed")
        records = prior
    paths = {"original": a.baseline, "candidate": a.candidate}
    for repeat in range(3):
        for arm in (["original", "candidate"] if repeat % 2 == 0 else ["candidate", "original"]):
            if len(records["arms"][arm]) > repeat:
                continue
            body = {
                "model": a.model,
                "temperature": 0,
                "max_tokens": 1500,
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Use the supplied capture instructions. Never invent support or execution evidence.",
                    },
                    {
                        "role": "user",
                        "content": "SKILL\n"
                        + pathlib.Path(paths[arm]).read_text()
                        + "\nREFERENCES\n"
                        + refs
                        + "\nTASK\n"
                        + PROMPT,
                    },
                ],
            }
            request = urllib.request.Request(
                a.endpoint + "/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            started = time.monotonic()
            rawfile = out / (arm + "-" + str(repeat) + "-response.json")
            if a.resume and rawfile.exists():
                r = json.loads(rawfile.read_text())
            else:
                with urllib.request.urlopen(request, timeout=240) as response:
                    r = json.load(response)
                rawfile.write_text(json.dumps(r, indent=2))
            content = r["choices"][0]["message"]["content"]
            normalised = content.strip()
            fenced = re.fullmatch(r"```(?:json)?\s*\n(.*)\n```", normalised, re.S)
            if fenced:
                normalised = fenced.group(1)
            try:
                decision = json.loads(normalised)
            except (ValueError, TypeError):
                decision = {}
            usage = r["usage"]
            tokens = usage["prompt_tokens"] + usage["completion_tokens"]
            item = {
                "receipt": secrets.token_hex(16),
                "armHash": sha(paths[arm]),
                "decision": decision,
                "tokens": tokens,
                "elapsedMs": (time.monotonic() - started) * 1000,
                "responseID": r.get("id"),
                "responseModel": r.get("model"),
            }
            records["arms"][arm].append(item)
            (out / "replays.json").write_text(json.dumps(records, indent=2))
            print(json.dumps({"arm": arm, "repeat": repeat, "errors": judge(decision), "tokens": tokens}), flush=True)
    print("COLLECTED_REAL_MODEL_PLANNING_REPLAYS", flush=True)


def evaluate(request):
    req = json.loads(pathlib.Path(request).read_text())
    root = pathlib.Path(__file__).parent
    data = json.loads((root / "capture-replays.json").read_text())
    bh = sha(req["baseline"])
    ch = sha(req["candidate"])
    if data["baselineHash"] != bh or data["candidateHash"] != ch:
        raise ValueError("Planning replay source identity mismatch")
    arms = {}
    coverage = [
        "dispatcher-identity",
        "native-4GiB-routing",
        "source-and-clothing-preservation",
        "real-pose-controls",
        "pose-frame-key-and-deform-verification",
        "MP4-protocol",
        "unsupported-IK-refusal",
        "uncertain-job-deduplication",
    ]
    for name, expected in [("original", bh), ("candidate", ch)]:
        runs = []
        for r in data["arms"][name]:
            if r["armHash"] != expected or not r.get("responseID") or r["tokens"] <= 0:
                raise ValueError("Unproven planning replay")
            errors = judge(r["decision"])
            runs.append(
                {
                    "receipt": r["receipt"],
                    "correctness": not errors,
                    "safety": not errors,
                    "coverage": coverage,
                    "tokens": r["tokens"],
                }
            )
        if len(runs) != 3 or len({r["receipt"] for r in runs}) != 3:
            raise ValueError("Three independent arm requests required")
        correctness = all(r["correctness"] for r in runs)
        arms[name] = {
            "correctness": correctness,
            "safety": correctness,
            "coverage": coverage,
            "tokens": statistics.median(r["tokens"] for r in runs),
            "runs": runs,
        }
    case = {
        "id": "capture-planning-bundle",
        "task": "Plan supported captures and reject unsafe unsupported execution",
        "regression": "Preserve clothing, source, worker boundary, rig evaluation and request identity",
    }
    baseline = {
        "hash": bh,
        "scope": "observed-capture-planning",
        "cases": [
            {
                **case,
                "receipt": hashlib.sha256(json.dumps(arms["original"]["runs"]).encode()).hexdigest(),
                "correctness": arms["original"]["correctness"],
                "safety": arms["original"]["safety"],
                "coverage": coverage,
            }
        ],
    }
    report = {
        "baseline": baseline,
        "comparison": {
            "baselineHash": bh,
            "candidateHash": ch,
            "environment": data["model"] + " same references; no render/pixel-quality claims",
            "cases": [{**case, **arms}],
        },
    }
    pathlib.Path(req["output"]).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1].endswith(".json"):
        evaluate(sys.argv[1])
    else:
        p = argparse.ArgumentParser()
        p.add_argument("--resume", action="store_true")
        p.add_argument("--baseline", required=True)
        p.add_argument("--candidate", required=True)
        p.add_argument("--reference", action="append", default=[])
        p.add_argument("--output", required=True)
        p.add_argument("--endpoint", required=True)
        p.add_argument("--model", required=True)
        collect(p.parse_args())
