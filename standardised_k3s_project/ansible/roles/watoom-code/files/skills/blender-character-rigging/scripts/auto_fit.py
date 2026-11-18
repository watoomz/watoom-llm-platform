"""auto_fit - place a Rigify metarig's joints on an unrigged mesh automatically.

Used by rigify_build.py --auto-fit. Works for humanoids (basic_human / human),
quadrupeds (basic_quadruped / wolf / cat / horse) and birds (bird), and can pick
the body type itself (rigify_build.py --add auto).

How it fits (no manual joint placement):
  1. Sample the mesh surface (area-weighted, so dense faces do not bias it).
  2. Find the ground contacts and which way the model faces (toes for bipeds,
     head end for quadrupeds), so a model rotated on the spot still fits.
  3. Measure landmarks in that facing frame: crotch, neck, head top, arm
     centrelines and hand tips (humanoid); feet, belly, back, nose and tail
     (quadruped); feet, belly, back, beak, tail and wingtips (bird).
  4. Move the anchor joints onto those landmarks: humanoid legs and spine follow
     the measured leg/torso centrelines, arms follow the measured arm centreline
     (T-pose and A-pose both work); animal bodies use a landmark warp, with
     quadruped legs refined independently from ground-up surface sections.
  5. Every other bone (fingers, toes, face, feathers, tail tips) follows its
     nearest placed ancestor by the same rotation + scale, and every bone's roll
     is carried through, so Rigify can generate from the result.
  6. Report quality: worst limb surface clearance, distal leg axis offset and
     bilateral height agreement; raw L/R stance offset remains diagnostic.

Assumes Z-up (Blender default, glTF/FBX imports) and a neutral standing pose:
T/A-pose for humanoids, four feet down for quadrupeds, standing for birds.
Arms held tight against the body, sitting/curled poses and non-standard
creatures (snakes, fish, multi-limbed) are out of scope; the report says so
through geometry diagnostics rather than failing silently.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

BODY_OF = {"basic_human": "humanoid", "human": "humanoid", "basic_quadruped": "quadruped", "horse": "quadruped",
           "wolf": "quadruped", "cat": "quadruped", "bird": "bird"}
DEFAULT_METARIG = {"humanoid": "basic_human", "quadruped": "wolf", "bird": "bird"}
JUNK_PREFIXES = ("Icosphere", "WGT-", "WGT_")


# ---------------------------------------------------------------- mesh sampling
def candidate_meshes(names=None):
    if names:
        return [bpy.data.objects[n] for n in names]
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()
            and not o.name.startswith(JUNK_PREFIXES)]


def sample_surface(meshes, n=60000, seed=0):
    # Prefer a complete body surface over dozens of overlapping wardrobe variants.
    # Split bodies (none spanning most of the height) retain all their parts.
    bounds = [np.array([ob.matrix_world @ Vector(c) for c in ob.bound_box]) for ob in meshes]
    if bounds:
        heights = np.array([np.ptp(b[:, 2]) for b in bounds])
        full_h = max(b[:, 2].max() for b in bounds) - min(b[:, 2].min() for b in bounds)
        whole = [i for i, bh in enumerate(heights) if bh >= 0.85 * full_h]
        if whole:
            # The tallest surface carries the head and feet; coats do not.
            meshes = [meshes[max(whole, key=lambda i: heights[i])]]
    deps = bpy.context.evaluated_depsgraph_get()
    tris, areas = [], []
    for ob in meshes:
        ev = ob.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        nv, nt = len(me.vertices), len(me.loop_triangles)
        if nt == 0:
            ev.to_mesh_clear()
            continue
        co = np.empty(nv * 3, np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(ob.matrix_world)
        co = co @ mw[:3, :3].T + mw[:3, 3]
        idx = np.empty(nt * 3, np.int64)
        me.loop_triangles.foreach_get("vertices", idx)
        t = co[idx.reshape(-1, 3)]
        a = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
        tris.append(t)
        areas.append(a)
        ev.to_mesh_clear()
    if not tris:
        raise ValueError("auto-fit: no mesh triangles to fit")
    t = np.concatenate(tris)
    a = np.concatenate(areas)
    if not np.isfinite(a).all() or a.sum() <= 0:
        raise ValueError("auto-fit: mesh surface has no finite positive area")
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(t), size=n, p=a / a.sum())
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    tt = t[pick]
    return tt[:, 0] + u[:, None] * (tt[:, 1] - tt[:, 0]) + v[:, None] * (tt[:, 2] - tt[:, 0])


def build_bvh(meshes, origin=None, scale=1.0):
    deps = bpy.context.evaluated_depsgraph_get()
    verts, polys, off = [], [], 0
    origin = Vector((0, 0, 0)) if origin is None else Vector(origin)
    for ob in meshes:
        ev = ob.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        verts += [(ob.matrix_world @ v.co - origin) / scale for v in me.vertices]
        polys += [tuple(i + off for i in lt.vertices) for lt in me.loop_triangles]
        off += len(me.vertices)
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)


def inside(bvh, p, eps=1e-5):
    """Ray-parity point-in-mesh test, voted over three directions (robust to small holes)."""
    votes = 0
    for d in (Vector((1, 0.0013, 0.0007)), Vector((-0.0011, 1, 0.0009)), Vector((0.0008, -0.0012, 1))):
        d.normalize()
        o, hits = Vector(p), 0
        for _ in range(64):
            loc, _n, _i, _d = bvh.ray_cast(o, d)
            if loc is None:
                break
            hits += 1
            o = loc + d * eps
        votes += hits % 2
    return votes >= 2


# ---------------------------------------------------------------- small helpers
def kmeans(x, k, trials=12, iters=40, seed=0):
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(trials):
        c = x[rng.choice(len(x), k, replace=False)]
        for _ in range(iters):
            lab = ((x[:, None] - c[None]) ** 2).sum(-1).argmin(1)
            c = np.array([x[lab == j].mean(0) if (lab == j).any() else c[j] for j in range(k)])
        sse = ((x - c[lab]) ** 2).sum()
        if best is None or sse < best[0]:
            best = (sse, c, lab)
    return best


def clusters_1d(v, step, gap=2):
    """Split 1-D samples into runs separated by >= gap empty bins; returns (lo, hi, count) per run."""
    if len(v) == 0:
        return []
    lo = v.min()
    b = np.floor((v - lo) / step).astype(int)
    occ = np.bincount(b)
    runs, start, empty = [], None, 0
    for i, c in enumerate(occ):
        if c:
            if start is None:
                start = i
            empty, end = 0, i
        else:
            empty += 1
            if start is not None and empty >= gap:
                runs.append((start, end))
                start = None
    if start is not None:
        runs.append((start, end))
    return [(lo + s * step, lo + (e + 1) * step, int(occ[s:e + 1].sum())) for s, e in runs]


def components_2d(xy, cell):
    """Connected components of occupied grid cells (8-neighbour). Returns point-index arrays, largest first."""
    if len(xy) == 0:
        return []
    g = np.floor((xy - xy.min(0)) / cell).astype(int)
    keys = {}
    for i, k in enumerate(map(tuple, g)):
        keys.setdefault(k, []).append(i)
    seen, comps = set(), []
    for k in keys:
        if k in seen:
            continue
        stack, idx = [k], []
        seen.add(k)
        while stack:
            c = stack.pop()
            idx += keys[c]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (c[0] + dx, c[1] + dy)
                    if n in keys and n not in seen:
                        seen.add(n)
                        stack.append(n)
        comps.append(np.array(idx))
    return sorted(comps, key=len, reverse=True)


def pw(v, src, dst):
    """Monotone piecewise-linear map with linear extrapolation."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    if v <= src[0]:
        return dst[0] + (v - src[0]) * (dst[1] - dst[0]) / max(src[1] - src[0], 1e-9)
    if v >= src[-1]:
        return dst[-1] + (v - src[-1]) * (dst[-1] - dst[-2]) / max(src[-1] - src[-2], 1e-9)
    return float(np.interp(v, src, dst))


