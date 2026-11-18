"""Render stills/animations with quality presets, per-camera batches, any output format.

Presets: preview (fast look-dev), final (production), product (clean, transparent bg).
Formats: PNG, JPEG, EXR (half float), EXR_MULTI (all passes), MP4 (H.264), WEBM.
Usage:
  blender -b f.blend -P render_batch.py -- [--engine CYCLES|BLENDER_EEVEE|BLENDER_WORKBENCH]
      [--preset preview|final|product] [--res 1920 1080] [--percent 100] [--samples N]
      [--out //render/shot_####] [--format PNG] [--frames 1-120 | 1,12,24] [--cameras CamA CamB]
      [--view AgX|"Khronos PBR Neutral"|Standard] [--look "AgX - Punchy"] [--transparent] [--device GPU|CPU]
  MCP: import render_batch as r; print(r.run(preset="preview", frames="1"))
Returns written files and seconds per image.
"""
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(__file__))
import _bpyx as bx  # noqa: E402

PRESETS = {
    "preview": {"cycles": dict(samples=64, adaptive_threshold=0.05, use_denoising=True),
                "eevee": dict(taa_render_samples=16, use_raytracing=False), "percent": 50},
    "final": {"cycles": dict(samples=512, adaptive_threshold=0.01, use_denoising=True),
              "eevee": dict(taa_render_samples=128, use_raytracing=True), "percent": 100},
    "product": {"cycles": dict(samples=1024, adaptive_threshold=0.005, use_denoising=True),
                "eevee": dict(taa_render_samples=256, use_raytracing=True), "percent": 100,
                "transparent": True},
}
FORMATS = {"PNG": ("IMAGE", "PNG", ".png"), "JPEG": ("IMAGE", "JPEG", ".jpg"),
           "EXR": ("IMAGE", "OPEN_EXR", ".exr"), "EXR_MULTI": ("MULTI_LAYER_IMAGE", "OPEN_EXR_MULTILAYER", ".exr"),
           "MP4": ("VIDEO", "FFMPEG", ".mp4"), "WEBM": ("VIDEO", "FFMPEG", ".webm")}


def _gpu(sc, device):
    return bx.configure_device(sc, device)

def _frames(spec, sc):
    if not spec:
        return [sc.frame_current]
    out = []
    for part in str(spec).split(","):
        if "-" in part.strip().lstrip("-"):
            a, b = part.strip().lstrip("-").split("-", 1)
            a = -int(a) if part.strip().startswith("-") else int(a)
            out += list(range(a, int(b) + 1))
        else:
            out.append(int(part))
    if not out:
        raise ValueError("frame spec %r selects no frames" % spec)
    return out


def _cameras(names, sc):
    if not names:
        if sc.camera is None:
            raise ValueError("scene has no camera (see blender-lighting-lookdev)")
        return [sc.camera]
    cams = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "CAMERA":
            raise ValueError("not a camera object: %s" % name)
        cams.append(obj)
    return cams


def run(engine=None, preset="preview", res=None, percent=None, samples=None, out="//render/####",
        format="PNG", frames=None, cameras=None, view=None, look=None, transparent=None,  # noqa: A002
        device="AUTO", **_):
    sc = bpy.context.scene
    r = sc.render
    if engine:
        bx.set_enum(r, "engine", engine)
    pr = PRESETS[preset]
    info = {"engine": r.engine}
    if r.engine == "CYCLES":
        info["device"] = _gpu(sc, device)
        for k, v in pr["cycles"].items():
            setattr(sc.cycles, k, v)
        sc.cycles.use_adaptive_sampling = True
        if samples:
            sc.cycles.samples = samples
        if info["device"] == "OPTIX":
            sc.cycles.denoiser = "OPTIX"
        else:
            sc.cycles.denoiser = "OPENIMAGEDENOISE"
    elif r.engine == "BLENDER_EEVEE":
        for k, v in pr["eevee"].items():
            setattr(sc.eevee, k, v)
        if samples:
            sc.eevee.taa_render_samples = samples
    if res:
        r.resolution_x, r.resolution_y = res
    r.resolution_percentage = percent or pr["percent"]
    r.film_transparent = pr.get("transparent", False) if transparent is None else transparent
    if view:
        bx.set_enum(sc.view_settings, "view_transform", view)
    if look:
        bx.set_enum(sc.view_settings, "look", look)
    media, fmt, ext = FORMATS[format]
    s = r.image_settings
    if hasattr(s, "media_type"):
        s.media_type = media
    s.file_format = fmt
    if fmt in ("OPEN_EXR", "OPEN_EXR_MULTILAYER"):
        s.color_depth, s.exr_codec = "16", "DWAA"
    elif fmt == "PNG":
        s.color_mode = "RGBA" if r.film_transparent else "RGB"
    if media == "VIDEO":
        r.ffmpeg.format = "MPEG4" if format == "MP4" else "WEBM"
        r.ffmpeg.codec = "H264" if format == "MP4" else "AV1"
        r.ffmpeg.constant_rate_factor = "HIGH"
    if r.film_transparent and fmt == "JPEG":
        info["warning"] = "JPEG has no alpha; use PNG/EXR for transparent renders"
    cams = _cameras(cameras, sc)
    base = bpy.path.abspath(out)
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    files, times = [], []
    for cam in cams:
        sc.camera = cam
        stem = base.replace("####", "") if len(cams) == 1 else f"{base.replace('####', '')}{cam.name}_"
        if media == "VIDEO":
            fr = _frames(frames, sc)
            sc.frame_start, sc.frame_end = fr[0], fr[-1]
            r.filepath = stem
            t = time.time()
            bpy.ops.render.render(animation=True)
            times.append(time.time() - t)
            # Movie names carry the frame range (e.g. shot_0001-0120.mp4); ask Blender for it.
            files.append(bpy.path.abspath(r.frame_path(frame=sc.frame_start)))
            continue
        for f in _frames(frames, sc):
            sc.frame_set(f)
            path = f"{stem}{f:04d}{ext}"
            r.filepath = path
            t = time.time()
            bpy.ops.render.render(write_still=True)
            times.append(time.time() - t)
            files.append(path)
    info.update({"ok": bool(files) and all(os.path.exists(f) for f in files), "files": files,
                 "sec_per_image": round(sum(times) / max(len(times), 1), 2),
                 "res": [r.resolution_x * r.resolution_percentage // 100,
                         r.resolution_y * r.resolution_percentage // 100],
                 "view": sc.view_settings.view_transform})
    return info


if __name__ == "__main__":
    p = bx.parser(__doc__)
    p.add_argument("--engine", default=None)
    p.add_argument("--preset", default="preview", choices=list(PRESETS))
    p.add_argument("--res", nargs=2, type=int, default=None)
    p.add_argument("--percent", type=int, default=None)
    p.add_argument("--samples", type=int, default=None)
    p.add_argument("--out", default="//render/####")
    p.add_argument("--format", default="PNG", choices=list(FORMATS))
    p.add_argument("--frames", default=None)
    p.add_argument("--cameras", nargs="*", default=None)
    p.add_argument("--view", default=None)
    p.add_argument("--look", default=None)
    p.add_argument("--transparent", action="store_true", default=None)
    p.add_argument("--device", default="AUTO", choices=["AUTO", "GPU", "OPTIX", "CPU"])
    bx.cli(run, p)
