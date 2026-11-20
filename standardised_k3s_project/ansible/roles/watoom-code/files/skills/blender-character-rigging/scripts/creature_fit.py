"""creature_fit - place a game skeleton on an unrigged tailed biped (theropod dinosaur, raptor, bird-like walker) from
its surface points alone. Pure numpy (no bpy), so it is unit-tested outside Blender; creature_rig.py builds the armature.

Why (T-0023, 2026-11-19): the owner's dinosaur packs are static statues. rigify_build --add auto picks 'bird' for them and
grades the fit poor (wings placed for the small arms, staggered statue legs throw the facing off), so tailed bipeds get their
own landmark fit with a plain engine skeleton (no Rigify control rig: the clips are generated procedurally by
blender-animation/scripts/creature_gait.py).

Method (Z up, any facing, any scale):
  1. Ground = lowest point; feet = points within 4 % of height of the ground; split left/right by the body midline.
  2. Long axis = principal axis of the horizontal spread; the head end is the end whose last 10 % sits higher (a theropod
     carries its head above its tail tip). forward/left/up form the creature frame.
  3. Hips sit above the mean of the two feet; hip height = 68 % of the back height there. Each leg's knee and ankle are the centroids of that side's leg points at 55 % and 18 % of
     hip height; ball = centroid of the foot contact points; toe = the foremost contact point.
  4. Centreline = 60 % up the wide body core (core(): thin sails/crests left out) of each of 48 slices (mean lateral) along the long axis, leg points excluded. Pelvis on it above the hips;
     tail = pelvis back to the tail tip; head base = the thinnest slice (the neck) in the front 35 % of the body;
     shoulders between hips and head base.
Returned joints are world-space; bones are UE-mannequin-like names: root, pelvis, spine_01..03, neck_01..02, head,
tail_01..N, thigh_l/r, calf_l/r, foot_l/r, ball_l/r.
"""
import numpy as np


def _frame(p, ground):
    xy = p[:, :2] - p[:, :2].mean(0)
    _, _, vt = np.linalg.svd(xy, full_matrices=False)
    ax = np.array([vt[0, 0], vt[0, 1], 0.0])
    u = p @ ax
    lo, hi = u.min(), u.max()
    span = hi - lo
    z_hi = p[u > hi - 0.1 * span, 2].mean()
    z_lo = p[u < lo + 0.1 * span, 2].mean()
    fwd = ax if z_hi >= z_lo else -ax
    up = np.array([0.0, 0.0, 1.0])
    left = np.cross(up, fwd)
    return fwd, left, up


def _centroid(pts, fallback):
    return pts.mean(0) if len(pts) else np.asarray(fallback, float)


def trace_leg(pts, foot_uv, hip_h, radius, steps=24):
    """pts (N,3) in (u, v, h); returns the leg centre path [(u, v, h)] from the foot up to the hip height."""
    cur = np.asarray(foot_uv, float)
    path = []
    dz = hip_h / steps
    for i in range(steps + 1):
        z = i * dz
        m = (np.abs(pts[:, 2] - z) < 0.6 * dz) & (np.hypot(pts[:, 0] - cur[0], pts[:, 1] - cur[1]) < radius)
        if m.sum() >= 3:
            cur = 0.5 * cur + 0.5 * pts[m, :2].mean(0)  # damped: one noisy slice cannot jump to the other leg
        path.append((cur[0], cur[1], z))
    return np.array(path)


def core(h, v, bins=16, keep=0.25):
    """(lo, hi) height range of the wide body core of one slice: height bins at least `keep` x the widest bin's lateral width.
    Thin vertical structures (a Spinosaurus sail, a crest, spikes) are left out, so they cannot lift the spine."""
    if len(h) < 3:
        return float(h.min()), float(h.max())
    edges = np.linspace(h.min(), h.max() + 1e-9, bins + 1)
    idx = np.clip(np.digitize(h, edges) - 1, 0, bins - 1)
    width = np.array([np.ptp(v[idx == i]) if (idx == i).sum() > 1 else 0.0 for i in range(bins)])
    ok = np.nonzero(width >= keep * width.max())[0]
    return float(edges[ok.min()]), float(edges[ok.max() + 1])


