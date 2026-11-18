"""Asset-aware Blender IK and geometric validation extension.

Uses bpy only; executes on an already loaded .blend. All coordinates supplied in the
plan are world-space metres-equivalent Blender units. Does not touch original file.

This is a bounded CCD solver for unconstrained humanoid FK chains, not a general
physics engine, collision-free motion planner or optimizer for arbitrary control rigs.
"""
import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector, Quaternion

CHAINS = {
    'hand.L': ('upper_arm.L', 'forearm.L', 'hand.L'),
    'hand.R': ('upper_arm.R', 'forearm.R', 'hand.R'),
    'foot.L': ('thigh.L', 'shin.L', 'foot.L'),
    'foot.R': ('thigh.R', 'shin.R', 'foot.R'),
}
# Approximate adult body-segment mass fractions (sum ≈ 1.0 over mapped roles).
# Not biomechanically certified; used only for coarse static COM projection.
MASS = {
    'pelvis': 0.16, 'spine': 0.19, 'chest': 0.19,
    'head': 0.08,
    'thigh.L': 0.10, 'thigh.R': 0.10,
    'shin.L': 0.045, 'shin.R': 0.045,
    'upper_arm.L': 0.02, 'upper_arm.R': 0.02,
    'forearm.L': 0.015, 'forearm.R': 0.015,
}


def xyz(seq):
    if not isinstance(seq, (list, tuple)) or len(seq) != 3:
        raise ValueError('Expected three world-space coordinates')
    v = Vector(tuple(float(x) for x in seq))
    if not all(math.isfinite(x) for x in v):
        raise ValueError('Nonfinite coordinates')
    return v


def world_point(arm, bone, tail=False):
    pb = arm.pose.bones[bone]
    return arm.matrix_world @ (pb.tail if tail else pb.head)


def chain_is_usable(arm, names):
    bones = [arm.pose.bones.get(n) for n in names]
    if any(b is None for b in bones):
        return False, 'Missing one or more chain bones'
    for i in range(1, len(bones)):
        if bones[i].parent != bones[i - 1]:
            return False, 'Chain does not have direct parent-child hierarchy'
    for pb in bones:
        if pb.constraints:
            return False, 'Existing rig constraints must be resolved by a rig-specific adapter'
        if pb.bone.use_connect is False and pb != bones[0]:
            if (pb.head - pb.parent.tail).length > max(0.005, pb.length * 0.08):
                return False, 'Disconnected chain geometry'
        if any(pb.lock_rotation):
            return False, 'Locked joint rotation'
    return True, ''


def _set_world_rotation(arm, pb, quat_world):
    """Apply a world rotation delta through Blender's rest-pose-aware matrix API.

    Blender Bone.convert_local_to_pose is required: parent pose inverse alone
    omits the child's rest orientation and inherit-scale/local-location rules.
    """
    current_world = (arm.matrix_world @ pb.matrix).to_quaternion()
    desired_world = (quat_world @ current_world).normalized()
    target_world = desired_world.to_matrix().to_4x4()
    target_world.translation = (arm.matrix_world @ pb.matrix).translation
    target_pose = arm.matrix_world.inverted_safe() @ target_world
    # Blender's pose matrix setter resolves the bone rest transform and parent
    # relationships. Read-back validation is performed after view-layer update.
    pb.rotation_mode = 'QUATERNION'
    pb.matrix = target_pose
    bpy.context.view_layer.update()


def _orientation_error(arm, name, quaternion):
    current = (arm.matrix_world @ arm.pose.bones[name].matrix).to_quaternion()
    return current.rotation_difference(quaternion).angle


