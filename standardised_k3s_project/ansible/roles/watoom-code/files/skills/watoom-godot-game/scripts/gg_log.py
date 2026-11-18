#!/usr/bin/env python3
"""Classify a Godot log. The exit code of godot is NOT trusted: errors print ERROR: lines and still exit 0.

  gg_log.py FILE [--strict-warnings]      exit 0 clean, 3 fatal engine lines, 4 gpu/crash lines

classify(text) -> {"fatal": [...], "warnings": [...], "noise": [...], "done": bool, "begun": bool}
Each entry: {"cls", "line_no", "text", "at": [continuation lines]}. Pure, stdlib only.
Unknown ERROR: lines are FATAL; only the explicit NOISE allowlist (audio / X / root notice) is ignored.
"""
import argparse
import json
import re
import sys

# (class, regex, anchored_at_line_start). Checked in order; first match wins.
FATAL_RULES = [
    ("gpu_error", r"VK_ERROR_|OUT_OF_DEVICE_MEMORY|Could not create.*(device|swapchain|context)|Unable to create DisplayServer|drivers seem not to support|Failed to initialize (Vulkan|OpenGL)", False),
    ("crash", r"Program crashed with signal|handle_crash|Dumping the backtrace", False),
    ("shader_error", r"SHADER ERROR:|Shader compilation failed|Fragment shader|Vertex shader|Error at \(\d+:\d+\)", False),
    ("script_error", r"^SCRIPT ERROR:|Parse Error:|Failed to load script|Invalid call\.|Invalid access to property|Invalid get index|Invalid set index", False),
    ("user_error", r"^USER (SCRIPT )?ERROR:", False),
    ("load_error", r"Failed loading resource:|No loader found for resource|Cannot open file|Resource file not found|Error importing|Failed to instantiate scene|Cannot open resource", False),
    ("engine_error", r"^ERROR:", False),
]
WARN_RULES = [r"^WARNING:", r"^USER WARNING:", r"leaked at exit", r"still in use at exit"]
# Reviewed noise. Every entry has a reason. Anchored on audio / display tokens; nothing generic.
NOISE = [
    (r"^ALSA lib ", "ALSA probe on a host without sound"),
    (r"^ALSA lib .*PulseAudio", "no pulse server in a headless session"),
    (r"^WARNING: All audio drivers failed", "audio falls back to dummy"),
    (r"^Set the environment variable `GODOT_SILENCE_ROOT_WARNING`", "lab runs as root"),
    (r"^WARNING: Started the engine as .root./superuser", "lab runs as root"),
    (r"^\[ *\d+% *\] .*(first_scan_filesystem|update_scripts_classes|loading_editor_layout)", "import progress output"),
    (r"^\[ DONE \] (first_scan_filesystem|update_scripts_classes|loading_editor_layout)", "import progress output"),
    (r"^Godot Engine v\d|^Vulkan \d|^OpenGL API|^Vulkan API|^\s*$", "banner"),
    (r"^WARNING: Could not set V-Sync mode, as changing V-Sync mode is not supported by the graphics driver", "measured under xvfb: the virtual display cannot change V-Sync; physics and pixels are unaffected (smoke run 2026-11-17)"),
]
DONE = "@@GG_DONE@@"
BEGIN = "@@GG_BEGIN@@"


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[(?:\d+;)*\d+m")


STRONG = re.compile(r"^(SCRIPT|SHADER|USER( SCRIPT)?) ERROR:|Parse Error:|Shader compilation failed")


def _is_noise(line):
    """Noise only if no strong error marker is on the line and an allowlist pattern matches the whole line shape."""
    return not STRONG.search(line) and any(re.search(p, line) for p, _ in NOISE)


def classify(text):
    out = {"fatal": [], "warnings": [], "noise": [], "done": False, "begun": False}
    last = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = ANSI.sub("", raw).rstrip()
        if DONE in line:
            out["done"] = True
        if BEGIN in line:
            out["begun"] = True
        if re.match(r"^\s+at: ", line) and last is not None:
            last["at"].append(line.strip())
            continue
        entry = None
        if _is_noise(line):
            if line.strip():
                out["noise"].append({"cls": "noise", "line_no": n, "text": line, "at": []})
            last = out["noise"][-1] if out["noise"] and out["noise"][-1]["line_no"] == n else None
            continue
        for cls, rx, _ in FATAL_RULES:
            if re.search(rx, line):
                entry = {"cls": cls, "line_no": n, "text": line, "at": []}
                out["fatal"].append(entry)
                break
        if entry is None:
            for rx in WARN_RULES:
                if re.search(rx, line):
                    entry = {"cls": "warning", "line_no": n, "text": line, "at": []}
                    out["warnings"].append(entry)
                    break
        last = entry
    return out


def exit_code(report, strict_warnings=False):
    """0 clean, 4 gpu/crash, 3 other fatal (4 wins)."""
    classes = {f["cls"] for f in report["fatal"]}
    if classes & {"gpu_error", "crash"}:
        return 4
    if classes or (strict_warnings and report["warnings"]):
        return 3
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file")
    ap.add_argument("--strict-warnings", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        text = open(a.file, errors="replace").read()
    except OSError as e:
        print("cannot read %s: %s" % (a.file, e), file=sys.stderr)
        return 2
    rep = classify(text)
    code = exit_code(rep, a.strict_warnings)
    if a.json:
        print(json.dumps(rep, indent=1))
    else:
        for f in rep["fatal"] + (rep["warnings"] if a.strict_warnings else []):
            print("%s line %d: %s" % (f["cls"], f["line_no"], f["text"]))
        print("log: %d fatal, %d warnings, %d noise, done=%s -> exit %d" % (len(rep["fatal"]), len(rep["warnings"]), len(rep["noise"]), rep["done"], code))
    return code


if __name__ == "__main__":
    sys.exit(main())
