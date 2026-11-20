#!/usr/bin/env python3
"""Idempotent migration: rename existing router model entries to their actual HuggingFace
source, and add new router models (NEW_MODELS) if a prior run
already seeded opencode.json (the template's `force: false` render never touches an existing file, so new/renamed
entries must land through a narrow script like this one instead). Native router discovery may already have added one of
them as a stub (name == its id, tools false); a stub is replaced, an operator-customised entry is left alone."""

import json, os, pathlib, sys, tempfile

NAMES = {
    "tiel-coder-35b-a3b-mtp": "peculiar-ragdoll/Cyber-Tiel-Coder-35B-A3B-GGUF-MTP (IQ4_XS)",
    "swift-qwen38-coder": "ajgazin/Swift-1.5-Qwen3.8-27B-Uncensored-Dynamic-MTP-GGUF",
    "mm-73306b413506f44b": "ukisai/Swift-Qwen3.8-27B-GGUF",
    "qwen38-uncensored-mtp": "Qwen3.8-27B-Uncensored-IQ4_XS_4BPW.gguf",
}
# output None = the role's watoom_code_model_output_tokens (argv[2])
NEW_MODELS = {
    "fable-cold-fusion-27b-mtp": {
        "modelID": "fable-cold-fusion-27b-mtp",
        "name": "DavidAU/Qwen3.8-27B-TURBO-Fable-Cold-Fusion-735-882-Heretic-Uncensored-NEO-CODER-MAX-MTP-GGUF (IQ4_XS)",
        "limit": {"context": 100000, "output": None},
        "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
    },
}

p = pathlib.Path(sys.argv[1])
output_tokens = int(sys.argv[2]) if len(sys.argv) > 2 else 16384
before = p.read_bytes()
data = json.loads(before)
models = data["providers"]["watoom"]["models"]
changed = False
for model_id, name in NAMES.items():
    entry = models.get(model_id)
    if entry is not None and entry.get("name") != name:
        entry["name"] = name
        changed = True
for model_id, spec in NEW_MODELS.items():
    current = models.get(model_id)
    if current is not None and current.get("name") != model_id:
        continue
    entry = json.loads(json.dumps(spec))
    if entry["limit"]["output"] is None:
        entry["limit"]["output"] = output_tokens
    if current != entry:
        models[model_id] = entry
        changed = True
if not changed:
    print("UNCHANGED")
    sys.exit(0)
st = p.stat()
fd, tmp = tempfile.mkstemp(prefix=".model-display-names-", dir=p.parent)
try:
    with os.fdopen(fd, "w") as f:
        os.fchmod(f.fileno(), st.st_mode & 0o777)
        os.fchown(f.fileno(), st.st_uid, st.st_gid)
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    assert p.read_bytes() == before, "Concurrent configuration edit"
    os.replace(tmp, p)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print("CHANGED")
