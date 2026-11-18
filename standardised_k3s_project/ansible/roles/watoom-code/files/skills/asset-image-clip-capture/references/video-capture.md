# Video, animation and turntable capture

Use the same native tool and declarative manifest as stills; video is not screen recording, diffusion or a separate invented worker operation. The selected images project has a pinned Blender5.2.1 CPU worker with a configured ffmpeg. Distinguish the requested result before submitting:

| Intent | Manifest mode | What moves |
| --- | --- | --- |
| Show a static asset from all sides | `turntable` | Camera orbits the evaluated subject; label as turntable |
| Play verified authored rig/scene motion | `animation` | Actual existing Action/scene animation at each frame |
| Newly choreographed or retargeted motion | Not supplied by this capture adapter | Needs a separately verified animation preparation route |

## Prepare once

Verify the source/texture/rig preparation, actual Action name and owner, authored frame range and frame rate. For Action selection use `action` plus actual `armature`; preserve scene animation/NLA only when verified. Static `pose` overrides apply after frame evaluation on every frame and are keyed in a working Action copy, with post-render channel checks; they are not a new motion generator. Confirm visible rig/mesh changes at two distinct authored frames. If no verified motion exists, report it; offer a clearly labelled turntable only as an alternative.

Set inclusive `frames:[start,end]`, `fps` and even `resolution` explicitly. Duration is `(end-start+1)/fps`; do not silently stretch, interpolate, repeat frames or truncate to fit. `output_format:"mp4"` produces H.264/yuv420p with faststart plus retained source PNG frames. PNG-only clips use `output_format:"png"`; encoding is not implied. Still mode cannot produce MP4. A video needs at least2frames.

Contract limits:2..120video frames,1..60fps,64..2048pixels per side, at most128Mi total framepixels,1..64samples. Runtime is900seconds **for loading, all frames and encoding together**, not per frame. Measure a representative preview and estimate `load + frame_count * measured_frame_seconds + encoding reserve`; stay comfortably below timeout. A character taking19seconds per frame cannot render96frames in this worker budget. Reduce preview cost/length with the user's intent preserved, or report the needed budget/segmented-workflow qualification; do not silently change the requested final video. For an inexpensive technical test use a tiny representative frame range; no universal4second default. Frames are deterministic, not wall-clock screenshots.

## Submit and wait

Write `.opencode/capture-jobs/<new-video-job>/request.json` first, using supported manifest fields only. Example shape (replace the source/hash/Action/rig with verified values): `schema:1, mode:animation, source:<canonical>, source_sha256:<actual>, action:<actual Action>, armature:<actual rig>, frames:[1,24], fps:12, resolution:[512,768], samples:8, output_format:mp4`. This is a2second request; only submit if the measured budget supports it. Omit Action fields for turntable. Add observed clothing/mask/pose choices as appropriate.

Invoke native `watoom_asset_capture` exactly `{action:"request",job:"<new-video-job>"}`; yield after QUEUED. Read the completion notification and root-owned receipt. Do not hold the app in a polling loop, start a parallel renderer or evict inference. If FAILED/CANCELLED, retain all partial frames and evidence; inspect the exact failure before a fresh revision. Never replay an uncertain job.

## Validate actual motion and delivery

Require exit0, actual4GiB cgroup, unchanged source, expected number/dimensions of fresh frame PNGs and a real MP4 when requested. On the operator/verified worker side inspect ffprobe metadata for H.264, yuv420p, dimensions, rational FPS, decoded frame count and duration against the request. If the app cannot run ffprobe, use the existing qualified operator route or report that gate pending; do not pretend the command exists locally. Preserve the actual probe report.

Inspect actual first/middle/last frames and contact/motion extrema: intended articulation or orbit, no frozen rig, texture failures, clipping, out-of-frame motion, lighting flicker or severe deformation. First/last-only equality is expected for a closed turntable and does not prove a frozen clip; review intermediate frames. Different hashes alone do not prove correct motion. Current camera bounds sample first/middle/last for animation; fast extrema need extra visual coverage. Return VISUAL_REVIEW_PENDING until this is done.

Deliver the actual MP4 through an existing supported media preview/file route with a representative image, duration,FPS,source/action or labelled orbit and concise limitations. Retain frame PNGs, pose evidence, logs, source/output hashes, worker receipt and ffprobe report. Save a video recipe only after real motion and playback validation; still acceptance does not qualify video.

## Repeat a short Action for a longer preview

Animation manifests now accept `loop_action: true` with an explicit existing `action` and `armature`. Keep pose overrides absent. Select output FPS and frame range for the requested capture duration (for example30frames at10fps gives3seconds); the worker samples the source Action at its saved source FPS and wraps its actual Action range, preserving motion speed. It does not lengthen the source animation or alter its keys. Zero-length Actions are rejected. Existing120-frame/pixel/runtime budgets still apply; a long source Action is not required for a3–5second preview. Review seam discontinuities and actual MP4 duration/frame count. A neutral one-bone fixture passed30frames/3seconds with repeated time sampling and changing pixels; character-video quality remains per-job validation.
