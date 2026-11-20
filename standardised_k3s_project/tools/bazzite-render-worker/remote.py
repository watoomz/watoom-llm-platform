"""Existing server-held credentials; pinned SSH host key; no credential arguments/logs."""

from pathlib import Path
import os, subprocess, tempfile, argparse

CREDENTIALS = Path("/home/codex/game_render_host.txt")
KNOWN = Path("/data/ai/helper-scripts/reports/game-render-host-audit-20261026/known_hosts")


def connection():
    rows = CREDENTIALS.read_text().splitlines()
    return rows[0].strip(), next(l.split(":", 1)[1].strip() for l in rows if l.startswith("username:"))


def run(script, timeout=900, privileged=False):
    if privileged:
        password = next(
            l.split(":", 1)[1].strip() for l in CREDENTIALS.read_text().splitlines() if l.startswith("password:")
        )
        script = (
            'import subprocess,sys\nr=subprocess.run(["sudo","-S","-p","","python3","-c",'
            + repr(script)
            + "],input="
            + repr(password + "\n")
            + ",text=True,capture_output=True);print(r.stdout);print(r.stderr);sys.exit(r.returncode)\n"
        )
    host, user = connection()
    with tempfile.TemporaryDirectory(prefix="render-ssh-", dir="/data/ai/private") as tmp:
        ask = Path(tmp) / "askpass.py"
        ask.write_text(
            "#!/usr/bin/python3\nfrom pathlib import Path\nfor l in Path('/home/codex/game_render_host.txt').read_text().splitlines():\n if l.startswith('password:'):print(l.split(':',1)[1].strip());break\n"
        )
        ask.chmod(0o700)
        return subprocess.run(
            [
                "ssh",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "ServerAliveInterval=15",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "UserKnownHostsFile=" + str(KNOWN),
                user + "@" + host,
                "python3 -",
            ],
            input=script,
            text=True,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, "SSH_ASKPASS": str(ask), "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"},
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("script", type=Path)
    a = p.parse_args()
    r = run(a.script.read_text())
    print(r.stdout)
    print(r.stderr)
    raise SystemExit(r.returncode)


def sftp_fetch(remote, local):
    import re

    if not re.fullmatch(r"/var/render_worker/[A-Za-z0-9_./-]+", remote) or ".." in Path(remote).parts:
        raise ValueError("Remote artifact path")
    local = Path(local)
    if any(c in str(local) for c in ["\n", "\r", '"']):
        raise ValueError("Local artifact path")
    host, user = connection()
    with tempfile.TemporaryDirectory(prefix="render-sftp-", dir="/data/ai/private") as tmp:
        ask = Path(tmp) / "askpass.py"
        ask.write_text(
            "#!/usr/bin/python3\nfrom pathlib import Path\nfor l in Path('/home/codex/game_render_host.txt').read_text().splitlines():\n if l.startswith('password:'):print(l.split(':',1)[1].strip());break\n"
        )
        ask.chmod(0o700)
        r = subprocess.run(
            [
                "sftp",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "ServerAliveInterval=10",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "UserKnownHostsFile=" + str(KNOWN),
                user + "@" + host,
            ],
            input='reget "' + remote + '" "' + str(local) + '"\nquit\n',
            text=True,
            capture_output=True,
            timeout=600,
            env={**os.environ, "SSH_ASKPASS": str(ask), "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"},
        )
        if r.returncode:
            raise ConnectionError("SFTP disconnected; retain partial artifact and reconcile status")
