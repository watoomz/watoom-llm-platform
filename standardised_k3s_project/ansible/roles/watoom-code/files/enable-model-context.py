"""Maintain user-selected application budgets without changing backend deployments."""

import json, os, re, sys
from pathlib import Path

# Reasoning models spend output tokens thinking before the tool call. At 4096 a long thought used the whole budget
# and the call arrived cut off (finish=length, 17 times in one day), so the default is generous; the context budget
# still bounds it (output is capped at half the context).
DEFAULT_OUTPUT = 16384
# 2026-11-19 (owner): each model's application context scales with its served llama-server context (the router's and
# Model Manager's application_context: 100K per 128K served, so 128K -> 100K, 256K -> 200K); `context` is only the
# default for a model that reports none.
DEFAULT_CONTEXT = 100000


def update(document, inventory, context=DEFAULT_CONTEXT, output=DEFAULT_OUTPUT):
    if not 512 <= context <= 1048576 or not 128 <= output <= 32768:
        raise ValueError("Invalid stable application budget")
    provider = document["providers"]["watoom"]
    models = provider.setdefault("models", {})
    for row in inventory["data"]:
        name = row["id"]
        if not re.fullmatch("[A-Za-z0-9_.-]{1,128}", name) or name == "llama-mesh":
            continue
        label = row.get("name") if isinstance(row.get("name"), str) and 0 < len(row["name"]) <= 200 else name
        item = models.setdefault(
            name,
            {"modelID": name, "name": label, "capabilities": {"tools": False, "input": ["text"], "output": ["text"]}},
        )
        # Model Manager publishes the repository name; replace only a stub that still shows the bare id.
        if item.get("name") == name and label != name:
            item["name"] = label
        served = row.get("application_context")
        budget = served if isinstance(served, int) and 512 <= served <= 1048576 else context
        maximum = row.get("context_limit")
        limit = min(budget, maximum) if isinstance(maximum, int) and maximum >= 512 else budget
        item["limit"] = {"context": limit, "output": min(output, limit // 2)}
        # T-0095 (owner 2026-11-19: vision where available): the router reports vision=true when the model's llama-server
        # loads a projector (--mmproj); image input follows it. None (unknown, e.g. an alias) leaves the entry as it is.
        vision = row.get("vision")
        if isinstance(vision, bool):
            capabilities = item.setdefault("capabilities", {"tools": False, "input": ["text"], "output": ["text"]})
            inputs = [x for x in capabilities.get("input", ["text"]) if x != "image"]
            capabilities["input"] = inputs + (["image"] if vision else [])
    return document


def main():
    path = Path(sys.argv[1])
    inventory = json.loads(Path(sys.argv[2]).read_text())
    before = path.read_text()
    document = update(
        json.loads(before),
        inventory,
        int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_CONTEXT,
        int(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_OUTPUT,
    )
    after = json.dumps(document, indent=2) + "\n"
    if json.loads(before) == document:
        print("UNCHANGED")
        return
    stat = path.stat()
    temporary = path.with_name(path.name + ".context-new")
    with temporary.open("w") as f:
        f.write(after)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(temporary, stat.st_mode & 0o777)
    os.chown(temporary, stat.st_uid, stat.st_gid)
    os.replace(temporary, path)
    print("UPDATED")


if __name__ == "__main__":
    main()
