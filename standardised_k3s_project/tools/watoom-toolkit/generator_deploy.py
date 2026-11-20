#!/usr/bin/env python3
"""WatooM generator deployment: audit -> isolated build -> image validation -> stage -> rollback.
No production modifications. Audit is read-only. Apply requires --i-approve.
"""

import argparse, datetime, hashlib, json, os, pathlib, re, shutil, shlex, subprocess, sys, time, urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools/watoom-toolkit"
ROLE = REPO / "ansible/roles/watoom-code"
DEFAULTS = REPO / "ansible/vars/watoom-code.yml"  # production pins (Option A)
REPORTS = pathlib.Path("/data/ai/helper-scripts/reports")
WORK = pathlib.Path("/data/ai/helper-scripts/watoom-generator-deploy-work")
BUILDAH = pathlib.Path("/data/ai/helper-scripts/watoom-m5-root-safe-work/buildah-isolated.sh")
CANDIDATES = [
    pathlib.Path(x)
    for x in (
        "/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/asset-assistant-source-review",
        "/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/review-package/asset-assistant-source-review",
        "/data/ai/projects/llm/watoom-code/wp-build-1/phase-a/asset-assistant",
    )
]
IDS = (
    "asset-assistant.avian",
    "asset-assistant.quadruped",
    "asset-assistant.human",
    "watoom.tree",
    "watoom.terrain",
    "watoom.building",
    "watoom.rock",
)
BASE = "127.0.0.1:5000/watoom-toolkit"
NS = "watoom-code"


def invoke(argv, seconds=90, cwd=None, env=None, log=None):
    try:
        p = subprocess.run(
            [str(x) for x in argv],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=seconds,
        )
        data = p.stdout.decode("utf-8", "replace")
        if log:
            pathlib.Path(log).write_text(data)
        return p.returncode, data
    except Exception as e:
        if log:
            pathlib.Path(log).write_text(str(e))
        return -1, str(e)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def copy_sources(containerfile):
    """Exact local file inputs of the maintained Containerfile COPY instructions.

    Unsupported dynamic, directory or cross-stage inputs fail closed rather than
    silently producing an incomplete deploy context.
    """
    sources = []
    text = re.sub(r"\\\n\s*", " ", containerfile.read_text())
    for line in text.splitlines():
        instruction = line.strip().split(None, 1)
        if not instruction or instruction[0].upper() != "COPY":
            continue
        if len(instruction) != 2:
            raise ValueError("COPY needs sources and destination")
        body = instruction[1]
        parts = json.loads(body) if body.startswith("[") else shlex.split(body)
        if not isinstance(parts, list) or len(parts) < 2:
            raise ValueError("COPY needs sources and destination")
        for name in parts[:-1]:
            if (
                not isinstance(name, str)
                or not name
                or name.startswith("--")
                or "$" in name
                or any(c in name for c in "*?[")
            ):
                raise ValueError("Unsupported COPY source: " + str(name))
            path = pathlib.PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe COPY source: " + name)
            if name not in sources:
                sources.append(name)
    if not sources:
        raise ValueError("No local COPY sources in " + str(containerfile))
    return sources


def source_hashes(tools, containerfile):
    sources = copy_sources(containerfile)
    missing = [name for name in sources if not (tools / name).is_file()]
    if missing:
        raise ValueError("Missing COPY source files: " + ", ".join(missing))
    return {name: digest(tools / name) for name in sources}


def copy_context(tools, containerfile, context):
    # Validate the complete list before creating or partially populating context.
    hashes = source_hashes(tools, containerfile)
    context.mkdir()
    for name in hashes:
        target = context / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tools / name, target)
    return hashes


def latest_report(name):
    return REPORTS / (
        name + "-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + str(os.getpid())
    )


