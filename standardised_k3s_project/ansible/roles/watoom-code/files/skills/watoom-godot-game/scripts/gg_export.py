#!/usr/bin/env python3
"""Export a smoke-tested level (3D) and prove the exported pack loads.

  gg_export.py status --project P
  gg_export.py build  --project P [--preset pck|linux|windows] [--out DIR]   exit 0 only if the export exists AND the pack loads in the engine

Refuses (exit 2) unless smoke_ok.json is valid (run gg_player.py smoke) and the preset is listed in gg_project.json export.presets. linux and windows need the
Godot export templates for the exact engine version; without them the refusal names the folder (only pck needs none). The project is never modified: a clean
copy (no gg_data, no .godot) is staged under gg_data/export/stage with run/main_scene set to the level, and exported from there.
Exit codes as everywhere: 0 pass, 1 check failed, 2 refused, 3 fatal engine log, 4 no verdict, 5 runner failure.
"""
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_log, gg_player, gg_project, gg_terrain  # noqa: E402

PLATFORM = {"pck": "Linux", "linux": "Linux", "windows": "Windows Desktop"}
OUTNAME = {"pck": "game.pck", "linux": "game.x86_64", "windows": "game.exe"}
SKIP = {"gg_data", ".godot", ".git", ".opencode", "export_presets.cfg"}


def templates_dir(version_string):
    return os.path.join(os.path.expanduser("~/.local/share/godot/export_templates"), version_string)


def engine_version(godot):
    rc, out, _ = gg_godot.subprocess_runner([godot, "--version"], 30)
    m = re.match(r"(\d+\.\d+(?:\.\d+)?\.[a-z0-9]+)", out.strip())
    if not m:
        raise gg_godot.Refused("cannot read the engine version from `godot --version`: %r" % out.strip()[:60])
    return m.group(1)


def preset_cfg(preset, out_path):
    opts = {"linux": 'binary_format/architecture="x86_64"\n', "pck": 'binary_format/architecture="x86_64"\n', "windows": ""}[preset]
    return ('[preset.0]\n\nname="%s"\nplatform="%s"\nrunnable=true\nadvanced_options=false\ndedicated_server=false\ncustom_features=""\n'
            'export_filter="all_resources"\ninclude_filter=""\nexclude_filter="gg_data/*, .opencode/*"\nexport_path="%s"\n\n[preset.0.options]\n\n%s'
            % (preset, PLATFORM[preset], out_path, opts))


def set_main_scene(text, scene):
    line = 'run/main_scene="%s"' % scene
    if re.search(r"^run/main_scene=.*$", text, re.M):
        return re.sub(r"^run/main_scene=.*$", line, text, flags=re.M)
    if re.search(r"^\[application\]\s*$", text, re.M):
        return re.sub(r"^(\[application\]\s*)$", r"\1\n" + line, text, count=1, flags=re.M)
    return text.rstrip("\n") + "\n\n[application]\n\n" + line + "\n"


def stage(project, dest, scene):
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    for name in os.listdir(project):
        if name in SKIP:
            continue
        s = os.path.join(project, name)
        (shutil.copytree if os.path.isdir(s) else shutil.copy2)(s, os.path.join(dest, name))
    pg = os.path.join(dest, "project.godot")
    with open(pg) as f:
        t = f.read()
    with open(pg, "w") as f:
        f.write(set_main_scene(t, scene))


def check_allowed(project, prof, preset, godot):
    """-> None or raises Refused."""
    hs = gg_terrain.load_world(project).get("heights_sha")
    ok, changed = gg_player.stamp_state(project, prof, "smoke_ok.json", hs)
    if not ok:
        raise gg_godot.Refused("no valid smoke test (%s): run gg_player.py build and gg_player.py smoke first" % ", ".join(changed))
    allowed = prof.get("export", {}).get("presets", [])
    if preset not in allowed:
        raise gg_godot.Refused("preset '%s' is not in gg_project.json export.presets %s" % (preset, allowed))
    if preset != "pck":
        d = templates_dir(engine_version(godot))
        if not (os.path.isdir(d) and os.listdir(d)):
            raise gg_godot.Refused("no export templates for this engine in %s: install them (Godot's Export Templates for %s) or export the pck preset" % (d, os.path.basename(d)))


