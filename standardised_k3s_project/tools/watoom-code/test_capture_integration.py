"""Operator-only integration acceptance against the fixed keyed rig fixture."""

import sys, json, pathlib, subprocess
from asset_capture import run
from asset_capture_contract import sha

project = pathlib.Path("/data/ai/projects/images")
evidence = pathlib.Path(sys.argv[1])
source = project / ".opencode/capture-fixtures/pose-video-v2/source.blend"
base = {
    "schema": 1,
    "mode": "still",
    "source": str(source),
    "source_sha256": sha(source),
    "resolution": [128, 192],
    "samples": 4,
    "frames": [2, 2],
    "pose": [{"armature": "FixtureRig", "bone": "Arm", "rotation_euler": [0, 0, -0.6]}],
}
results = []
for suffix, edits in [
    ("pose", {}),
    (
        "animation",
        {
            "mode": "animation",
            "frames": [1, 4],
            "fps": 4,
            "pose": [],
            "action": "FixtureMotion",
            "armature": "FixtureRig",
            "output_format": "mp4",
        },
    ),
    ("turntable", {"mode": "turntable", "frames": [1, 4], "fps": 4, "output_format": "mp4"}),
]:
    job = "capture-accept-" + suffix + "-20261025-v3"
    folder = project / ".opencode/capture-jobs" / job
    folder.mkdir(exist_ok=False)
    v = dict(base, **edits)
    (folder / "request.json").write_text(json.dumps(v, indent=2))
    rc = run(str(project), job, str(evidence / suffix))
    assert rc == 0, (suffix, rc)
    r = json.loads((evidence / suffix / "result.json").read_text())
    out = pathlib.Path(r["output"])
    if suffix == "pose":
        proof = json.loads((out / "pose-evidence.json").read_text())
        assert proof[0]["changed_deform_bones"] > 0
        assert all(abs(a - b) < 1e-5 for a, b in zip(proof[0]["controls"][0]["actual"], [0, 0, -0.6]))
    else:
        cmd = [
            "/usr/sbin/ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_read_frames,duration",
            "-of",
            "json",
            str(out / "capture.mp4"),
        ]
        probe = json.loads(subprocess.check_output(cmd, text=True))
        stream = probe["streams"][0]
        assert (
            stream["codec_name"] == "h264"
            and int(stream["nb_read_frames"]) == 4
            and stream["r_frame_rate"] == "4/1"
            and stream["width"] == 128
            and stream["height"] == 192
            and abs(float(stream["duration"]) - 1) < 0.05
        )
        (evidence / suffix / "ffprobe.json").write_text(json.dumps(probe, indent=2))
        inventory = json.loads((out / "prepared-inventory.json").read_text())
        assert inventory["objects"]
    results.append(
        {"case": suffix, "status": "PASS", "output": str(out), "receipt": str(evidence / suffix / "result.json")}
    )
(evidence / "integration-result.json").write_text(json.dumps(results, indent=2))
print("INTEGRATION_CASES_PASS", json.dumps(results))
