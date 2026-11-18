"""watoom-texture-layering: one project profile for every Unreal helper (host-side, stdlib only).

The helpers need a handful of facts about the game they run on: the landscape actor label, the landscape height mapping
(z0, raw_per_cm), its edge length (size_m), the sea level, the content root and the label prefix. Instead of repeating them on
every command line (and hard-coding one game's values), put them in a JSON profile and pass `--project FILE` (or set the
UE_PROJECT environment variable). A value given on the command line always wins. Without a profile nothing changes: the
arguments stay required.

  {"landscape": "Landscape", "z0": 3677.7, "raw_per_cm": 4.4387, "size_m": 4000, "sea_cm": 4849.26,
   "label_prefix": "MyGame_", "content_root": "/Game/MyGame", "water_material": "/Game/MyGame/Water/MI_River",
   "plane_water_material": "/Game/Pack/Materials/M_Inst_Water", "rig_content_dir": "F:/Documents/Unreal Projects/MyGame/Content/",
   "host": "10.99.1.44", "port": 2224, "user": "uemcp", "key_dir": "/data/ai/ue-mcp-ssh"}

Use it in a script with `import ue_project` then `ue_project.apply(ap)` just before `ap.parse_args(argv)`; read the extra keys
(label_prefix, content_root, ...) with `ue_project.get(name, default)`.

A key only reaches a script that has the matching flag (DEST below). Who reads what (2026-11-16):
  z0, raw_per_cm, size_m   every script with --z0 / --raw-per-cm / --size-m (NOT unreal_scene_scatter.py: it takes --min-z / --max-z)
  sea_cm                   every script with --sea-cm or --sea-z
  landscape                every script with --landscape
  water_material           ue_place_river.py --material only (a Water-plugin river material for a WaterBodyRiver)
  plane_water_material     unreal_creeks.py --material only (a material that renders on plain Plane actors; a Water-plugin
                           material renders nothing or white there, so the two keys are separate on purpose)
  label_prefix             unreal_village.py --prefix only (labels of the existing village actors)
  content_root             ue_village_build.py only (foliage types go to <content_root>/Foliage/Village)
  rig_content_dir          rig_copy_pack.py --dest only
  exposure                 unreal_atmosphere.py --exposure (the locked auto-exposure value; measure it with ue_look_probe.py)
  post_process_label, sun_label, sky_dome_label   read by unreal_atmosphere.py with ue_project.get() (defaults <label_prefix>PostProcess,
                           <label_prefix>Sun, <label_prefix>StarDome; sky_dome_label "" = no nebula dome)
  host, port, user, key_dir  every tools/rig-ue-mcp script with --host / --port / --user / --key-dir (rig connection details,
                           previously only a hard-coded CLI default repeated per script; T-0055 item 7)
Not profile-driven (fixed in the scripts): the labels Creek_<n>_<k>, CreekRibbon_<n>_<k>, Lake_<n> (unreal_creeks.py), Ocean
(unreal_island.py), Village_House_<n> / Village_Prop_<n> (unreal_scene_scatter.py), and the layer names grass, dry_grass, dirt, mud,
rock (unreal_ground_paint.py, tools/rig-ue-mcp/ue_ground_fetch.py). A game with other names must edit those constants.
"""
import argparse
import json
import os
import sys

# argparse dest -> profile key. sea_z and sea_cm are the same number under two flag names.
DEST = {"z0": "z0", "raw_per_cm": "raw_per_cm", "size_m": "size_m", "sea_z": "sea_cm", "sea_cm": "sea_cm",
        "landscape": "landscape", "material": "water_material", "plane_material": "plane_water_material",
        "prefix": "label_prefix", "content_root": "content_root", "dest": "rig_content_dir",
        "host": "host", "port": "port", "user": "user", "key_dir": "key_dir",
        "exposure": "exposure", "underground_prefixes": "underground_label_prefixes"}
_profile = {}


def load(path):
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("%s: a project profile is a JSON object" % path)
    return data


def _project_path(argv):
    for i, a in enumerate(argv):
        if a == "--project" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--project="):
            return a.split("=", 1)[1]
    return os.environ.get("UE_PROJECT")


def _parsers(ap):
    yield ap
    for action in ap._actions:
        choices = getattr(action, "choices", None)
        for sub in (choices.values() if isinstance(choices, dict) else ()):  # a plain choices=[...] list is not a sub-command table
            if hasattr(sub, "_actions"):
                yield from _parsers(sub)


def apply(ap, argv=None):
    """Add --project, load it and use it as the default (and drop `required`) for every matching flag."""
    argv = sys.argv[1:] if argv is None else argv
    for parser in _parsers(ap):  # accepted before or after a sub-command
        parser.add_argument("--project", default=argparse.SUPPRESS, metavar="FILE", help="project profile JSON (default: $UE_PROJECT); fills z0, raw-per-cm, size-m, sea level, landscape and friends")
    path = _project_path(argv)
    _profile.clear()
    if not path:
        return {}
    _profile.update(load(path))
    for parser in _parsers(ap):
        for action in parser._actions:
            key = DEST.get(action.dest)
            if key in _profile:
                value = _profile[key]
                if action.type:
                    value = action.type(value)
                parser.set_defaults(**{action.dest: value})
                action.required = False
    return dict(_profile)


def get(key, default=None):
    return _profile.get(key, default)