def build(project, preset="pck", out=None, runner=gg_godot.subprocess_runner):
    prof = gg_project.load_profile(project)
    godot = gg_godot.find_godot()
    if not godot:
        raise gg_godot.Refused("godot not found (set GG_GODOT or install godot 4.7.2)")
    if prof.get("dimension") != "3d":
        raise gg_godot.Refused("only 3D levels export for now (2D players are not built yet)")
    if preset not in PLATFORM:
        raise gg_godot.Refused("unknown preset '%s' (have %s)" % (preset, ", ".join(PLATFORM)))
    if not os.path.isfile(os.path.join(project, "addons", "gg", "ops", "pack_check.gd")):
        raise gg_godot.Refused("the project runtime has no pack_check op: run gg_project.py sync-runtime")
    check_allowed(project, prof, preset, godot)
    level = prof["level"]
    scene = "res://levels/%s/level.tscn" % level
    out = os.path.realpath(out) if out else os.path.join(project, "gg_data", "export", preset)
    os.makedirs(out, exist_ok=True)
    target = os.path.join(out, OUTNAME[preset])
    if os.path.exists(target):
        os.remove(target)
    st = os.path.join(project, "gg_data", "export", "stage")
    stage(project, st, scene)
    with open(os.path.join(st, "export_presets.cfg"), "w") as f:
        f.write(preset_cfg(preset, target))
    flag = "--export-pack" if preset == "pck" else "--export-release"
    rc, text, to = runner([godot, "--headless", "--audio-driver", "Dummy", "--path", st, "--import"], 300)
    rc, text, to = runner([godot, "--headless", "--audio-driver", "Dummy", "--path", st, "--log-file", os.path.join(out, "export.log"), flag, preset, target], 600)
    rep = gg_log.classify(text)
    if to:
        return 4, {"why": "export timed out"}
    if rep["fatal"]:
        f = rep["fatal"][0]
        return 3, {"why": "engine log %s at line %d: %s" % (f["cls"], f["line_no"], f["text"])}
    if not os.path.isfile(target) or os.path.getsize(target) == 0:
        return 1, {"why": "the export produced no %s (see %s)" % (OUTNAME[preset], os.path.join(out, "export.log"))}
    pack = target if preset == "pck" else os.path.join(out, "game.pck")
    if preset != "pck" and not os.path.isfile(pack):
        return 1, {"why": "the %s export wrote no game.pck beside the binary" % preset}
    code, rep2 = check_pack(project, pack, scene, godot, runner)
    if code:
        return code, rep2
    ev = {"preset": preset, "file": target, "bytes": os.path.getsize(target), "pack": rep2["data"]}
    if preset == "linux":
        code, rep3 = check_binary(project, target, out, runner)
        if code:
            return code, rep3
        ev["binary"] = rep3["data"]
    gg_player.gg_scatter.atomic_json(os.path.join(out, "export_ok.json"), ev)
    return 0, {"evidence": ev}


def check_pack(project, pack, scene, godot, runner=gg_godot.subprocess_runner):
    """Load the exported pack in the engine and run the pack_check op inside it."""
    job, jd = gg_godot._new_job(project, "pack_check")
    with open(os.path.join(jd, "spec.json"), "w") as f:
        json.dump({"schema": 1, "op": "pack_check", "job": job, "args": {"scene": scene}}, f)
    argv = [godot, "--headless", "--audio-driver", "Dummy", "--main-pack", pack, "--log-file", os.path.join(jd, "godot.log"), "--quit-after", "600",
            "-s", "res://addons/gg/gg_runner.gd", "--", "--spec=" + os.path.join(jd, "spec.json"), "--result=" + os.path.join(jd, "result.json")]
    rc, out, to = runner(argv, 180)
    logf = os.path.join(jd, "godot.log")
    text = open(logf, errors="replace").read() if os.path.exists(logf) and os.path.getsize(logf) else out
    report = gg_log.classify(text)
    rp = os.path.join(jd, "result.json")
    result = json.load(open(rp)) if os.path.exists(rp) else None
    code, why = gg_godot.decide(rc, to, report, result, job)
    if code:
        return code, {"why": "pack check: " + why}
    return 0, {"data": result["data"]}


MIN_STD, MIN_COLORS, MAX_START_DIFF = 0.03, 500, 0.05