def monotone(seq, eps):
    out = list(seq)
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1] + eps)
    return out


class Frame:
    """Facing frame: model faces -Y, its left is +X, ground at z=0 (matches every Rigify metarig)."""

    def __init__(self, center_xy, yaw, z0):
        self.c, self.yaw, self.z0 = np.asarray(center_xy, float), yaw, z0
        cs, sn = math.cos(yaw), math.sin(yaw)
        self.r = np.array([[cs, -sn], [sn, cs]])

    def to(self, p):
        p = np.atleast_2d(p).astype(float)
        q = p.copy()
        q[:, :2] = (p[:, :2] - self.c) @ self.r.T
        q[:, 2] = p[:, 2] - self.z0
        return q

    def back(self, q):
        q = np.atleast_2d(q).astype(float)
        p = q.copy()
        p[:, :2] = q[:, :2] @ self.r + self.c
        p[:, 2] = q[:, 2] + self.z0
        return p


def yaw_to_face_neg_y(fwd_xy):
    return -math.pi / 2 - math.atan2(fwd_xy[1], fwd_xy[0])


# ---------------------------------------------------------------- body detection
def ground_contacts(p, k):
    h = np.ptp(p[:, 2])
    low = p[p[:, 2] < p[:, 2].min() + 0.06 * h][:, :2]
    if len(low) < 4 * k:
        low = p[p[:, 2] < p[:, 2].min() + 0.12 * h][:, :2]
    return kmeans(low, k)[1]


def torso_extent(p):
    """Longest horizontal extent of the main body cross-section at 45/55/65% height, as a fraction of height.
    Upright bodies (humanoids) stay narrow; horizontal bodies (quadrupeds, birds) are long."""
    h, z0 = np.ptp(p[:, 2]), p[:, 2].min()
    best = 0.0
    for f in (0.45, 0.55, 0.65):
        s = p[np.abs(p[:, 2] - (z0 + f * h)) < 0.02 * h][:, :2]
        comps = components_2d(s, 0.02 * h)
        if not comps:
            continue
        m = s[comps[0]]
        ax = np.linalg.svd(m - m.mean(0))[2][0] if len(m) > 2 else np.array([1.0, 0.0])
        best = max(best, float(np.ptp(m @ ax)) / h)
    return best


def contact_count(p):
    h = np.ptp(p[:, 2])
    low = p[p[:, 2] < p[:, 2].min() + 0.04 * h][:, :2]
    comps = components_2d(low, 0.015 * h)
    return sum(len(c) >= 0.04 * len(low) for c in comps)


