#!/usr/bin/env python3
"""watoom-texture-layering: decide what happens to foliage after a creek was carved deeper (planner only; numpy + pillow).

After unreal_creek_profile.py lowers the bed, plants and trees that stood on the old ground hang in the air, and ones in the deep
middle would stand 7 m under water. This plans, for every foliage instance near the creek:
  remove  the ground under it is more than --keep-depth-cm below the water level (the deep middle of the creek),
  refit   it stands on the shallow edge or bank and the new ground is more than --tol-cm away from its Z: remove and add again at the new Z,
  keep    everything else.
Trees at the shallow edges are kept on purpose: they may stand in the shallow water at the sides of the creek.

  plan(instances, new_raw, z0, raw_per_cm, px_cm, samples, reach_cm, keep_depth_cm=150, tol_cm=15) -> {"remove": [...], "add": [...], "kept": n}
instances: [{"type": path, "index": i, "x", "y", "z", "rotation": {...}, "scale": {...}}, ...] as foliage.get_instances returns them.
samples: dense creek line (x, y, water_z) from unreal_creek_profile.hermite. The driver is tools/rig-ue-mcp/ue_creek_foliage.py.
"""
import numpy as np


def ground_z(raw, x, y, z0, raw_per_cm, px_cm):
    """Bilinear ground height in world cm at world (x, y)."""
    n, m = raw.shape
    gx = np.clip(x / px_cm, 0, m - 1.001)
    gy = np.clip(y / px_cm, 0, n - 1.001)
    j, i = int(gx), int(gy)
    fx, fy = gx - j, gy - i
    h = (raw[i, j] * (1 - fx) * (1 - fy) + raw[i, j + 1] * fx * (1 - fy) + raw[i + 1, j] * (1 - fx) * fy + raw[i + 1, j + 1] * fx * fy)
    return float(h) / raw_per_cm + z0


def nearest(samples, x, y):
    d = np.hypot(samples[:, 0] - x, samples[:, 1] - y)
    j = int(d.argmin())
    return float(d[j]), float(samples[j, 2])


def plan(instances, new_raw, z0, raw_per_cm, px_cm, samples, reach_cm, keep_depth_cm=150.0, tol_cm=15.0):
    remove, add, kept = [], [], 0
    for it in instances:
        s, wz = nearest(samples, it["x"], it["y"])
        if s > reach_cm:
            kept += 1
            continue
        gz = ground_z(new_raw, it["x"], it["y"], z0, raw_per_cm, px_cm)
        if wz - gz > keep_depth_cm:
            remove.append({"type": it["type"], "index": it["index"]})
        elif abs(gz - it["z"]) > tol_cm:
            remove.append({"type": it["type"], "index": it["index"]})
            add.append({"type": it["type"], "location": {"x": it["x"], "y": it["y"], "z": gz},
                        "rotation": it.get("rotation", {"pitch": 0, "yaw": 0, "roll": 0}), "scale": it.get("scale", {"x": 1, "y": 1, "z": 1})})
        else:
            kept += 1
    return {"remove": remove, "add": add, "kept": kept}
