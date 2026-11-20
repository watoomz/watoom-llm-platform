"""Skills hooks for the existing admission-fenced release coordinator. No second deploy path."""

import copy, hashlib, importlib.util, json, pathlib, re, sqlite3
from release_guard import UnsafeRelease


class Release:
    def __init__(self, root, out, accepted, source, config):
        required = [
            "skills",
            "skill_security",
            "skill_versions",
            "skill_persistence",
            "skill_browser",
            "skill_runtime",
            "skill_old_image_rollback",
        ]
        if any(accepted.get(key) != "PASS" for key in required):
            raise UnsafeRelease("Skills candidate acceptance incomplete")
        self.source = source.resolve(strict=True)
        self.root = root
        self.out = out
        self.changed = False
        if hashlib.sha256(self.source.read_bytes()).hexdigest() != accepted.get("skill_collection_sha256"):
            raise UnsafeRelease("Reviewed discovery snapshot changed")
        self.config = copy.deepcopy(config)
        self.config["skill_catalog"]["collection"] = accepted["skill_collection_root"]
        if self.config["skill_catalog"]["collection"] != "/data/ai/skill-registry/wp-sk1-20261014/repositories":
            raise UnsafeRelease("Unexpected retained source root")
        self.agents = []
        for name in [
            "watoom-workflow",
            "watoom-builder",
            "watoom-investigator",
            "watoom-reviewer",
            "watoom-critic",
            "watoom-kali",
        ]:
            destination = pathlib.Path("/data/ai/watoom-code/config/agents") / (name + ".md")
            sourcepath = root / "ansible/roles/watoom-code/files/native/agents" / (name + ".md")
            if destination.is_symlink() or not destination.is_file():
                raise UnsafeRelease("Managed agent identity changed")
            old = destination.read_bytes()
            new = sourcepath.read_text().replace("  model: active-model", "  model: swift-qwen38-coder").encode()
            (out / (name + ".skills-before.md")).write_bytes(old)
            self.agents.append((destination, old, new))

    def apply(self, atomic):
        self.atomic = atomic
        if any(path.read_bytes() != old for path, old, new in self.agents):
            raise UnsafeRelease("Managed agent changed concurrently")
        spec = importlib.util.spec_from_file_location(
            "watoom_skill_import", self.root / "tools/watoom-code/import-skill-collection.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.merge(self.source, "/data/ai/watoom-code/catalog.sqlite")
        (self.out / "skills-import.json").write_text(json.dumps(result, indent=2))
        self.changed = True
        for path, old, new in self.agents:
            atomic(path, new)

    def rollback(self):
        if not self.changed:
            return
        for path, old, new in self.agents:
            if path.read_bytes() not in (old, new):
                raise UnsafeRelease("Agent changed during rollback; refusing overwrite")
            self.atomic(path, old)
        # Discovery metadata is additive and compatible with the independently tested old image.
        # Never restore an older SQLite database over newer user reviews or assignments.
        (self.out / "skills-rollback.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "agents": "restored",
                    "catalog": "additive metadata retained; user reviews and assignments preserved",
                }
            )
        )

    def verify(self, get):
        page = get("/api/skill/catalog?approvedOnly=false&limit=1")["data"]
        if page["discovered"] < 197:
            raise UnsafeRelease("Retained skills collection unavailable")
        if any(path.read_bytes() != new for path, old, new in self.agents):
            raise UnsafeRelease("Managed agent bytes differ")
        return {"skills_catalog": "PASS", "all_six_agents": "PASS"}


