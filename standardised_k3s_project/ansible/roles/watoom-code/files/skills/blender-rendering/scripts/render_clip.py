"""Render an animation clip (Action on a rig, or scene animation) to a verified MP4 + contact sheet.

Frames the camera on the evaluated, deformed bounds of the WHOLE clip (not first/last
frames), stages a floor and three-point light rig scaled to the subject, renders with
Cycles CPU + denoising, encodes H.264/yuv420p, then checks the file with ffprobe.
Skeleton-only rigs (e.g. a retarget onto a metarig) get a proxy mannequin from bones.
The .blend is not saved; output goes to a fresh directory.

Usage:
  blender -b f.blend -P render_clip.py -- --out DIR [--armature Rig] [--action Name]
      [--frames 1-120] [--fps 30] [--res 720 720] [--samples 16]
      [--camera three-quarter|front|side|orbit|follow] [--proxy auto|on|off]
      [--max-seconds 840] [--ffmpeg /usr/bin/ffmpeg] [--keep-frames] [--no-isolate]
  MCP: import render_clip as r; print(r.run(out="/tmp/clip", action="Walk"))
Returns the MP4, contact sheet, ffprobe facts, seconds per frame and SHA-256 hashes.
"""
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

CAMERAS = {"front": (0, -1, 0.18), "three-quarter": (0.75, -1, 0.3), "side": (1, 0, 0.18),
           "orbit": None, "follow": (0.75, -1, 0.3)}


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _frames(spec, scene, action):
    if spec:
        a, b = (int(x) for x in str(spec).split("-", 1))
    elif action:
        a, b = (int(round(v)) for v in action.frame_range)
    else:
        a, b = scene.frame_start, scene.frame_end
    if b <= a:
        raise ValueError("A clip needs at least 2 frames")
    if b - a + 1 > 2400:
        raise ValueError("At most 2400 frames per clip")
    return list(range(a, b + 1))


def _assign(armature, action_name):
    rig = None
    if armature:
        rig = bpy.data.objects.get(armature)
        if rig is None or rig.type != "ARMATURE":
            raise ValueError("Armature not found: " + armature)
    else:
        rigs = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
        rig = rigs[0] if len(rigs) == 1 else None
        if action_name and rig is None:
            raise ValueError("Several or no armatures; pass --armature")
    action = None
    if action_name:
        action = bpy.data.actions.get(action_name)
        if action is None:
            raise ValueError("Action not found: " + action_name)
        ad = rig.animation_data_create()
        for track in ad.nla_tracks:  # show exactly this Action
            track.mute = True
        ad.action = action
        # Layered actions (Blender 4.4+) only animate through an assigned slot.
        if getattr(ad, "action_slot", 1) is None and ad.action_suitable_slots:
            ad.action_slot = ad.action_suitable_slots[0]
    elif rig and rig.animation_data:
        action = rig.animation_data.action
    return rig, action


def _bound_meshes(rig):
    scene_meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.visible_get()]
    if rig is None:
        return scene_meshes
    return [o for o in scene_meshes if o.parent == rig or o.find_armature() == rig]


def _proxy(rig):
    """Capsule-like proxy per deform bone so skeleton-only rigs are visible."""
    mat = bpy.data.materials.new("ClipProxy")
    mat.diffuse_color = (0.62, 0.64, 0.68, 1)
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.62, 0.64, 0.68, 1)
        bsdf.inputs["Roughness"].default_value = 0.55
    made = []
    bones = [b for b in rig.data.bones if b.use_deform and b.length > 0.004] or [b for b in rig.data.bones if b.length > 0.004]
    for b in bones:
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=max(0.006, b.length * 0.16), depth=b.length,
                                            location=(0, b.length / 2, 0), rotation=(math.pi / 2, 0, 0))
        ob = bpy.context.object
        ob.name = "ClipProxy_" + b.name
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)
        ob.data.materials.append(mat)
        for poly in ob.data.polygons:
            poly.use_smooth = True
        ob.parent = rig
        ob.parent_type = "BONE"
        ob.parent_bone = b.name
        # Bone parenting attaches at the tail; shift back to the head in bone space.
        ob.matrix_parent_inverse = Matrix.Translation((0, -b.length, 0))
        made.append(ob)
    return made


