#!/usr/bin/env python3
"""Niagara VFX from small recipes: projectile, impact, muzzle, area, aura, tracer, lightning (and anything built from layers) -> ue-mcp call phases.

  unreal_niagara_fx.py --spec fx.json --out fx_calls.json      then  tools/rig-ue-mcp/ue_run_phases.py fx_calls.json
  spec: {"content_root": "/Game/<Game>/Combat",
         "fx": {"NS_Fireball_Trail":  {"recipe": "projectile", "element": "Fire"},
                "NS_Fireball_Impact": {"recipe": "impact", "element": "Fire", "scale": 1.5},
                "NS_Frost_Nova":      {"recipe": "area", "element": "Frost", "radius": 400},
                "NS_Custom":          {"layers": [{"template": "Fountain", "inputs": {"EmitterUpdate/SpawnRate/SpawnRate": 30}}]}}}
  unreal_combat.py accepts the same "fx" section in a combat spec; a weapon/spell field naming one of these systems
  (ProjectileFx, TracerFx, ImpactFx.Niagara, CastFx.Niagara, AttackFx.Niagara) resolves to its asset path.

Why (T-0063, 2026-11-18): the owner has no spell VFX pack, so magic effects are generated. Each layer is a COPY of an engine
template emitter (/Niagara/DefaultAssets/Templates/Emitters/<T>) with module inputs overridden in the system; templates keep the
modules and renderers working, overrides only tune them. Measured on UE 5.8 (list_module_inputs on each template):
 - InitializeParticle exposes Color, Lifetime Min/Max and Uniform Sprite Size Min/Max on Fountain / OmnidirectionalBurst /
   HangingParticulates (Sprite Size Min/Max vec2 on DirectionalBurst); SingleLoopingParticle hides Color behind a switch, so
   recipes do not use it.
 - Burst templates (OmnidirectionalBurst, DirectionalBurst) loop ONCE (EmitterState Loop Behavior = Once): an impact spawned
   with SpawnSystemAtLocation finishes and is destroyed. Fountain/HangingParticulates/LocationBasedRibbon loop forever: use them
   only for effects owned by something that ends (a projectile, a buff).
 - Loop Behavior is a static switch (set_static_switch), not an input: "aura" sets it to Once with a Loop Duration, so a
   cast aura ends (measured: 0 particles 4 s after spawn, ~40 while looping).
 - Speeds come from the template (AddVelocity speed is a linked random range, not settable); recipes tune count, size,
   lifetime, colour, spawn radius and gravity.
 - Colour above 1 is HDR: the default sprite material is unlit-additive, so (8, 2, 0.3) blooms as fire.
"""
import argparse
import json
import os
import sys

TEMPLATES = "/Niagara/DefaultAssets/Templates/Emitters/"
INIT = "ParticleSpawn/InitializeParticle/"
ELEMENTS = {  # HDR particle colour per damage type (Damage.Type.<Element>)
    "Fire": (8.0, 2.0, 0.3), "Frost": (0.5, 2.0, 8.0), "Lightning": (3.0, 3.0, 10.0), "Poison": (1.0, 6.0, 0.5),
    "Arcane": (5.0, 0.8, 8.0), "Holy": (8.0, 7.0, 3.0), "Physical": (2.0, 2.0, 2.0), "Shadow": (0.6, 0.2, 1.2),
}
SPARK = (0.9, 0.95)
VEC3 = "/Script/CoreUObject.Vector3f"
# Beam End of the DynamicBeam template is an offset in the SYSTEM's local axes (measured 2026-11-19 with capture_sim_cache:
# BeamEnd (1500,0,30000) on a system at (0,0,30000) drew to z 60000, and turned with the system's yaw). AWatooMCombatCharacter::
# MulticastTracer sets User.BeamEnd to the WORLD hit point, so the input is this expression, not a plain link to the parameter.
BEAM_END_TO_LOCAL = "mul(float4(User.BeamEnd, 1.0), Engine.Owner.SystemWorldToLocal).xyz"
SCRIPTS = {"SystemSpawn": "SystemSpawnScript", "SystemUpdate": "SystemUpdateScript", "EmitterSpawn": "EmitterSpawnScript",
           "EmitterUpdate": "EmitterUpdateScript", "ParticleSpawn": "ParticleSpawnScript", "ParticleUpdate": "ParticleUpdateScript"}