def frame_verdict(frame, start=None):
    """Pure: frame (and the smoke start shot, if any) as float RGB arrays in 0..1 -> (ok, evidence dict, why)."""
    import numpy as np
    ev = {"std": round(float(frame.std()), 3), "colors": int(len(np.unique((frame * 255).astype(int).reshape(-1, 3), axis=0)))}
    if ev["std"] < MIN_STD or ev["colors"] < MIN_COLORS:
        return False, ev, "the shipped binary drew a blank or flat frame (std %.3f, %d colours)" % (ev["std"], ev["colors"])
    if start is not None:
        ev["start_diff"] = round(float(np.abs(frame - start).mean()), 3)
        if ev["start_diff"] > MAX_START_DIFF:
            return False, ev, "the shipped binary's first view differs from the smoke test's start view (mean abs diff %.3f > %.2f): it is not showing the level" % (ev["start_diff"], MAX_START_DIFF)
    return True, ev, "ok"


def check_binary(project, binary, out, runner=gg_godot.subprocess_runner, frames=90):
    """Run the exported linux binary like a player would (xvfb, real renderer), record frames, scan the log, judge the last frame.
    Release templates ignore -s, so the engine-side pack_check cannot run inside the binary."""
    import numpy as np
    from PIL import Image
    mv = os.path.join(out, "run")
    shutil.rmtree(mv, ignore_errors=True)
    os.makedirs(mv)
    log = os.path.join(mv, "run.log")
    argv = ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24", binary, "--rendering-method", "forward_plus", "--rendering-driver", "vulkan", "--resolution", "1280x720",
            "--audio-driver", "Dummy", "--write-movie", os.path.join(mv, "f.png"), "--fixed-fps", "60", "--quit-after", str(frames), "--log-file", log]
    rc, text, to = runner(argv, 180)
    rep = gg_log.classify(open(log, errors="replace").read() if os.path.isfile(log) else text)
    if to:
        return 4, {"why": "the exported binary did not exit within 180 s"}
    if any(f["cls"] in ("gpu_error", "crash") for f in rep["fatal"]):
        return 4, {"why": "binary run: %s" % rep["fatal"][0]["text"]}
    if rep["fatal"]:
        return 3, {"why": "binary run log %s at line %d: %s" % (rep["fatal"][0]["cls"], rep["fatal"][0]["line_no"], rep["fatal"][0]["text"])}
    shots = sorted(f for f in os.listdir(mv) if f.endswith(".png"))
    if rc != 0 or len(shots) < frames // 2:
        return 4, {"why": "the exported binary exit %s with %d frames recorded (expected about %d)" % (rc, len(shots), frames)}
    frame = np.asarray(Image.open(os.path.join(mv, shots[-1])).convert("RGB")).astype(float) / 255
    sp = os.path.join(project, "gg_data", "smoke", "start.png")
    start = np.asarray(Image.open(sp).convert("RGB").resize((frame.shape[1], frame.shape[0]))).astype(float) / 255 if os.path.isfile(sp) else None
    ok, ev, why = frame_verdict(frame, start)
    ev["frames"] = len(shots)
    return (0, {"data": ev}) if ok else (1, {"why": why})


def status(project):
    prof = gg_project.load_profile(project)
    hs = gg_terrain.load_world(project).get("heights_sha")
    ok, changed = gg_player.stamp_state(project, prof, "smoke_ok.json", hs)
    print("smoke_ok.json  %s%s" % ("VALID" if ok else "STALE or missing", "" if ok else " (%s): run gg_player.py smoke" % ", ".join(changed)))
    godot = gg_godot.find_godot()
    d = templates_dir(engine_version(godot)) if godot else "?"
    print("templates      %s" % (d if os.path.isdir(d) and os.listdir(d) else "none in %s: only the pck preset can export" % d))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("build", "status"):
        p = sub.add_parser(n)
        p.add_argument("--project", required=True)
        if n == "build":
            p.add_argument("--preset", default="pck")
            p.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        project = os.path.abspath(a.project)
        if a.cmd == "status":
            return status(project)
        code, rep = build(project, a.preset, a.out)
        print("EXPORT PASS: " + json.dumps(rep["evidence"]) if not code else "FAILED (exit %d): %s" % (code, rep.get("why")))
        return code
    except (gg_godot.Refused, ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