def _clip_bounds(meshes, frames, scene):
    lo = Vector((math.inf,) * 3)
    hi = Vector((-math.inf,) * 3)
    centres = {}
    step = max(1, len(frames) // 240)  # cap evaluation cost on very long clips
    sampled = frames[::step] + ([frames[-1]] if frames[-1] not in frames[::step] else [])
    for f in sampled:
        scene.frame_set(f)
        deps = bpy.context.evaluated_depsgraph_get()
        flo = Vector((math.inf,) * 3)
        fhi = Vector((-math.inf,) * 3)
        for ob in meshes:
            ev = ob.evaluated_get(deps)
            for c in ev.bound_box:
                p = ev.matrix_world @ Vector(c)
                for i in range(3):
                    flo[i] = min(flo[i], p[i])
                    fhi[i] = max(fhi[i], p[i])
        centres[f] = (flo + fhi) / 2
        for i in range(3):
            lo[i] = min(lo[i], flo[i])
            hi[i] = max(hi[i], fhi[i])
    if not math.isfinite(lo.x):
        raise ValueError("Nothing visible to frame")
    return lo, hi, centres, sampled


def _stage(scene, lo, hi):
    size = max((hi - lo).length, 0.1)
    centre = (lo + hi) / 2
    world = bpy.data.worlds.new("ClipWorld")
    scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.045, 0.048, 0.055, 1)
        bg.inputs["Strength"].default_value = 1.0
    bpy.ops.mesh.primitive_plane_add(size=size * 12, location=(centre.x, centre.y, lo.z - size * 0.002))
    floor = bpy.context.object
    floor.name = "ClipFloor"
    fm = bpy.data.materials.new("ClipFloor")
    fbsdf = fm.node_tree.nodes.get("Principled BSDF") if fm.node_tree else None
    if fbsdf:
        fbsdf.inputs["Base Color"].default_value = (0.16, 0.165, 0.175, 1)
        fbsdf.inputs["Roughness"].default_value = 0.8
    floor.data.materials.append(fm)
    for name, offset, energy, scale in (("Key", (1.2, -1.4, 1.6), 900, 0.9), ("Fill", (-1.6, -0.8, 0.9), 260, 1.4),
                                        ("Rim", (-0.4, 1.6, 1.8), 520, 0.7)):
        light = bpy.data.lights.new("Clip" + name, "AREA")
        light.energy = energy * size * size / 4
        light.size = size * scale
        ob = bpy.data.objects.new(light.name, light)
        scene.collection.objects.link(ob)
        ob.location = centre + Vector(offset) * size
        ob.rotation_euler = (centre - ob.location).to_track_quat("-Z", "Y").to_euler()
    return floor


def _camera(scene, mode, lo, hi, res):
    data = bpy.data.cameras.new("ClipCamera")
    data.lens = 50
    data.sensor_fit = "AUTO"
    cam = bpy.data.objects.new("ClipCamera", data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    centre = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 0.05)
    aspect = res[0] / res[1]
    fov = 2 * math.atan(data.sensor_width / (2 * data.lens))
    narrow = fov if aspect >= 1 else 2 * math.atan(math.tan(fov / 2) * aspect)
    distance = radius / math.sin(narrow / 2) * 1.06
    data.clip_start = max(0.001, distance / 1000)
    data.clip_end = distance * 50
    return cam, centre, distance


def _place(cam, mode, centre, distance, frame_index, total, follow_centre=None):
    target = follow_centre if (mode == "follow" and follow_centre is not None) else centre
    if mode == "orbit":
        angle = 2 * math.pi * frame_index / total
        direction = Vector((math.sin(angle), -math.cos(angle), 0.25)).normalized()
    else:
        direction = Vector(CAMERAS[mode]).normalized()
    cam.location = target + direction * distance
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()


def _probe(ffprobe, path):
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                          "stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames:format=duration",
                          "-of", "json", path], capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise RuntimeError("ffprobe failed: " + out.stderr[-300:])
    data = json.loads(out.stdout)
    s = data["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    return {"codec": s["codec_name"], "pix_fmt": s["pix_fmt"], "width": s["width"], "height": s["height"],
            "fps": round(num / den, 3), "frames": int(s["nb_read_frames"]), "duration": float(data["format"]["duration"])}