def detect_body(p):
    if torso_extent(p) < 0.5:
        return "humanoid"
    if contact_count(p) >= 3:
        return "quadruped"
    # Spread arms or bulky sleeves can join the trunk in a horizontal slice.
    # An upright biped is still shallow in the direction perpendicular to its feet.
    h, z0 = np.ptp(p[:, 2]), p[:, 2].min()
    fwd, _ = facing_biped(p)
    trunk = p[(p[:, 2] > z0 + 0.4 * h) & (p[:, 2] < z0 + 0.7 * h)]
    if np.ptp(trunk[:, :2] @ fwd) < 0.4 * h:
        return "humanoid"
    return "bird"


# ---------------------------------------------------------------- facing
def facing_biped(p):
    h = np.ptp(p[:, 2])
    zmin = p[:, 2].min()
    torso = p[(p[:, 2] > zmin + 0.45 * h) & (p[:, 2] < zmin + 0.65 * h)][:, :2]
    c2 = ground_contacts(p, 2)
    lr = c2[1] - c2[0]
    if np.linalg.norm(lr) < 0.05 * h and len(torso) > 50:  # feet together: use torso width axis
        lr = np.linalg.svd(torso - torso.mean(0))[2][0]
    lr = lr / max(np.linalg.norm(lr), 1e-9)
    fwd = np.array([-lr[1], lr[0]])
    toes = p[p[:, 2] < zmin + 0.035 * h][:, :2]
    ankles = p[(p[:, 2] > zmin + 0.06 * h) & (p[:, 2] < zmin + 0.12 * h)][:, :2]
    cue = (toes.mean(0) - ankles.mean(0)) @ fwd if len(toes) and len(ankles) else 0.0
    if abs(cue) < 0.004 * h:
        # Weak toe cue: default to the conventional Blender front (-Y).
        return (fwd if fwd @ np.array([0, -1]) >= 0 else -fwd), "default-front"
    return (fwd if cue > 0 else -fwd), "toes"


def facing_quadruped(p):
    c4 = ground_contacts(p, 4)
    ctr = c4.mean(0)
    ax = np.linalg.svd(c4 - ctr)[2][0]
    proj = (c4 - ctr) @ ax
    o = np.argsort(proj)
    a, b = c4[o[:2]].mean(0), c4[o[2:]].mean(0)
    top = p[p[:, 2] > p[:, 2].max() - 0.08 * np.ptp(p[:, 2])][:, :2].mean(0)
    fwd = (b - a) if (top - ctr) @ (b - a) >= 0 else (a - b)
    return fwd / np.linalg.norm(fwd), "head-end"


# ---------------------------------------------------------------- metarig access
def edit_points(meta):
    """{bone: (head, tail, z_axis)} in world space, from edit bones."""
    mw = meta.matrix_world
    return {b.name: (mw @ b.head, mw @ b.tail, (mw.to_3x3() @ b.z_axis).normalized()) for b in meta.data.edit_bones}


def write_bones(meta, placed):
    inv = meta.matrix_world.inverted()
    connected = {b.name for b in meta.data.edit_bones if b.use_connect}
    extent = max((v[1] - v[0]).length for v in placed.values())
    for b in meta.data.edit_bones:
        b.use_connect = False
    for b in meta.data.edit_bones:
        if b.name in placed:
            h, t, z = placed[b.name]
            b.head, b.tail = inv @ h, inv @ t
            b.align_roll(inv.to_3x3() @ z)
    for b in meta.data.edit_bones:  # restore connections whose joints coincide
        if b.name in connected and b.parent and (b.head - b.parent.tail).length < extent * 1e-6:
            b.use_connect = True


def rot_between(a, b):
    a, b = Vector(a), Vector(b)
    if a.length < 1e-9 or b.length < 1e-9:
        return Matrix.Identity(3)
    return a.normalized().rotation_difference(b.normalized()).to_matrix()


def propagate(meta, old, anchors):
    """Anchored bones keep their computed head/tail; all others follow their nearest anchored ancestor."""
    placed, xf = {}, {}
    order = []

    def walk(b):
        order.append(b)
        for c in b.children:
            walk(c)

    for b in meta.data.edit_bones:
        if b.parent is None:
            walk(b)
    for b in order:
        oh, ot, oz = old[b.name]
        if b.name in anchors:
            nh, nt = anchors[b.name]
            r = rot_between(ot - oh, nt - nh)
            s = (nt - nh).length / max((ot - oh).length, 1e-9)
            xf[b.name] = (oh, nh, r, s)
            placed[b.name] = (nh, nt, r @ oz)
            continue
        p = b.parent
        while p is not None and p.name not in xf:
            p = p.parent
        if p is None:
            placed[b.name] = (oh, ot, oz)
            continue
        po, pn, r, s = xf[p.name]
        f = (lambda v: pn + s * (r @ (v - po)))
        placed[b.name] = (f(oh), f(ot), r @ oz)
        xf[b.name] = xf[p.name]
    return placed


