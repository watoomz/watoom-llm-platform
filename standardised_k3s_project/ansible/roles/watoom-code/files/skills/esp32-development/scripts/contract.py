"""Declarative ESP32 operations, canonical sources and USB enrollment checks."""

import json, re, hashlib, pathlib, stat, subprocess, os

PROJECT = "/data/ai/projects/llm/esp32"
ARTIFACTS = "/data/ai/artifacts/esp32"
PROFILE = "esp32-div-v2-s3"
# Operator-owned source budgets (entries visited, bytes, files). A build manifest may select a profile by name but never
# set numbers, so the ceiling stays here. 'large' is the ceiling for a full firmware port.
SOURCE_PROFILES = {"standard": (256, 4 * 1024**2, 128), "large": (2048, 16 * 1024**2, 2048)}
OPS = {"inventory", "build", "probe", "flash", "restore", "monitor", "serial"}


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def contained(value, root, kind="file"):
    p = pathlib.Path(value)
    if not p.is_absolute() or p.is_symlink() or p.resolve(strict=True) != p or not p.is_relative_to(pathlib.Path(root)):
        raise ValueError("Canonical in-project path required")
    if (kind == "file" and not p.is_file()) or (kind == "dir" and not p.is_dir()):
        raise ValueError("Input type mismatch")
    return p