def orient_end_effector(arm, name, quaternion, tolerance=0.12):
    pb = arm.pose.bones[name]
    if pb.constraints or any(pb.lock_rotation):
        return {'status': 'BLOCKED', 'reason': 'End-effector constraints or locked rotation'}
    if len(quaternion) != 4 or not all(math.isfinite(float(x)) for x in quaternion):
        raise ValueError('orientation quaternion must contain four finite values [w,x,y,z]')
    target = Quaternion(tuple(float(x) for x in quaternion)).normalized()
    current = (arm.matrix_world @ pb.matrix).to_quaternion()
    _set_world_rotation(arm, pb, target @ current.inverted())
    error = _orientation_error(arm, name, target)
    return {'status': 'PASS' if error <= tolerance else 'FAIL', 'error_rad': round(error, 6)}


def check_joint_limits(arm, roles, settings):
    """Explicit user/rig-calibrated Euler limits, never guessed from bone names."""
    limits = settings.get('joint_limits', {})
    errors = []
    skipped = []
    for role, name in roles.items():
        pb = arm.pose.bones.get(name)
        if pb is None:
            continue
        spec = limits.get(role)
        if spec is None:
            skipped.append(role)
            continue
        # These limits are bone-local XYZ Euler radians, derived from the
        # pose basis quaternion. They must be calibrated to each rig.
        e = pb.matrix_basis.to_quaternion().to_euler('XYZ')
        for axis, value in zip('xyz', e):
            rng = spec.get(axis)
            if rng is None:
                continue
            if len(rng) != 2 or not all(math.isfinite(float(v)) for v in rng):
                raise ValueError('Invalid joint limit for ' + role + '.' + axis)
            if value < float(rng[0]) - 1e-4 or value > float(rng[1]) + 1e-4:
                errors.append({'role': role, 'axis': axis, 'radians': round(value, 5)})
    return {'status': 'FAIL' if errors else ('NOT TESTED' if skipped else 'PASS'),
            'violations': errors, 'unbounded_roles': skipped}


def ccd(arm, names, target, pole=None, iterations=70, tolerance=0.025,
        max_step=0.18, pole_step=0.07):
    """CCD reaches an endpoint at the distal bone TAIL; pole biases middle joint.

    No joint limits are inferred from names. Rigs that need limits must supply
    them via a separate adapter or accept UNVERIFIED status.
    """
    ok, reason = chain_is_usable(arm, names)
    if not ok:
        return {'status': 'BLOCKED', 'reason': reason}
    root = world_point(arm, names[0])
    reach = sum(arm.pose.bones[n].length for n in names)
    dist = (target - root).length
    if dist > reach * 1.02:
        return {
            'status': 'BLOCKED',
            'reason': 'Target outside maximum limb reach',
            'distance': round(dist, 5),
            'reach': round(reach, 5),
        }

    best_error = float('inf')
    best_state = None

    for it in range(iterations):
        end = world_point(arm, names[-1], tail=True)
        err = (end - target).length
        if err < best_error:
            best_error = err
            best_state = {
                n: arm.pose.bones[n].matrix_basis.copy()
                for n in names[:-1]
            }
        if err <= tolerance:
            break

        # Distal-to-proximal joint updates
        for name in reversed(names[:-1]):
            base = world_point(arm, name)
            curr = world_point(arm, names[-1], tail=True) - base
            desired = target - base
            if curr.length < 1e-8 or desired.length < 1e-8:
                continue
            q = curr.rotation_difference(desired)
            axis, angle = q.to_axis_angle()
            # Damped step prevents oscillation on near-singular configurations
            step = min(abs(angle), max_step)
            if step < 1e-6:
                continue
            q = Quaternion(axis, math.copysign(step, angle))
            _set_world_rotation(arm, arm.pose.bones[name], q)

        # Optional pole bias (keeps elbow/knee on the preferred side of the plane)
        if pole is not None and len(names) >= 3:
            a = world_point(arm, names[0])
            b = world_point(arm, names[1])
            c = world_point(arm, names[-1], tail=True)
            axis = c - a
            if axis.length > 1e-7:
                axis.normalize()
                v = b - a
                w = pole - a
                v = v - axis * v.dot(axis)
                w = w - axis * w.dot(axis)
                if v.length > 1e-6 and w.length > 1e-6:
                    theta = math.atan2(axis.dot(v.cross(w)), v.dot(w))
                    theta = max(-pole_step, min(pole_step, theta))
                    if abs(theta) > 1e-5:
                        _set_world_rotation(
                            arm, arm.pose.bones[names[0]], Quaternion(axis, theta)
                        )

    # Restore best configuration if the final iterate drifted
    final_err = (world_point(arm, names[-1], tail=True) - target).length
    if best_state is not None and best_error + 1e-6 < final_err:
        for n, q in best_state.items():
            pb = arm.pose.bones[n]
            pb.matrix_basis = q
        bpy.context.view_layer.update()
        final_err = best_error

    endpoint = [round(x, 5) for x in world_point(arm, names[-1], tail=True)]
    return {
        'status': 'PASS' if final_err <= tolerance else 'FAIL',
        'error': round(final_err, 6),
        'tolerance': tolerance,
        'endpoint': endpoint,
        'iterations_used': it + 1,
    }


