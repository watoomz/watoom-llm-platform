#!/usr/bin/env python3
"""Check Niagara systems made by unreal_niagara_fx.py (or any calls file with niagara.create_system_from_spec) on the rig.

  ue_fx_check.py --from-calls fx_calls.json [--at X Y Z] [--keep]

Per system: niagara.validate (every emitter enabled, spawns, renders), then a temporary NiagaraActor in the editor world,
reactivate + capture_sim_cache, and per emitter the particle count, colour range and spread (Position min/max). Exit 1 when a
system is invalid or an emitter that SHOULD be caught has no particles. The temporary actors are deleted unless --keep.

Why (T-0063, 2026-11-18): a viewport screenshot cannot judge one-shot effects (the capture takes seconds; a 0.2 s impact is
long gone) and says nothing about colour values. The sim cache does, with one gap measured on UE 5.8 and reported as SKIP,
never as a failure: reactivate and capture are separate calls, the editor ticks in real time between them, so an emitter
whose Lifetime Max is under 0.25 s is dead before the first frame (a 0.06 s muzzle flash read 0; with lifetime 1 s, 4/4).
An empty ribbon is a FAIL: the LocationBasedRibbon template has no spawn module (it read 0 on a flying fireball too, until
unreal_niagara_fx.py added SpawnPerFrame).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402

SHORT_LIFE = 0.25


def systems_from_calls(calls_file):
    """-> {system path: {emitter name: {"lifetime_max": float|None, "moves": bool}}}"""
    with open(calls_file) as f:
        data = json.load(f)
    out, templates = {}, {}
    for p in data.get("phases", []):
        for m, a in p["calls"]:
            if m == "niagara.create_emitter":
                templates[a["name"]] = a.get("templatePath", "")
            elif m == "niagara.create_system_from_spec":
                sp = "%s/%s" % (a.get("packagePath", "").rstrip("/"), a["name"])
                out[sp] = {}
                for e in a.get("emitters", []):
                    en = e["path"].rsplit("/", 1)[-1]
                    out[sp][en] = {"lifetime_max": None, "moves": "Ribbon" in templates.get(en, "")}
            elif m == "niagara.set_module_input" and a.get("inputName") in ("Lifetime Max", "Lifetime"):
                em = out.get(a["systemPath"], {}).get(a.get("emitterName"))
                if em is not None:
                    em["lifetime_max"] = float(a["value"])
    return out


def judge(emitter, info, counts):
    """-> (verdict, why). counts: particles per captured frame."""
    if max(counts or [0]) > 0:
        return "OK", "%d particles" % max(counts)
    if info.get("lifetime_max") is not None and info["lifetime_max"] < SHORT_LIFE:
        return "SKIP", "lifetime %.2f s < %.2f s: dies between reactivate and capture" % (info["lifetime_max"], SHORT_LIFE)
    return "FAIL", "no particles"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-calls", required=True)
    ap.add_argument("--at", nargs=3, type=float, default=[0.0, -3000.0, 150.0])
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    a = ap.parse_args(argv)
    t = ue_route.SshTransport(ue_route.ssh_command("10.99.1.44", 2224, "uemcp", a.key_dir))

    def call(spec, args, timeout=300):
        cat, meth = spec.split(".", 1)
        r = t.call(cat, meth, args, timeout)
        try:
            return json.loads(r[r.index("{"):])
        except ValueError:
            return {"success": False, "error": r[:300]}
    bad, placed = 0, []
    try:
        for i, (sp, emitters) in enumerate(sorted(systems_from_calls(a.from_calls).items())):
            name = sp.rsplit("/", 1)[-1]
            v = call("niagara.validate", {"systemPath": sp})
            if not v.get("valid"):
                print("FAIL %s: validate %s" % (name, json.dumps(v)[:300]))
                bad += 1
                continue
            label = "FXCHECK_" + name
            loc = {"x": a.at[0] + 400 * i, "y": a.at[1], "z": a.at[2]}
            call("niagara.spawn_actor", {"systemPath": sp, "label": label, "location": loc})
            placed.append(label)
            call("niagara.reactivate", {"actorLabel": label})
            cap = call("niagara.capture_sim_cache", {"actorLabel": label, "frames": 4, "advanceSimulation": True, "tickDelta": 0.03})
            counts = {e["name"]: e.get("numInstancesPerFrame", []) for e in cap.get("emitters", [])}
            for en in sorted(emitters):
                verdict, why = judge(en, emitters[en], counts.get(en, []))
                extra = ""
                if verdict == "OK":
                    r = call("niagara.read_sim_cache", {"simCachePath": cap["simCachePath"], "emitterName": en, "frameIndex": 1,
                                                        "attributes": ["Color", "Position"], "summarize": True, "limit": 1})
                    for at in r.get("attributes", []) if isinstance(r.get("attributes"), list) else []:
                        if at.get("min") is not None:
                            extra += " %s %s..%s" % (at.get("name"), [round(x, 1) for x in at["min"]], [round(x, 1) for x in at["max"]])
                print("%-4s %s / %s: %s%s" % (verdict, name, en, why, extra))
                bad += verdict == "FAIL"
    finally:
        if not a.keep:
            for label in placed:
                call("level.delete_actor", {"actorLabel": label})
        t.close()
    print("%d problem(s)" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