ONCE = "NewEnumerator1"  # EmitterState "Loop Behavior" enum value of the one-shot burst templates (Infinite is NewEnumerator0)  # spark/ember layers are a little brighter than the element colour


def colour(element, k=1.0, alpha=1.0):
    if isinstance(element, (list, tuple)):
        r, g, b = element[:3]
    elif element in ELEMENTS:
        r, g, b = ELEMENTS[element]
    else:
        raise ValueError("unknown element %r: use one of %s or an [r, g, b] list" % (element, ", ".join(sorted(ELEMENTS))))
    return {"r": round(r * k, 3), "g": round(g * k, 3), "b": round(b * k, 3), "a": alpha}


def _size(lo, hi, s):
    return {INIT + "Uniform Sprite Size Min": round(lo * s, 2), INIT + "Uniform Sprite Size Max": round(hi * s, 2)}


def _life(lo, hi):
    return {INIT + "Lifetime Min": lo, INIT + "Lifetime Max": hi}


def recipe_layers(fx):
    """fx dict -> [{"name", "template", "inputs": {"Stack/Module/Input": value}}]"""
    if "layers" in fx:
        return [dict(l, name=l.get("name", "L%d" % i)) for i, l in enumerate(fx["layers"])]
    r, el, s = fx.get("recipe"), fx.get("element", "Fire"), float(fx.get("scale", 1.0))
    zero_g = {"ParticleUpdate/GravityForce/Gravity": {"x": 0, "y": 0, "z": 0}}
    if r == "projectile":
        return [
            {"name": "Core", "template": "Fountain", "inputs": dict({
                INIT + "Color": colour(el, 1.5), "EmitterUpdate/SpawnRate/SpawnRate": 80,
                "ParticleSpawn/ShapeLocation/Sphere Radius": 4 * s, "ParticleUpdate/Drag/Drag": 20}, **_size(28, 44, s), **_life(0.12, 0.22), **zero_g)},
            {"name": "Embers", "template": "Fountain", "inputs": dict({
                INIT + "Color": colour(el, SPARK[0] * 1.2), "EmitterUpdate/SpawnRate/SpawnRate": 140,
                "ParticleSpawn/AddVelocity/Cone Angle": 180, "ParticleSpawn/ShapeLocation/Sphere Radius": 10 * s,
                "ParticleUpdate/GravityForce/Gravity": {"x": 0, "y": 0, "z": -150}}, **_size(2, 5, s), **_life(0.25, 0.5))},
            # LocationBasedRibbon ships WITHOUT a spawn module (measured: 0 particles on a flying fireball): add SpawnPerFrame,
            # one ribbon point per frame wherever the projectile is.
            {"name": "Trail", "template": "LocationBasedRibbon", "add_modules": [["EmitterUpdate", "/Niagara/Modules/Emitter/SpawnPerFrame"]],
             "inputs": {INIT + "Color": colour(el, 0.8), INIT + "Lifetime": 0.35}},
        ]
    if r in ("tracer", "lightning"):
        # a beam from the system (spawned at the muzzle/hand) to User.BeamEnd, one short burst: Loop Behavior Once.
        # "lightning" = a wide soft glow under a thin hot core, a little longer.
        bolt = r == "lightning"
        def beam(name, width, k, life):
            return {"name": name, "template": "DynamicBeam", "switches": {"EmitterUpdate/EmitterState/Loop Behavior": ONCE},
                    # Beam Width is driven by a FloatFromCurve dynamic input in the template, which set_module_input cannot
                    # reach ("not found"); an HLSL constant replaces the curve (uniform width)
                    "user_vars": {"BeamEnd": VEC3}, "expressions": {"EmitterUpdate/BeamEmitterSetup/Beam End": BEAM_END_TO_LOCAL,
                                                                    "ParticleSpawn/BeamWidth/Beam Width": "%.2f" % (width * s)},
                    # the beam's colour is the ParticleUpdate Color module (InitializeParticle Color is not reachable on it)
                    # no InitializeParticle on the beam template: the beam lives while the emitter does (Loop Duration, Once)
                    "inputs": dict({"EmitterUpdate/EmitterState/Loop Duration": life, "ParticleUpdate/Color/Color": colour(el, k),
                                    "EmitterUpdate/SpawnBurst_Instantaneous/Spawn Count": 48 if bolt else 24})}
        if bolt:
            return [beam("Core", 3, 3.0, 0.18), beam("Glow", 18, 0.8, 0.22)]
        return [beam("Beam", 2.5, 2.5, 0.08)]
    if r == "impact":
        return [
            {"name": "Sparks", "template": "OmnidirectionalBurst", "inputs": dict({
                INIT + "Color": colour(el, SPARK[1] * 1.3), "EmitterUpdate/SpawnBurst_Instantaneous/Spawn Count": int(80 * s),
                "ParticleSpawn/ShapeLocation/Sphere Radius": 15 * s}, **_size(3, 9, s), **_life(0.25, 0.7))},
            {"name": "Flash", "template": "OmnidirectionalBurst", "inputs": dict({
                INIT + "Color": colour(el, 2.0), "EmitterUpdate/SpawnBurst_Instantaneous/Spawn Count": 4,
                "ParticleSpawn/ShapeLocation/Sphere Radius": 2, "ParticleUpdate/Drag/Drag": 50}, **_size(90, 150, s), **_life(0.08, 0.16), **zero_g)},
        ]
    if r == "muzzle":
        return [
            {"name": "Sparks", "template": "DirectionalBurst", "inputs": dict({
                INIT + "Color": colour(el, 1.5), "EmitterUpdate/SpawnBurst_Instantaneous/Spawn Count": int(25 * s),
                "ParticleSpawn/AddVelocity/Cone Angle": 12}, **_life(0.04, 0.1))},
            {"name": "Flash", "template": "OmnidirectionalBurst", "inputs": dict({
                INIT + "Color": colour(el, 2.5), "EmitterUpdate/SpawnBurst_Instantaneous/Spawn Count": 2,
                "ParticleSpawn/ShapeLocation/Sphere Radius": 1, "ParticleUpdate/Drag/Drag": 50}, **_size(25, 40, s), **_life(0.03, 0.06), **zero_g)},
        ]
    if r == "area":
        rad = float(fx.get("radius", 300))
        return [
            {"name": "Burst", "template": "OmnidirectionalBurst", "inputs": dict({
                INIT + "Color": colour(el, 1.2), "EmitterUpdate/SpawnBurst_Instantaneous/Spawn Count": int(min(60 + rad * 0.5, 400)),
                "ParticleSpawn/ShapeLocation/Sphere Radius": rad * 0.8, "ParticleUpdate/Drag/Drag": 2,
                # a flat disc on the ground, not a sphere half under it (measured: z -224 for a 400 cm nova at 150 cm)
                "ParticleSpawn/ShapeLocation/Non Uniform Scale": {"x": 1, "y": 1, "z": 0.2}}, **_size(6, 16, s), **_life(0.5, 1.0), **zero_g)},
            {"name": "Flash", "template": "OmnidirectionalBurst", "inputs": dict({
                INIT + "Color": colour(el, 1.5), "EmitterUpdate/SpawnBurst_Instantaneous/Spawn Count": 6,
                "ParticleSpawn/ShapeLocation/Sphere Radius": rad * 0.3, "ParticleUpdate/Drag/Drag": 50}, **_size(rad * 0.5, rad * 0.8, 1.0), **_life(0.1, 0.2), **zero_g)},
        ]
    if r == "aura":
        # Fountain loops forever; a cast/buff effect is spawned unattached and only cleans up when it completes, so the aura
        # plays ONCE for "duration" seconds (EmitterState Loop Behavior = Once, the value the burst templates carry).
        return [
            {"name": "Motes", "template": "Fountain", "switches": {"EmitterUpdate/EmitterState/Loop Behavior": ONCE},
             "inputs": dict({"EmitterUpdate/EmitterState/Loop Duration": float(fx.get("duration", 1.5)),
                INIT + "Color": colour(el, 1.0), "EmitterUpdate/SpawnRate/SpawnRate": int(40 * s),
                "ParticleSpawn/ShapeLocation/Sphere Radius": 40 * s, "ParticleSpawn/AddVelocity/Cone Angle": 10,
                "ParticleUpdate/GravityForce/Gravity": {"x": 0, "y": 0, "z": 60}}, **_size(3, 6, s), **_life(0.8, 1.3))},
        ]
    raise ValueError("fx recipe %r: use projectile, impact, muzzle, area, aura, tracer, lightning or give 'layers'" % r)