def _point_seg_distance(a, b, c, d):
    # Closest distance between two 3D finite segments (robust to parallelism).
    u = b - a
    v = d - c
    w = a - c
    aa = u.dot(u)
    bb = u.dot(v)
    cc = v.dot(v)
    dd = u.dot(w)
    ee = v.dot(w)
    det = aa * cc - bb * bb
    s_n = 0.0
    s_d = det
    t_n = 0.0
    t_d = det
    if det < 1e-12:
        s_n = 0.0
        s_d = 1.0
        t_n = ee
        t_d = cc
    else:
        s_n = bb * ee - cc * dd
        t_n = aa * ee - bb * dd
        if s_n < 0:
            s_n = 0
            t_n = ee
            t_d = cc
        elif s_n > s_d:
            s_n = s_d
            t_n = ee + bb
            t_d = cc
    if t_n < 0:
        t_n = 0
        if -dd < 0:
            s_n = 0
        elif -dd > aa:
            s_n = s_d
        else:
            s_n = -dd
            s_d = aa
    elif t_n > t_d:
        t_n = t_d
        if (-dd + bb) < 0:
            s_n = 0
        elif (-dd + bb) > aa:
            s_n = s_d
        else:
            s_n = -dd + bb
            s_d = aa
    s = 0.0 if abs(s_n) < 1e-12 else s_n / max(s_d, 1e-12)
    t = 0.0 if abs(t_n) < 1e-12 else t_n / max(t_d, 1e-12)
    return (w + s * u - t * v).length


def support_test(arm, roles, contacts, margin=0.08):
    """Approximate COM from role-weighted bone centres; support points are explicit.

    Not a validated biomechanical mass distribution or dynamic stability calculation.
    """
    weighted = []
    for role, weight in MASS.items():
        name = roles.get(role)
        if name and arm.pose.bones.get(name):
            a = world_point(arm, name)
            b = world_point(arm, name, tail=True)
            weighted.append(((a + b) * 0.5, weight))
    if not weighted:
        return {'status': 'NOT TESTED', 'reason': 'No mapped body segments'}
    total_w = sum(w for _, w in weighted)
    com = sum((p * w for p, w in weighted), Vector((0, 0, 0))) / total_w
    if not contacts:
        return {
            'status': 'NOT TESTED',
            'reason': 'No static support contacts (dynamic pose)',
            'com': [round(v, 5) for v in com],
        }
    # Multi-contact convex hull in world XY
    pts = sorted(set((round(p.x, 6), round(p.y, 6)) for p in contacts))
    if len(pts) == 1:
        distance = math.hypot(com.x - pts[0][0], com.y - pts[0][1])
        inside = distance <= margin
    elif len(pts) == 2:
        p = Vector(pts[0])
        q = Vector(pts[1])
        x = Vector((com.x, com.y))
        v = q - p
        t = max(0.0, min(1.0, (x - p).dot(v) / max(1e-12, v.length_squared)))
        distance = (x - (p + t * v)).length
        inside = distance <= margin
    else:
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        lo, hi = [], []
        for p in pts:
            while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
                lo.pop()
            lo.append(p)
        for p in reversed(pts):
            while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
                hi.pop()
            hi.append(p)
        hull = lo[:-1] + hi[:-1]
        x = (com.x, com.y)
        inside = all(
            cross(hull[i], hull[(i + 1) % len(hull)], x) >= -1e-7
            for i in range(len(hull))
        )
        distance = None
    return {
        'status': 'PASS' if inside else 'FAIL',
        'com': [round(v, 5) for v in com],
        'support_points': pts,
        'outside_or_distance': None if distance is None else round(distance, 5),
        'method': 'approximate COM weighted bones / ground XY supports; NOT physical stability proof',
    }