def sources(directory, profile="standard"):
    if profile not in SOURCE_PROFILES:
        raise ValueError("Unknown source_profile; allowed: " + ", ".join(SOURCE_PROFILES))
    max_visited, max_size, max_files = SOURCE_PROFILES[profile]
    hint = (
        ""
        if profile == "large"
        else "; resubmit with source_profile 'large' (up to "
        + str(SOURCE_PROFILES["large"][2])
        + " files / "
        + str(SOURCE_PROFILES["large"][1] // 1024**2)
        + " MiB)"
    )
    p = contained(directory, PROJECT, "dir")
    result = []
    size = 0
    visited = 0
    for folder in ["src", "include"]:
        base = p / folder
        if not base.exists():
            continue
        stack = [base]
        while stack:
            current = stack.pop()
            contained(str(current), PROJECT, "dir")
            with os.scandir(current) as entries:
                for entry in entries:
                    visited += 1
                    if visited > max_visited:
                        raise ValueError(
                            "Source directory entry budget ("
                            + str(max_visited)
                            + ") exceeded for profile '"
                            + profile
                            + "'"
                            + hint
                        )
                    path = pathlib.Path(entry.path)
                    if path.is_symlink() or len(path.relative_to(p).parts) > 12:
                        raise ValueError("Symlink/deep source forbidden")
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(path)
                        continue
                    contained(str(path), PROJECT)
                    if path.suffix not in [".cpp", ".c", ".h", ".hpp", ".ino"]:
                        raise ValueError("Only C/C++/Arduino sources; no build scripts or user platform files")
                    size += path.stat().st_size
                    if size > max_size or len(result) >= max_files:
                        raise ValueError(
                            "Source size/file budget ("
                            + str(max_files)
                            + " files / "
                            + str(max_size // 1024**2)
                            + " MiB) exceeded for profile '"
                            + profile
                            + "'"
                            + hint
                        )
                    result.append({"path": str(path.relative_to(p)), "sha256": sha(path)})
    if not result:
        raise ValueError("No sources in src/include")
    return sorted(result, key=lambda item: item["path"])


def fingerprint(directory, profile="standard"):
    return hashlib.sha256(
        json.dumps(sources(directory, profile), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def manifest(v):
    if not isinstance(v, dict) or v.get("schema") != 1 or v.get("operation") not in OPS:
        raise ValueError("ESP32 operation schema")
    op = v["operation"]
    fields = {"schema", "operation"}
    if op == "build":
        fields |= {"source", "source_sha256", "profile"}
        if "psram" in v:
            fields |= {"psram"}
        if "source_profile" in v:
            fields |= {"source_profile"}
    elif op != "inventory":
        fields |= {"device"}
    if op == "flash":
        fields |= {"build", "firmware_sha256", "confirm_flash"}
        if "reuse_backup" in v or "reuse_backup_sha256" in v:
            fields |= {"reuse_backup", "reuse_backup_sha256"}
    if op == "restore":
        fields |= {"backup", "backup_sha256", "confirm_restore"}
    if op in ["monitor", "serial"]:
        fields |= {"seconds", "baud"}
    if op == "serial":
        fields |= {"text"}
    if set(v) != fields:
        raise ValueError("Exact operation fields required; arbitrary commands forbidden")
    if op == "build":
        if (
            v["profile"] != PROFILE
            or fingerprint(v["source"], v.get("source_profile", "standard")) != v["source_sha256"]
        ):
            raise ValueError("Source/profile revision mismatch")
        # Real esp32s3 Arduino-core PSRAM menu values (checked against the pinned toolchain's boards.txt), not the
        # qualified default. Overriding is compile-only here -- it never touches the physical board; the existing
        # flash path (explicit confirm_flash, physical MAC match, full backup-before-write) is the actual safety
        # net if a build produced with this override is later flashed and tested.
        if "psram" in v and v["psram"] not in ("disabled", "enabled", "opi"):
            raise ValueError("Unsupported PSRAM option for esp32s3")
    if op not in ["inventory", "build"] and (
        not isinstance(v["device"], str) or not re.fullmatch("[a-zA-Z0-9_-]{1,64}", v["device"])
    ):
        raise ValueError("Enrolled device ID required")
    if op == "flash":
        contained(v["build"], ARTIFACTS, "dir")
        if v["confirm_flash"] is not True or not re.fullmatch("[a-f0-9]{64}", v["firmware_sha256"]):
            raise ValueError("Explicit flash and firmware revision required")
    if op == "flash" and "reuse_backup" in v:
        if not re.fullmatch("[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", v["reuse_backup"]) or not re.fullmatch(
            "[a-f0-9]{64}", v["reuse_backup_sha256"]
        ):
            raise ValueError("Pinned backup reuse identity required")
    if op == "restore":
        if (
            v["confirm_restore"] is not True
            or not re.fullmatch("[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", v["backup"])
            or not re.fullmatch("[a-f0-9]{64}", v["backup_sha256"])
        ):
            raise ValueError("Pinned backup identity and explicit restore required")
    if op in ["monitor", "serial"]:
        if type(v["seconds"]) != int or not 1 <= v["seconds"] <= 600 or v["baud"] not in [9600, 57600, 115200]:
            raise ValueError("Bounded serial duration/baud required")
    if op == "serial" and (
        not isinstance(v["text"], str)
        or not 1 <= len(v["text"].encode()) <= 256
        or any(ord(c) < 32 and c not in "\r\n\t" for c in v["text"])
    ):
        raise ValueError("Bounded serial text required")
    return v


def usb(path):
    p = pathlib.Path(path)
    target = p.resolve(strict=True)
    if (
        not str(p).startswith("/dev/serial/by-id/")
        or not stat.S_ISCHR(target.stat().st_mode)
        or not re.fullmatch("/dev/tty(?:USB|ACM)[0-9]+", str(target))
    ):
        raise ValueError("Stable USB serial device required")
    x = subprocess.run(
        ["udevadm", "info", "--query=property", "--name=" + str(target)], capture_output=True, text=True, timeout=5
    )
    if x.returncode:
        raise ValueError("USB identity unavailable")
    attrs = dict(line.split("=", 1) for line in x.stdout.splitlines() if "=" in line)
    ident = {k: attrs.get(k) for k in ["ID_VENDOR_ID", "ID_MODEL_ID", "ID_SERIAL_SHORT", "ID_PATH"]}
    if not all(ident.values()):
        raise ValueError("USB serial VID/PID/unique serial required")
    return {"by_id": str(p), "target": str(target), "identity": ident, "rdev": target.stat().st_rdev}


def inventory(cfg):
    found = []
    for p in sorted(pathlib.Path("/dev/serial/by-id").glob("*")):
        try:
            row = usb(p)
            row["enrolled_as"] = [
                name
                for name, e in cfg["devices"].items()
                if e.get("by_id") == str(p) and e.get("identity") == row["identity"]
            ]
            found.append(row)
        except ValueError:
            continue
    return found


def enrolled(name, cfg, flash=False):
    entry = cfg["devices"].get(name)
    if not entry or entry.get("profile") != PROFILE or (flash and entry.get("allow_flash") is not True):
        raise ValueError("Device not explicitly enrolled for requested operation")
    row = usb(entry["by_id"])
    if row["identity"] != entry["identity"]:
        raise ValueError("USB board identity changed")
    return row
