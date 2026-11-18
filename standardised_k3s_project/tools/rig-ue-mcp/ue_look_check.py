#!/usr/bin/env python3
"""Check the level's look settings against the recipe that worked (read-only; exits 1 on any drift).

  ue_look_check.py --from-calls atmo.json [--from-calls sky.json]     any game: check every value those calls set
  ue_look_check.py [--checks FILE] [--level-path /Game/Maps/L.L:PersistentLevel] [--project FILE]

Why (T-0027 / T-0049, 2026-11-18): the owner saw pale, washed-out leaves again. Every light and leaf value was still right, but the
star dome had lost its MI_Star_Nebula_02 override and was drawing its black base material (a MaterialInstanceDynamic of
M_Star_Nebula with no cubemap), so a third of a horizon view was pure black and auto exposure brightened everything else. Nothing
reported it. Run this after an editor crash or restart, after level.load, and before judging any colour or texture work.

Each check reads one value: {"object": "<name under the persistent level>", "property": "...", ...} with editor.get_property, or
{"material": "/Game/...MI", "scalar": "<parameter>", ...} with material.read_instance. The expectation is one of
"equals" (exact), "approx" with "tol" (numbers; a struct compares its "X"), or "contains" (substring of the value as text).
A check may also name an actor by label: {"label": "<actor label>", "component": "<component name, optional>", "property": ...};
the label is resolved with level.get_actor_details, so a check works on any level whatever its object names.
--from-calls FILE (repeatable) builds the checks from a calls json the pipeline applied (unreal_atmosphere.py, unreal_sky.py, ...):
every level.set_post_process_settings value and its bOverride_ flag, level.set_component_property, numeric material.set_parameter,
an OverrideMaterials bulk set, and editor.set_property. That is the generic form: whatever a game's pipeline set is what gets checked.
Without --from-calls or --checks the defaults are the documented recipe of the test game (L_ZAS_Terrain) only.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts"))
import ue_route  # noqa: E402
import ue_project  # noqa: E402

LEAVES = ["/Game/Wildwood/Material/MI_Tree%s_Leaves_0%d" % (s, n) for s in ("Big", "Medium", "Small") for n in (1, 2)]
DEFAULT_CHECKS = (
    [{"object": "BP_Star_Dome_C_0.Dome", "property": "OverrideMaterials", "contains": "MI_Star_Nebula_",
      "why": "a dome without its nebula MI draws black; auto exposure then washes out the scene"},
     {"object": "DirectionalLight_0.LightComponent0", "property": "Intensity", "approx": 3.2, "tol": 0.05, "why": "sun"},
     {"object": "SkyLight_0.SkyLightComponent0", "property": "Intensity", "approx": 0.9, "tol": 0.05, "why": "ambient fill"},
     {"object": "SkyLight_0.SkyLightComponent0", "property": "SourceType", "equals": "SLS_SpecifiedCubemap",
      "why": "a captured sky light sees the non-Is-Sky dome as black"},
     {"object": "SkyLight_0.SkyLightComponent0", "property": "bRealTimeCapture", "equals": False, "why": "cubemap sky light"},
     {"object": "PostProcessVolume_0", "property": "Settings.ColorContrast", "approx": 1.25, "tol": 0.01, "why": "leaf recipe"},
     {"object": "PostProcessVolume_0", "property": "Settings.bOverride_ColorContrast", "equals": True,
      "why": "without the override flag the ColorContrast value is ignored"},
     # unreal_atmosphere.py (2026-11-18): locked exposure, dimmer nebula, weak atmosphere, clouds, fog
     {"object": "PostProcessVolume_0", "property": "Settings.AutoExposureMinBrightness", "approx": 0.45, "tol": 0.01,
      "why": "exposure lock; at 0.3 the scene is washed out"},
     {"object": "PostProcessVolume_0", "property": "Settings.AutoExposureMaxBrightness", "approx": 0.45, "tol": 0.01,
      "why": "exposure lock (Min = Max)"},
     {"object": "PostProcessVolume_0", "property": "Settings.bOverride_AutoExposureMinBrightness", "equals": True, "why": "flag"},
     {"object": "PostProcessVolume_0", "property": "Settings.bOverride_AutoExposureMaxBrightness", "equals": True, "why": "flag"},
     {"object": "SkyAtmosphere_0.SkyAtmosphereComponent", "property": "AerialPespectiveViewDistanceScale", "approx": 0.35, "tol": 0.01,
      "why": "1.0 hides the nebula behind plain blue; no atmosphere leaves black sky and flat clouds"},
     {"object": "VolumetricCloud_0.VolumetricCloudComponent", "property": "Material", "contains": "MI_ZAS_Clouds", "why": "project cloud MI"},
     {"object": "VolumetricCloud_0.VolumetricCloudComponent", "property": "LayerBottomAltitude", "approx": 1.0, "tol": 0.01,
      "why": "the default 5 km layer hides behind the 20 km dome near the horizon"},
     {"object": "ExponentialHeightFog_0.HeightFogComponent0", "property": "FogDensity", "approx": 0.01, "tol": 0.002, "why": "light haze"},
     {"material": "/Game/Animated_Nebulas_Starter_Pack/Planet_System/Materials/Star_Dome/MI_Star_Nebula_02", "scalar": "Power",
      "approx": 1.4, "tol": 0.01, "why": "nebula Power is an exponent; lower blows the sun-side sky out"},
     {"material": "/Game/ZAS/Sky/MI_ZAS_Clouds", "scalar": "Cloud_GlobalCoverage", "approx": 0.35, "tol": 0.01, "why": "cloud cover"}]
    + [{"material": m, "scalar": p, "approx": v, "tol": 0.005, "why": "leaf recipe"}
       for m in LEAVES for p, v in (("Contrast", 2.8), ("SS Power", 0.03))])


def as_json(reply):
    return json.loads(reply[reply.index("{"):])


def compare(check, value):
    """-> (ok, shown value)."""
    if isinstance(value, dict) and "approx" in check:
        value = value.get("X", value.get("x"))
    if "equals" in check:
        return value == check["equals"], value
    if "approx" in check:
        return isinstance(value, (int, float)) and abs(value - check["approx"]) <= check.get("tol", 0), value
    text = value if isinstance(value, str) else json.dumps(value)
    return check["contains"] in text, value


def _expect(value):
    if isinstance(value, bool) or isinstance(value, str):
        return {"equals": value}
    if isinstance(value, (int, float)):
        return {"approx": float(value), "tol": max(1e-3, abs(value) * 1e-3)}
    return None


def checks_from_calls(calls):
    """A calls json ({"phases": [...]} or a plain list of [method, args]) -> the checks that verify what it set."""
    items = [c for p in calls.get("phases", []) for c in p["calls"]] if isinstance(calls, dict) else calls
    out = []
    for method, a in items:
        why = "set by " + method
        if method == "level.set_post_process_settings":
            for k, v in a.get("settings", {}).items():
                e = _expect(v)
                if e:
                    out.append(dict(e, label=a["actorLabel"], property="Settings." + k, why=why))
                if a.get("enableOverrides"):
                    out.append({"label": a["actorLabel"], "property": "Settings.bOverride_" + k, "equals": True,
                                "why": "a post-process value without its override flag is ignored"})
        elif method == "level.set_component_property":
            e = _expect(a["value"]) if not (isinstance(a["value"], str) and "/" in a["value"]) else \
                {"contains": a["value"].rsplit("/", 1)[-1].split(".")[0]}
            if e:
                out.append(dict(e, label=a["actorLabel"], component=a.get("componentName") or None, property=a["propertyName"], why=why))
        elif method == "material.set_parameter" and isinstance(a.get("value"), (int, float)) and not isinstance(a.get("value"), bool):
            out.append(dict(_expect(a["value"]), material=a["assetPath"], scalar=a["parameterName"], why=why))
        elif method == "level.bulk_set_component_property" and a.get("propertyName") == "OverrideMaterials":
            out.append({"label": a["labelPrefix"], "component": a["componentName"], "property": "OverrideMaterials",
                        "contains": a["value"][0].rsplit("/", 1)[-1].split(".")[0], "why": why + " (a construction-script rerun drops it)"})
        elif method == "editor.set_property":
            e = _expect(a["value"])
            if e:
                out.append(dict(e, path=a["objectPath"], property=a["propertyName"], why=why))
    return out


def object_path(call, check, level_path, cache):
    if "path" in check:
        return check["path"]
    if "label" in check:
        key = "label:" + check["label"]
        if key not in cache:
            cache[key] = as_json(call("level", "get_actor_details", {"actorLabel": check["label"]}, "actor " + check["label"]))["path"]
        return cache[key] + ("." + check["component"] if check.get("component") else "")
    return level_path + "." + check["object"]


def read(call, check, level_path, cache):
    if "material" in check:
        if check["material"] not in cache:
            cache[check["material"]] = as_json(call("material", "read_instance", {"assetPath": check["material"]}, check["material"]))
        for p in cache[check["material"]].get("scalarParameters", []):
            if p.get("name") == check["scalar"]:
                return p.get("value")
        return None
    d = as_json(call("editor", "get_property", {"objectPath": object_path(call, check, level_path, cache), "propertyName": check["property"]},
                     label(check)))
    return d.get("value")


def run(call, checks, level_path):
    """-> list of (check, ok, value)."""
    cache = {}
    return [(c,) + compare(c, read(call, c, level_path, cache)) for c in checks]


def label(check):
    if "material" in check:
        return "%s %s" % (check["material"].split("/")[-1], check["scalar"])
    where = check.get("object") or check.get("label") or check.get("path", "").rsplit(":", 1)[-1]
    return "%s%s %s" % (where, "." + check["component"] if check.get("component") else "", check["property"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checks", help="JSON list of checks (default: the test game's documented recipe)")
    ap.add_argument("--from-calls", action="append", default=[], metavar="FILE",
                    help="build the checks from an applied calls json (repeatable); the generic form for any game")
    ap.add_argument("--level-path", help="persistent level object path (default: read with level.get_current)")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    if a.from_calls:
        checks = [c for f in a.from_calls for c in checks_from_calls(json.load(open(f)))]
    else:
        checks = json.load(open(a.checks)) if a.checks else DEFAULT_CHECKS
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))

    def call(cat, meth, args, what, timeout=120):
        r = t.call(cat, meth, args, timeout)
        if ue_route.reply_failed(r, getattr(t, "is_error", False)):
            raise SystemExit("FAILED %s: %s" % (what, r[:400]))
        return r
    try:
        level_path = a.level_path
        if not level_path:
            pkg = as_json(call("level", "get_current", {}, "get_current"))["mapPackagePath"]
            level_path = "%s.%s:PersistentLevel" % (pkg, pkg.rsplit("/", 1)[-1])
        results = run(call, checks, level_path)
    finally:
        t.close()
    drift = 0
    for c, ok, v in results:
        drift += not ok
        print("%-5s %-60s %s%s" % ("ok" if ok else "DRIFT", label(c), json.dumps(v)[:90], "" if ok else "  <- " + c.get("why", "")))
    print("%d check(s), %d drift" % (len(results), drift))
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