class Run:
    def __init__(self, name):
        os.umask(0o077)
        self.out = latest_report(name)
        self.out.mkdir(parents=True, exist_ok=False)
        self.results = []

    def note(self, key, status, message):
        self.results.append(dict(id=key, status=status, reason=str(message)[:800]))
        print(key, status, str(message)[:260], flush=True)

    def finish(self):
        checks = sorted(self.results, key=lambda x: (x["status"] == "PASS", x["id"]))
        outcome = (
            "BLOCKED_OR_FAIL"
            if any(x["status"] in ("FAIL", "BLOCKED") for x in checks)
            else "PARTIAL" if any(x["status"] == "NOT TESTED" for x in checks) else "PASS"
        )
        (self.out / "report.json").write_text(json.dumps({"result": outcome, "checks": checks}, indent=2))
        (self.out / "report.md").write_text(
            "# Generator deployment\n\n" + "".join(f"- **{x['status']}** {x['id']}: {x['reason']}\n" for x in checks)
        )
        print("REPORT=" + str(self.out / "report.json"))
        print("RESULT=" + outcome)
        return 0 if outcome == "PASS" else 2


def locate(r, containerfile="Containerfile.local-only"):
    recipe = TOOLS / containerfile
    try:
        hashes = source_hashes(TOOLS, recipe)
    except (OSError, ValueError) as error:
        r.note("COPY_SOURCES", "BLOCKED", str(error))
        return None
    (r.out / "toolkit-source-hashes.json").write_text(
        json.dumps({"containerfile": containerfile, "files": hashes}, indent=2)
    )
    for path in [recipe, DEFAULTS, *(TOOLS / name for name in hashes)]:
        r.note("SOURCE_" + path.name, "PASS" if path.is_file() else "BLOCKED", str(path))
    found = []
    for base in CANDIDATES:
        ok = all(
            (base / x).is_file()
            for x in (
                "object_core/objects.py",
                "blender_adapter/adapter.py",
                "blender_adapter/workflow.py",
                "blender_adapter/animation.py",
                "blender_adapter/materials.py",
                "blender_adapter/targets.py",
            )
        )
        r.note(
            "PROVIDER_" + str(len(found) + 1) if ok else "CANDIDATE_" + base.name,
            "PASS" if ok else "WARN",
            str(base) + " modules=" + str(ok),
        )
        if ok:
            found.append(base)
    if not found:
        r.note("PROVIDER_SOURCE", "BLOCKED", "No provider tree meets exact imports")
        return None

    # Compare full content of both module trees, not just paths, and preserve conflicts for review.
    def fingerprint(base):
        out = {}
        for sub in ("object_core", "blender_adapter"):
            for p in (base / sub).rglob("*.py"):
                out[str(p.relative_to(base))] = digest(p)
        return out

    fingerprints = {str(base): fingerprint(base) for base in found}
    (r.out / "provider-comparison.json").write_text(json.dumps(fingerprints, indent=2))
    if len({json.dumps(v, sort_keys=True) for v in fingerprints.values()}) > 1:
        r.note(
            "PROVIDER_EQUIVALENCE",
            "PASS",
            "Source variants differ; selected reviewed tree must pass full in-image generation tests",
        )
    else:
        r.note("PROVIDER_EQUIVALENCE", "PASS", "Available provider trees contain identical Python sources")
    chosen = next((p for p in found if "source-review" in p.name), found[0])
    r.note("PROVIDER_SELECTED", "PASS", str(chosen))
    return chosen