def mesh_intersections(arm, settings):
    """Triangle collision tests via world-space evaluated Blender BVHs.

    Surface intersections are detected; complete containment is NOT detected.
    Clothing / attachment overlaps are common false positives and are reported
    as WARN rather than FAIL unless they involve environment geometry.
    """
    from mathutils.bvhtree import BVHTree

    dg = bpy.context.evaluated_depsgraph_get()
    attached, surroundings, omitted = [], [], []
    exclude = set(settings.get('exclude_environment_objects', []))
    max_tris = int(settings.get('max_collision_faces_per_mesh', 60000))
    if max_tris < 1 or max_tris > 400000:
        raise ValueError('Invalid max_collision_faces_per_mesh')

    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH' or obj.hide_get() or obj.hide_render:
            continue
        is_character = (
            obj.parent == arm
            or any(m.type == 'ARMATURE' and m.object == arm for m in obj.modifiers)
        )
        if not is_character and obj.name in exclude:
            continue
        try:
            ev = obj.evaluated_get(dg)
            mesh = ev.to_mesh()
            try:
                if len(mesh.polygons) > max_tris:
                    omitted.append(obj.name + ': face budget exceeded')
                    continue
                verts = [ev.matrix_world @ v.co for v in mesh.vertices]
                mesh.calc_loop_triangles()
                polys = [tuple(t.vertices) for t in mesh.loop_triangles]
                if not verts or not polys:
                    continue
                tree = BVHTree.FromPolygons(
                    verts, polys, all_triangles=False, epsilon=0.00001
                )
                (attached if is_character else surroundings).append((obj.name, tree, verts, polys))
            finally:
                ev.to_mesh_clear()
        except Exception as exc:
            omitted.append(obj.name + ': ' + type(exc).__name__)

    if not attached:
        return {
            'status': 'NOT TESTED',
            'reason': 'No evaluated skinned meshes',
            'omitted': omitted,
        }

    hits = []

    def check(a, b, classification):
        try:
            overlap = a[1].overlap(b[1])
            if overlap:
                hits.append({
                    'objects': [a[0], b[0]],
                    'classification': classification,
                    'triangle_pairs': len(overlap),
                })
        except Exception as exc:
            omitted.append(a[0] + '/' + b[0] + ': ' + type(exc).__name__)

    # Same-mesh triangle intersections; reject adjacent/shared-vertex pairs.
    # BVH self-overlap returns candidate pairs; false positives from co-planar
    # close surfaces are marked WARN, not proof of penetration.
    max_candidates = int(settings.get('max_self_collision_candidates', 100000))
    if not 1 <= max_candidates <= 1000000:
        raise ValueError('Invalid max_self_collision_candidates')
    for obj_name, tree, verts, polys in attached:
        try:
            seen = set()
            count = 0
            for i, j in tree.overlap(tree):
                if i == j or i < 0 or j < 0:
                    continue
                pair = (min(i, j), max(i, j))
                if pair in seen:
                    continue
                seen.add(pair)
                if len(seen) > max_candidates:
                    omitted.append(obj_name + ': self collision candidate budget exceeded')
                    break
                if set(polys[i]).intersection(polys[j]):
                    continue
                count += 1
            if count:
                hits.append({'objects': [obj_name, obj_name],
                             'classification': 'self_mesh', 'triangle_pairs': count})
        except Exception as exc:
            omitted.append(obj_name + ': self collision ' + type(exc).__name__)

    for i, a in enumerate(attached):
        for b in attached[i + 1:]:
            check(a, b, 'character_parts')
        for b in surroundings:
            check(a, b, 'environment')

    return {
        'status': 'WARN' if hits or omitted else 'PASS',
        'intersections': hits,
        'omitted': omitted,
        'limitations': [
            'Self-intersecting triangle candidates are tested, but touching surfaces may be false positives',
            'Does not detect complete enclosure without intersecting surfaces',
            'Mesh touching and interpenetration can produce false positives or intentional clothing contacts',
        ],
    }


