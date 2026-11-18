"""Narrow reviewed Mesh integration delta for the existing guarded release."""
import copy
import json
from pathlib import Path
import release_guard

def desired(deployment, rendered, config, adapter, canonical, bridge_host):
    if bridge_host != "/app/ai/services/opencode/home/.config/opencode/mesh-bridge":
        raise release_guard.UnsafeRelease("Mesh bridge path is not the verified existing bridge")
    if Path(adapter).read_bytes() != Path(canonical).read_bytes():
        raise release_guard.UnsafeRelease("Installed Mesh adapter differs from reviewed source")
    result = copy.deepcopy(deployment)
    spec = result["spec"]["template"]["spec"]
    container = next(c for c in spec["containers"] if c["name"] == "app")
    if spec["securityContext"].get("runAsUser") != 1001 or 1009 not in spec["securityContext"].get("supplementalGroups", []):
        raise release_guard.UnsafeRelease("Mesh caller identity differs")
    volume = {"name": "mesh-bridge", "hostPath": {"path": bridge_host, "type": "Directory"}}
    mount = {"name": "mesh-bridge", "mountPath": "/home/opencode/.config/opencode/mesh-bridge", "readOnly": True}
    for items, wanted in [(spec["volumes"], volume), (container["volumeMounts"], mount)]:
        found = [x for x in items if x["name"] == "mesh-bridge"]
        if found and found != [wanted]:
            raise release_guard.UnsafeRelease("Existing Mesh access differs; no broad mount rewrite")
        if not found:
            items.append(wanted)
    expected = next(c for c in rendered["spec"]["template"]["spec"]["containers"] if c["name"] == "app")
    if mount not in expected["volumeMounts"] or volume not in rendered["spec"]["template"]["spec"]["volumes"]:
        raise release_guard.UnsafeRelease("Reviewed Mesh delta is missing from maintained IaC")
    updated = copy.deepcopy(config)
    servers = updated.setdefault("mcp", {}).setdefault("servers", {})
    entry = {"type": "local", "command": ["/usr/bin/python3", "/config/watoom-tools/watoom-llama-mesh.py", "mcp"],
             "environment": {"WATOOM_MESH_ASSET_ROOT": "/data/ai/assets"},
             "timeout": {"catalog": 30000, "execution": 3600000}, "codemode": True}
    if "watoom-llama-mesh" in servers and servers["watoom-llama-mesh"] != entry:
        raise release_guard.UnsafeRelease("Mesh registration changed concurrently")
    servers["watoom-llama-mesh"] = entry
    return result, (json.dumps(updated, indent=2) + "\n").encode()
