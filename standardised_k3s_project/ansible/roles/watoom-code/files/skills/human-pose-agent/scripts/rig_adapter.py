"""Fixed, fingerprinted MHX control adapter. Run only in the admitted Blender worker."""

import json, math, pathlib, hashlib
import bpy
from mathutils import Vector, Euler

PROFILE = pathlib.Path(__file__).resolve().parent.parent / "references/adapters/shadowheart-mhx-v1.json"
FIELDS = [
    "target",
    "subtarget",
    "pole_target",
    "pole_subtarget",
    "chain_count",
    "pole_angle",
    "owner_space",
    "target_space",
    "use_limit_x",
    "use_limit_y",
    "use_limit_z",
    "min_x",
    "max_x",
    "min_y",
    "max_y",
    "min_z",
    "max_z",
]


def canonical(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, list):
        return [canonical(x) for x in v]
    if isinstance(v, dict):
        return {k: canonical(x) for k, x in v.items()}
    return v


def constraint(c):
    row = {"name": c.name, "type": c.type}
    for key in FIELDS:
        if hasattr(c, key):
            v = getattr(c, key)
            row[key] = v.name if hasattr(v, "name") else v
    return row


def bone_signature(b):
    return {
        "name": b.name,
        "parent": b.parent.name if b.parent else None,
        "rest": [list(row) for row in b.bone.matrix_local],
        "lock_rotation": list(b.lock_rotation),
        "lock_location": list(b.lock_location),
        "rotation_mode": b.rotation_mode,
        "constraints": [constraint(c) for c in b.constraints],
    }


def expected_signature(row):
    return {k: row[k] for k in ["name", "parent", "rest", "lock_rotation", "lock_location", "rotation_mode"]} | {
        "constraints": [{k: v for k, v in c.items() if k not in ["influence", "mute"]} for c in row["constraints"]]
    }


def driver_signature(d):
    return {
        "path": d.data_path,
        "index": d.array_index,
        "expression": d.driver.expression,
        "variables": [
            {
                "name": v.name,
                "type": v.type,
                "targets": [{"id": getattr(t.id, "name", None), "data_path": t.data_path} for t in v.targets],
            }
            for v in d.driver.variables
        ],
    }