def validate(arm, roles, targets, settings):
    up = settings.get('world_up', 'Z')
    if up != 'Z':
        return {'status': 'BLOCKED', 'reason': 'Validator currently supports world Z-up only'}
    tolerance = float(settings.get('endpoint_tolerance', 0.03))
    min_clearance = float(settings.get('ground_penetration_tolerance', 0.02))
    radius_factor = float(settings.get('limb_capsule_radius_factor', 0.11))
    if tolerance <= 0 or min_clearance < 0 or not 0.01 <= radius_factor <= 0.35:
        raise ValueError('Unsafe validation thresholds')

    endpoint = {}
    fails = []
    warnings = []

    for role, spec in targets.items():
        if role not in CHAINS:
            continue
        names = [roles[x] for x in CHAINS[role]]
        actual = world_point(arm, names[-1], tail=True)
        err = (actual - xyz(spec['point'])).length
        endpoint[role] = {
            'status': 'PASS' if err <= tolerance else 'FAIL',
            'error': round(err, 5),
        }
        if err > tolerance:
            fails.append(role + ' endpoint error')

    contacts = []
    for role, spec in targets.items():
        if role not in CHAINS or not spec.get('ground_contact'):
            continue
        names = [roles[x] for x in CHAINS[role]]
        contact = world_point(arm, names[-1], tail=True)
        contacts.append(contact)
        if 'ground_z' not in spec:
            warnings.append('No measured ground_z for ' + role)
        elif abs(contact.z - float(spec['ground_z'])) > tolerance:
            fails.append(role + ' contact height mismatch')

    ground_z = settings.get('ground_z')
    penetrations = []
    if ground_z is not None:
        z = float(ground_z)
        for role in ('foot.L', 'foot.R', 'hand.L', 'hand.R'):
            name = roles.get(role)
            if name and arm.pose.bones.get(name):
                p = world_point(arm, name, tail=True)
                if p.z < z - min_clearance:
                    penetrations.append({'role': role, 'depth': round(z - p.z, 5)})
    else:
        warnings.append('Scene ground not supplied; broad ground penetration NOT TESTED')
    if penetrations:
        fails.append('Ground penetrations')

    # Conservative capsule self-clipping (false positives likely near torso)
    limb_segments = []
    for role in (
        'upper_arm.L', 'forearm.L', 'upper_arm.R', 'forearm.R',
        'thigh.L', 'shin.L', 'thigh.R', 'shin.R',
    ):
        n = roles.get(role)
        if n and arm.pose.bones.get(n):
            a = world_point(arm, n)
            b = world_point(arm, n, tail=True)
            limb_segments.append(
                (role, n, a, b, max((b - a).length * radius_factor, 0.001))
            )
    possible = []
    for i, (ra, na, a, b, r) in enumerate(limb_segments):
        for rb, nb, c, d, s in limb_segments[i + 1:]:
            ba = arm.pose.bones[na]
            bb = arm.pose.bones[nb]
            if ba.parent == bb or bb.parent == ba:
                continue
            if ra.startswith('upper_arm') and rb.startswith('upper_arm'):
                continue
            if ra.startswith('thigh') and rb.startswith('thigh'):
                continue
            dist = _point_seg_distance(a, b, c, d)
            if dist < r + s:
                possible.append({
                    'segments': [ra, rb],
                    'overlap_estimate': round(r + s - dist, 5),
                })
    if possible:
        warnings.append('Possible limb-limb capsule overlaps (must verify mesh)')

    mesh_collision = (
        mesh_intersections(arm, settings)
        if settings.get('check_mesh_collisions', True)
        else {'status': 'NOT TESTED', 'reason': 'Disabled'}
    )
    if mesh_collision['status'] == 'WARN':
        if any(x['classification'] == 'environment' for x in mesh_collision.get('intersections', [])):
            fails.append('Character-environment mesh intersection')
        if any(x['classification'] in ('character_parts', 'self_mesh') for x in mesh_collision.get('intersections', [])):
            warnings.append(
                'Possible character mesh-part clipping (may include intended clothing overlap)'
            )
        if mesh_collision.get('omitted'):
            warnings.append('Some mesh collision objects were skipped')
    if mesh_collision['status'] == 'NOT TESTED':
        warnings.append('Mesh intersection checks not performed')

    joint_limits = check_joint_limits(arm, roles, settings)
    if joint_limits['status'] == 'FAIL':
        fails.append('Anatomical joint limit exceeded')
    if joint_limits['status'] == 'NOT TESTED':
        warnings.append('Joint limits not calibrated for some bones')

    balance = support_test(
        arm, roles, contacts, float(settings.get('balance_margin', 0.12))
    )
    if balance['status'] == 'FAIL' and settings.get('static_pose', True):
        fails.append('COM outside approximated support')
    if balance['status'] == 'NOT TESTED' and settings.get('static_pose', True):
        warnings.append('Static balance not tested')

    return {
        'status': 'FAIL' if fails else ('WARN' if warnings else 'PASS'),
        'endpoint_checks': endpoint,
        'support_balance': balance,
        'joint_limits': joint_limits,
        'ground_penetrations': penetrations,
        'mesh_intersections': mesh_collision,
        'capsule_overlap_candidates': possible,
        'failures': fails,
        'warnings': warnings,
        'not_tested': [
            'Fully contained geometry without surface intersections',
            'Joint-limit verification for roles without calibrated metadata',
            'Dynamic forces and momentum',
            'Foot sole contact orientation unless provided as endpoint marker',
        ],
    }