def fx_calls(root, fx_specs):
    """-> (phase list, {system name: asset path})."""
    out, paths = [], {}
    for name, fx in sorted(fx_specs.items()):
        if not name.replace("_", "").isalnum():
            raise ValueError("fx %r: plain asset names only" % name)
        layers = recipe_layers(fx)
        pkg, epkg = root + "/FX", root + "/FX/Emitters"
        calls, emitters = [], []
        for l in layers:
            en = "NE_%s_%s" % (name[3:] if name.startswith("NS_") else name, l["name"])
            t = l["template"] if l["template"].startswith("/") else TEMPLATES + l["template"]
            calls.append(["niagara.create_emitter", {"name": en, "packagePath": epkg, "templatePath": t, "onConflict": "skip"}])
            emitters.append(en)
        sp = "%s/%s" % (pkg, name)
        calls.append(["niagara.create_system_from_spec", {"name": name, "packagePath": pkg, "onConflict": "skip",
                                                          "emitters": [{"path": "%s/%s" % (epkg, e)} for e in emitters]}])
        user_vars = {}
        for l in layers:
            user_vars.update(l.get("user_vars", {}))
        if user_vars:
            # Niagara toolset (engine plugin NiagaraToolsets must be enabled): bare names, no "User." prefix; re-adding replaces
            calls.append(["niagara.epic_add_user_variables", {"system": {"refPath": "%s.%s" % (sp, name)}, "variablesToAdd": [
                {"name": n, "type": {"classStructOrEnum": t}, "defaultValue": {"struct": t, "value": {"x": 0, "y": 0, "z": 0}}}
                for n, t in sorted(user_vars.items())]}])
        for en, l in zip(emitters, layers):
            for key, expr in sorted(l.get("expressions", {}).items()):
                stack, module, inp = key.split("/", 2)
                calls.append(["niagara.epic_set_stack_input_data", {"stackInputRef": {
                    "system": {"refPath": "%s.%s" % (sp, name)}, "emitterName": en, "scriptName": SCRIPTS[stack], "moduleName": module,
                    "rendererIndex": -1, "inputNameStack": [inp]},
                    "inputData": {"struct": "/Script/NiagaraEditor.NiagaraExt_StackInputData_HlslExpression",
                                  "value": {"hlslExpression": expr}}}])
            for stack, script in l.get("add_modules", []):
                # add_module is NOT idempotent (a re-run gave SpawnPerFrame + SpawnPerFrame001, two spawners): remove the
                # module by name first; remove_module on a missing module succeeds with alreadyRemoved.
                calls.append(["niagara.remove_module", {"systemPath": sp, "emitterName": en, "stackContext": stack,
                                                        "moduleName": script.rsplit("/", 1)[-1].split(".")[0]}])
                calls.append(["niagara.add_module", {"systemPath": sp, "emitterName": en, "stackContext": stack, "moduleScript": script}])
            for key, value in sorted(l.get("switches", {}).items()):
                stack, module, sw = key.split("/", 2)
                calls.append(["niagara.set_static_switch", {"systemPath": sp, "emitterName": en, "stackContext": stack,
                                                            "moduleName": module, "switchName": sw, "value": value}])
            for key, value in sorted(l.get("inputs", {}).items()):
                stack, module, inp = key.split("/", 2)
                calls.append(["niagara.set_module_input", {"systemPath": sp, "emitterName": en, "stackContext": stack,
                                                           "moduleName": module, "inputName": inp, "value": value}])
        calls.append(["niagara.compile", {"systemPath": sp}])
        # set_module_input/add_module/set_static_switch leave the system DIRTY, not saved: without this the edits live only
        # in the editor's memory and a restart loses them (found 2026-11-18: six systems sat in a "Save Content" prompt).
        calls.append(["asset.save", {"assetPaths": [sp] + ["%s/%s" % (epkg, e) for e in emitters]}])
        calls.append(["niagara.validate", {"systemPath": sp}])
        out.append({"name": "fx " + name, "calls": calls})
        paths[name] = sp
    return out, paths


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.spec) as f:
        spec = json.load(f)
    phases, paths = fx_calls(spec["content_root"].rstrip("/"), spec.get("fx", {}))
    with open(a.out, "w") as f:
        json.dump({"phases": phases}, f, indent=1)
    print("%s: %d systems, %d calls" % (a.out, len(paths), sum(len(p["calls"]) for p in phases)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