# ---------------------------------------------------------------- humanoid
def fit_humanoid(meta, p, old):
    fwd, cue = facing_biped(p)
    fr = Frame(p[:, :2].mean(0), yaw_to_face_neg_y(fwd), p[:, 2].min())
    q = fr.to(p)
    h = q[:, 2].max()
    step = 0.01 * h

    def slice_(z, half=0.006):
        return q[np.abs(q[:, 2] - z) < half * h]

    def central(s):
        runs = clusters_1d(s[:, 0], step)
        mid = [r for r in runs if r[0] <= 0 <= r[1]] or sorted(runs, key=lambda r: min(abs(r[0]), abs(r[1])))[:1]
        return mid[0] if mid else (0.0, 0.0, 0)

    # crotch: first height (scanning up) where the body is continuous across the centre line
    crotch = 0.47 * h
    for z in np.arange(0.62 * h, 0.2 * h, -step / 2):
        s = slice_(z, 0.004)
        if len(s) and (np.abs(s[:, 0]) < 0.008 * h).sum() == 0 and (s[:, 0] > 0).any() and (s[:, 0] < 0).any():
            crotch = z
            break
    crotch = float(np.clip(crotch, 0.40 * h, 0.55 * h))
    # neck: narrowest central width between 0.75H and 0.95H
    zs = np.arange(0.74 * h, 0.95 * h, step)
    widths = []
    for z in zs:
        s = slice_(z)
        lo, hi, n = central(s) if len(s) else (0, 0, 0)
        widths.append(hi - lo if n else 1e9)
    neck_mid = zs[int(np.argmin(widths))]
    neck_base = neck_mid - 0.035 * h
    chest_z = crotch + 0.62 * (neck_base - crotch)
    clo, chi, _ = central(slice_(chest_z))
    chest_hw = float(np.clip(max(abs(clo), abs(chi)), 0.055 * h, 0.22 * h))

    def torso_c(z):
        s = slice_(z)
        if not len(s):
            return np.array([0.0, 0.0])
        lo, hi, _ = central(s)
        m = s[(s[:, 0] >= lo) & (s[:, 0] <= hi)]
        return m[:, :2].mean(0) if len(m) else np.array([0.0, 0.0])

    # legs: track each leg's centreline from the ankle up to the crotch
    def leg_line(side):
        pts, prev = [], None
        for z in np.arange(0.04 * h, crotch - 0.01 * h, step):
            s = slice_(z)
            s = s[np.sign(s[:, 0]) == side] if len(s) else s
            if not len(s):
                continue
            runs = clusters_1d(s[:, 0], step)
            if prev is None:
                r = min(runs, key=lambda r: abs((r[0] + r[1]) / 2 - side * 0.05 * h))
            else:
                r = min(runs, key=lambda r: abs((r[0] + r[1]) / 2 - prev))
            m = s[(s[:, 0] >= r[0]) & (s[:, 0] <= r[1])]
            c = m[:, :2].mean(0)
            c[1] = np.percentile(m[:, 1], [10, 90]).mean()
            prev = c[0]
            pts.append((z, c[0], c[1]))
        return np.array(pts)

    def leg_at(line, z):
        return np.array([np.interp(z, line[:, 0], line[:, 1]), np.interp(z, line[:, 0], line[:, 2])])

    # arms: hand tip = most lateral point above 0.3H; centreline sampled toward the shoulder
    def arm(side):
        cand = q[(q[:, 2] > 0.3 * h) & (side * q[:, 0] > chest_hw * 1.05)]
        if len(cand) < 20:
            return None
        tip = cand[np.argmax(side * cand[:, 0])]
        sh_guess = np.array([side * chest_hw, torso_c(neck_base)[1], neck_base - 0.04 * h])
        d = tip - sh_guess
        L = np.linalg.norm(d)
        d = d / L
        rel = cand - sh_guess
        t = rel @ d
        perp = np.linalg.norm(rel - np.outer(t, d), axis=1)
        keep = (perp < 0.09 * h) & (t > 0)
        line = []
        for t0 in np.linspace(0.05 * L, 0.98 * L, 24):
            m = cand[keep & (np.abs(t - t0) < 0.03 * L)]
            if len(m) > 3:
                center = m.mean(0)
                center[1] = np.percentile(m[:, 1], [10, 90]).mean()
                line.append(center)
        if len(line) < 4:
            return None
        line = np.array(line)
        # Estimate the shoulder from the arm shaft, away from bulky deltoids,
        # sleeves and shoulder ornaments. A short noisy segment must not decide
        # an unbounded extrapolation back into the torso.
        shx = side * 1.1 * chest_hw
        shaft_x = shx + side * 0.06 * h
        near = cand[keep & (np.abs(cand[:, 0] - shaft_x) < 0.018 * h)]
        a = np.median(near, axis=0) if len(near) > 5 else line[0].copy()
        if len(near) > 5:
            a[1] = np.percentile(near[:, 1], [10, 90]).mean()
        slope = d / max(abs(d[0]), 1e-9) * side
        slope[1] = np.clip(slope[1], -0.4, 0.4)
        slope[2] = np.clip(slope[2], -1.1, 1.1)
        shoulder = a + slope * (shx - a[0])
        line = line[side * line[:, 0] > side * shx]
        line = np.vstack([shoulder, line, tip])
        seg = np.linalg.norm(np.diff(line, axis=0), axis=1)
        cum = np.concatenate([[0], np.cumsum(seg)])

        def at(f):
            return np.array([np.interp(f * cum[-1], cum, line[:, i]) for i in range(3)])
        return {"shoulder": shoulder, "elbow": at(0.42) + np.array([0, 0.006 * h, 0]),
                "wrist": at(0.75), "palm": at(0.86), "tip": tip}

    zsrc = [0.0, 0.93, 1.658, 1.98]
    zdst = monotone([0.0, crotch, neck_base, h], 0.01 * h)
    zmap = lambda z: pw(z, zsrc, zdst)  # noqa: E731
    ms = h / 1.98
    anchors = {}
    to_w = lambda v: Vector(fr.back(np.asarray(v, float))[0])  # noqa: E731

    inv = meta.matrix_world.inverted()
    template = np.array([inv @ v for hv in old.values() for v in hv[:2]])
    template_floor = template[:, 2].min()
    template_scale = np.ptp(template[:, 2]) / 1.98

    def mframe(v):  # canonical human units, including metarigs previously height-fitted
        a = np.array(inv @ v)
        a[2] -= template_floor
        return a / template_scale

    # spine chain on the torso centreline
    for name in [n for n in old if n.startswith("spine")]:
        oh, ot, _ = old[name]
        hh, tt = mframe(oh), mframe(ot)
        nh = np.array([0.0, 0.0, zmap(hh[2])])
        nt = np.array([0.0, 0.0, zmap(tt[2])])
        for v, o in ((nh, hh), (nt, tt)):
            c = torso_c(min(v[2], h * 0.97))
            v[0], v[1] = c[0], c[1] + o[1] * ms
        anchors[name] = (to_w(nh), to_w(nt))

    for side, sfx in ((1, ".L"), (-1, ".R")):
        line = leg_line(side)
        if len(line) >= 4 and f"thigh{sfx}" in old:
            hip_z = zmap(mframe(old[f"thigh{sfx}"][0])[2])
            knee_z = 0.5 * (hip_z + 0.05 * h)
            ank_z = 0.05 * h
            hip = leg_at(line, crotch - 0.03 * h)
            knee = leg_at(line, knee_z)
            ank = leg_at(line, max(ank_z, 0.10 * h))
            P = lambda xy, z: np.array([xy[0], xy[1], z])  # noqa: E731
            anchors[f"thigh{sfx}"] = (to_w(P(hip, hip_z)), to_w(P(knee + [0, -0.006 * h], knee_z)))
            anchors[f"shin{sfx}"] = (anchors[f"thigh{sfx}"][1], to_w(P(ank, ank_z)))
            foot = q[(q[:, 2] < 0.05 * h) & (np.abs(q[:, 0] - ank[0]) < 0.06 * h)]
            if len(foot) > 10:
                toe_y = foot[:, 1].min()
                ball = np.array([ank[0], ank[1] + 0.72 * (toe_y - ank[1]), 0.02 * h])
                anchors[f"foot{sfx}"] = (anchors[f"shin{sfx}"][1], to_w(ball))
                anchors[f"toe{sfx}"] = (to_w(ball), to_w(np.array([ank[0], toe_y, 0.02 * h])))
        a = arm(side)
        if a and f"upper_arm{sfx}" in old:
            anchors[f"upper_arm{sfx}"] = (to_w(a["shoulder"]), to_w(a["elbow"]))
            anchors[f"forearm{sfx}"] = (to_w(a["elbow"]), to_w(a["wrist"]))
            anchors[f"hand{sfx}"] = (to_w(a["wrist"]), to_w(a["palm"]))
            if f"shoulder{sfx}" in old:
                nb = torso_c(neck_base)
                anchors[f"shoulder{sfx}"] = (to_w(np.array([side * 0.1 * chest_hw, nb[1] - 0.02 * h, neck_base - 0.03 * h])),
                                             to_w(a["shoulder"]))
    lm = {"cue": cue, "height": round(float(h), 4), "crotch": round(float(crotch / h), 3),
          "neck_base": round(float(neck_base / h), 3), "chest_half_width": round(float(chest_hw / h), 3),
          "arms_found": sum(f"upper_arm{s}" in anchors for s in (".L", ".R")),
          "legs_found": sum(f"thigh{s}" in anchors for s in (".L", ".R"))}
    return anchors, fr, lm


