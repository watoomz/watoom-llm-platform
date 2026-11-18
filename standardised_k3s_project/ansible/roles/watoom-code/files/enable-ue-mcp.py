#!/usr/bin/env python3
"""Maintain only the watoom-ue MCP entry in the existing native opencode.json (usage: path host port user, or path - to remove).

The entry runs `ssh` to the restricted ForceCommand-only account on the rig (tools/rig-ue-mcp); the credentials are
staged by playbooks/ue-mcp-ssh.yml. Other entries and user settings are left untouched.
"""
import ipaddress, json, os, pathlib, re, sys, tempfile

NAME = "watoom-ue"
CRED = "/config/watoom-tools/ue-mcp-credentials"


def entry(host, port, user):
    return {
        "type": "local",
        "command": ["ssh", "-i", f"{CRED}/key",
                    "-o", f"UserKnownHostsFile={CRED}/known_hosts",
                    "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes",
                    "-p", str(port), f"{user}@{host}"],
        "timeout": {"catalog": 60000, "execution": 600000},
        "codemode": False,
    }


def main(argv):
    p = pathlib.Path(argv[1])
    remove = len(argv) == 3 and argv[2] == "-"
    if not remove:
        if len(argv) != 5:
            raise SystemExit("usage: enable-ue-mcp.py CONFIG HOST PORT USER | CONFIG -")
        host, port, user = argv[2], argv[3], argv[4]
        ipaddress.ip_address(host)  # a literal address only: this entry must not resolve through DNS
        if not (port.isdigit() and 0 < int(port) < 65536):
            raise SystemExit("Invalid port")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", user):
            raise SystemExit("Invalid user name")
    if p.is_symlink():
        raise SystemExit("Real native configuration required")
    before = p.read_bytes()
    data = json.loads(before)
    servers = data.setdefault("mcp", {}).setdefault("servers", {})
    if remove:
        servers.pop(NAME, None)
    else:
        servers[NAME] = entry(host, port, user)
    if data == json.loads(before):
        print("UNCHANGED")
        return
    st = p.stat()
    fd, tmp = tempfile.mkstemp(prefix=".ue-mcp-", dir=p.parent)
    try:
        with os.fdopen(fd, "w") as f:
            os.fchmod(f.fileno(), st.st_mode & 0o777)
            os.fchown(f.fileno(), st.st_uid, st.st_gid)
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        if p.read_bytes() != before:
            raise RuntimeError("Concurrent native configuration edit")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print("CHANGED")


if __name__ == "__main__":
    main(sys.argv)