def profile_check(rig, profile):
    errors = []
    if rig.type != "ARMATURE" or len(rig.pose.bones) != profile["bone_count"] or rig.get("MhxRig") is not True:
        errors.append("MHX rig identity/bone count mismatch")
    actual = []
    for row in profile["bones"]:
        bone = rig.pose.bones.get(row["name"])
        if bone is None:
            errors.append("Missing control " + row["name"])
            continue
        current = bone_signature(bone)
        actual.append(current)
        if canonical(current) != canonical(expected_signature(row)):
            errors.append("Control structure changed: " + row["name"])
    drivers = {(d.data_path, d.array_index): d for d in rig.animation_data.drivers} if rig.animation_data else {}
    for row in profile["drivers"]:
        d = drivers.get((row["path"], row["index"]))
        if d is None or d.mute or canonical(driver_signature(d)) != canonical(row):
            errors.append("IK/FK driver mismatch: " + row["path"])
    for prop in profile["switches"].values():
        if type(rig.get(prop)) not in (int, float):
            errors.append("Missing IK/FK property " + prop)
    fingerprint = hashlib.sha256(
        json.dumps(canonical(actual), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return errors, fingerprint


def inventory():
    profile = json.loads(PROFILE.read_text())
    rig = bpy.data.objects.get(profile["armature"])
    if rig is None:
        return {"adapter": profile["id"], "compatible": False, "errors": ["Armature missing"]}
    errors, fingerprint = profile_check(rig, profile)
    point = lambda name: list(rig.matrix_world @ rig.pose.bones[name].head)
    return {
        "adapter": profile["id"],
        "compatible": not errors,
        "errors": errors,
        "rig_fingerprint": fingerprint,
        "profile_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
        "controls": {
            role: {
                "bone": name,
                "world_position": point(name),
                "rotation_mode": rig.pose.bones[name].rotation_mode,
                "rotation_euler": list(rig.pose.bones[name].rotation_euler),
                "lock_rotation": list(rig.pose.bones[name].lock_rotation),
                "lock_location": list(rig.pose.bones[name].lock_location),
            }
            for role, name in profile["controls"].items()
            if rig.pose.bones.get(name)
        },
        "endpoints": {
            role: {**row, "world_position": point(row["bone"])} for role, row in profile["endpoints"].items()
        },
        "switches": {role: {"property": prop, "value": rig[prop]} for role, prop in profile["switches"].items()},
        "limits": "Qualified only for this fingerprint; no constraint/driver disabling, arbitrary properties, retargeting or collision/seat-contact guarantees.",
    }


def refresh(rig):
    rig.update_tag()
    bpy.context.view_layer.update()


def point(rig, bone):
    return rig.matrix_world @ rig.pose.bones[bone].head


def matrix_values(b):
    return tuple(v for row in b.matrix for v in row)


def constraint_state(rig):
    return [(b.name, c.name, c.type, c.mute) for b in rig.pose.bones for c in b.constraints]


def driver_state(rig):
    return (
        [(d.data_path, d.array_index, d.mute, d.driver.expression) for d in rig.animation_data.drivers]
        if rig.animation_data
        else []
    )


def set_position(rig, bone_name, target):
    bone = rig.pose.bones[bone_name]
    if bone.constraints or any(bone.lock_location):
        raise ValueError("Translation control is constrained/locked: " + bone_name)
    matrix = bone.matrix.copy()
    matrix.translation = rig.matrix_world.inverted() @ Vector(target)
    bone.matrix = matrix
    refresh(rig)
    bone.keyframe_insert(data_path="location", frame=bpy.context.scene.frame_current, group=bone_name)


def set_rotation(rig, name, angles):
    bone = rig.pose.bones[name]
    current = bone.rotation_quaternion.to_euler("XYZ") if bone.rotation_mode == "QUATERNION" else bone.rotation_euler
    if any(locked and abs(value - old) > 1e-6 for locked, value, old in zip(bone.lock_rotation, angles, current)):
        raise ValueError("Locked rotation axis: " + name)
    for c in bone.constraints:
        if c.type == "LIMIT_ROTATION" and not c.mute:
            if c.owner_space != "LOCAL":
                raise ValueError("Unqualified rotation limit space")
            for axis, value in zip("xyz", angles):
                if (
                    getattr(c, "use_limit_" + axis)
                    and not getattr(c, "min_" + axis) - 1e-6 <= value <= getattr(c, "max_" + axis) + 1e-6
                ):
                    raise ValueError("Rotation exceeds authored joint limit: " + name + "." + axis)
        elif c.type not in ("COPY_LOCATION", "LIMIT_ROTATION"):
            raise ValueError("Unqualified driven rotation: " + name)
    order = bone.rotation_mode if bone.rotation_mode in ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"] else "XYZ"
    if bone.rotation_mode == "QUATERNION":
        bone.rotation_quaternion = Euler(angles, order).to_quaternion()
        channel = "rotation_quaternion"
    elif bone.rotation_mode == "AXIS_ANGLE":
        raise ValueError("Axis-angle control not qualified")
    else:
        bone.rotation_euler = Euler(angles, order)
        channel = "rotation_euler"
    bone.keyframe_insert(data_path=channel, frame=bpy.context.scene.frame_current, group=name)
    refresh(rig)


def apply(plan, out):
    profile = json.loads(PROFILE.read_text())
    rig = bpy.data.objects.get(plan["armature"])
    if rig is None:
        raise ValueError("Missing adapter armature")
    frame = plan.get("frame", 1)
    scene = bpy.context.scene
    scene.frame_set(frame)
    refresh(rig)
    errors, fingerprint = profile_check(rig, profile)
    if errors:
        raise ValueError("RIG_ADAPTER_MISMATCH: " + "; ".join(errors[:4]))
    before = {b.name: matrix_values(b) for b in rig.pose.bones if b.bone.use_deform}
    constraints = constraint_state(rig)
    drivers = driver_state(rig)
    rig.animation_data_create()
    if rig.animation_data.action:
        rig.animation_data.action = rig.animation_data.action.copy()
    edits = plan.get("controls", {})
    if "head" in edits and not rig.get("MhaNeckControl"):
        raise ValueError("MHX neck control mode is disabled")
    if any(role in edits for role in ["spine", "chest"]) and (
        not rig.get("MhaSpineControl") or rig.get("MhaSpineIk") != 0
    ):
        raise ValueError("MHX FK spine control mode required")
    switches = dict(plan.get("switches", {}))
    for role in edits:
        if role.startswith(("hand_ik.", "foot_ik.")):
            switches[("arm" if role.startswith("hand") else "leg") + role[-2:]] = "IK"
    for role in plan.get("targets", {}):
        switches[profile["endpoints"][role]["switch"]] = "IK"
    # Preserve the evaluated IK/FK mode unless the plan explicitly requests a switch.
    for role, mode in switches.items():
        prop = profile["switches"][role]
        path = '["' + prop + '"]'
        if any(d.data_path == path for d in rig.animation_data.drivers):
            raise ValueError("IK/FK property is itself driven")
        rig[prop] = 1.0 if mode == "IK" else 0.0
        rig.keyframe_insert(data_path=path, frame=frame, group="Adapter IK FK")
    refresh(rig)
    edits = plan.get("controls", {})
    ordered = sorted(edits, key=lambda role: 0 if role == "hips" else 1)
    for role in ordered:
        name = profile["controls"][role]
        edit = edits[role]
        if "world_position" in edit:
            set_position(rig, name, edit["world_position"])
        if "rotation_euler" in edit:
            set_rotation(rig, name, edit["rotation_euler"])
    # Translate real IK handles by the evaluated endpoint error. Foot handle origin
    # differs from the ankle; targeting its raw origin would give wrong contacts.
    tolerance = plan.get("tolerance", 0.02)
    for _ in range(8):
        for role, target in plan.get("targets", {}).items():
            row = profile["endpoints"][role]
            delta = Vector(target) - point(rig, row["bone"])
            if delta.length > tolerance / 4:
                set_position(rig, row["control"], point(rig, row["control"]) + delta)
        refresh(rig)
    checks = {}
    for role, target in plan.get("targets", {}).items():
        actual = point(rig, profile["endpoints"][role]["bone"])
        error = (Vector(target) - actual).length
        checks[role] = {"target": target, "actual": list(actual), "error": error}
        if error > tolerance:
            raise ValueError("IK endpoint unreachable/outside tolerance: " + role + " error=" + str(error))
    keyed = {}
    for role in ordered:
        bone = rig.pose.bones[profile["controls"][role]]
        keyed[bone.name] = {
            "location": list(bone.location),
            "rotation_mode": bone.rotation_mode,
            "rotation": list(bone.rotation_quaternion if bone.rotation_mode == "QUATERNION" else bone.rotation_euler),
        }
    for role in plan.get("targets", {}):
        bone = rig.pose.bones[profile["endpoints"][role]["control"]]
        keyed[bone.name] = {
            "location": list(bone.location),
            "rotation_mode": bone.rotation_mode,
            "rotation": list(bone.rotation_quaternion if bone.rotation_mode == "QUATERNION" else bone.rotation_euler),
        }
    expected_properties = {profile["switches"][role]: 1.0 if mode == "IK" else 0.0 for role, mode in switches.items()}

    def verify(current):
        for prop, val in expected_properties.items():
            if abs(current[prop] - val) > 1e-6:
                raise ValueError("IK/FK switch overridden after frame evaluation")
        for name, expected in keyed.items():
            b = current.pose.bones[name]
            rotation = b.rotation_quaternion if expected["rotation_mode"] == "QUATERNION" else b.rotation_euler
            if (
                max(abs(a - b) for a, b in zip(b.location, expected["location"])) > 1e-5
                or max(abs(a - b) for a, b in zip(rotation, expected["rotation"])) > 1e-5
            ):
                raise ValueError("Keyed control overridden: " + name)
        for role, edit in edits.items():
            if (
                "world_position" in edit
                and (point(current, profile["controls"][role]) - Vector(edit["world_position"])).length > tolerance
            ):
                raise ValueError("World-space control changed: " + role)
        for role, target in plan.get("targets", {}).items():
            if (point(current, profile["endpoints"][role]["bone"]) - Vector(target)).length > tolerance:
                raise ValueError("Evaluated endpoint changed: " + role)
        if constraint_state(current) != constraints or driver_state(current) != drivers:
            raise ValueError("Constraint or driver state changed")
        for b in current.pose.bones:
            if not all(math.isfinite(x) for x in matrix_values(b)):
                raise ValueError("Nonfinite pose matrix")

    scene.frame_set(frame)
    refresh(rig)
    verify(rig)
    changed = sum(
        max(abs(a - b) for a, b in zip(matrix_values(rig.pose.bones[name]), values)) > 1e-5
        for name, values in before.items()
    )
    if not changed:
        raise ValueError("Adapter did not change evaluated deform bones")
    dst = out / "posed.blend"
    if dst.exists():
        raise ValueError("Refusing prepared output overwrite")
    bpy.ops.wm.save_as_mainfile(filepath=str(dst), check_existing=True)
    # Reopen the saved candidate to prove keys/switches survive reload.
    bpy.ops.wm.open_mainfile(filepath=str(dst), load_ui=False, use_scripts=False)
    bpy.context.scene.frame_set(frame)
    rig = bpy.data.objects[plan["armature"]]
    refresh(rig)
    verify(rig)
    result = {
        "status": "SAVED_UNVALIDATED_POSE",
        "adapter": profile["id"],
        "rig_fingerprint": fingerprint,
        "profile_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
        "frame": frame,
        "changed_deform_bones": changed,
        "keyed_controls": keyed,
        "switches": expected_properties,
        "endpoint_checks": checks,
        "constraints_preserved": True,
        "drivers_preserved": True,
        "saved_pose_reopened": True,
        "limitations": [
            "Actual clothing/anatomy image review required",
            "No automatic seat-contact, collision-free or biomechanical certification",
            "Only measured endpoints and mapped MHX controls; no arbitrary rig properties",
        ],
    }
    (out / "pose-validation.json").write_text(json.dumps(result, indent=2))
    return result
