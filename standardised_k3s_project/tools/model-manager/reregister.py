#!/usr/bin/env python3
"""Operator entry point for Operations.reregister (T-0123): retire + register a Model Manager model again so it picks up
the broker's current workload (e.g. --metrics, Swift's runtime), files and mm-* identity kept.

Runs as the catalogue owner (uid/gid 1009, like the model-manager pod), never as root, so SQLite never leaves
root-owned journal files the pod cannot open. The broker refuses while the GPU controller has an owner and retire
refuses a deployment that is running, so only unloaded models can be re-registered.

  sudo setpriv --reuid=1009 --regid=1009 --clear-groups python3 reregister.py --list
  sudo setpriv --reuid=1009 --regid=1009 --clear-groups python3 reregister.py mm-6f1168c199628118 --set cache_k=turbo5
"""
import argparse, json, os, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from store import Store  # noqa: E402
from operations import Operations  # noqa: E402
from broker_service import Client  # noqa: E402

CATALOG = pathlib.Path("/data/ai/model-manager/catalog.sqlite")
SOCKET = "/data/ai/helper-scripts/state/model-manager-broker/broker.sock"
MODELS = "/data/ai/models"


def value(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("models", nargs="*", help="mm-<16 hex> aliases or full ids")
    a.add_argument("--list", action="store_true", help="list LLM installations and their runtime settings")
    a.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override (%s)" % ", ".join(Operations.REREGISTER_OVERRIDES))
    a = a.parse_args()
    if os.geteuid() != CATALOG.stat().st_uid:
        raise SystemExit("run as the catalogue owner (uid %d), not uid %d" % (CATALOG.stat().st_uid, os.geteuid()))
    store = Store(str(CATALOG))
    rows = {i: json.loads(r) for i, r in store.db.execute("SELECT id, record FROM models")}
    llm = {i: r for i, r in rows.items() if r.get("kind") in ("gguf", "gguf-lora")}
    if a.list:
        for i, r in llm.items():
            s = r["settings"]
            print("mm-%s registered=%s cache=%s/%s ubatch=%s reasoning=%s" % (i[:16], r.get("registered"), s.get("cache_k"), s.get("cache_v"), s.get("ubatch"), s.get("reasoning")))
        return
    overrides = dict((k, value(v)) for k, v in (x.split("=", 1) for x in a.set))
    ops = Operations(store, MODELS, Client(SOCKET))
    failed = 0
    for name in a.models:
        key = name[3:] if name.startswith("mm-") else name
        match = [i for i in llm if i.startswith(key)]
        if len(match) != 1:
            print(json.dumps({"model": name, "error": "no unique installation"}))
            failed += 1
            continue
        record = llm[match[0]]
        try:
            out = ops.reregister(match[0], record["revision"], overrides)
            ok = out.get("registered") is True
            print(json.dumps({"model": name, "registered": ok, "error": out.get("registration_error"), "reregistered_from": out.get("reregistered_from")}))
            failed += not ok
        except Exception as e:  # noqa: BLE001 -- report per model, keep going
            print(json.dumps({"model": name, "error": type(e).__name__ + ": " + str(e)[:300]}))
            failed += 1
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