def main_cluster(u, gap):
    """Mask of the largest run of u values with no gap over `gap` (a foot, not a hand or tail tip touching the ground)."""
    order = np.argsort(u)
    breaks = np.nonzero(np.diff(u[order]) > gap)[0]
    runs = np.split(order, breaks + 1)
    best = max(runs, key=len)
    m = np.zeros(len(u), bool)
    m[best] = True
    return m


def fit(points, tail_bones=6):
    """points: (N, 3) surface samples. Returns {'joints': {name: (head, tail)}, 'parents': {...}, 'frame': ..., 'report': ...}."""
    p = np.asarray(points, float)
    z0 = p[:, 2].min()
    H = p[:, 2].max() - z0
    fwd, left, up = _frame(p, z0)
    u, v, h = p @ fwd, p @ left, p[:, 2] - z0
    L = u.max() - u.min()

    feet = h < 0.04 * H
    if feet.sum() < 4:
        raise ValueError("no ground contact found (needs a standing pose)")
    v_mid = np.median(v[h > 0.5 * H]) if (h > 0.5 * H).any() else np.median(v)
    side = {"l": feet & (v >= v_mid), "r": feet & (v < v_mid)}
    if side["l"].sum() < 2 or side["r"].sum() < 2:
        raise ValueError("found one foot only; tailed-biped fit needs two feet on the ground")
    for s_ in side:  # keep each side's biggest contact patch: a hand or the tail tip on the ground is not a foot (Spinosaurus)
        idx = np.nonzero(side[s_])[0]
        keep = idx[main_cluster(u[idx], 0.04 * L)]
        side[s_] = np.zeros(len(u), bool)
        side[s_][keep] = True
    foot_u = {s: u[m].mean() for s, m in side.items()}
    hip_u = 0.5 * (foot_u["l"] + foot_u["r"])
    step = abs(foot_u["l"] - foot_u["r"])

    # body centreline height at the hips (points above the leg region)
    band = np.abs(u - hip_u) < max(0.03 * L, 0.5 * step + 0.02 * L)
    body_z = h[band & (h > 0.35 * H)]
    if not len(body_z):
        raise ValueError("no body above the feet")
    # acetabulum ~2/3 of the back height over the feet (measured on the T-Rex statue); the back = top of the wide body core
    hip_h = 0.68 * core(body_z, v[band & (h > 0.35 * H)])[1]

    # leg points: below the hip, near the feet along the body
    reach = 0.5 * step + 0.12 * L
    legs = (h < hip_h) & (np.abs(u - hip_u) < reach)
    j = {}

    def W(uu, vv, hh):
        return uu * fwd + vv * left + (hh + z0) * up

    for s, sgn in (("l", 1), ("r", -1)):
        mine = legs & ((v >= v_mid) if sgn > 0 else (v < v_mid))
        top = mine & (h > 0.85 * hip_h)
        hip_v = v[top].mean() if top.any() else v_mid + sgn * 0.1 * L
        hip = W(hip_u, hip_v, hip_h)
        contact = side[s]
        # trace the leg up from its own foot: each height step keeps only points near the previous centroid, so a staggered
        # statue leg is followed and the other leg or the belly never pull it (2026-11-19: whole-side slices put the rear
        # T-Rex knee on the front leg)
        path = trace_leg(np.c_[u, v, h][mine], (u[contact].mean(), v[contact].mean()), hip_h, 0.07 * L)
        at_h = lambda frac: np.array([np.interp(frac * hip_h, path[:, 2], path[:, k]) for k in (0, 1)] + [frac * hip_h])
        kn, an = at_h(0.55), at_h(0.18)
        ball = (u[contact].mean(), v[contact].mean(), 0.02 * H)
        toe_i = np.argmax(np.where(contact, u, -np.inf))
        toe = (u[toe_i], v[contact].mean(), 0.01 * H)
        knee, ankle = W(*kn), W(*an)
        j["thigh_" + s] = (hip, knee)
        j["calf_" + s] = (knee, ankle)
        j["foot_" + s] = (ankle, W(*ball))
        j["ball_" + s] = (W(*ball), W(*toe) if toe[0] - ball[0] > 0.01 * L else W(ball[0] + 0.03 * L, ball[1], ball[2]))

    # centreline along the body, legs excluded
    body = ~legs
    edges = np.linspace(u[body].min(), u[body].max(), 49)
    cl, thick = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        m = body & (u >= a) & (u <= b)
        if m.sum() < 3:
            continue
        lo, hi = core(h[m], v[m])
        cl.append(((a + b) / 2, v[m].mean(), lo + 0.6 * (hi - lo)))  # spine sits above the middle of the body core
        thick.append(hi - lo)
    cl, thick = np.array(cl), np.array(thick)

    def at(uu):
        return W(uu, np.interp(uu, cl[:, 0], cl[:, 1]), np.interp(uu, cl[:, 0], cl[:, 2]))

    nose_u, tail_u = cl[-1, 0], cl[0, 0]
    front = (cl[:, 0] > nose_u - 0.35 * (nose_u - hip_u)) & (cl[:, 0] < nose_u - 0.06 * L)
    head_u = cl[front, 0][np.argmin(thick[front])] if front.any() else nose_u - 0.15 * L
    shoulder_u = head_u - 0.3 * (head_u - hip_u)
    pelvis_tail_u = hip_u + 0.15 * (shoulder_u - hip_u)

    root_at = W(hip_u, v_mid, 0.0)
    j["root"] = (root_at, root_at + up * 0.1 * H)
    j["pelvis"] = (at(hip_u), at(pelvis_tail_u))
    sp = np.linspace(pelvis_tail_u, shoulder_u, 4)
    for i in range(3):
        j["spine_%02d" % (i + 1)] = (at(sp[i]), at(sp[i + 1]))
    nk = np.linspace(shoulder_u, head_u, 3)
    for i in range(2):
        j["neck_%02d" % (i + 1)] = (at(nk[i]), at(nk[i + 1]))
    j["head"] = (at(head_u), at(nose_u))
    tl = np.linspace(hip_u, tail_u, tail_bones + 1)
    for i in range(tail_bones):
        j["tail_%02d" % (i + 1)] = (at(tl[i]), at(tl[i + 1]))
    # the first tail bone starts at the pelvis head, so tail and spine share the hip joint
    parents = {"root": None, "pelvis": "root", "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02",
               "neck_01": "spine_03", "neck_02": "neck_01", "head": "neck_02", "tail_01": "pelvis"}
    for i in range(2, tail_bones + 1):
        parents["tail_%02d" % i] = "tail_%02d" % (i - 1)
    for s in "lr":
        parents.update({"thigh_" + s: "pelvis", "calf_" + s: "thigh_" + s, "foot_" + s: "calf_" + s, "ball_" + s: "foot_" + s})
    report = {"height": float(H), "length": float(L), "hip_height": float(hip_h), "step": float(step),
              "head_base_from_nose_pct": float(100 * (nose_u - head_u) / L),
              "knee_forward": {s: float((j["calf_" + s][0] - j["thigh_" + s][0]) @ fwd) for s in "lr"},
              "facing": [float(x) for x in fwd]}
    return {"joints": {k: (np.asarray(a).tolist(), np.asarray(b).tolist()) for k, (a, b) in j.items()},
            "parents": parents, "frame": {"forward": fwd.tolist(), "left": left.tolist(), "up": up.tolist()},
            "report": report}
