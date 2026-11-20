"""Read-only status publication by the existing controller; never calls an actuator."""

import json, os, secrets, time
from pathlib import Path


def publish(state_root, output, primary):
    root = Path(state_root)
    target = Path(output)
    if not target.is_absolute() or target.parent.is_symlink():
        raise ValueError("Untrusted observation path")
    state = json.loads((root / "state.json").read_text())
    if (
        type(state.get("generation")) is not int
        or type(state.get("uncertain")) is not bool
        or not isinstance(state.get("phase"), str)
    ):
        raise ValueError("Invalid durable ownership state")
    leases = []
    path = root / "inference-leases.json"
    if path.exists():
        data = json.loads(path.read_text())
        leases = data.get("leases", {}) if isinstance(data, dict) else data
        if data.get("version") != 1 or not isinstance(leases, dict):
            raise ValueError("Invalid request accounting")
    value = {
        "schema": "watoom.gpu-observation.v1",
        "sampledAt": int(time.time() * 1000),
        "phase": state["phase"],
        "owner": state.get("owner"),
        "generation": state["generation"],
        "uncertain": state["uncertain"],
        "primary": primary,
        "activeRequests": len(leases),
    }
    # Mutation journal uncertainty is never hidden by a healthy-looking state file.
    intents = root / "intents"
    if intents.exists():
        for item in intents.glob("*.json"):
            record = json.loads(item.read_text())
            if record.get("status") in ("pending", "uncertain") or record.get("phase") in ("pending", "uncertain"):
                value["uncertain"] = True
    parent = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temp = "." + target.name + "." + secrets.token_hex(8)
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=parent)
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o644)
            json.dump(value, stream)
        os.replace(temp, target.name, src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        os.close(parent)
    return value
