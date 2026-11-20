#!/usr/bin/env python3
"""Combat core: attribute/damage/effect math (the Godot equivalent of T-0063's Unreal/GAS core, generic step
only -- see references/gg-combat.md for the full plan and what is NOT built yet: weapon/spell/item specs,
animation, VFX, items, multiplayer replication).

  gg_combat.py init  --project P [--dry-run]   write tests/test_combat.gd into an existing project (addons/gg
                                                must already be installed: run gg_project.py sync-runtime first)
  gg_combat.py check --project P [--timeout 60]  run the engine op that proves CombatComponent works live in a
                                                SceneTree (damage-once, cooldowns, teammate immunity, death,
                                                a refused resource cost not eating its own cooldown). No scene
                                                or assets needed -- headless, no rendering.
  gg_combat.py slice --project P [--timeout 60]  T-0070 vertical slice: a real CharacterBody3D attacker and
                                                dummy with real CollisionShape3D colliders, ticked through
                                                physics_frame; sword (melee range), gun (a real PhysicsServer
                                                raycast against the dummy's real collider) and spell (instant
                                                at range) all land, cooldowns gate each, the dummy dies.
  gg_combat.py pickups --project P [--timeout 60]  T-0071 items/pickups: a real Area3D (game/pickup.gd) whose
                                                OWN physics-driven body_entered signal (not a scripted call)
                                                grants an effect to a CharacterBody3D's CombatComponent, then
                                                despawns (one-shot) or respawns on a real timer.
  gg_combat.py mp --project P [--timeout 20]   T-0072 server authority: two REAL, concurrently-running godot
                                                processes (server + client) over a real ENetMultiplayerPeer
                                                on localhost. The client's direct local call to
                                                CombatComponent.request_ability is rejected (it is never the
                                                authority); its rpc_id(1, ...) call reaches the server, which
                                                is the one that actually changes its own health.
  gg_combat.py spec --project P --spec FILE (--weapon NAME | --spell NAME) [--timeout 60]
                                                T-0075: load+validate a declarative weapon/spell spec (JSON,
                                                see templates/combat_spec.example.json) and prove ONE named
                                                entry live: real melee-range/raycast/instant delivery per its
                                                "delivery" field, its own cooldown_s/effect/cost, and its vfx
                                                recipes building (ops/combat_spec_check.gd) -- the data-driven
                                                generalisation of `slice` above, which stays hardcoded and
                                                untouched for backward compatibility.

The library itself lives in the shared runtime (game/combat_attributes.gd, game/combat.gd,
game/combat_component.gd) and is installed into every project's addons/gg by gg_project.py sync-runtime like
every other gg_* runtime file; `init` here only adds the starter GDScript test (run it with `gg_ui.py test`;
this script does not duplicate that runner). `check` is the one op this stage owns: a scripted scenario
(ops/combat_check.gd) run headless, standing in for ue_combat_check.py until items/animation/multiplayer are
built (see references/gg-combat.md and T-0065 for what's left). Exit codes (shared with the other gg_* stages):
0 pass | 1 a check failed | 2 refused | 3 fatal engine log line | 4 no verdict | 5 runner failure.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
import gg_godot  # noqa: E402
import gg_log  # noqa: E402
import gg_schema as S  # noqa: E402

# T-0075: declarative weapon/spell spec schema (the Godot-side equivalent of watoom-unreal-combat's
# combat_spec.zas.json), checked with the same gg_schema.check() every other gg_*.py profile uses (see
# gg_project.py's PROFILE_SCHEMA). "damage_type" (not "element") is the exact field game/combat.gd's
# apply_effect/deal_damage reads for the resist lookup -- see references/gg-combat.md for why the ticket's
# own "element" wording and this field's real name differ.
RESOURCES = ["health", "shield", "stamina", "mana", "ammo"]
EFFECT_SCHEMA = {"t": "obj", "fields": {
    "kind": {"t": "str", "enum": ["damage", "heal", "cost", "grant"]},
    "amount": {"t": "float", "min": 0},
    "resource": {"t": "str", "enum": RESOURCES, "opt": True},
    "damage_type": {"t": "str", "opt": True},
}}
ABILITY_SCHEMA = {"t": "obj", "fields": {
    "display_name": {"t": "str", "opt": True},
    "mesh": {"t": "str", "opt": True},
    "parts": {"t": "list", "opt": True, "items": {"t": "str"}},
    "delivery": {"t": "str", "enum": ["melee", "raycast", "instant"]},
    "range_m": {"t": "float", "min": 0, "max": 10000},
    "cooldown_s": {"t": "float", "min": 0, "max": 600},
    "effect": EFFECT_SCHEMA,
    "cost": {"t": "obj", "opt": True, "fields": {"resource": {"t": "str", "enum": RESOURCES}, "amount": {"t": "float", "min": 0}}},
    "vfx": {"t": "obj", "open": True, "opt": True},
    "animation": {"t": "obj", "open": True, "opt": True},
}}
SPEC_SCHEMA = {"t": "obj", "fields": {
    "schema": {"t": "int", "min": 1, "max": 1},
    "pack": {"t": "str", "opt": True},
    "weapons": {"t": "obj", "open": True, "opt": True},
    "spells": {"t": "obj", "open": True, "opt": True},
}}

TEST_COMBAT_GD = '''extends "res://addons/gg/lib/gg_test.gd"
const Combat := preload("res://addons/gg/game/combat.gd")
const CombatAttributes := preload("res://addons/gg/game/combat_attributes.gd")

func test_calc_damage_applies_multiplier_and_resist() -> void:
\tnear(Combat.calc_damage(10.0, 2.0, 0.5), 10.0, 0.001, "10 base x2 crit x(1-0.5 resist)")
\teq(Combat.calc_damage(-5.0, 2.0, 0.0), 0.0, "negative base floors at 0")
\teq(Combat.calc_damage(10.0, -3.0, 0.0), 0.0, "negative multiplier clamps to 0")
\tnear(Combat.calc_damage(10.0, 1.0, 5.0), 0.0, 0.001, "resist above 1.0 clamps to full absorb")

func test_apply_damage_shield_first_then_health_then_death() -> void:
\tvar a := CombatAttributes.new()
\ta.max_health = 100.0; a.health = 100.0
\ta.max_shield = 20.0; a.shield = 20.0
\tvar r1 := a.apply_damage(30.0)
\teq(r1["shield_lost"], 20.0, "shield absorbs first")
\teq(r1["health_lost"], 10.0, "overflow hits health")
\teq(r1["died"], false, "90 health left")
\tnear(a.health, 90.0, 0.001, "health after overflow")
\teq(a.shield, 0.0, "shield emptied")
\tvar r2 := a.apply_damage(1000.0)
\teq(r2["died"], true, "lethal hit reports died")
\teq(a.dead, true, "attrs.dead flips")
\teq(a.health, 0.0, "health clamps at 0, never negative")

func test_deal_damage_looks_up_resist_by_damage_type() -> void:
\tvar a := CombatAttributes.new()
\ta.max_health = 100.0; a.health = 100.0
\ta.resist = {"fire": 0.5}
\tvar r := Combat.deal_damage(a, 40.0, "fire")
\tnear(r["amount"], 20.0, 0.001, "fire resist halves the roll")
\tnear(a.health, 80.0, 0.001, "health reduced by the resisted amount")
\tvar r2 := Combat.deal_damage(a, 10.0, "physical")
\tnear(r2["amount"], 10.0, 0.001, "no resist entry for physical -> full damage")

func test_heal_clamps_at_max_and_reports_actual_gain() -> void:
\tvar a := CombatAttributes.new()
\ta.max_health = 100.0; a.health = 90.0
\teq(a.apply_heal(5.0), 5.0, "normal heal")
\teq(a.apply_heal(100.0), 5.0, "heal past max only grants what's missing")
\teq(a.health, 100.0, "health clamped at max")

func test_team_and_friendly_fire() -> void:
\tok(not Combat.is_friendly(0, 1), "different teams are not friendly")
\tok(Combat.is_friendly(1, 1), "same team is friendly")
\tok(not Combat.is_friendly(-1, -1), "-1 team is never friendly with itself (neutral/dummy)")
\tok(Combat.can_damage(0, 1), "hostile teams can always damage")
\tok(not Combat.can_damage(1, 1), "same team blocked by default")
\tok(Combat.can_damage(1, 1, true), "same team allowed with friendly_fire=true")

func test_cooldown_ready() -> void:
\tok(Combat.cooldown_ready(-1.0, 100.0, 5.0), "never used -> ready")
\tok(not Combat.cooldown_ready(100.0, 102.0, 5.0), "2s of a 5s cooldown elapsed -> not ready")
\tok(Combat.cooldown_ready(100.0, 105.0, 5.0), "exactly the cooldown elapsed -> ready")

func test_apply_effect_dispatches_by_kind() -> void:
\tvar a := CombatAttributes.new()
\ta.max_health = 100.0; a.health = 100.0
\ta.max_mana = 50.0; a.mana = 50.0
\tvar dmg := Combat.apply_effect(a, {"kind": "damage", "amount": 25.0})
\tnear(dmg["amount"], 25.0, 0.001, "damage effect")
\tnear(a.health, 75.0, 0.001, "health after damage effect")
\tvar heal := Combat.apply_effect(a, {"kind": "heal", "amount": 10.0})
\teq(heal["healed"], 10.0, "heal effect")
\tvar cost_ok := Combat.apply_effect(a, {"kind": "cost", "resource": "mana", "amount": 20.0})
\teq(cost_ok["ok"], true, "affordable mana cost")
\tnear(a.mana, 30.0, 0.001, "mana spent")
\tvar cost_fail := Combat.apply_effect(a, {"kind": "cost", "resource": "mana", "amount": 1000.0})
\teq(cost_fail["ok"], false, "unaffordable mana cost refused")
\tnear(a.mana, 30.0, 0.001, "mana unchanged on a refused cost")
\tvar unknown := Combat.apply_effect(a, {"kind": "nonsense"})
\teq(unknown["ok"], false, "unknown effect kind refused, not a crash")
'''


def check_project(project):
    if not os.path.isfile(os.path.join(project, "project.godot")):
        raise gg_godot.Refused("%s has no project.godot: run an init stage (e.g. gg_ui.py init / gg_player.py init) first" % project)
    if not os.path.isfile(os.path.join(project, "addons", "gg", "game", "combat.gd")):
        raise gg_godot.Refused("%s has no addons/gg/game/combat.gd: run gg_project.py sync-runtime first" % project)


def init(a):
    project = os.path.abspath(a.project)
    check_project(project)
    tests = os.path.join(project, "tests")
    dest = os.path.join(tests, "test_combat.gd")
    if os.path.exists(dest) and not a.force:
        raise gg_godot.Refused("%s already exists (pass --force to overwrite)" % dest)
    if a.dry_run:
        print("gg_combat init: would write %s" % dest)
        return 0
    os.makedirs(tests, exist_ok=True)
    with open(dest, "w") as f:
        f.write(TEST_COMBAT_GD)
    print("gg_combat init: wrote %s; run `gg_ui.py test --project %s` to verify (tests/test_combat.gd exercises "
          "addons/gg/game/combat.gd + combat_attributes.gd: damage/resist math, shield-then-health, death, heal "
          "clamping, team/friendly-fire, cooldowns, and the damage/heal/cost effect kinds)" % (dest, project))
    return 0


def check(a):
    project = os.path.abspath(a.project)
    check_project(project)
    r = gg_godot.run(project, "combat_check", {}, render=False, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code not in (0, 1, 5) or not d:
        print("gg_combat check: exit %d: %s (job %s)" % (r.code, r.why, r.job_dir))
        return r.code
    for row in d["checks"]:
        print("  [%s] %s: %s" % ("ok" if row["ok"] else "FAIL", row["name"], row["detail"]))
    ok = all(row["ok"] for row in d["checks"])
    print("gg_combat check: %s: %d check(s) (job %s)" % ("PASS" if ok else "FAIL", len(d["checks"]), r.job_dir))
    return 0 if ok else 1


def slice_(a):
    project = os.path.abspath(a.project)
    check_project(project)
    r = gg_godot.run(project, "combat_slice", {}, render=False, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code not in (0, 1, 5) or not d:
        print("gg_combat slice: exit %d: %s (job %s)" % (r.code, r.why, r.job_dir))
        return r.code
    for row in d["checks"]:
        print("  [%s] %s: %s" % ("ok" if row["ok"] else "FAIL", row["name"], row["detail"]))
    ok = all(row["ok"] for row in d["checks"])
    print("gg_combat slice: %s: %d check(s) (job %s)" % ("PASS" if ok else "FAIL", len(d["checks"]), r.job_dir))
    return 0 if ok else 1


def pickups(a):
    project = os.path.abspath(a.project)
    check_project(project)
    r = gg_godot.run(project, "pickup_check", {}, render=False, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code not in (0, 1, 5) or not d:
        print("gg_combat pickups: exit %d: %s (job %s)" % (r.code, r.why, r.job_dir))
        return r.code
    for row in d["checks"]:
        print("  [%s] %s: %s" % ("ok" if row["ok"] else "FAIL", row["name"], row["detail"]))
    ok = all(row["ok"] for row in d["checks"])
    print("gg_combat pickups: %s: %d check(s) (job %s)" % ("PASS" if ok else "FAIL", len(d["checks"]), r.job_dir))
    return 0 if ok else 1


def spec_errors(doc):
    """Validate a loaded weapon/spell spec doc (templates/combat_spec.example.json shape). -> list of error strings."""
    errs = S.check(doc, SPEC_SCHEMA)
    if not isinstance(doc, dict):
        return errs
    weapons = doc.get("weapons") or {}
    spells = doc.get("spells") or {}
    if not weapons and not spells:
        errs.append("$: spec has neither 'weapons' nor 'spells' (need at least one ability)")
    for category, group in (("weapons", weapons), ("spells", spells)):
        if not isinstance(group, dict):
            continue
        for name, entry in group.items():
            errs += S.check(entry, ABILITY_SCHEMA, "$.%s.%s" % (category, name))
    return errs


def load_spec(path):
    """Load+validate a weapon/spell spec JSON file. -> dict. Raises gg_godot.Refused on any schema problem."""
    if not os.path.isfile(path):
        raise gg_godot.Refused("%s: no such spec file" % path)
    with open(path) as f:
        doc = json.load(f)
    errs = spec_errors(doc)
    if errs:
        raise gg_godot.Refused("%s invalid:\n  " % path + "\n  ".join(errs))
    return doc


def resolve_ability(doc, category, name):
    """-> the ability dict for one named weapon/spell ("weapons"|"spells") in a loaded spec. Raises gg_godot.Refused if missing."""
    group = doc.get(category) or {}
    if name not in group:
        raise gg_godot.Refused("%s '%s' not found in spec (have: %s)" % (category[:-1], name, ", ".join(sorted(group)) or "none"))
    return group[name]


def spec(a):
    project = os.path.abspath(a.project)
    check_project(project)
    if bool(a.weapon) == bool(a.spell):
        raise gg_godot.Refused("pass exactly one of --weapon or --spell")
    doc = load_spec(a.spec)
    category, name = ("weapons", a.weapon) if a.weapon else ("spells", a.spell)
    ability = resolve_ability(doc, category, name)
    r = gg_godot.run(project, "combat_spec_check", {"category": category, "name": name, "ability": ability}, render=False, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code not in (0, 1, 5) or not d:
        print("gg_combat spec: exit %d: %s (job %s)" % (r.code, r.why, r.job_dir))
        return r.code
    for row in d["checks"]:
        print("  [%s] %s: %s" % ("ok" if row["ok"] else "FAIL", row["name"], row["detail"]))
    ok = all(row["ok"] for row in d["checks"])
    print("gg_combat spec: %s: %s.%s, %d check(s) (job %s)" % ("PASS" if ok else "FAIL", category, name, len(d["checks"]), r.job_dir))
    return 0 if ok else 1


def _wait_process(p, timeout):
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = p.communicate()
        return -9, out or "", True


def mp(a):
    project = os.path.abspath(a.project)
    check_project(project)
    godot = gg_godot.find_godot()
    if not godot:
        raise gg_godot.Refused("godot not found (set GG_GODOT or install godot 4.7.2)")
    drift = gg_godot.runtime_drift(project)
    if drift:
        raise gg_godot.Refused("runtime drift (someone edited addons/gg): %s; fix with gg_project.py sync-runtime" % "; ".join(drift[:3]))

    # one shared --import preflight: both processes point at the same project.
    rc, out, to = gg_godot.subprocess_runner([godot, "--headless", "--audio-driver", "Dummy", "--path", project, "--import"], 300)
    if to or gg_log.classify(out)["fatal"]:
        print("gg_combat mp: project import failed", file=sys.stderr)
        return 4

    port = 20000 + (os.getpid() % 10000)
    job_s, dir_s = gg_godot._new_job(project, "mp_server_check")
    job_c, dir_c = gg_godot._new_job(project, "mp_client_check")
    with open(os.path.join(dir_s, "spec.json"), "w") as f:
        json.dump({"schema": 1, "op": "mp_server_check", "job": job_s, "args": {"port": port, "timeout_s": a.timeout}}, f)
    with open(os.path.join(dir_c, "spec.json"), "w") as f:
        json.dump({"schema": 1, "op": "mp_client_check", "job": job_c, "args": {"port": port, "host": "127.0.0.1", "timeout_s": a.timeout}}, f)

    argv_s = gg_godot.build_argv(godot, project, dir_s, render=False, renderer="forward_plus", size=(640, 480))
    argv_c = gg_godot.build_argv(godot, project, dir_c, render=False, renderer="forward_plus", size=(640, 480))
    open(os.path.join(dir_s, "argv.txt"), "w").write(" ".join(argv_s) + "\n")
    open(os.path.join(dir_c, "argv.txt"), "w").write(" ".join(argv_c) + "\n")

    p_s = subprocess.Popen(argv_s, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    time.sleep(1.0)   # let the server bind and start listening before the client tries to connect
    p_c = subprocess.Popen(argv_c, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)

    rc_c, out_c, to_c = _wait_process(p_c, a.timeout + 15)
    rc_s, out_s, to_s = _wait_process(p_s, 15)   # the server should finish shortly after the client's grace window

    ok = True
    for name, job, d, rc, out, to in (("server", job_s, dir_s, rc_s, out_s, to_s), ("client", job_c, dir_c, rc_c, out_c, to_c)):
        logf = os.path.join(d, "godot.log")
        text = open(logf, errors="replace").read() if os.path.exists(logf) and os.path.getsize(logf) > 0 else out
        with open(os.path.join(d, "console.txt"), "w") as f:
            f.write(out)
        report = gg_log.classify(text)
        result = None
        rp = os.path.join(d, "result.json")
        if os.path.exists(rp):
            try:
                result = json.load(open(rp))
            except ValueError:
                result = None
        code, why = gg_godot.decide(rc, to, report, result, job)
        print("gg_combat mp: %s exit %d: %s (job %s)" % (name, code, why, d))
        if code not in (0, 5):
            ok = False
        for row in ((result or {}).get("data") or {}).get("checks", []):
            print("  [%s] %s: %s" % ("ok" if row["ok"] else "FAIL", row["name"], row["detail"]))
            ok = ok and row["ok"]
    print("gg_combat mp: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--project", required=True)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("--project", required=True)
    p.add_argument("--timeout", type=int, default=60)
    p = sub.add_parser("slice")
    p.add_argument("--project", required=True)
    p.add_argument("--timeout", type=int, default=60)
    p = sub.add_parser("pickups")
    p.add_argument("--project", required=True)
    p.add_argument("--timeout", type=int, default=60)
    p = sub.add_parser("mp")
    p.add_argument("--project", required=True)
    p.add_argument("--timeout", type=int, default=20)
    p = sub.add_parser("spec")
    p.add_argument("--project", required=True)
    p.add_argument("--spec", required=True, help="path to a weapon/spell spec JSON file (see templates/combat_spec.example.json)")
    p.add_argument("--weapon", default=None, help="name of an entry under the spec's \"weapons\"")
    p.add_argument("--spell", default=None, help="name of an entry under the spec's \"spells\"")
    p.add_argument("--timeout", type=int, default=60)
    a = ap.parse_args(argv)
    try:
        return {"init": init, "check": check, "slice": slice_, "pickups": pickups, "mp": mp, "spec": spec}[a.cmd](a)
    except gg_godot.Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
