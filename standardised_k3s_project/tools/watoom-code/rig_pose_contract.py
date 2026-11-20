"""Pure schema for the fixed Shadowheart MHX adapter; no executable fields."""

import math

CONTROLS = {"hips", "head", "spine", "chest"} | {
    x + "." + s
    for x in ["hand_ik", "foot_ik", "elbow", "knee", "upper_arm.fk", "forearm.fk", "thigh.fk", "shin.fk"]
    for s in ["L", "R"]
}
ENDPOINTS = {x + "." + s for x in ["hand", "foot"] for s in ["L", "R"]}
SWITCHES = {x + "." + s for x in ["arm", "leg"] for s in ["L", "R"]}


def vector(v, size=3):
    if (
        not isinstance(v, list)
        or len(v) != size
        or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 10000 for x in v)
    ):
        raise ValueError("Finite rig vector required")


def validate(plan):
    if (
        set(plan) - {"schema", "adapter", "armature", "frame", "controls", "targets", "switches", "tolerance"}
        or plan.get("schema") != "watoom.rig_pose.v1"
        or plan.get("adapter") != "shadowheart-mhx-v1"
        or plan.get("armature") != "Shadowheart"
    ):
        raise ValueError("Unsupported fixed rig adapter/schema")
    controls = plan.get("controls", {})
    targets = plan.get("targets", {})
    switches = plan.get("switches", {})
    if (
        not all(isinstance(x, dict) for x in [controls, targets, switches])
        or set(controls) - CONTROLS
        or set(targets) - ENDPOINTS
        or set(switches) - SWITCHES
        or not (controls or targets or switches)
    ):
        raise ValueError("Unsupported/empty rig edits")
    tolerance = plan.get("tolerance", 0.02)
    if type(tolerance) not in (float, int) or not 0.001 <= tolerance <= 0.03:
        raise ValueError("Endpoint tolerance budget")
    for role, edit in controls.items():
        if not isinstance(edit, dict) or not edit or set(edit) - {"world_position", "rotation_euler"}:
            raise ValueError("Unsupported rig channels")
        if "world_position" in edit and role not in {"hips", "elbow.L", "elbow.R", "knee.L", "knee.R"}:
            raise ValueError("Use endpoint targets for hand/foot placement")
        if "rotation_euler" in edit and role.startswith(("knee.", "elbow.")):
            raise ValueError("Pole rotation is locked")
        for key, v in edit.items():
            vector(v)
            if key == "rotation_euler" and any(abs(x) > math.pi for x in v):
                raise ValueError("Rotation budget")
    for role, v in targets.items():
        vector(v)
        kind = ("arm" if role.startswith("hand") else "leg") + role[-2:]
        if switches.get(kind, "IK") != "IK":
            raise ValueError("Endpoint target conflicts with FK mode")
    for role, val in switches.items():
        if val not in ("IK", "FK"):
            raise ValueError("IK/FK mode required")
    for role in controls:
        if role.startswith(("hand_ik.", "foot_ik.")):
            kind = ("arm" if role.startswith("hand") else "leg") + role[-2:]
            if switches.get(kind, "IK") != "IK":
                raise ValueError("IK handle conflicts with FK mode")
        if ".fk." in role:
            kind = ("arm" if role.startswith(("upper_arm", "forearm")) else "leg") + role[-2:]
            if kind not in switches or switches[kind] != "FK":
                raise ValueError("FK controls require explicit FK switch")
            if ("hand" if kind.startswith("arm") else "foot") + role[-2:] in targets:
                raise ValueError("Conflicting limb routes")
