from pathlib import Path
import urllib.request, hashlib, tarfile, subprocess, json, os

root = Path("/var/render_worker/runtime")
root.mkdir(exist_ok=True)
archive = root / "blender-5.2.1-linux-x64.tar.xz"
expected = "a31f524fa99a527d3d52b7f5aaa68c34e1a19d5a1c9473f79c5cc610fd5b10e9"
if not archive.exists():
    temporary = archive.with_suffix(".download")
    urllib.request.urlretrieve("https://download.blender.org/release/Blender5.2/" + archive.name, temporary)
    assert hashlib.sha256(temporary.read_bytes()).hexdigest() == expected
    os.replace(temporary, archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
engine = root / "blender-5.2.1-linux-x64/blender"
if not engine.exists():
    with tarfile.open(archive) as a:
        for m in a.getmembers():
            p = Path(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError("Archive escape")
        a.extractall(root, filter="data")
r = subprocess.run(
    [
        str(engine),
        "--background",
        "--factory-startup",
        "--python-expr",
        "import bpy;assert bpy.app.version_string=='5.2.1 LTS';assert bpy.app.build_hash==b'9e2066aef7ef';print('MATCHES_RIG',bpy.app.version_string,bpy.app.build_hash)",
    ],
    capture_output=True,
    text=True,
    timeout=40,
)
print(r.stdout, r.stderr)
assert r.returncode == 0
(root / "blender-5.2.1-pin.json").write_text(
    json.dumps(
        {
            "version": "5.2.1 LTS",
            "build": "9e2066aef7ef",
            "archive_sha256": expected,
            "binary_sha256": hashlib.sha256(engine.read_bytes()).hexdigest(),
            "engine": str(engine),
        },
        indent=2,
    )
)
print("PINNED_WORKER_BLENDER_READY")
