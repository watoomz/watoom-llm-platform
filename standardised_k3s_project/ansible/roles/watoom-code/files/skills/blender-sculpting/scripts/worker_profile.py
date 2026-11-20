"""Execution policy for every installed EL4CTEO component, not a dispatcher."""

import hashlib, json, pathlib, sys

PROFILES = pathlib.Path(__file__).with_name("worker-profiles.json")
_checked = set()


def descriptor():
    profiles = json.loads(PROFILES.read_text())
    return profiles["rig-optix"] if sys.platform == "win32" else profiles["server-cpu"]


def verify_external():
    profile = descriptor()
    if sys.platform == "win32":
        from _worker_runtime import current_limit

        boundary = current_limit()
    else:
        line = next(x for x in pathlib.Path("/proc/self/cgroup").read_text().splitlines() if x.startswith("0::"))
        group = pathlib.Path("/sys/fs/cgroup") / line[3:].lstrip("/")
        actual = (group / "memory.max").read_text().strip()
        if actual != "4294967296":
            raise RuntimeError(
                "External 4GiB server worker or 8GiB RIG worker required; the 2GiB app shell is forbidden"
            )
        boundary = {"memory_limit_verified": True, "memory_limit_bytes": int(actual), "boundary": "Linux cgroup"}
    return dict(profile, boundary=boundary)


def verify_binary(path):
    profile = descriptor()
    path = pathlib.Path(path)
    key = (str(path), path.stat().st_size, path.stat().st_mtime_ns, profile["sha256"])
    if key not in _checked:
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != profile["sha256"]:
                raise RuntimeError("Pinned Blender executable hash changed")
        _checked.add(key)
    return profile


def configure_device(scene, requested="AUTO"):
    import bpy

    profile = verify_external()
    verify_binary(bpy.app.binary_path)
    if tuple(bpy.app.version[:3]) != tuple(profile["version"]):
        raise RuntimeError("Unqualified Blender version")
    device = requested.upper()
    if device == "AUTO":
        device = profile["default_device"]
    scene.render.threads_mode = "FIXED"
    scene.render.threads = profile["threads"]
    if device == "CPU":
        scene.cycles.device = "CPU"
        return "CPU"
    if device not in ("GPU", "OPTIX") or profile["cpu_only"]:
        raise ValueError("GPU execution requires the admitted RIG profile; do not use the app shell or inference GPU")
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "OPTIX"
    preferences.refresh_devices()
    if not any(item.type == "OPTIX" for item in preferences.devices):
        raise RuntimeError("Requested OptiX device unavailable; no silent CPU fallback")
    for item in preferences.devices:
        item.use = item.type == "OPTIX"
    scene.cycles.device = "GPU"
    return "OPTIX"
