#!/usr/bin/env python3
"""Conservative replay contract for structural revisions. No domain benefit claim."""

import pathlib, json, hashlib, time, re, sys

request = json.loads(pathlib.Path(sys.argv[1]).read_text())
original = pathlib.Path(request["baseline"]).read_text()
candidate = pathlib.Path(request["candidate"]).read_text()
sha = lambda text: hashlib.sha256(text.encode()).hexdigest()


def instructions(body):
    return [x for x in body.splitlines() if x.strip()]


def fences(body):
    result = []
    current = []
    opening = None
    for line in body.splitlines(keepends=True):
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
        if opening:
            current.append(line)
            if match and match[1][0] == opening[0] and len(match[1]) >= opening[1] and not match[2].strip():
                result.append("".join(current))
                current = []
                opening = None
        elif match:
            opening = (match[1][0], len(match[1]))
            current = [line]
    if current:
        result.append("".join(current))
    return result


checks = {
    "read-procedure": lambda b: all(x in instructions(b) for x in instructions(original))
    and instructions(b)[: len(instructions(original))] == instructions(original),
    "preserve-code": lambda b: fences(b) == fences(original),
    "references-and-safety": lambda b: set(re.findall(r"\]\(([^)]+)\)", original))
    <= set(re.findall(r"\]\(([^)]+)\)", b))
    and all(
        x in b
        for x in original.splitlines()
        if re.search(r"\b(?:must|never|permission|safety|preserve|do not)\b", x, re.I)
    ),
}
coverage = {
    "read-procedure": ["all-original-instructions-and-order"],
    "preserve-code": ["all-fenced-bytes"],
    "references-and-safety": ["all-original-links-and-explicit-restrictions"],
}
cases = []
baselines = []
for case in request["caseIDs"]:
    arms = {}
    for arm, body in [("original", original), ("candidate", candidate)]:
        runs = []
        for i in range(3):
            start = time.perf_counter_ns()
            ok = checks[case](body)
            elapsed = (time.perf_counter_ns() - start) / 1e6
            runs.append(
                {
                    "receipt": sha(json.dumps([request["nonce"], case, arm, i, sha(body), ok])),
                    "correctness": ok,
                    "safety": ok,
                    "coverage": coverage[case],
                    "repeatedCommands": 0,
                    "failedAttempts": int(not ok),
                    "contractValidationMs": elapsed,
                }
            )
        arms[arm] = {
            "correctness": all(r["correctness"] for r in runs),
            "safety": all(r["safety"] for r in runs),
            "coverage": coverage[case],
            "tokens": None,
            "latencyMs": None,
            "repeatedCommands": 0,
            "failedAttempts": int(not runs[0]["correctness"]),
            "runs": runs,
        }
    task = "Native Skill instruction contract: " + case
    regression = "Immutable source, code, references and restrictions"
    baselines.append(
        {
            "id": case,
            "task": task,
            "regression": regression,
            "receipt": runs[0]["receipt"] if arm == "original" else arms["original"]["runs"][0]["receipt"],
            "correctness": arms["original"]["correctness"],
            "safety": arms["original"]["safety"],
            "coverage": coverage[case],
        }
    )
    cases.append({"id": case, "task": task, "regression": regression, **arms})
report = {
    "baseline": {"hash": sha(original), "scope": "structural-contract", "cases": baselines},
    "comparison": {
        "baselineHash": sha(original),
        "candidateHash": sha(candidate),
        "environment": "offline-read-only-cpu-contract-v1",
        "cases": cases,
    },
    "limits": "Instruction-retention replay is not a domain workflow benchmark. Tokens and workflow latency are unmeasured; no efficiency benefit is claimed.",
}
pathlib.Path(request["output"]).write_text(json.dumps(report, indent=2))
