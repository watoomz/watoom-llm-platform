"""Preserve an existing weighted character and derive only a missing compatible Run."""

import bpy
from creative_blender_common import load


def fcurves(action):
    # Blender 5 removed Action.fcurves; layered actions keep curves in per-slot channelbags.
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    return [fc for layer in action.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]


def slot(owner):
    # Layered actions (Blender 4.4+) animate only through an assigned slot; 4.2 has no slots.
    if getattr(owner, "action_slot", 1) is None and owner.action_suitable_slots:
        owner.action_slot = owner.action_suitable_slots[0]


def prepare(request, work):
    objects = load(request["sources"][0]["path"])
    rigs = [o for o in objects if o.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError("Select a source with one verified compatible skeleton")
    rig = rigs[0]
    rig.animation_data_create()
    actions = list(bpy.data.actions)
    named = {}
    for name in ("Idle", "Walk", "Run"):
        found = list(
            {
                strip.action
                for track in rig.animation_data.nla_tracks
                if track.name.lower() == name.lower()
                for strip in track.strips
                if strip.action
            }
        )
        if not found:
            found = [a for a in actions if a.name.split("|")[-1].lower() == name.lower()]
        if len(found) == 1:
            named[name] = found[0]
    if not {"Idle", "Walk"}.issubset(named):
        raise ValueError(
            "Source lacks compatible Idle/Walk: "
            + repr([(t.name, [s.action.name for s in t.strips if s.action]) for t in rig.animation_data.nla_tracks])
        )
    derived = []
    if "Run" not in named:
        run = named["Walk"].copy()
        run.name = "Run"
        start = float(run.frame_range[0])
        for fc in fcurves(run):
            for key in fc.keyframe_points:
                for point in (key.co, key.handle_left, key.handle_right):
                    point.x = start + (point.x - start) * 0.6
            fc.update()
        named["Run"] = run
        derived.append({"clip": "Run", "source": "Walk", "method": "retime 0.6; no new gait synthesis"})
    for track in list(rig.animation_data.nla_tracks):
        rig.animation_data.nla_tracks.remove(track)
    for name, action in named.items():
        action.name = name
        action.use_fake_user = True
        track = rig.animation_data.nla_tracks.new()
        track.name = name
        slot(track.strips.new(name, int(action.frame_range[0]), action))
    rig.animation_data.action = named["Idle"]
    slot(rig.animation_data)
    meshes = [o for o in objects if o.type == "MESH"]
    if not any(any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers) and o.vertex_groups for o in meshes):
        raise ValueError("Source lacks weighted mesh bound to selected skeleton")
    return {
        "character": {
            "rig": "reused existing skeleton and vertex weights",
            "source_clips": [a.name for a in actions],
            "required_clips": list(named),
            "derived": derived,
            "bones": len(rig.data.bones),
        }
    }