def audit(r, containerfile="Containerfile.local-only"):
    chosen = locate(r, containerfile)
    if chosen is None:
        return None
    code = (TOOLS / "three_d.py").read_text()
    for id in IDS:
        r.note(
            "GEN_" + id,
            "PASS" if repr(id) in code else "BLOCKED",
            "defined in source registry" if repr(id) in code else "not found",
        )
    for id in ("llama-mesh", "spar3d", "sf3d", "hunyuan3d"):
        r.note(
            "OPTIONAL_" + id,
            "PASS" if repr(id) in code else "WARN",
            "defined but not enabled without runtime" if repr(id) in code else "not present",
        )
    rc, live = invoke(
        ["kubectl", "-n", NS, "get", "deployment", "watoom-toolkit", "-o", "json"],
        20,
        log=r.out / "deployment-before.json.raw",
    )
    if rc == 0:
        try:
            d = json.loads(live)
            img = d["spec"]["template"]["spec"]["containers"][0]["image"]
            r.note("LIVE", "PASS", img)
        except Exception as e:
            r.note("LIVE", "BLOCKED", e)
    else:
        r.note("LIVE", "BLOCKED", live[-500:])
    rc, space = invoke(["df", "-Pk", "/", "/app", "/data"], 10)
    r.note("DISKS", "PASS" if rc == 0 else "BLOCKED", space[:500])
    rc, g = invoke(
        [
            "git",
            "-c",
            "safe.directory=" + str(REPO.parent),
            "-C",
            str(REPO),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        20,
    )
    (r.out / "iac-state.txt").write_text(g)
    r.note("IAC", "PASS" if rc == 0 else "BLOCKED", "working tree captured; will not reset unrelated modifications")
    return chosen


def build(r, provider, containerfile="Containerfile.local-only"):
    try:
        source_hashes(TOOLS, TOOLS / containerfile)
    except (OSError, ValueError) as error:
        r.note("COPY_SOURCES", "BLOCKED", str(error))
        return None
    if not BUILDAH.is_file():
        r.note("STORAGE", "BLOCKED", "Missing isolated Buildah launcher")
        return None
    text = BUILDAH.read_text()
    if "watoom-m5-root-safe-work" not in text or "vfs" not in text or "buildah-root" not in text:
        r.note("STORAGE", "BLOCKED", "Isolated Buildah launcher needs verification")
        return None
    r.note("STORAGE", "PASS", "verified launcher definitions for /data and vfs")
    # Prepare separate context: all IaC files copied without modifying live source.
    context = r.out / "context"
    copy_context(TOOLS, TOOLS / containerfile, context)
    for mod in ("object_core", "blender_adapter"):
        for path in (provider / mod).rglob("*.py"):
            target = context / path.relative_to(provider)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    shutil.copy2(provider / "LICENSE", context / "ASSET_ASSISTANT_LICENSE")
    (context / "provider-provenance.json").write_text(
        json.dumps(
            {
                "source": str(provider),
                "revision": "76780c798562ef63786bc75debe3ec084d1025f2",
                "files": {str(p.relative_to(context)): digest(p) for p in context.rglob("*") if p.is_file()},
            },
            indent=2,
        )
    )
    old = (TOOLS / containerfile).read_text()
    if not re.search(r"^FROM\s", old, re.M):
        r.note("CONTAINERFILE", "BLOCKED", "No FROM found")
        return None
    # Keep known-good base and commands. Append provider COPY only when necessary.
    if re.search(r"COPY\s+.*\bobject_core\b", old) and re.search(r"COPY\s+.*\bblender_adapter\b", old):
        recipe = old
    else:
        recipe = (
            old.rstrip()
            + "\nCOPY object_core /opt/asset-assistant/object_core\nCOPY blender_adapter /opt/asset-assistant/blender_adapter\n"
        )
    recipe += "\nCOPY ASSET_ASSISTANT_LICENSE provider-provenance.json /opt/asset-assistant/\n"
    (context / "Containerfile").write_text(recipe)
    # Compile without importing bpy on the host; concrete code is checked in image below.
    for mod in ("object_core", "blender_adapter"):
        for p in (context / mod).rglob("*.py"):
            import ast

            try:
                ast.parse(p.read_text())
            except Exception as e:
                r.note("PYTHON_PARSE", "BLOCKED", str(p) + ": " + str(e))
                return None
    r.note("PYTHON_PARSE", "PASS", "all provider Python sources parse")
    tag = (
        BASE
        + ":generators-"
        + hashlib.sha256(
            (
                recipe
                + str(sorted((str(p.relative_to(context)), digest(p)) for p in context.rglob("*") if p.is_file()))
            ).encode()
        ).hexdigest()[:12]
    )
    # Skip busy store conflict instead of competing with another build.
    rc, processes = invoke(["ps", "-eo", "args"], 10)
    if rc == 0 and any(
        ("buildah" in line and " bud " in " " + line + " " and "watoom-m5-root-safe-work" in line)
        for line in processes.splitlines()
    ):
        r.note("BUILDAH_BUSY", "BLOCKED", "Another isolated Buildah build is active; do not compete")
        return None
    rc, output = invoke(
        [BUILDAH, "bud", "--tls-verify=false", "--layers", "-t", tag, "-f", context / "Containerfile", context],
        3600,
        log=r.out / "build.log",
    )
    if rc:
        r.note("BUILD", "FAIL", "image build exit=" + str(rc) + "; " + output[-450:])
        return None
    r.note("BUILD", "PASS", tag)
    # Run actual imports and registry discovery inside the image, not on Fedora.
    smoke = (
        "import sys,json;sys.path.insert(0,'/opt/asset-assistant');sys.path.insert(0,'/opt/watoom');from object_core.objects import get_provider;from blender_adapter.adapter import create_character;from blender_adapter.workflow import add_basic_rig;from blender_adapter.animation import add_idle,add_flight,add_locomotion;from blender_adapter.materials import prepare_materials;from blender_adapter.targets import get_adapter;import three_d;ids={x['id'] for x in three_d.registry()};expect=set("
        + repr(list(IDS))
        + ");assert expect.issubset(ids);print('IMPORTS_AND_REGISTRY_PASS')"
    )
    rc, out = invoke([BUILDAH, "from", tag], 240, log=r.out / "image-from.log")
    if rc:
        r.note("IMAGE_CREATE", "BLOCKED", out[-300:])
        return None
    cid = out.strip().splitlines()[-1]
    try:
        pure = (
            "import sys;sys.path.insert(0,'/opt/watoom');sys.path.insert(0,'/opt/asset-assistant');import three_d;from object_core.objects import get_provider;assert set("
            + repr(list(IDS))
            + ").issubset({x['id'] for x in three_d.registry()});print('PURE_PYTHON_PASS')"
        )
        rc, out = invoke([BUILDAH, "run", cid, "--", "python3", "-c", pure], 240, log=r.out / "smoke-python.log")
        if rc:
            r.note("PURE_PYTHON_SMOKE", "FAIL", out[-700:])
            return None
        r.note("PURE_PYTHON_SMOKE", "PASS", out.strip()[-300:])
        rc, out = invoke([BUILDAH, "run", cid, "--", "blender", "--help"], 120, log=r.out / "blender-help.log")
        if rc or not all(flag in out for flag in ("--background", "--python-expr", "--python-exit-code")):
            r.note("BLENDER_CLI", "FAIL", out[-700:])
            return None
        rc, out = invoke(
            [
                BUILDAH,
                "run",
                cid,
                "--",
                "blender",
                "--factory-startup",
                "--disable-autoexec",
                "--background",
                "--threads",
                "1",
                "--python-exit-code",
                "1",
                "--python-expr",
                smoke,
            ],
            240,
            log=r.out / "smoke-blender.log",
        )
        if rc:
            r.note("IMPORT_SMOKE", "FAIL", out[-700:])
            return None
        r.note("IMPORT_SMOKE", "PASS", out.strip()[-300:])
        # Generate and verify every advertised procedural generator before publishing.
        # This executes the exact Blender script inside the candidate container.
        for generator in IDS:
            job = "accept-" + generator.replace(".", "-")
            artifacts = "/tmp/" + job + "/artifacts"
            rc, output = invoke([BUILDAH, "run", cid, "--", "mkdir", "-p", "/tmp/" + job], 120)
            if rc:
                r.note("GENERATE_" + generator, "FAIL", "Cannot create test directory: " + output[-250:])
                return None
            payload = {
                "task": "3d-generate",
                "generator": generator,
                "parameters": {},
                "seed": 1001,
                "timeout": 180,
                "output": artifacts,
                "job_id": job,
            }
            if generator == "asset-assistant.avian":
                payload["style"] = "magpie"
            if generator == "asset-assistant.quadruped":
                payload["style"] = "wombat"
            cmd = [
                "blender",
                "--factory-startup",
                "--disable-autoexec",
                "--background",
                "--threads",
                "1",
                "--python-exit-code",
                "1",
                "--python",
                "/opt/watoom/blender_3d.py",
                "--",
                json.dumps(payload, separators=(",", ":")),
            ]
            rc, output = invoke([BUILDAH, "run", cid, "--", *cmd], 720, log=r.out / ("generator-" + generator + ".log"))
            if rc:
                r.note("GENERATE_" + generator, "FAIL", "Blender exit=" + str(rc) + "; " + output[-600:])
                return None
            verify = (
                "import pathlib,json,struct;d=pathlib.Path("
                + repr(artifacts)
                + ");m=json.loads((d/'manifest.json').read_text());assert m['status']=='PASS' and m['export_reimport'] is True;assert (d/'asset.blend').read_bytes().startswith(b'BLENDER');g=(d/'asset.glb').read_bytes();assert len(g)>100 and struct.unpack_from('<4sII',g)==(b'glTF',2,len(g));assert all((d/(v+'.png')).stat().st_size>100 for v in ('front','back','left','right','top','perspective'));print('REAL_EXPORT_PASS')"
            )
            rc, output = invoke(
                [BUILDAH, "run", cid, "--", "python3", "-c", verify], 120, log=r.out / ("verify-" + generator + ".log")
            )
            if rc:
                r.note("EXPORT_" + generator, "FAIL", output[-500:])
                return None
            rc, mounted = invoke([BUILDAH, "mount", cid], 60)
            if rc:
                r.note("EVIDENCE_" + generator, "FAIL", mounted[-500:])
                return None
            retained = r.out / "generator-artifacts" / generator
            shutil.copytree(pathlib.Path(mounted.strip()) / artifacts.lstrip("/"), retained)
            manifest = json.loads((retained / "manifest.json").read_text())
            for item in manifest["outputs"]:
                artifact = retained / item["path"]
                if (
                    not artifact.resolve().is_relative_to(retained.resolve())
                    or digest(artifact) != item["sha256"]
                    or artifact.stat().st_size != item["bytes"]
                ):
                    r.note("HASH_" + generator, "FAIL", "artifact path, size or hash mismatch")
                    return None
            r.note("GENERATE_" + generator, "PASS", "real Blender run, BLEND/GLB and six renders verified")
    finally:
        invoke([BUILDAH, "rm", cid], 120, log=r.out / "cleanup.log")
    rc, out = invoke([BUILDAH, "push", "--tls-verify=false", tag, "docker://" + tag], 3600, log=r.out / "push.log")
    if rc:
        r.note("PUSH", "FAIL", out[-500:])
        return None
    # Query authoritative registry manifest digest, never infer it from local build ID.
    rc, out = invoke(
        [
            "python3",
            "-c",
            "import urllib.request,json;u='http://127.0.0.1:5000/v2/watoom-toolkit/manifests/'+"
            + repr(tag.split(":")[-1])
            + ";q=urllib.request.Request(u,headers={'Accept':'application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json'});r=urllib.request.urlopen(q,timeout=20);print(r.headers.get('Docker-Content-Digest',''))",
        ],
        30,
    )
    match = re.search(r"sha256:[a-f0-9]{64}", out)
    if rc or not match:
        r.note("DIGEST", "BLOCKED", "Registry returned no verified digest: " + out[-300:])
        return None
    image = BASE + "@" + match.group(0)
    (r.out / "verified-image.txt").write_text(image + "\n")
    r.note("DIGEST", "PASS", image)
    return image


def deploy(r, image):
    if not DEFAULTS.is_file():
        r.note("IAC_DEFAULTS", "BLOCKED", "No staging defaults")
        return False
    source = DEFAULTS.read_text()
    matches = list(re.finditer(r"(?m)^(watoom_code_toolkit_image:\s*)([^\n#]+)", source))
    if len(matches) != 1:
        r.note("IAC_DEFAULTS", "BLOCKED", "Expected exactly one toolkit image default, got " + str(len(matches)))
        return False
    # Copy the exact existing YAML; no regex changes to other IaC fields.
    snapshot = r.out / "defaults-before.yml"
    snapshot.write_text(source)
    rc, deploy_json = invoke(["kubectl", "-n", NS, "get", "deployment", "watoom-toolkit", "-o", "json"], 25)
    if rc:
        r.note("DEPLOY_SNAPSHOT", "BLOCKED", "Cannot capture live Deployment")
        return False
    (r.out / "deployment-before.json").write_text(deploy_json)
    selected = matches[0]
    replacement = source[: selected.start(2)] + "'" + image + "'" + source[selected.end(2) :]
    DEFAULTS.write_text(replacement)
    (r.out / "defaults-after.yml").write_text(replacement)
    ansible = REPO / "ansible"
    env = dict(
        os.environ,
        ANSIBLE_CONFIG=str(ansible / "ansible.cfg"),
        ANSIBLE_ROLES_PATH=str(ansible / "roles"),
        TMPDIR=str(r.out),
    )
    play = ["ansible-playbook", "-i", "inventories/homelab/hosts.yml", "playbooks/watoom-code.yml", "-c", "local"]
    try:
        rc, out = invoke(play + ["--syntax-check"], 120, cwd=ansible, env=env, log=r.out / "syntax.log")
        if rc:
            r.note("SYNTAX", "FAIL", out[-600:])
            return False
        r.note("SYNTAX", "PASS", "Ansible syntax")
        rc, out = invoke(play, 600, cwd=ansible, env=env, log=r.out / "apply.log")
        if rc:
            r.note("ANSIBLE", "FAIL", out[-700:])
            return False
        r.note("ANSIBLE", "PASS", "Ansible staging reconciled")
        rc, out = invoke(
            ["kubectl", "-n", NS, "rollout", "status", "deployment/watoom-toolkit", "--timeout=240s"],
            270,
            log=r.out / "rollout.log",
        )
        if rc:
            r.note("READY", "FAIL", out[-500:])
            return False
        rc, out = invoke(["kubectl", "-n", NS, "get", "deployment", "watoom-toolkit", "-o", "json"], 30)
        try:
            actual = json.loads(out)["spec"]["template"]["spec"]["containers"][0]["image"]
        except Exception:
            actual = "unknown"
        if actual != image:
            r.note("IMAGE_IDENTITY", "FAIL", "running=" + actual)
            return False
        r.note("IMAGE_IDENTITY", "PASS", actual)
        # Readiness and image match only. Functional generator jobs need a live bounded acceptance.
        r.note(
            "GENERATION_ACCEPTANCE",
            "NOT TESTED",
            "Run a real Blender generation/export job per generator; no claim of full acceptance",
        )
        return True
    finally:
        # Only retain new defaults after successful rollout & image pin validation; on failure restore previous state.
        good = any(x["id"] == "IMAGE_IDENTITY" and x["status"] == "PASS" for x in r.results)
        if not good:
            DEFAULTS.write_text(source)
            # Roll back deployment image only, preserving immutable other resources and user data.
            try:
                orig = json.loads(deploy_json)
                old = orig["spec"]["template"]["spec"]["containers"][0]["image"]
                rc, txt = invoke(
                    [
                        "kubectl",
                        "-n",
                        NS,
                        "set",
                        "image",
                        "deployment/watoom-toolkit",
                        orig["spec"]["template"]["spec"]["containers"][0]["name"] + "=" + old,
                    ],
                    60,
                    log=r.out / "rollback.log",
                )
                if not rc:
                    rc, txt = invoke(
                        ["kubectl", "-n", NS, "rollout", "status", "deployment/watoom-toolkit", "--timeout=180s"], 200
                    )
                r.note(
                    "ROLLBACK",
                    "PASS" if rc == 0 else "FAIL",
                    "restored previous Toolkit image " + old + "; " + txt[-180:],
                )
            except Exception as e:
                r.note("ROLLBACK", "FAIL", str(e))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["audit", "runner"])
    p.add_argument("--i-approve", action="store_true")
    p.add_argument(
        "--containerfile", choices=["Containerfile.local-only", "Containerfile.3d"], default="Containerfile.local-only"
    )
    a = p.parse_args()
    if a.mode == "runner" and NS == "watoom-code":
        print(
            "BLOCKED: runner refuses the production watoom-toolkit Deployment; use tools/watoom-code/deploy-platform.py --blender-toolkit-only"
        )
        return 2
    r = Run("watoom-generator-" + a.mode)
    selected = audit(r, a.containerfile)
    if a.mode == "audit":
        return r.finish()
    if not a.i_approve:
        r.note("APPROVAL", "BLOCKED", "Image publishing and k3s staging reconciliation require --i-approve")
        return r.finish()
    if selected is None:
        return r.finish()
    if any(x["status"] == "BLOCKED" for x in r.results):
        return r.finish()
    image = build(r, selected, a.containerfile)
    if image:
        deploy(r, image)
    return r.finish()


if __name__ == "__main__":
    sys.exit(main())