def run(out, armature=None, action=None, frames=None, fps=None, res=None, samples=16, camera="three-quarter",
        proxy="auto", max_seconds=840, ffmpeg=None, keep_frames=False, isolate=True, **_):
    started = time.monotonic()
    if camera not in CAMERAS:
        raise ValueError("camera: " + ", ".join(CAMERAS))
    out = os.path.abspath(out)
    os.makedirs(out, exist_ok=False)
    ffmpeg = ffmpeg or shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe", path=os.path.dirname(ffmpeg)) if ffmpeg else None
    ffprobe = ffprobe or shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg and ffprobe are required for MP4 output")
    res = [int(v) for v in (res or (720, 720))]
    if any(v < 64 or v > 2048 or v % 2 for v in res):
        raise ValueError("res: even values in 64..2048")
    scene = bpy.context.scene
    rig, act = _assign(armature, action)
    clip = _frames(frames, scene, act)
    fps = int(fps or scene.render.fps)
    if not 1 <= fps <= 60:
        raise ValueError("fps: 1..60")
    meshes = _bound_meshes(rig)
    hidden = []
    if rig and isolate:
        # Only the rig and what it carries: scene props animated elsewhere are not part of the clip under review.
        keep = {rig, *meshes} | {o for o in scene.objects if o.parent == rig}
        hidden = [o for o in scene.objects if o not in keep and o.type not in ("LIGHT", "CAMERA") and not o.hide_render]
        for o in hidden:
            o.hide_render = True
    proxies = []
    if rig and (proxy == "on" or (proxy == "auto" and not meshes)):
        proxies = _proxy(rig)
        meshes = meshes + proxies
    if not meshes:
        raise ValueError("No visible mesh bound to the subject; use --proxy on for a skeleton")
    lo, hi, centres, sampled = _clip_bounds(meshes, clip, scene)
    _stage(scene, lo, hi)
    cam, centre, distance = _camera(scene, camera, lo, hi, res)
    # Smooth the follow camera: moving average of sampled per-frame centres.
    def follow(f):
        near = sorted(sampled, key=lambda s: abs(s - f))[:5]
        return sum((centres[s] for s in near), Vector()) / len(near)
    if camera == "follow":
        distance *= 0.75  # tracking the subject, so travel no longer needs to fit in frame
    r = scene.render
    r.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(samples)
    scene.cycles.use_denoising = True
    r.use_persistent_data = True
    r.resolution_x, r.resolution_y = res
    r.resolution_percentage = 100
    r.fps = fps
    r.fps_base = 1
    r.image_settings.file_format = "PNG"
    r.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    frame_dir = os.path.join(out, "frames")
    os.makedirs(frame_dir)
    times = []
    for i, f in enumerate(clip):
        t = time.monotonic()
        scene.frame_set(f)
        _place(cam, camera, centre, distance, i, len(clip), follow(f) if camera == "follow" else None)
        r.filepath = os.path.join(frame_dir, "frame-%04d.png" % (i + 1))
        bpy.ops.render.render(write_still=True)
        times.append(time.monotonic() - t)
        if i == 1:
            projected = (time.monotonic() - started) + sum(times) / len(times) * (len(clip) - 2) + 20
            if projected > max_seconds:
                raise RuntimeError("Projected %.0fs exceeds the %ss budget at %.2fs/frame; lower --samples/--res or the frame range"
                                   % (projected, max_seconds, sum(times) / len(times)))
    mp4 = os.path.join(out, "clip.mp4")
    enc = subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-framerate", str(fps), "-i",
                          os.path.join(frame_dir, "frame-%04d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4], capture_output=True, text=True, timeout=600)
    if enc.returncode:
        raise RuntimeError("ffmpeg failed: " + enc.stderr[-400:])
    probe = _probe(ffprobe, mp4)
    expected = len(clip) / fps
    problems = []
    if probe["codec"] != "h264" or probe["pix_fmt"] != "yuv420p":
        problems.append("codec/pixel format")
    if [probe["width"], probe["height"]] != res:
        problems.append("dimensions")
    if probe["frames"] != len(clip):
        problems.append("frame count %d != %d" % (probe["frames"], len(clip)))
    if abs(probe["fps"] - fps) > 0.01 or abs(probe["duration"] - expected) > 1.5 / fps:
        problems.append("timing")
    sheet = os.path.join(out, "contact-sheet.png")
    step = max(1, len(clip) // 8)
    subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-y", "-i", mp4, "-vf",
                    "select='not(mod(n\\,%d))',scale=%d:-2,tile=4x2" % (step, min(res[0], 480)), "-frames:v", "1", sheet],
                   capture_output=True, timeout=120)
    if not keep_frames:
        shutil.rmtree(frame_dir)
    report = {"ok": not problems, "problems": problems, "mp4": mp4, "mp4_sha256": _sha(mp4),
              "contact_sheet": sheet if os.path.exists(sheet) else None, "frames": [clip[0], clip[-1]], "frame_count": len(clip),
              "fps": fps, "duration_seconds": round(expected, 3), "res": res, "camera": camera, "samples": int(samples),
              "armature": rig.name if rig else None, "action": act.name if act else None, "proxy_bones": len(proxies), "isolated_hidden_objects": len(hidden),
              "bounds": {"min": list(lo), "max": list(hi)}, "probe": probe,
              "sec_per_frame": round(sum(times) / len(times), 2), "total_seconds": round(time.monotonic() - started, 1),
              "blender": bpy.app.version_string, "review": "Technical checks only; watch the clip before accepting motion or framing."}
    with open(os.path.join(out, "clip-report.json"), "w") as f:
        json.dump(report, f, indent=2, default=str)
    return report


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--armature", default=None)
    p.add_argument("--action", default=None)
    p.add_argument("--frames", default=None, help="start-end, inclusive")
    p.add_argument("--fps", type=int, default=None)
    p.add_argument("--res", nargs=2, type=int, default=None)
    p.add_argument("--samples", type=int, default=16)
    p.add_argument("--camera", default="three-quarter", choices=list(CAMERAS))
    p.add_argument("--proxy", default="auto", choices=["auto", "on", "off"])
    p.add_argument("--max-seconds", dest="max_seconds", type=int, default=840)
    p.add_argument("--ffmpeg", default=None)
    p.add_argument("--keep-frames", dest="keep_frames", action="store_true")
    p.add_argument("--no-isolate", dest="isolate", action="store_false", help="also render scene objects not carried by the rig")
    bx.cli(run, p)
