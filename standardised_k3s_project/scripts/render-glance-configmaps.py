#!/usr/bin/env python3
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/10-infrastructure/glance/glance.yml"
CONFIG = ROOT / "config/glance/glance.yml"
HELPER = ROOT / "config/glance/helper.py"

class LiteralStr(str):
    pass

def str_presenter(dumper, data):
    if isinstance(data, LiteralStr) or "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)

yaml.add_representer(LiteralStr, str_presenter, Dumper=yaml.SafeDumper)

def load_docs(path):
    with path.open() as f:
        return list(yaml.safe_load_all(f))

def find_configmap(docs, name):
    for doc in docs:
        if doc and doc.get("kind") == "ConfigMap" and doc.get("metadata", {}).get("name") == name:
            return doc
    raise SystemExit(f"Missing ConfigMap in manifest: {name}")

def main():
    for path in [MANIFEST, CONFIG, HELPER]:
        if not path.exists():
            raise SystemExit(f"Missing required file: {path}")

    # Parse Glance config before embedding it so broken layout YAML fails early.
    yaml.safe_load(CONFIG.read_text())
    compile(HELPER.read_text(), str(HELPER), "exec")

    docs = load_docs(MANIFEST)
    find_configmap(docs, "glance-config")["data"] = {"glance.yml": LiteralStr(CONFIG.read_text())}
    find_configmap(docs, "glance-helper")["data"] = {"helper.py": LiteralStr(HELPER.read_text())}

    MANIFEST.write_text(yaml.safe_dump_all(docs, sort_keys=False, explicit_start=True, width=1000, allow_unicode=True))
    print(f"Rendered {MANIFEST} from {CONFIG} and {HELPER}")

if __name__ == "__main__":
    main()
