#!/usr/bin/env python3
"""WatooM Human Pose Asset Inspector and Safe Pose Executor.

Run inside Blender:
  blender -b CHARACTER.blend --python human_pose_agent.py -- --report /path/report.json

Optional calibrated pose:
  --recipe recipe.json --output /path/new_posed.blend

Optional automatic IK + validation:
  --auto-plan plan.json --output /path/new_posed.blend --validation-report /path/val.json

Never edits the source blend. Blender Python API + standard library only.
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import traceback
from pathlib import Path

try:
    import bpy
    from mathutils import Vector, Quaternion
except ImportError:
    raise SystemExit("BLOCKED: Run via Blender --python, not system Python")

POSES = {
    "idle_relaxed": {
        "intent": "Quiet asymmetric stance, unlocked knees, staggered weight",
        "contacts": ["both feet"],
        "pelvis": "slight lateral shift toward load-bearing foot",
        "spine": "small opposing curve, rib cage stacked over pelvis",
        "head": "level with subtle look direction",
        "arms": "unequal relaxed elbow flexion; hands near thighs",
        "legs": "one primary support leg, other relaxed",
        "checks": ["centre of mass over foot support area", "shoulders do not mirror perfectly"],
    },
    "idle_alert": {
        "intent": "Ready but not rigid",
        "contacts": ["both feet"],
        "pelvis": "neutral, slight hip-width stance",
        "spine": "tall but not hyperextended",
        "head": "eyes toward stimulus",
        "arms": "soft elbows, hands ready",
        "legs": "knees unlocked",
        "checks": ["weight centred", "hands not intersecting torso"],
    },
    "walk_contact": {
        "intent": "One heel touches down while opposite foot prepares toe-off",
        "contacts": ["forward heel", "rear forefoot"],
        "pelvis": "rotate subtly toward stepping leg",
        "spine": "small counter-rotation",
        "head": "gaze stable forward",
        "arms": "opposite arm advances with stepping leg",
        "legs": "front knee nearly extended but soft; rear hip extended",
        "checks": ["contact points actually reach ground", "contralateral arm swing"],
    },
    "walk_passing": {
        "intent": "Swinging foot passes planted foot",
        "contacts": ["one planted foot"],
        "pelvis": "translate over stance foot",
        "spine": "upright counterbalanced",
        "head": "stable",
        "arms": "moderate opposing swing",
        "legs": "stance knee soft; swing knee flexed to clear floor",
        "checks": ["support foot planted", "toe clearance", "pelvis over support"],
    },
    "run_contact": {
        "intent": "Forward lean with brief single-leg support",
        "contacts": ["one forefoot"],
        "pelvis": "supports forward drive",
        "spine": "slight forward lean from ankles/hips",
        "head": "neutral with spine",
        "arms": "elbows roughly bent, opposite arm leads",
        "legs": "support knee flexes for impact, trailing leg folds",
        "checks": ["landing foot beneath or slightly ahead of centre of mass", "no locked landing knee"],
    },
    "run_flight": {
        "intent": "Both feet airborne, compact recovery",
        "contacts": [],
        "pelvis": "forward trajectory",
        "spine": "forward lean moderate",
        "head": "looking direction of travel",
        "arms": "counter-rotate rhythmically",
        "legs": "lead knee drives forward; rear knee flexes",
        "checks": ["no planted foot", "clear silhouette between limbs"],
    },
    "sprint_drive": {
        "intent": "Explosive acceleration posture",
        "contacts": ["one forefoot"],
        "pelvis": "strong hip extension on support side",
        "spine": "forward lean across whole torso",
        "head": "aligned, not craned back",
        "arms": "strong opposing pump",
        "legs": "drive knee high, back leg extended",
        "checks": ["forward impulse readable", "no elbow hyperextension"],
    },
    "crouch": {
        "intent": "Low guarded stance with balance",
        "contacts": ["both feet"],
        "pelvis": "back and down; depth constrained by ankle range",
        "spine": "torso leans as needed to keep balance",
        "head": "gaze toward task",
        "arms": "forward reach or elbows near knees for balance",
        "legs": "hips/knees bend; knees roughly track toe direction",
        "checks": ["heels/floor support plausible", "no knee penetration into torso"],
    },
    "deep_squat": {
        "intent": "Low squat, dependent on individual mobility",
        "contacts": ["both feet"],
        "pelvis": "lower between legs",
        "spine": "allow modest forward tilt without severe collapse",
        "head": "neutral",
        "arms": "forward for counterbalance",
        "legs": "high hip/knee flexion, variable heel lift",
        "checks": ["ankle mobility considered", "no impossible heel constraint"],
    },
    "kneel_one_knee": {
        "intent": "One knee down, other foot supporting",
        "contacts": ["one knee", "opposite foot", "optional rear toe"],
        "pelvis": "roughly between supports",
        "spine": "upright or task-directed",
        "head": "toward task",
        "arms": "rest on front thigh or interact",
        "legs": "front thigh angled; rear knee grounded",
        "checks": ["knee touches surface", "foot remains stable"],
    },
    "sit_chair": {
        "intent": "Supported seated posture",
        "contacts": ["pelvis/seat", "one or both feet"],
        "pelvis": "supported by actual seat surface",
        "spine": "natural lumbar curve, modest forward/back lean",
        "head": "balanced above torso",
        "arms": "lap, armrests or task pose",
        "legs": "hips/knees roughly bent according to chair geometry",
        "checks": ["buttocks touch seat", "no thigh/seat clipping", "feet reach floor or footrest"],
    },
    "sit_ground": {
        "intent": "Seated on floor, legs forward or crossed",
        "contacts": ["pelvis/floor", "legs/feet or hands"],
        "pelvis": "rests on ground",
        "spine": "balanced over sit bones",
        "head": "neutral",
        "arms": "support behind or rest on legs",
        "legs": "comfortably folded or extended; respect mobility",
        "checks": ["pelvis ground contact", "avoid impossible hip twisting"],
    },
    "jump_takeoff": {
        "intent": "Extension after loading crouch",
        "contacts": ["toes about to leave ground"],
        "pelvis": "rises rapidly",
        "spine": "extends without arching excessively",
        "head": "follows jump",
        "arms": "swing upward",
        "legs": "hips/knees/ankles extending",
        "checks": ["arms clear head", "feet at takeoff level"],
    },
    "jump_airborne": {
        "intent": "Body off ground at apex",
        "contacts": [],
        "pelvis": "raised relative to start",
        "spine": "stable core",
        "head": "forward",
        "arms": "varies with activity; not perfectly symmetric",
        "legs": "soft knees; feet clear floor",
        "checks": ["airborne clearance", "natural momentum silhouette"],
    },
    "jump_landing": {
        "intent": "Absorb impact with flexed joints",
        "contacts": ["both feet or one foot"],
        "pelvis": "lowers over support",
        "spine": "forward incline for absorption",
        "head": "stable gaze",
        "arms": "counterbalance",
        "legs": "knees and hips flex; knees aligned with toes",
        "checks": ["no locked impact knees", "ground contact maintained"],
    },
    "lift_ground_object": {
        "intent": "Reach to object then rise using lower body",
        "contacts": ["both feet", "hands/object when grasped"],
        "pelvis": "hip hinge and knee bend",
        "spine": "avoid extreme loaded lumbar rounding",
        "head": "follow object",
        "arms": "hands contact actual grip locations",
        "legs": "stable foot base, knee flexion appropriate",
        "checks": ["hands touch object", "object mass handled plausibly", "object held close when possible"],
    },
    "carry_box": {
        "intent": "Carry two-handed object close to torso",
        "contacts": ["both or one foot depending on locomotion", "both hands/object"],
        "pelvis": "counterbalance carried mass",
        "spine": "upright with small lean",
        "head": "look past item",
        "arms": "elbows flexed; wrists align with box grips",
        "legs": "stable stance",
        "checks": ["both hands on object", "arms not inside box", "centre of mass over base"],
    },
    "reach_overhead": {
        "intent": "One or two arms reach up",
        "contacts": ["feet"],
        "pelvis": "subtle counter-shift",
        "spine": "thoracic extension and optional side bend",
        "head": "look at target",
        "arms": "scapula rotates upward; shoulder elevates; elbows soft",
        "legs": "balanced support",
        "checks": ["no shoulder dislocation appearance", "no wrist crossing head geometry"],
    },
    "push": {
        "intent": "Apply force to forward object",
        "contacts": ["feet", "hands/object"],
        "pelvis": "back leg helps drive",
        "spine": "forward lean with braced trunk",
        "head": "toward target",
        "arms": "hands planted; elbows partly flexed",
        "legs": "staggered stance",
        "checks": ["hands match contact surface", "line of action supported by feet"],
    },
    "pull": {
        "intent": "Pull object with body counterweight",
        "contacts": ["feet", "hands/object"],
        "pelvis": "moves rearward",
        "spine": "lean back moderately",
        "head": "toward object",
        "arms": "tension along hand-object line",
        "legs": "knees soft, wide stance",
        "checks": ["feet support pull", "hands maintain grip"],
    },
    "punch_guard": {
        "intent": "Balanced combat guard",
        "contacts": ["both feet"],
        "pelvis": "slightly bladed stance",
        "spine": "chin tucked, torso ready to rotate",
        "head": "eyes on opponent",
        "arms": "hands near cheeks, elbows protecting body",
        "legs": "staggered and springy",
        "checks": ["no rigid symmetrical fists", "arms clear face"],
    },
    "punch_extension": {
        "intent": "Controlled straight punch",
        "contacts": ["both feet"],
        "pelvis": "turns toward striking side",
        "spine": "torso rotation transfers force",
        "head": "focused",
        "arms": "one punch extending with nonlocked elbow, opposite hand guards",
        "legs": "grounded rotation",
        "checks": ["shoulder and hip turn coordinated", "no elbow hyperextension"],
    },
    "climb_step": {
        "intent": "Ascend a stair or obstacle",
        "contacts": ["one foot higher step", "other foot or hand support"],
        "pelvis": "shifts to lead leg",
        "spine": "leans slightly up/forward",
        "head": "find next foothold",
        "arms": "counterbalance or grasp",
        "legs": "one knee elevated, other pushes",
        "checks": ["foot on actual tread", "not penetrating step geometry"],
    },
    "fall_recovery": {
        "intent": "Off-balance recovery step",
        "contacts": ["one foot plus emerging recovery foot"],
        "pelvis": "moves toward recovering support",
        "spine": "tilt and countertwist",
        "head": "stabilize gaze",
        "arms": "out for balance, asymmetric",
        "legs": "one leg catches weight",
        "checks": ["motion direction consistent", "recovery support in reach"],
    },
    "lie_supine": {
        "intent": "Resting face-up",
        "contacts": ["back", "pelvis", "heels or calves", "head"],
        "pelvis": "supported by surface",
        "spine": "follows support without forced flatness",
        "head": "supported",
        "arms": "relaxed away from torso",
        "legs": "knees slightly soft",
        "checks": ["support contact", "limbs not clipping surface"],
    },
    "wave": {
        "intent": "Friendly one-handed wave",
        "contacts": ["feet"],
        "pelvis": "mild offset",
        "spine": "small corresponding shift",
        "head": "toward recipient",
        "arms": "one upper arm raised, elbow bent, wrist loose",
        "legs": "comfortable stance",
        "checks": ["hand visible next to head", "elbow not unnaturally twisted"],
    },
    "point": {
        "intent": "Indicate target with arm and gaze",
        "contacts": ["feet"],
        "pelvis": "slight turn",
        "spine": "turn toward target",
        "head": "eyes follow target",
        "arms": "leading hand points; opposing arm balances",
        "legs": "natural stance",
        "checks": ["finger/arm target direction consistent", "wrist aligned"],
    },
}

# Conservative name-matching only. Never treated as calibrated joint axes.
ALIASES = {
    "pelvis": ["pelvis", "hips", "hip", "c_hips", "root_pelvis", "hip_c", "root"],
    "spine": ["spine", "spine1", "spine_01", "lowerback", "abdomen", "spine_lower"],
    "chest": ["chest", "spine2", "spine_02", "spine3", "spine_03", "upperchest", "thorax", "spine_upper"],
    "neck": ["neck"],
    "head": ["head"],
    "upper_arm.L": [
        "upperarm_l", "upper_arm_l", "leftarm", "arm_l", "l_upperarm",
        "mixamorig:leftarm", "upperarm.l", "upperarm.l.", "clavicle_l",
    ],
    "upper_arm.R": [
        "upperarm_r", "upper_arm_r", "rightarm", "arm_r", "r_upperarm",
        "mixamorig:rightarm", "upperarm.r", "upperarm.r.", "clavicle_r",
    ],
    "forearm.L": [
        "lowerarm_l", "forearm_l", "leftforearm", "l_forearm",
        "mixamorig:leftforearm", "forearm.l", "forearm.l.",
    ],
    "forearm.R": [
        "lowerarm_r", "forearm_r", "rightforearm", "r_forearm",
        "mixamorig:rightforearm", "forearm.r", "forearm.r.",
    ],
    "hand.L": ["hand_l", "lefthand", "l_hand", "mixamorig:lefthand", "hand.l", "hand.l."],
    "hand.R": ["hand_r", "righthand", "r_hand", "mixamorig:righthand", "hand.r", "hand.r."],
    "thigh.L": [
        "thigh_l", "upperleg_l", "leftupleg", "leftupperleg", "l_thigh",
        "mixamorig:leftupleg", "thigh.l", "thigh.l.",
    ],
    "thigh.R": [
        "thigh_r", "upperleg_r", "rightupleg", "rightupperleg", "r_thigh",
        "mixamorig:rightupleg", "thigh.r", "thigh.r.",
    ],
    "shin.L": [
        "shin_l", "calf_l", "lowerleg_l", "leftleg", "l_calf",
        "mixamorig:leftleg", "shin.l", "shin.l.",
    ],
    "shin.R": [
        "shin_r", "calf_r", "lowerleg_r", "rightleg", "r_calf",
        "mixamorig:rightleg", "shin.r", "shin.r.",
    ],
    "foot.L": ["foot_l", "leftfoot", "l_foot", "mixamorig:leftfoot", "foot.l", "foot.l."],
    "foot.R": ["foot_r", "rightfoot", "r_foot", "mixamorig:rightfoot", "foot.r", "foot.r."],
    "toe.L": ["toe_l", "lefttoebase", "toes_l", "toe.l", "toebase.l"],
    "toe.R": ["toe_r", "righttoebase", "toes_r", "toe.r", "toebase.r"],
}

REQUIRED = [
    "pelvis", "spine", "head",
    "upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R",
    "thigh.L", "thigh.R", "shin.L", "shin.R", "foot.L", "foot.R",
]


def canonical(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def detect_map(names):
    """Name-based role candidates. Geometry / hierarchy must still be verified by the agent."""
    result, ambiguous = {}, {}
    for role, alts in ALIASES.items():
        matches = []
        for name in names:
            cn = canonical(name)
            if any(cn == canonical(a) for a in alts):
                matches.append(name)
        if len(matches) == 1:
            result[role] = matches[0]
        elif len(matches) > 1:
            ambiguous[role] = matches
    return result, ambiguous


def v3(v):
    return [round(float(c), 5) for c in v]


def bounds(mesh_objects):
    pts = []
    for o in mesh_objects:
        try:
            pts.extend([o.matrix_world @ Vector(c) for c in o.bound_box])
        except Exception:
            pass
    if not pts:
        return None
    mins = [min(v[i] for v in pts) for i in range(3)]
    maxs = [max(v[i] for v in pts) for i in range(3)]
    return {
        "world_min": v3(mins),
        "world_max": v3(maxs),
        "size": v3([maxs[i] - mins[i] for i in range(3)]),
    }


def limb_info(arm):
    out = []
    for b in arm.data.bones:
        pb = arm.pose.bones.get(b.name)
        out.append({
            "name": b.name,
            "parent": b.parent.name if b.parent else None,
            "children": [x.name for x in b.children],
            "use_deform": bool(b.use_deform),
            "rest_head_local": v3(b.head_local),
            "rest_tail_local": v3(b.tail_local),
            "length": round(float(b.length), 5),
            "rotation_mode": pb.rotation_mode if pb else None,
            "rotation_locks": list(pb.lock_rotation) if pb else None,
            "constraints": [
                {"name": c.name, "type": c.type, "mute": bool(c.mute)}
                for c in pb.constraints
            ] if pb else [],
            "custom_properties": [str(k) for k in pb.keys()] if pb else [],
        })
    return out


def inspect():
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    arm_infos = []
    for arm in arms:
        bound = [
            m for m in meshes
            if m.parent == arm
            or any(mod.type == "ARMATURE" and mod.object == arm for mod in m.modifiers)
        ]
        mapping, ambiguous = detect_map([b.name for b in arm.pose.bones])
        missing = [k for k in REQUIRED if k not in mapping]
        blockers = []
        if missing:
            blockers.append("Unmapped required humanoid controls: " + ", ".join(missing))
        if ambiguous:
            blockers.append("Ambiguous bone-name matches require explicit map")
        if any(c.type == "IK" for pb in arm.pose.bones for c in pb.constraints):
            blockers.append("IK controls found: solve IK targets and poles before FK keyframes")
        if any(
            c.type in ("COPY_ROTATION", "COPY_TRANSFORMS", "CHILD_OF")
            for pb in arm.pose.bones for c in pb.constraints
        ):
            blockers.append("Constraint-driven rig: pose driven controls, not deform bones")
        arm_infos.append({
            "object": arm.name,
            "data_name": arm.data.name,
            "world_matrix": [[round(float(c), 5) for c in r] for r in arm.matrix_world],
            "bound_meshes": [m.name for m in bound],
            "mesh_world_bounds": bounds(bound),
            "role_candidates": mapping,
            "ambiguous_roles": ambiguous,
            "missing_required_roles": missing,
            "bone_count": len(arm.data.bones),
            "bones": limb_info(arm),
            "pose_constraints_count": sum(len(b.constraints) for b in arm.pose.bones),
            "animation_action": getattr(
                getattr(arm.animation_data, "action", None), "name", None
            ),
            "readiness": (
                "NEEDS_CALIBRATION"
                if blockers or len(mapping) < len(REQUIRED)
                else "MAPPING_FOUND_AXES_UNCALIBRATED"
            ),
            "blockers": blockers,
        })
    return {
        "schema": "watoom.human_pose_asset.v1",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "blend_file": bpy.data.filepath or None,
        "blender_version": bpy.app.version_string,
        "scene": {
            "frame": bpy.context.scene.frame_current,
            "fps": bpy.context.scene.render.fps,
            "unit_scale": bpy.context.scene.unit_settings.scale_length,
        },
        "objects": [
            {"name": o.name, "type": o.type, "parent": o.parent.name if o.parent else None}
            for o in bpy.data.objects
        ],
        "meshes": [
            {
                "name": m.name,
                "vertex_count": len(m.data.vertices),
                "materials": [s.name for s in m.material_slots if s.material],
                "shape_keys": (
                    [k.name for k in m.data.shape_keys.key_blocks]
                    if m.data.shape_keys else []
                ),
                "armature_modifiers": [
                    mod.object.name if mod.object else None
                    for mod in m.modifiers if mod.type == "ARMATURE"
                ],
                "vertex_groups": [g.name for g in m.vertex_groups],
            }
            for m in meshes
        ],
        "armatures": arm_infos,
        "pose_catalog": POSES,
        "agent_instructions": [
            "Choose actual armature and linked skinned meshes from this report; do not assume the selected object is the character.",
            "Check role_candidates against rest heads, tails, hierarchy, mesh and left/right convention; these are name matches only.",
            "Identify rig forward/up axes and confirm local joint axes from a controlled non-destructive calibration; never infer them from bone names.",
            "Inspect IK/FK switches, targets, pole vectors, twist bones, constraints and driven properties. For constrained rigs pose only correct animator controls.",
            "Plan limb endpoints and contacts in world space; solve pelvis/feet/hands using IK or validated FK, with ground/seat/prop geometry.",
            "Place centre of mass projection in polygon of support for static poses, account for inertia in dynamic poses.",
            "Match ground to actual collision geometry, not a presumed world Z=0 for rotated/imported assets.",
            "Avoid knee/elbow hyperextension, reversed bending, mesh penetrations, foot sliding and dead-symmetry.",
            "Use calibrated bone local channels only with an approved recipe. Export to a new file, never overwrite source.",
            "Evaluate posed world-space joint locations, mesh silhouette and render from front, side and three-quarter views before approval.",
        ],
    }


def atomic_json(path, data):
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        raise RuntimeError("Refusing overwrite of existing report: " + str(p))
    tmp = p.with_name(p.name + ".tmp-" + str(os.getpid()))
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()


def apply_recipe(report, recipe_path, output):
    """Only exact calibrated LOCAL transforms. The agent must supply per-bone pose keys."""
    recipe = json.loads(Path(recipe_path).read_text(encoding="utf-8"))
    if recipe.get("schema") != "watoom.human_pose_recipe.v1":
        raise ValueError("Recipe schema mismatch")
    if not recipe.get("calibration_verified") or not recipe.get("human_reviewed"):
        raise ValueError("BLOCKED: calibration_verified and human_reviewed must both be true")
    arm = bpy.data.objects.get(recipe.get("armature", ""))
    if not arm or arm.type != "ARMATURE":
        raise ValueError("Specified armature not found")
    frame = int(recipe.get("frame", 1))
    poses = recipe.get("poses", {})
    if not poses:
        raise ValueError("No bone pose channels in recipe")
    if not Path(output).is_absolute():
        raise ValueError("Output path must be absolute")
    source = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    dst = Path(output).resolve()
    if dst.exists() or (source and source == dst):
        raise ValueError("Refusing output overwrite or source modification")
    if not dst.parent.is_dir():
        raise ValueError("Output directory must exist")

    # Preflight all channels before changing the scene
    for name, channels in poses.items():
        pb = arm.pose.bones.get(name)
        if not pb:
            raise ValueError("Missing recipe bone: " + name)
        if pb.constraints and not channels.get("allow_constrained", False):
            raise ValueError("Constrained bone requires explicit allow_constrained: " + name)
        if "rotation_quaternion" in channels:
            q = channels["rotation_quaternion"]
            if len(q) != 4 or not all(math.isfinite(float(v)) for v in q):
                raise ValueError("Invalid quaternion: " + name)
            if sum(float(x) * float(x) for x in q) < 0.000001:
                raise ValueError("Zero quaternion: " + name)
        if "location" in channels and (
            len(channels["location"]) != 3
            or not all(math.isfinite(float(x)) for x in channels["location"])
        ):
            raise ValueError("Invalid location: " + name)
        if "rotation_quaternion" not in channels and "location" not in channels:
            raise ValueError("Missing channels: " + name)

    bpy.context.scene.frame_set(frame)
    for name, channels in poses.items():
        pb = arm.pose.bones[name]
        if "rotation_quaternion" in channels:
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = Quaternion(
                tuple(float(x) for x in channels["rotation_quaternion"])
            ).normalized()
            pb.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=name)
        if "location" in channels:
            pb.location = Vector(tuple(float(x) for x in channels["location"]))
            pb.keyframe_insert(data_path="location", frame=frame, group=name)
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(dst), check_existing=True)
    return {
        "status": "SAVED_UNVALIDATED_POSE",
        "output": str(dst),
        "bones_keyed": list(poses),
        "frame": frame,
        "limitations": [
            "No automatic collision checks",
            "No camera/render validation",
            "No guarantee physically correct pose; agent must review",
        ],
    }


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Fresh JSON report filename; no overwrite")
    parser.add_argument("--recipe", help="Calibrated JSON channels (optional; explicit opt-in)")
    parser.add_argument("--output", help="New .blend output; required with --recipe or --auto-plan")
    parser.add_argument("--auto-plan", help="World-space endpoint targets JSON for automatic IK")
    parser.add_argument("--validation-report", help="New validation JSON path for automatic IK")
    args = parser.parse_args(argv)

    if args.recipe and args.auto_plan:
        parser.error("--recipe and --auto-plan are mutually exclusive")
    if bool(args.output) != bool(args.recipe or args.auto_plan):
        parser.error("--output requires --recipe or --auto-plan")
    if args.auto_plan and not args.validation_report:
        parser.error("--auto-plan requires --validation-report")

    report = inspect()
    atomic_json(args.report, report)
    print(
        "INSPECTION=PASS",
        "REPORT=" + str(Path(args.report).resolve()),
        "ARMATURES=" + str(len(report["armatures"])),
    )
    for a in report["armatures"]:
        print(
            "ARMATURE=" + a["object"],
            "MAPPED=" + str(len(a["role_candidates"])),
            "STATUS=" + a["readiness"],
        )

    if args.auto_plan:
        # Prefer same-directory import; fall back to script directory
        script_dir = Path(__file__).resolve().parent
        if str(script_dir) not in sys.path:
            sys.path.insert(0, str(script_dir))
        from auto_ik_validation import apply_auto_plan
        result = apply_auto_plan(report, args.auto_plan, args.output, args.validation_report)
        print(json.dumps(result, indent=2))
        if result["status"] == "FAIL":
            sys.exit(3)
    elif args.recipe:
        result = apply_recipe(report, args.recipe, args.output)
        print(json.dumps(result, indent=2))
    else:
        print("POSE_APPLICATION=NOT_REQUESTED; inspection is read-only for asset")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("RESULT=FAIL", repr(exc))
        traceback.print_exc()
        sys.exit(2)