class NativeRelease:
    """Additive reviewed native files, using existing config discovery; no app rollout."""

    def __init__(self, root, out, names, target=None, previous=None, provenance=None):
        import shutil, os

        self.out = pathlib.Path(out)
        self.target = pathlib.Path(target or "/data/ai/watoom-code/config/skills")
        self.installed = []
        self.names = list(names)
        self.entries = self.names + (
            ["blender-source.json", "blender-LICENSE"] if provenance is None else list(provenance)
        )
        self.source = pathlib.Path(root) / "ansible/roles/watoom-code/files/skills"
        self.stage = self.out / "native-staging"
        self.stage.mkdir(mode=0o700)
        self.previous = json.loads((pathlib.Path(previous) / "native-release.json").read_text()) if previous else None
        if self.previous and self.previous["target"] != str(self.target):
            raise UnsafeRelease("Previous native target differs")
        self.old_hashes = {}
        self.hashes = {}
        self.backup = self.out / "native-before"
        self.backup.mkdir(mode=0o700)
        for name in self.entries:
            if "/" in name or name.startswith("."):
                raise UnsafeRelease("Unsafe native entry")
            source = self.source / name
            dest = self.target / name
            if source.is_symlink() or not source.exists() or dest.is_symlink():
                raise UnsafeRelease("Unsafe native source/destination: " + name)
            if dest.exists() and not self.previous:
                raise UnsafeRelease("Additive native release refuses existing destinations: " + name)
            for file in ([source] if source.is_file() else source.rglob("*")):
                if file.is_symlink():
                    raise UnsafeRelease("Native source symlink forbidden")
            if source.is_dir():
                shutil.copytree(source, self.stage / name)
            else:
                shutil.copy2(source, self.stage / name)
            for file in [self.stage / name, *((self.stage / name).rglob("*") if (self.stage / name).is_dir() else [])]:
                os.chown(file, 1001, 1001)
                os.chmod(file, 0o750 if file.is_dir() else 0o644)
            self.hashes[name] = self.digest(self.stage / name)
            self.old_hashes[name] = self.digest(dest) if dest.exists() else None
            if self.previous and self.old_hashes[name] not in (self.previous["hashes"].get(name), self.hashes[name]):
                raise UnsafeRelease("Owned native bytes changed outside release: " + name)
        self.save()

    @staticmethod
    def digest(path):
        if path.is_symlink():
            raise UnsafeRelease("Native target symlink forbidden")
        if path.is_file():
            return hashlib.sha256(path.read_bytes()).hexdigest()
        files = {
            str(f.relative_to(path)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(path.rglob("*"))
            if f.is_file() and not f.is_symlink() and "__pycache__" not in f.relative_to(path).parts
        }
        if any(f.is_symlink() for f in path.rglob("*")):
            raise UnsafeRelease("Native target symlink forbidden")
        return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()

    def save(self):
        (self.out / "native-release.json").write_text(
            json.dumps(
                {
                    "target": str(self.target),
                    "names": self.names,
                    "hashes": self.hashes,
                    "installed": self.installed,
                    "old_hashes": self.old_hashes,
                },
                indent=2,
            )
        )

    def apply(self):
        import subprocess

        for name in self.entries:
            current = self.target / name
            if current.is_symlink() or (self.digest(current) if current.exists() else None) != self.old_hashes[name]:
                raise UnsafeRelease("Native destination changed concurrently")
        for name in self.entries:
            if self.old_hashes[name] == self.hashes[name]:
                continue
            if self.old_hashes[name] is not None:
                (self.target / name).rename(self.backup / name)
            (self.stage / name).rename(self.target / name)
            self.installed.append(name)
            self.save()
            subprocess.run(["restorecon", "-R", str(self.target / name)], check=True, capture_output=True)
        if any(self.digest(self.target / n) != h for n, h in self.hashes.items()):
            raise UnsafeRelease("Native installed hashes differ")

    def rollback(self):
        retained = self.out / "retained-native"
        retained.mkdir(exist_ok=True, mode=0o700)
        for name in reversed(self.installed):
            target = self.target / name
            if self.digest(target) != self.hashes[name]:
                raise UnsafeRelease("Native bytes changed; refusing rollback overwrite: " + name)
            target.rename(retained / name)
            if (self.backup / name).exists():
                (self.backup / name).rename(target)
        self.installed = []
        self.save()

    def verify(self, get, before):
        import time

        deadline = time.monotonic() + 45
        while True:
            skills = get("/api/skill?directory=/workspace")["data"]
            names = {x["name"] for x in skills}
            if set(self.names).issubset(names) and set(before).issubset({x["id"] for x in skills}):
                break
            if time.monotonic() > deadline:
                raise UnsafeRelease("Native discovery did not settle")
            time.sleep(0.5)
        return {
            "status": "PASS",
            "added": self.names,
            "total_registered": len(skills),
            "previous_skills_preserved": True,
            "hashes_verified": all(self.digest(self.target / n) == h for n, h in self.hashes.items()),
        }


def promote_native_blender(prompt_skills=False):
    import argparse, sys, os, time
    from maintenance_guard import Maintenance
    import release_guard

    p = argparse.ArgumentParser()
    p.add_argument("--prompt-skills-only" if prompt_skills else "--blender-skills-only", action="store_true")
    p.add_argument("--iac-root", required=True, type=pathlib.Path)
    p.add_argument("--evidence", required=True, type=pathlib.Path)
    p.add_argument("--i-approve", action="store_true")
    p.add_argument("--update-owned-native", type=pathlib.Path)
    a = p.parse_args()
    print(
        "RISK: installs or updates only the reviewed native "
        + ("prompt creation/pipeline skill trees" if prompt_skills else "23 Blender skill trees and their provenance")
        + " in production discovery. No application, inference or network restart. A native idle fence, database snapshot and scoped rollback protect existing work.",
        flush=True,
    )
    if not a.i_approve:
        raise UnsafeRelease("--i-approve required")
    out = a.evidence.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    m = Maintenance("watoom-code", "watoom-code", out, True, True)
    get = m.request

    def clearance():
        release_guard.active_clear(get("/api/session/active"))
        release_guard.durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite"))
        jobs = m.kub("get", "jobs")["items"]
        if any(x.get("status", {}).get("active") for x in jobs):
            raise UnsafeRelease("Active worker Job; retry after completion")

    baseline = m.kub("get", "deploy", "watoom-code")
    before = get("/api/skill?directory=/workspace")["data"]
    (out / "application-before.json").write_text(json.dumps(baseline, indent=2))
    (out / "skills-before.json").write_text(json.dumps(before, indent=2))
    source = a.iac_root / "ansible/roles/watoom-code/files/skills"
    if prompt_skills:
        import re

        expected = {
            x["id"] for x in json.loads((a.iac_root / "config/glance/pipeline-prompts.json").read_text())["templates"]
        } | {"blender-builder"}
        names = ["watoom-prompt-creator"] + sorted("watoom-prompt-" + x for x in expected)
        for name in names:
            text = (source / name / "SKILL.md").read_text()
            match = re.search(r"```prompt-builder\s*\n([\s\S]*?)\n```", text)
            if not match:
                raise UnsafeRelease("Prompt skill contract missing: " + name)
            value = json.loads(match[1])
            if value.get("version") != 1 or value.get("kind") != (
                "creator" if name == "watoom-prompt-creator" else "pipeline"
            ):
                raise UnsafeRelease("Prompt skill contract invalid: " + name)
        release = NativeRelease(a.iac_root, out, names, previous=a.update_owned_native, provenance=[])
    else:
        report = json.loads((source / "blender-source.json").read_text())
        if (
            report["commit"] != "71d031dab8bc6729504d11a78cbe91945401045f"
            or report["validation"]["modules"] != 20
            or any(c.startswith("FAIL ") for c in report["validation"]["checks"])
            or report["validation"]["cpu_render"]["status"] != "PASS"
        ):
            raise UnsafeRelease("Pinned real CPU compatibility acceptance required")
        if a.update_owned_native and report.get("runner_recovery", {}).get("status") != "PASS":
            raise UnsafeRelease("Actual runner interruption/recovery acceptance required for owned update")
        names = sorted(x.name for x in source.glob("blender-*") if x.is_dir()) + ["watoom-blender-asset-builder"]
        if len(names) != 23:
            raise UnsafeRelease("Exactly 22 upstream skills plus builder required")
        release = NativeRelease(a.iac_root, out, names, previous=a.update_owned_native)

    def save(owner):
        with (out / "guard-owner.private").open("x") as f:
            f.write(owner)
            f.flush()
            os.fsync(f.fileno())

    owner = release_guard.acquire(get, lambda path, body: m.request(path, body), save, clearance)
    healthy = True
    try:
        release_guard.snapshot_database(
            pathlib.Path("/data/ai/watoom-code/application.sqlite"), out / "application-before.private.sqlite"
        )
        healthy = False
        release.apply()
        result = release.verify(get, [x["id"] for x in before])
        healthy = True
        if m.kub("get", "deploy", "watoom-code")["spec"] != baseline["spec"]:
            raise UnsafeRelease("Application deployment changed during skill installation")
        (out / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    except BaseException:
        release.rollback()
        healthy = True
        raise
    finally:
        if healthy:
            release_guard.release(get, lambda path, body: m.request(path, body), owner)
