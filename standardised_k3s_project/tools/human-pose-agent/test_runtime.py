import bpy, sys, json, math, hashlib
from pathlib import Path
from mathutils import Vector, Matrix, Quaternion
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--scripts", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
ROOT = Path(args.output)
ROOT.mkdir(parents=True, exist_ok=False)
(ROOT / "test-output").mkdir()
sys.path.insert(0, args.scripts)
import human_pose_agent as agent
import auto_ik_validation as ik

RESULTS = []


def test(name, fn):
    try:
        fn()
        RESULTS.append({"test": name, "status": "PASS"})
    except Exception as e:
        RESULTS.append({"test": name, "status": "FAIL", "error": repr(e)})
    print(json.dumps(RESULTS[-1]), flush=True)


def rig(disconnected=False, rotated=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    data = bpy.data.armatures.new("Rig")
    arm = bpy.data.objects.new("Rig", data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    previous = None
    for i, name in enumerate(["upper_arm.L", "forearm.L", "hand.L"]):
        b = data.edit_bones.new(name)
        b.head = (i * 0.7, i * 0.2, 1 + i * 0.1)
        b.tail = ((i + 1) * 0.7, (i + 1) * 0.2, 1 + (i + 1) * 0.1)
        b.roll = 0.23 * (i + 1)
        if previous:
            b.parent = previous
            b.use_connect = not disconnected
        if disconnected and i == 1:
            b.head.x += 0.3
        previous = b
    bpy.ops.object.mode_set(mode="OBJECT")
    if rotated:
        arm.rotation_euler = (0.2, -0.15, 0.3)
    bpy.context.view_layer.update()
    roles = {n: n for n in ["upper_arm.L", "forearm.L", "hand.L"]}
    return arm, roles


NAMES = ["upper_arm.L", "forearm.L", "hand.L"]


def disconnected():
    arm, _ = rig(True)
    assert not ik.chain_is_usable(arm, NAMES)[0]


def transformed():
    arm, _ = rig(rotated=True)
    target = ik.world_point(arm, NAMES[-1], True) + Vector((-0.3, 0.15, 0.1))
    result = ik.ccd(arm, NAMES, target, iterations=200, tolerance=0.03)
    assert result["status"] == "PASS", result
    assert (ik.world_point(arm, NAMES[-1], True) - target).length <= 0.03
    q = Quaternion((1, 0, 0, 0))
    result = ik.orient_end_effector(arm, NAMES[-1], q, 0.03)
    assert result["status"] == "PASS", result


def constraints():
    arm, _ = rig()
    arm.pose.bones[NAMES[1]].constraints.new("COPY_ROTATION")
    before = [b.matrix_basis.copy() for b in arm.pose.bones]
    assert not ik.chain_is_usable(arm, NAMES)[0]
    assert before == [b.matrix_basis for b in arm.pose.bones]


def limits():
    arm, roles = rig()
    assert ik.check_joint_limits(arm, roles, {})["status"] == "NOT TESTED"
    try:
        ik.check_joint_limits(arm, roles, {"joint_limits": {NAMES[0]: {"x": [1]}}})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid limits accepted")
    arm.pose.bones[NAMES[0]].rotation_mode = "XYZ"
    arm.pose.bones[NAMES[0]].rotation_euler.x = 0.8
    bpy.context.view_layer.update()
    assert ik.check_joint_limits(arm, roles, {"joint_limits": {NAMES[0]: {"x": [-0.1, 0.1]}}})["status"] == "FAIL"


def missing_contacts():
    arm, roles = rig()
    end = ik.world_point(arm, NAMES[-1], True)
    v = ik.validate(arm, roles, {"hand.L": {"point": list(end)}}, {"check_mesh_collisions": False})
    assert v["status"] == "WARN" and v["support_balance"]["status"] == "NOT TESTED", v


def mesh(arm, name, vertices, faces, offset=None, attached=True):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    o = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(o)
    if attached:
        o.modifiers.new("Armature", "ARMATURE").object = arm
    if offset:
        o.location = offset
    bpy.context.view_layer.update()
    return o


def self_collision():
    arm, _ = rig()
    mesh(
        arm,
        "Crossing",
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0.25, 0.25, -1), (0.25, 0.25, 1), (0.75, 0.25, 0)],
        [(0, 1, 2), (3, 4, 5)],
    )
    result = ik.mesh_intersections(arm, {})
    assert any(x["classification"] == "self_mesh" for x in result["intersections"]), result
    arm, _ = rig()
    mesh(arm, "Adjacent", [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)], [(0, 1, 2), (1, 3, 2)])
    assert not ik.mesh_intersections(arm, {})["intersections"]


def environment():
    arm, roles = rig()
    mesh(arm, "Body", [(0, 0, -1), (0, 0, 1), (1, 0, 0)], [(0, 1, 2)], offset=(3, 0, 0))
    mesh(arm, "Ground", [(2, -2, 0), (5, -2, 0), (3, 2, 0)], [(0, 1, 2)], attached=False)
    result = ik.validate(arm, roles, {}, {})
    assert result["status"] == "FAIL" and "Character-environment mesh intersection" in result["failures"], result
    assert ik.mesh_intersections(arm, {})["intersections"]


def failure_and_save():
    arm, roles = rig()
    folder = ROOT / "test-output"
    folder.mkdir(exist_ok=True)
    source = folder / "source.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(source))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    report = {"armatures": [{"object": "Rig", "role_candidates": roles}]}
    plan = {
        "schema": "watoom.human_pose_auto_plan.v1",
        "armature": "Rig",
        "targets": {"hand.L": {"point": [100, 100, 100]}},
        "settings": {"check_mesh_collisions": False},
    }
    p = folder / "unreachable.json"
    p.write_text(json.dumps(plan))
    output = folder / "must-not-exist.blend"
    result = ik.apply_auto_plan(report, p, output, folder / "failure.json")
    assert result["status"] == "FAIL" and not output.exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    end = ik.world_point(arm, NAMES[-1], True) + Vector((-0.3, 0.1, 0.1))
    plan["targets"]["hand.L"]["point"] = list(end)
    p = folder / "reachable.json"
    p.write_text(json.dumps(plan))
    output = folder / "posed.blend"
    result = ik.apply_auto_plan(report, p, output, folder / "success.json")
    assert result["status"] == "WARN" and output.exists(), result
    bpy.ops.wm.open_mainfile(filepath=str(output))
    bpy.context.scene.frame_set(1)
    arm = bpy.data.objects["Rig"]
    assert (ik.world_point(arm, NAMES[-1], True) - end).length <= 0.03
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    inspection = agent.inspect()
    assert len(inspection["armatures"]) == 1


for name, fn in [
    ("disconnected_chain", disconnected),
    ("rest_roll_world_transform_endpoint_orientation", transformed),
    ("constrained_rig_blocked", constraints),
    ("missing_invalid_exceeded_limits", limits),
    ("missing_ground_balance_warn", missing_contacts),
    ("same_mesh_crossing_adjacent_exclusion", self_collision),
    ("evaluated_world_environment_collision", environment),
    ("failure_no_save_source_hash_and_reloaded_pose", failure_and_save),
]:
    test(name, fn)
(ROOT / "test-output/acceptance.json").write_text(json.dumps(RESULTS, indent=2))
if any(x["status"] != "PASS" for x in RESULTS):
    raise SystemExit(1)