def apply_auto_plan(report, plan_path, output, result_path):
    """Run CCD on clean FK chains, validate, then save new .blend if acceptable."""
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8'))
    if plan.get('schema') != 'watoom.human_pose_auto_plan.v1':
        raise ValueError('Invalid auto plan schema')
    arm = bpy.data.objects.get(plan.get('armature', ''))
    if arm is None or arm.type != 'ARMATURE':
        raise ValueError('Armature not found')
    info = next((a for a in report['armatures'] if a['object'] == arm.name), None)
    if info is None:
        raise ValueError('Armature not present in inspection')
    roles = dict(info['role_candidates'])
    roles.update(plan.get('role_overrides', {}))
    targets = plan.get('targets', {})
    if not targets:
        raise ValueError('No world-space IK targets')
    for role in targets:
        if role not in CHAINS:
            raise ValueError('Unsupported target role: ' + role)
        for component in CHAINS[role]:
            if component not in roles:
                raise ValueError('Unmapped chain component: ' + component)

    out = Path(output).expanduser().resolve()
    src = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    if out.suffix.lower() != '.blend' or out.exists() or (src and out == src):
        raise ValueError('Output must be new .blend and may not overwrite source')
    if not out.parent.is_dir():
        raise ValueError('Output parent must already exist')
    result = Path(result_path).expanduser().resolve()
    if result.exists() or not result.parent.is_dir():
        raise ValueError('Result report must be a new path in existing directory')

    # Explicit preflight of every chain before any pose change
    for role in targets:
        names = [roles[x] for x in CHAINS[role]]
        ok, reason = chain_is_usable(arm, names)
        if not ok:
            raise ValueError(role + ' BLOCKED: ' + reason)

    settings = plan.get('settings', {})
    if settings.get('world_up', 'Z') != 'Z':
        raise ValueError('Only Z-up environments currently supported')
    bpy.context.scene.frame_set(int(plan.get('frame', 1)))
    iterations = int(settings.get('iterations', 90))
    if not 1 <= iterations <= 400:
        raise ValueError('iterations outside 1..400')
    tolerance = float(settings.get('endpoint_tolerance', 0.03))

    solutions = {}
    orientation_solutions = {}
    max_passes = int(settings.get('full_body_passes', 5))
    if not 1 <= max_passes <= 30:
        raise ValueError('full_body_passes must be 1..30')
    pelvis_spec = plan.get('pelvis_world_position')
    if pelvis_spec is not None:
        pelvis_name = roles.get('pelvis')
        if not pelvis_name or not arm.pose.bones.get(pelvis_name):
            raise ValueError('Pelvis role not mapped')
        pelvis = arm.pose.bones[pelvis_name]
        if pelvis.constraints or any(pelvis.lock_location):
            raise ValueError('Pelvis control locked or constrained')
        delta_world = xyz(pelvis_spec) - world_point(arm, pelvis_name)
        # Delta transformed into armature-local displacement. Parentless pelvis
        # only; inherited location semantics for parented pelvis require adapter.
        if pelvis.parent:
            raise ValueError('Parented pelvis requires rig-specific adapter')
        pelvis.location += arm.matrix_world.inverted_safe().to_3x3() @ delta_world
        bpy.context.view_layer.update()

    for sweep in range(max_passes):
        for role, spec in targets.items():
            names = [roles[x] for x in CHAINS[role]]
            solutions[role] = ccd(
                arm, names, xyz(spec['point']),
                xyz(spec['pole']) if 'pole' in spec else None,
                iterations, tolerance,
            )
        if all((world_point(arm, roles[CHAINS[r][-1]], tail=True) - xyz(t['point'])).length <= tolerance
               for r, t in targets.items()):
            break

    for role, spec in targets.items():
        if 'orientation_world_quat' in spec:
            orientation_solutions[role] = orient_end_effector(
                arm, roles[CHAINS[role][-1]], spec['orientation_world_quat'],
                float(settings.get('orientation_tolerance_rad', 0.12)))

    validation = validate(arm, roles, targets, settings)
    validation['end_effector_orientations'] = orientation_solutions
    if any(s['status'] != 'PASS' for s in orientation_solutions.values()):
        validation['failures'].append('End-effector orientation did not converge')
        validation['status'] = 'FAIL'
    if any(s['status'] != 'PASS' for s in solutions.values()):
        validation['failures'].append('One or more IK chains did not converge')
        validation['status'] = 'FAIL'

    status = (
        'FAIL' if validation['failures']
        else ('WARN' if validation['status'] == 'WARN' else 'PASS')
    )
    outcome = {
        'schema': 'watoom.human_pose_auto_result.v1',
        'status': status,
        'armature': arm.name,
        'solutions': solutions,
        'orientation_solutions': orientation_solutions,
        'full_body_sweeps': sweep + 1,
        'validation': validation,
        'saved': False,
        'output': None,
    }

    # Save only non-FAIL results so the agent can inspect WARN poses
    if status != 'FAIL':
        frame = bpy.context.scene.frame_current
        keyed = set()
        for role in targets:
            for name in [roles[x] for x in CHAINS[role]]:
                pb = arm.pose.bones[name]
                pb.rotation_mode = 'QUATERNION'
                # Ensure the quaternion we key is the one the solver left
                pb.keyframe_insert(data_path='rotation_quaternion', frame=frame, group=name)
                # Only key location if the bone actually moved in translation
                # (most pure FK chains leave location at rest)
                if pb.location.length > 1e-6:
                    pb.keyframe_insert(data_path='location', frame=frame, group=name)
                keyed.add(name)
        bpy.ops.wm.save_as_mainfile(filepath=str(out), check_existing=True)
        outcome['saved'] = True
        outcome['output'] = str(out)
        outcome['bones_keyed'] = sorted(keyed)

    result.write_text(json.dumps(outcome, indent=2) + '\n', encoding='utf-8')
    return outcome
