#!/usr/bin/env python3
"""Live combat check in PIE for a slice made by unreal_combat.py: melee, spells, pickups, and (--net) client authority + teams.

  ue_combat_check.py --from-calls combat_calls.json [--net] [--keep-pie]

Reads the applied calls file (player defaults, weapon/spell data, placed dummies and pickups), starts PIE on the spec's map
and checks, printing PASS/FAIL with the numbers read:
  melee     the player's first weapon, swung at the first placed dummy from 110 cm: dummy Shield+Health drop by the damage
  spell N   each spell: Projectile/Hitscan aimed from the real camera at the dummy's chest, Area next to it -> damage;
            Self with Healing -> health rises; mana falls by ManaCost every time
  pickup    each placed consumable: the restored attribute is lowered first, the player is moved onto it -> it rises
  --net     PlayNetMode listen server + 1 client: the CLIENT's swing damages the dummy on the server; the client's swing at
            the host (same team) does nothing. (Replication to the client view was checked by hand: references/combat.md.)
Every check resets the dummy (Shield/Health to max) and the player's mana first. Exit 1 on any FAIL.

Why (T-0063, 2026-11-19): every one of these was first checked by hand with long shell loops; the slice is IaC, so its proof
must be a command too. Lessons it encodes: the editor throttle is turned off for the run and restored (a 0.24 s hit window
passes in one throttled frame); spells are aimed from pie.view_trace's camera, not the pawn (the over-shoulder camera sits
~90 cm right); a client pawn's facing is the client's control rotation, so the dummy is moved in front of it, not the pawn
rotated; gas.get_attribute reads the server world (no pieInstance).
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402

PERF = "/Script/UnrealEd.Default__EditorPerformanceSettings"
PLAY = "/Script/UnrealEd.Default__LevelEditorPlaySettings"
RESTORE = {"RestoreHealth": "Health", "RestoreShield": "Shield", "RestoreMana": "Mana"}


def plan(calls_file):
    """-> dict: player class/label, primary/spell actions, weapons, spells, dummies, pickups, map (pure, tested)."""
    with open(calls_file) as f:
        phases = json.load(f)["phases"]
    defaults, data, placed, props, lvl = {}, {}, [], {}, None
    for p in phases:
        for m, a in p["calls"]:
            if m == "blueprint.set_class_default":
                bp = a["assetPath"].rsplit("/", 1)[-1]
                defaults.setdefault(bp, {})[a["propertyName"]] = a["value"]
            elif m == "asset.bulk_upsert_data_assets":
                for it in a["items"]:
                    data["%s/%s" % (it["packagePath"], it["name"])] = dict(it["properties"], _class=it["className"])
            elif m == "level.place_actor":
                placed.append(a)
            elif m == "level.set_actor_property":
                props.setdefault(a["actorLabel"], {})[a["propertyName"]] = a["value"]
            elif m == "level.load":
                lvl = a["levelPath"]
    # the player is the game mode's DefaultPawnClass (what PIE spawns), else the first character with input
    pawn = next((d["DefaultPawnClass"].rsplit(".", 1)[-1][:-2] for d in defaults.values() if d.get("DefaultPawnClass")), None)
    player = pawn if pawn in defaults else next((bp for bp, d in sorted(defaults.items()) if d.get("PrimaryAction")), None)
    if not player:
        raise ValueError("no player character (PrimaryAction) in the calls")
    d = defaults[player]
    weapons = [dict(data[w], path=w) for w in d.get("StartingWeapons", []) if w in data]
    spells = [dict(data[s], path=s, action=act) for s, act in zip(d.get("StartingSpells", []), d.get("SpellActions", [])) if s in data]
    dummies, pickups = [], []
    for a in placed:
        loc = (a["location"]["x"], a["location"]["y"], a["location"]["z"])
        if a["actorClass"].endswith("WatooMPickup"):
            item = data.get(props.get(a["label"], {}).get("Item", ""), {})
            pickups.append({"label": a["label"], "location": loc, "item": item})
        elif not a["actorClass"].startswith("/Script/") and a["actorClass"] != "StaticMeshActor" and player not in a["actorClass"]:
            cls = a["actorClass"].rsplit(".", 1)[-1][:-2]
            if defaults.get(cls, {}).get("TeamId") is not None and defaults[cls]["TeamId"] == d.get("TeamId"):
                continue            # a friendly NPC (e.g. the wandering Rogue, team 1) is not a target
            dummies.append({"label": a["label"], "location": loc})
    return {"player": player, "player_label": player + "0", "primary": d["PrimaryAction"], "weapons": weapons,
            "next_weapon": d.get("NextWeaponAction"),
            "spells": spells, "dummies": dummies, "pickups": pickups, "map": lvl, "team": d.get("TeamId")}


def aim(camera, target):
    """Control rotation from the camera to a point (pitch, yaw in degrees)."""
    dx, dy, dz = (target[i] - camera[i] for i in range(3))
    return {"pitch": round(math.degrees(math.atan2(dz, math.hypot(dx, dy))), 3), "yaw": round(math.degrees(math.atan2(dy, dx)), 3), "roll": 0}


def expected_damage(spec_damage, shield, health):
    """Total Shield+Health drop for one hit (shield first, never below 0)."""
    return min(spec_damage, shield + health)


class Rig:
    def __init__(self, key_dir):
        self.t = ue_route.SshTransport(ue_route.ssh_command("10.99.1.44", 2224, "uemcp", key_dir))

    def call(self, spec, args, timeout=300):
        cat, meth = spec.split(".", 1)
        r = self.t.call(cat, meth, args, timeout)
        try:
            return json.loads(r[r.index("{"):])
        except ValueError:
            return {"success": False, "error": r[:300]}

    def attr(self, label, name):
        return float(self.call("gas.get_attribute", {"actorLabel": label, "world": "pie", "attribute": name}).get("currentValue", float("nan")))

    def set_attr(self, label, name, value):
        self.call("gas.set_attribute", {"actorLabel": label, "world": "pie", "attribute": name, "value": value})

    def move(self, label, loc, yaw=None, pie_instance=None):
        a = {"actorLabel": label, "world": "pie", "location": {"x": loc[0], "y": loc[1], "z": loc[2]}}
        if yaw is not None:
            a["rotation"] = {"pitch": 0, "yaw": yaw, "roll": 0}
        if pie_instance is not None:
            a["pieInstance"] = pie_instance
        self.call("level.move_actor", a)

    def press(self, action, pie_instance=None, rotation=None):
        if rotation:
            a = {"action_path": action, "value_x": 1, "duration_seconds": 0.1, "control_rotation": rotation}
            m = "pie.inject_input_start"
        else:
            a, m = {"action_path": action, "value_x": 1}, "pie.inject_input"
        if pie_instance is not None:
            a["pie_instance"] = pie_instance
        self.call(m, a)


def vitals(rig, label):
    return rig.attr(label, "Shield") + rig.attr(label, "Health")


def reset_dummy(rig, label):
    for v in ("Health", "Shield"):
        rig.set_attr(label, v, rig.attr(label, "Max" + v))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-calls", required=True)
    ap.add_argument("--net", action="store_true")
    ap.add_argument("--keep-pie", action="store_true")
    ap.add_argument("--no-warmup", action="store_true",
                    help="skip the throw-away first PIE session (needed after new blueprints were created: measured 2026-11-19, the "
                         "first session after applying the wizard hero fired nothing, 4 false FAILs; the next one passed 8/8)")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    a = ap.parse_args(argv)
    p = plan(a.from_calls)
    if not p["dummies"]:
        raise SystemExit("no dummy placed in the calls; nothing to hit")
    rig, results = Rig(a.key_dir), []
    me, dummy = p["player_label"], p["dummies"][0]
    dl = dummy["location"]

    def report(name, ok, detail):
        results.append(ok)
        print("%s %-12s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)

    throttle = rig.call("editor.get_property", {"objectPath": PERF, "propertyName": "bThrottleCPUWhenNotForeground"}).get("valueText", "True")
    try:
        rig.call("editor.play_in_editor", {"pieAction": "stop"})
        if p["map"]:
            rig.call("level.load", {"levelPath": p["map"], "saveFirst": False, "discardUnsaved": True})
        rig.call("editor.set_property", {"objectPath": PERF, "propertyName": "bThrottleCPUWhenNotForeground", "value": False, "save": False})
        if not a.no_warmup:
            rig.call("editor.play_in_editor", {"pieAction": "start"})
            time.sleep(10)
            rig.call("editor.play_in_editor", {"pieAction": "stop"})
            time.sleep(2)
        rig.call("editor.play_in_editor", {"pieAction": "start"})
        time.sleep(8)
        # melee: from 110 cm in front of the dummy, facing it
        melee = next((w for w in p["weapons"] if w.get("Kind") == "Melee"), None)
        if melee and p["weapons"][0] is melee:
            reset_dummy(rig, dummy["label"])
            rig.move(me, (dl[0] - 110, dl[1], dl[2]), yaw=0)
            time.sleep(1)
            before = vitals(rig, dummy["label"])
            rig.press(p["primary"])
            time.sleep(2)
            drop = before - vitals(rig, dummy["label"])
            report("melee", drop >= expected_damage(float(melee.get("Damage", 0)), before, 0) - 0.5,
                   "%s: dummy Shield+Health %.0f -> %.0f (damage %s)" % (melee["path"].rsplit("_", 1)[-1], before, before - drop, melee.get("Damage")))
        else:
            print("SKIP melee: the first starting weapon is not melee")
        # guns and bows: each of the loadout, reached with NextWeapon from the starting weapon; one shot from 4 m, aimed at the
        # dummy's chest; at least one pellet's damage must land (spread can miss the rest, a head hit doubles it)
        current, settled = 0, bool(melee and p["weapons"][0] is melee)
        for i, w in enumerate(p["weapons"]):
            if w.get("Kind") not in ("Gun", "Bow"):  # a bow is checked like a gun: its arrow must land the damage
                continue
            if not settled:
                # a gun-first loadout fires ~10 s after PIE start (no melee check before it): one such first shot missed in
                # 4 runs (2026-11-19, pistol; the spawn equip montage is the suspect), so give the pawn time to settle
                time.sleep(3)
                settled = True
            if i and not p.get("next_weapon"):
                print("SKIP gun %s: no NextWeaponAction to switch to it" % w["path"].rsplit("_", 1)[-1])
                continue
            while current < i:
                rig.press(p["next_weapon"])
                time.sleep(1)
                current += 1
            reset_dummy(rig, dummy["label"])
            rig.move(me, (dl[0] - 400, dl[1], dl[2]), yaw=0)
            time.sleep(1.5)
            v = rig.call("pie.view_trace", {"distance": 100}).get("viewLocation")
            rot = aim((v["x"], v["y"], v["z"]), (dl[0], dl[1], dl[2] + 30)) if v else None
            before = vitals(rig, dummy["label"])
            rig.press(p["primary"], rotation=rot)
            time.sleep(2)
            drop = before - vitals(rig, dummy["label"])
            report(w["Kind"].lower(), drop >= float(w.get("Damage", 0)) - 0.5,
                   "%s: dummy %.0f -> %.0f (damage %s x %s pellet(s))" % (w["path"].rsplit("_", 1)[-1], before, before - drop,
                                                                           w.get("Damage"), w.get("PelletsPerShot", 1)))
        # spells
        for s in p["spells"]:
            name = s["path"].rsplit("_", 1)[-1]
            reset_dummy(rig, dummy["label"])
            rig.set_attr(me, "Mana", rig.attr(me, "MaxMana"))
            delivery = s.get("Delivery", "Projectile")
            if delivery == "Self":
                rig.set_attr(me, "Health", 40)
                h0, m0 = rig.attr(me, "Health"), rig.attr(me, "Mana")
                rig.press(s["action"])
                time.sleep(2)
                h1, m1 = rig.attr(me, "Health"), rig.attr(me, "Mana")
                ok = h1 - h0 >= min(float(s.get("Healing", 0)), 60) - 0.5 and abs((m0 - m1) - float(s.get("ManaCost", 0))) < 0.5
                report("spell " + name, ok, "Self: health %.0f -> %.0f (heal %s), mana %.0f -> %.0f" % (h0, h1, s.get("Healing"), m0, m1))
                continue
            dist = 150 if delivery == "Area" else 600
            rig.move(me, (dl[0] - dist, dl[1], dl[2]), yaw=0)
            time.sleep(1.5)
            rot = None
            if delivery in ("Projectile", "Hitscan"):
                v = rig.call("pie.view_trace", {"distance": 100}).get("viewLocation")
                if v:
                    rot = aim((v["x"], v["y"], v["z"]), (dl[0], dl[1], dl[2] + 30))
            before, m0 = vitals(rig, dummy["label"]), rig.attr(me, "Mana")
            rig.press(s["action"], rotation=rot)
            time.sleep(3)
            drop, m1 = before - vitals(rig, dummy["label"]), rig.attr(me, "Mana")
            ok = drop >= float(s.get("Damage", 0)) - 0.5 and abs((m0 - m1) - float(s.get("ManaCost", 0))) < 0.5
            report("spell " + name, ok, "%s: dummy %.0f -> %.0f (damage %s), mana %.0f -> %.0f" % (delivery, before, before - drop, s.get("Damage"), m0, m1))
        # pickups (consumables)
        for pk in p["pickups"]:
            item = pk["item"]
            attr = next((RESTORE[k] for k in ("RestoreHealth", "RestoreShield", "RestoreMana") if float(item.get(k, 0)) > 0), None)
            if item.get("Kind") != "Consumable" or not attr:
                print("SKIP pickup %s: %s item (checked by hand: reserve ammo goes to its gun)" % (pk["label"], item.get("Kind")))
                continue
            rig.move(me, (0, 0, pk["location"][2] + 40))
            rig.set_attr(me, attr, 10)
            v0 = rig.attr(me, attr)
            rig.move(me, (pk["location"][0], pk["location"][1], pk["location"][2] + 40))
            time.sleep(2)
            v1 = rig.attr(me, attr)
            report("pickup", v1 > v0, "%s: %s %.0f -> %.0f" % (pk["label"], attr, v0, v1))
        if a.net:
            rig.call("editor.play_in_editor", {"pieAction": "stop"})
            rig.call("editor.set_property", {"objectPath": PLAY, "propertyName": "PlayNetMode", "value": "PIE_ListenServer", "save": False})
            rig.call("editor.set_property", {"objectPath": PLAY, "propertyName": "PlayNumberOfClients", "value": 2, "save": False})
            rig.call("editor.play_in_editor", {"pieAction": "start"})
            time.sleep(15)
            client = p["player"] + "1"
            spot = (-500.0, 0.0, dl[2])
            rig.move(me, (0, 800, dl[2]), pie_instance=0)
            rig.move(client, spot, pie_instance=0)
            time.sleep(3)
            # the client's facing is its own control rotation: read it, put the target in front (110 cm for a swing; 4 m for
            # a gun, whose shot is aimed from the client's own view at the target's chest, as in the standalone gun check)
            gun = bool(p["weapons"]) and p["weapons"][0].get("Kind") == "Gun"
            cp = rig.call("editor.get_pie_pawn", {"pieInstance": 1})
            yaw = math.radians(float(cp.get("controlRotation", cp.get("rotation", {})).get("yaw", 0)))
            reach = 400 if gun else 110
            front = (spot[0] + reach * math.cos(yaw), spot[1] + reach * math.sin(yaw), dl[2])
            reset_dummy(rig, dummy["label"])
            rig.move(dummy["label"], front, pie_instance=0)
            time.sleep(2)
            crot = None
            if gun:
                v = rig.call("pie.view_trace", {"distance": 100, "pieInstance": 1}).get("viewLocation")
                crot = aim((v["x"], v["y"], v["z"]), (front[0], front[1], front[2] + 30)) if v else None
            before = vitals(rig, dummy["label"])
            rig.press(p["primary"], pie_instance=1, rotation=crot)
            time.sleep(3)
            after = vitals(rig, dummy["label"])
            report("net client", after < before, "client %s: dummy (server) %.0f -> %.0f" % ("shot" if gun else "swing", before, after))
            rig.move(dummy["label"], (dl[0] + 2000, dl[1], dl[2]), pie_instance=0)
            rig.move(me, front, pie_instance=0)
            time.sleep(3)
            h0 = vitals(rig, me)
            rig.press(p["primary"], pie_instance=1, rotation=crot)
            time.sleep(3)
            h1 = vitals(rig, me)
            report("net team", abs(h1 - h0) < 0.5, "client swing at the host (same team): %.0f -> %.0f" % (h0, h1))
    finally:
        if not a.keep_pie:
            rig.call("editor.play_in_editor", {"pieAction": "stop"})
        if a.net:
            rig.call("editor.set_property", {"objectPath": PLAY, "propertyName": "PlayNetMode", "value": "PIE_Standalone", "save": False})
            rig.call("editor.set_property", {"objectPath": PLAY, "propertyName": "PlayNumberOfClients", "value": 1, "save": False})
        rig.call("editor.set_property", {"objectPath": PERF, "propertyName": "bThrottleCPUWhenNotForeground",
                                         "value": throttle.strip().lower() == "true", "save": False})
        rig.t.close()
    bad = results.count(False)
    print("%d check(s), %d failed" % (len(results), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