# ---------------------------------------------------------------- quadruped / bird
def _meta_ref(meta, old, body):
    m = {n: (np.array(meta.matrix_world.inverted() @ v[0]), np.array(meta.matrix_world.inverted() @ v[1])) for n, v in old.items()}
    allp = np.array([x for hv in m.values() for x in hv])

    def heads(names):
        v = [m[n][0] for n in names if n in m]
        return np.array(v) if v else None
    feet_h = heads(["toe.L", "toe.R"])
    ref = {"top": allp[:, 2].max(), "nose": -allp[:, 1].min(), "tail": -allp[:, 1].max(),
           "s_hind": -feet_h[:, 1].mean(), "half": np.abs(feet_h[:, 0]).mean()}
    spine = np.array([m[n][0] for n in m if n.startswith("spine")])
    ref["spine_z"] = spine[:, 2].mean()
    if body == "quadruped":
        ff = heads(["front_toe.L", "front_toe.R"])
        ref["s_front"] = -ff[:, 1].mean()
        roots = heads(["thigh.L", "thigh.R", "front_thigh.L", "front_thigh.R"])
    else:
        roots = heads(["thigh.L", "thigh.R"])
        wing = np.array([x for n, hv in m.items() if ("Wing" in n or "w_feather" in n) and n.endswith(".L") for x in hv])
        ref["wing"] = wing[:, 0].max() if len(wing) else ref["half"] * 4
    ref["root_z"] = roots[:, 2].mean()
    return ref


