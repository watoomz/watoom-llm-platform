"""Pinned SDXL runtime publication on /data, not node imagefs."""

import argparse, hashlib, json, os, shutil, subprocess, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOFTWARE = (
    "127.0.0.1:5000/watoom-model-manager-sdxl@sha256:92b130715fb325780b1be5a9f8d8130f828e326933bf94efcc5bf5ad02678d71"
)
UMOCI_URL = "https://github.com/opencontainers/umoci/releases/download/v0.6.0/umoci.linux.amd64"
UMOCI_SHA = "b51c267ec394499e42c6fde47f240b7b7dba57ea49df0b5acd304378b82a3b71"
TOOLCHAIN = Path("/data/ai/toolchains/model-manager-sdxl")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(2 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(payload):
    root = Path(payload["path"])
    manifest = Path(payload["manifest"])
    if not root.is_relative_to(TOOLCHAIN) or root.is_symlink() or not root.is_dir():
        raise ValueError("Published SDXL payload required")
    if manifest.is_symlink() or not manifest.is_relative_to(TOOLCHAIN) or sha(manifest) != payload["sha256"]:
        raise ValueError("Payload manifest changed")
    for path in (root, manifest):
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("Runtime must be root-owned and application-read-only")
    if not (root / "bin/python").is_file():
        raise ValueError("Published interpreter absent")
    return root


def publish(out, software=SOFTWARE):
    if os.geteuid() != 0:
        raise ValueError("Administrative publication required")
    if (
        not software.startswith("127.0.0.1:5000/watoom-model-manager-sdxl@sha256:")
        or len(software.rsplit(":", 1)[1]) != 64
    ):
        raise ValueError("Pinned software required")
    if shutil.disk_usage("/data/ai").free < 50 * 1024**3 or shutil.disk_usage("/").free < 5 * 1024**3:
        raise ValueError("Filesystem reserve unavailable")
    from manage import run, write

    key = software.rsplit(":", 1)[1]
    destination = TOOLCHAIN / key
    tool = Path("/app/model-manager/build-tools/umoci-0.6.0/umoci")
    tool.parent.mkdir(parents=True, exist_ok=True)
    if not tool.exists():
        with urllib.request.urlopen(UMOCI_URL, timeout=60) as f:
            raw = f.read(9000000)
        if hashlib.sha256(raw).hexdigest() != UMOCI_SHA:
            raise ValueError("Unpacker checksum mismatch")
        tool.write_bytes(raw)
        tool.chmod(0o755)
    if sha(tool) != UMOCI_SHA:
        raise ValueError("Installed unpacker changed")
    destination.mkdir(parents=True, exist_ok=True, mode=0o755)
    oci = destination / "oci"
    bundle = destination / "bundle"
    conda = bundle / "rootfs/opt/conda"
    receipt = destination / "payload.json"
    if not receipt.exists():
        if not (oci / "index.json").exists():
            run(
                [
                    "skopeo",
                    "copy",
                    "--src-tls-verify=false",
                    "--override-os",
                    "linux",
                    "--override-arch",
                    "amd64",
                    "docker://" + software,
                    "oci:" + str(oci) + ":software",
                ],
                timeout=1800,
            )
        if not conda.is_dir():
            if bundle.exists():
                raise ValueError("Partial unpack retained for reconciliation")
            run([str(tool), "unpack", "--rootless", "--image", str(oci) + ":software", str(bundle)], timeout=1800)
        files = []
        for parent, dirs, names in os.walk(conda, followlinks=False):
            parent = Path(parent)
            os.chown(parent, 0, 0)
            os.chmod(parent, parent.stat().st_mode & 0o755)
            for name in dirs + names:
                path = parent / name
                if path.is_symlink():
                    target = os.readlink(path)
                    if target.startswith("/opt/conda/"):
                        target = os.path.relpath(conda / target[len("/opt/conda/") :], path.parent)
                        path.unlink()
                        path.symlink_to(target)
                    files.append({"path": str(path.relative_to(conda)), "link": target})
                    continue
                if path.is_file():
                    info = path.stat()
                    os.chown(path, 0, 0)
                    os.chmod(path, info.st_mode & 0o755)
                    files.append({"path": str(path.relative_to(conda)), "bytes": info.st_size, "sha256": sha(path)})
        write(
            receipt, {"format": "read-only-conda-v1", "software": software, "umoci_sha256": UMOCI_SHA, "files": files}
        )
        receipt.chmod(0o644)
    payload = {
        "format": "read-only-conda-v1",
        "path": str(conda),
        "manifest": str(receipt),
        "sha256": sha(receipt),
        "software": software,
    }
    verify(payload)
    # Label only this new read-only application payload; never change enforcement/policy.
    if shutil.which("getenforce") and run(["getenforce"]).strip() != "Disabled":
        run(["chcon", "--recursive", "--no-dereference", "--type", "container_file_t", "--", str(conda)], timeout=300)
    write(out / "sdxl-runtime.json", payload)
    profile = json.loads((ROOT / "config/llm/model-manager/runtime.json").read_text())
    cpu = profile["cpu_image"]["image"]
    code = "import sys,json,torch,diffusers,transformers,peft;from diffusers import StableDiffusionXLPipeline;print(json.dumps(dict(python=sys.version.split()[0],torch=torch.__version__,diffusers=diffusers.__version__,gpu=torch.cuda.is_available())))"
    proof = json.loads(
        run(
            [
                "docker",
                "run",
                "--rm",
                "--runtime",
                "runc",
                "--network",
                "none",
                "--memory",
                "768m",
                "--cpus",
                "1",
                "-e",
                "CUDA_VISIBLE_DEVICES=",
                "-e",
                "NVIDIA_VISIBLE_DEVICES=void",
                "-e",
                "LD_LIBRARY_PATH=/app/runtime/lib",
                "--mount",
                "type=bind,src=" + str(conda) + ",dst=/app/runtime,readonly",
                "--entrypoint",
                "/app/runtime/bin/python",
                cpu,
                "-c",
                code,
            ],
            timeout=180,
        )
        .strip()
        .splitlines()[-1]
    )
    if proof["gpu"]:
        raise ValueError("Unexpected GPU exposure")
    write(out / "payload-cpu-import.json", proof)
    tag = (
        "127.0.0.1:5000/watoom-model-manager-sdxl-runner:"
        + run(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT).strip()
    )
    run(
        [
            "docker",
            "build",
            "--memory",
            "256m",
            "--cpuset-cpus",
            "0",
            "--build-arg",
            "MANAGER_IMAGE=" + cpu,
            "--label",
            "org.opencontainers.image.revision=" + run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip(),
            "--label",
            "au.watoom.runtime-manifest-sha256=" + payload["sha256"],
            "-t",
            tag,
            "-f",
            str(ROOT / "tools/model-manager/Dockerfile.sdxl-runner"),
            str(ROOT / "tools/model-manager"),
        ],
        timeout=600,
    )
    run(["docker", "push", tag], timeout=180)
    image = json.loads(run(["docker", "image", "inspect", tag]))[0]
    artifact = {
        "image": next(
            v for v in image["RepoDigests"] if v.startswith("127.0.0.1:5000/watoom-model-manager-sdxl-runner@")
        ),
        "source_commit": run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip(),
        "runtime": payload,
        "generation": "NOT TESTED",
    }
    write(out / "sdxl-artifact.json", artifact)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    out = Path(args.evidence)
    if not out.is_absolute() or not out.is_relative_to("/data/ai/helper-scripts"):
        raise SystemExit("Private evidence path required")
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    print(json.dumps(publish(out)))