def fit_quadruped_legs(q, contacts, lm, anchors, fr):
    """Recover four independent limb columns, preserving the body landmark warp.

    Work upwards in height slices, separating front/hind and left/right before
    measuring robust section centres. This avoids transferring the template's
    stride and digitigrade proportions to every animal.
    """
    h = lm["top"]
    belly, back = lm["belly"], lm["back"]
    split_y = -(lm["s_hind"] + lm["s_front"]) / 2
    step = .0125 * h
    for front in (False, True):
        for side, sign in ((".L", 1), (".R", -1)):
            region = q[(q[:, 0] * sign > 0) &
                       ((q[:, 1] < split_y) if front else (q[:, 1] >= split_y))]
            feet = contacts[((contacts[:, 1] < split_y) if front else
                             (contacts[:, 1] >= split_y)) & (contacts[:, 0] * sign > 0)]
            if not len(feet):
                continue
            centre = feet[0].copy()
            line = []
            for z in np.arange(.04 * h, belly + .01 * h, step):
                section = region[np.abs(region[:, 2] - z) < .012 * h]
                if len(section) < 8:
                    continue
                # Follow the closest occupied section; detached tails and fur
                # must not pull the upper hind leg away from its shaft.
                comps = components_2d(section[:, :2], .018 * h)
                comps = [ix for ix in comps if len(ix) >= 5]
                if not comps:
                    continue
                ix = min(comps, key=lambda ix: np.linalg.norm(
                    np.median(section[ix, :2], axis=0) - centre))
                section = section[ix]
                centre = np.percentile(section[:, :2], [10, 90], axis=0).mean(0)
                line.append([centre[0], centre[1], z])
            if len(line) < 6:
                continue
            line = np.array(line)

            def at(z):
                return np.array([np.interp(z, line[:, 2], line[:, j]) for j in (0, 1)] + [z])

            knee_z = .8 * belly
            ankle_z = .35 * belly
            if front:
                # Infer the humeral root from the local barrel proportions.
                # A wide chest joins the foreleg lower than a narrow chest;
                # surface medians depend heavily on tessellation and fur.
                shaft = at(.7 * belly)
                column = q[(np.abs(q[:, 1] - shaft[1]) < .04 * h) &
                           (q[:, 2] > belly)]
                local_back = np.percentile(column[:, 2], 95) if len(column) > 20 else back
                barrel = column[(column[:, 2] < local_back) &
                                (column[:, 2] > belly + .15 * (local_back - belly))]
                width = np.percentile(np.abs(barrel[:, 0]), 90) if len(barrel) > 20 else abs(shaft[0])
                shoulder_z = np.clip(local_back - 2.1 * width + abs(shaft[0]),
                                     belly + .1 * (back - belly), local_back - .1 * (back - belly))
                root = at(shoulder_z)
                # Continue the isolated shaft into the chest; the last slice
                # at belly height can already include the neck or barrel.
                root[:2] = shaft[:2]
                knee_z = .62 * belly
            else:
                root_z = belly + .65 * (back - belly)
                root = at(root_z)
                # The pelvis stays over the muscular upper leg, rather than
                # above its backward pointing hock.
                root[1] = at(.9 * belly)[1]
                # The hock is the largest sagittal bend below the stifle.
                # Search below the stifle so its upper bend cannot masquerade
                # as a hock on a long, straight distal limb.
                # Reject tiny bends (straight ungulate legs) and retain the
                # proportional fallback when no clear digitigrade hock exists.
                lower = line[(line[:, 2] >= .18 * belly) & (line[:, 2] <= .65 * belly)]
                if len(lower) >= 8:
                    chord = np.interp(lower[:, 2], lower[[0, -1], 2], lower[[0, -1], 1])
                    bend = lower[:, 1] - chord
                    ix = int(np.argmax(bend))
                    if bend[ix] > .025 * h:
                        ankle_z = lower[ix, 2]
            joints = [root, at(knee_z), at(ankle_z)]
            prefix = "front_" if front else ""
            names = [prefix + n + side for n in ("thigh", "shin", "foot", "toe")]
            if not all(n in anchors for n in names):
                continue
            # Keep the warped toe and its descendants attached to the new foot.
            toe = fr.to(np.array(anchors[names[3]][0]))[0]
            joints.append(toe)
            for i, n in enumerate(names[:3]):
                anchors[n] = (Vector(fr.back(joints[i])[0]), Vector(fr.back(joints[i + 1])[0]))


def fit_warp(meta, p, old, body):
    if body == "quadruped":
        fwd, cue = facing_quadruped(p)
    else:
        fwd, cue = facing_biped(p)
    fr = Frame(p[:, :2].mean(0), yaw_to_face_neg_y(fwd), p[:, 2].min())
    q = fr.to(p)
    s_ = -q[:, 1]
    h = q[:, 2].max()
    k = 4 if body == "quadruped" else 2
    c = ground_contacts(np.column_stack([q[:, :2], q[:, 2]]), k)
    cs = -c[:, 1]
    o = np.argsort(cs)
    lm = {"cue": cue, "tail": s_.min(), "nose": s_.max(), "top": h}
    if body == "quadruped":
        lm["s_hind"], lm["s_front"] = cs[o[:2]].mean(), cs[o[2:]].mean()
        lm["half"] = (abs(c[o[0], 0] - c[o[1], 0]) + abs(c[o[2], 0] - c[o[3], 0])) / 4
        mid_s = (lm["s_hind"] + lm["s_front"]) / 2
        span = lm["s_front"] - lm["s_hind"]
    else:
        lm["s_hind"] = cs.mean()
        lm["half"] = abs(c[0, 0] - c[1, 0]) / 2
        lm["wing"] = np.abs(q[:, 0]).max()
        mid_s = lm["s_hind"]
        span = 0.3 * (lm["nose"] - lm["tail"])
    col = q[(np.abs(s_ - mid_s) < 0.15 * span) & (np.abs(q[:, 0]) < max(0.5 * lm["half"], 0.02 * h))]
    trunk_points = col[col[:, 2] > 0.03 * h]
    if len(trunk_points) < 10:
        trunk_points = q[(np.abs(s_ - mid_s) < 0.3 * span)]
    lm["belly"] = np.percentile(trunk_points[:, 2], 1)
    lm["back"] = np.percentile(trunk_points[:, 2], 99)
    ref = _meta_ref(meta, old, body)
    if body == "quadruped":
        s_src = [ref["tail"], ref["s_hind"], ref["s_front"], ref["nose"]]
        s_dst = [lm["tail"], lm["s_hind"], lm["s_front"], lm["nose"]]
    else:
        s_src = [ref["tail"], ref["s_hind"], ref["nose"]]
        s_dst = [lm["tail"], lm["s_hind"], lm["nose"]]
    s_src, s_dst = monotone(s_src, 1e-6 * ref["top"]), monotone(s_dst, 1e-6 * h)
    depth = lm["back"] - lm["belly"]
    trunk = lm["belly"] + (0.82 if body == "quadruped" else 0.5) * depth
    root_z = lm["belly"] + (0.7 if body == "quadruped" else 0.3) * depth
    z_src = monotone([0.0, ref["root_z"], max(ref["spine_z"], ref["root_z"] + 1e-3 * ref["top"]), ref["top"]], 1e-6 * ref["top"])
    z_dst = monotone([0.0, root_z, trunk, h], 1e-6 * h)
    if body == "bird":
        x_src = [0.0, ref["half"], ref["wing"]]
        x_dst = monotone([0.0, lm["half"], max(lm["wing"], lm["half"] * 1.5)], 1e-6 * h)
    else:
        x_src, x_dst = [0.0, ref["half"]], [0.0, lm["half"]]
    inv = meta.matrix_world.inverted()

    def mp(v):
        a = np.array(inv @ v)
        x = math.copysign(pw(abs(a[0]), x_src, x_dst), a[0])
        return Vector(fr.back(np.array([x, -pw(-a[1], s_src, s_dst), pw(a[2], z_src, z_dst)]))[0])
    anchors = {n: (mp(v[0]), mp(v[1])) for n, v in old.items()}
    if body == "quadruped":
        fit_quadruped_legs(q, c, lm, anchors, fr)
    lm = {k2: round(float(v), 4) if not isinstance(v, str) else v for k2, v in lm.items()}
    return anchors, fr, lm


# ---------------------------------------------------------------- entry point
def auto_fit(meta, meshes, body=None, samples=60000):
    """Fit metarig `meta` to `meshes`. Returns a JSON-able report."""
    bpy.context.view_layer.objects.active = meta
    for o in bpy.context.selected_objects:
        o.select_set(False)
    meta.select_set(True)
    p = sample_surface(meshes, samples)
    body = body or detect_body(p)
    # Keep template coordinates intact: each fitting map computes its own scale.
    # Applying a mesh-height scale here makes the canonical landmarks scale twice.
    h = np.ptp(p[:, 2])
    bpy.context.view_layer.update()
    bpy.ops.object.mode_set(mode="EDIT")
    old = edit_points(meta)
    if body == "humanoid":
        anchors, fr, lm = fit_humanoid(meta, p, old)
    elif body in ("quadruped", "bird"):
        anchors, fr, lm = fit_warp(meta, p, old, body)
    else:
        bpy.ops.object.mode_set(mode="OBJECT")
        raise ValueError(f"auto-fit: unsupported body type {body!r}")
    placed = propagate(meta, old, anchors)
    write_bones(meta, placed)
    bpy.ops.object.mode_set(mode="OBJECT")
    quality = score_fit(meta, meshes, body, fr, p)
    return {"body": body, "facing_yaw_deg": round(math.degrees(fr.yaw), 1), "landmarks": lm,
            "anchored": len(anchors), "bones": len(placed), **quality}


def score_fit(meta, meshes, body, frame, points=None):
    """Geometry diagnostics, reusable after manual edits without refitting.

    Midpoint containment remains diagnostic only. Surface clearance tolerates
    thin/open limbs; worst-chain clearance, local leg axes and bilateral height
    disagreement prevent well-fitted trunk bones from hiding a displaced leg.
    All distances in the report are percentages of mesh height.
    """
    p = sample_surface(meshes) if points is None else points
    h = np.ptp(p[:, 2])
    # Ray intersections are performed at unit height, including millimetre assets.
    # Blender's BVH arithmetic otherwise loses thin toes and overlapping surfaces.
    origin = Vector(p.mean(0))
    bvhs = [build_bvh([m], origin, h) for m in meshes]
    minor = ("face", "lip", "brow", "lid", "nose", "cheek", "jaw", "chin", "teeth", "tongue", "ear", "temple",
             "forehead", "eye", "f_", "r_", "t_", "palm", "thumb", "index", "middle", "ring", "pinky", "toe", "heel",
             "breast", "pelvis", "beak", "skull", "w_feather", "n_feather", "toes_parent")
    core = [b for b in meta.data.bones if b.use_deform and not b.name.lower().startswith(minor)
            and b.length >= 0.03 * h]
    mids = [meta.matrix_world @ ((b.head_local + b.tail_local) / 2) for b in core]
    inside_n = sum(any(inside(bv, (v - origin) / h, eps=1e-6) for bv in bvhs) for v in mids)
    ratio = inside_n / max(len(mids), 1)
    chains = (("thigh", "shin", "foot"), ("upper_arm", "forearm", "hand")) if body == "humanoid" else (
        ("thigh", "shin", "foot"), ("front_thigh", "front_shin", "front_foot")) if body == "quadruped" else (
        ("thigh", "shin", "foot"), ("Wing", "Wing.001", "Wing.002"))
    chain_errors, axis_errors, asymmetry, vertical_asymmetry = {}, {}, [], []
    q = frame.to(p)
    # Compact horizontal sections give an independent medial-axis check on
    # distal legs. Broad/merged torso sections cannot identify an isolated leg.
    ceiling = {"humanoid": .4, "quadruped": .4, "bird": .22}[body] * h

    def section_error(v):
        v = frame.to(np.array(v))[0]
        if not .025 * h < v[2] < ceiling:
            return None
        section = q[np.abs(q[:, 2] - v[2]) < .008 * h]
        comps = components_2d(section[:, :2], .012 * h)
        comps = [ix for ix in comps if len(ix) >= 8]
        if not comps:
            return None
        # Select the local component before rejecting broad/merged sections.
        # Otherwise a nearby merged leg would be compared with a distant foot.
        ix = min(comps, key=lambda ix: np.min(np.linalg.norm(section[ix, :2] - v[:2], axis=1)))
        xy = section[ix, :2]
        if np.max(np.ptp(xy, axis=0)) >= .16 * h:
            return None
        centre = np.percentile(xy, [10, 90], axis=0).mean(0)
        return np.linalg.norm(v[:2] - centre) / h

    for chain in chains:
        for side in ("L", "R"):
            errors, axis = [], []
            for name in chain:
                bone = meta.data.bones.get(name + "." + side)
                if bone is None:
                    continue
                for t in (0., .25, .5, .75, 1.):
                    v = meta.matrix_world @ bone.head_local.lerp(bone.tail_local, t)
                    if name in ("shin", "front_shin") and t in (.25, .5, .75):
                        error = section_error(v)
                        if error is not None:
                            axis.append(error)
                    v = (v - origin) / h
                    # Distance to the union of surfaces, zero inside any part.
                    distances = [bv.find_nearest(v)[3] for bv in bvhs]
                    distance = min((d for d in distances if d is not None), default=1.)
                    if distance > .005 and any(inside(bv, v, eps=1e-6) for bv in bvhs):
                        distance = 0.
                    errors.append(distance)
                other = meta.data.bones.get(name + ".R")
                if side == "L" and other:
                    a = frame.to(np.array(meta.matrix_world @ bone.head_local))[0]
                    b = frame.to(np.array(meta.matrix_world @ other.head_local))[0]
                    # Compare sagittal coordinates, independent of a lateral
                    # frame offset from a tail or outstretched hand.
                    asymmetry.append(np.linalg.norm(a[1:] - b[1:]) / h)
                    vertical_asymmetry.append(abs(a[2] - b[2]) / h)
            if errors:
                chain_errors[chain[0] + "." + side] = float(np.percentile(errors, 90))
            if axis:
                axis_errors[chain[0] + "." + side] = float(np.percentile(axis, 90))
    clearance = max(chain_errors.values(), default=1.)
    symmetry = max(asymmetry, default=0.)
    # Longitudinal L/R offsets can be a supported staggered stance.
    # Grade their agreement with local sections, retaining raw asymmetry as
    # a diagnostic; unequal joint heights remain a separate warning.
    vertical = max(vertical_asymmetry, default=0.)
    medial = max(axis_errors.values(), default=0.)
    severity = max(clearance, medial, vertical) / .04
    quality = "good" if severity <= 1 else "review" if severity <= 2 else "poor"
    return {"inside_ratio": round(ratio, 3), "quality": quality,
            "quality_score": round(max(0., 1. - severity / 3.), 3),
            "max_chain_surface_pct_height": round(100 * clearance, 3),
            "max_lr_asymmetry_pct_height": round(100 * symmetry, 3),
            "max_lr_height_asymmetry_pct_height": round(100 * vertical, 3),
            "max_chain_axis_pct_height": round(100 * medial, 3),
            "chain_axis_pct_height": {k: round(100 * v, 3) for k, v in axis_errors.items()},
            "chain_surface_pct_height": {k: round(100 * v, 3) for k, v in chain_errors.items()}}
