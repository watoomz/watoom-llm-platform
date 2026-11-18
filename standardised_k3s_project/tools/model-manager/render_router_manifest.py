"""Render the tracked router manifests from the authored router source.

The GPU controller role applies these manifests, so they must already carry what cutover installs
(authored router.py plus the managed catalogue volumes, mounts and env); otherwise a routine
controller deploy restores the older embedded router.

  python3 render_router_manifest.py          # rewrite both manifests
  python3 render_router_manifest.py --check  # exit 1 when either is stale
"""
import sys
import yaml
from cutover import router_plan
from manage import ROOT

ROUTER = ROOT / "ansible/roles/llm-model-lab/files/gpu-controller-router.py"
MANIFESTS = [ROOT / "manifests/10-infrastructure/llm" / name for name in ("llm-router.yml", "llm-router-gpu-controller.yml")]


def render(text, code):
    docs = list(yaml.safe_load_all(text))
    cm = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "llm-router-app")
    dep = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "llm-router")
    new_cm, new_dep = router_plan(cm, dep, code)
    # A fixed restart stamp would roll the router on every apply.
    new_dep["spec"]["template"]["metadata"].get("annotations", {}).pop("kubectl.kubernetes.io/restartedAt", None)
    if not new_dep["spec"]["template"]["metadata"].get("annotations", True):
        del new_dep["spec"]["template"]["metadata"]["annotations"]
    docs = [new_cm if d is cm else new_dep if d is dep else d for d in docs]
    return yaml.safe_dump_all(docs, sort_keys=False, width=100)


def main():
    code = ROUTER.read_text()
    stale = []
    for path in MANIFESTS:
        desired = render(path.read_text(), code)
        if path.read_text() != desired:
            stale.append(path)
            if "--check" not in sys.argv:
                path.write_text(desired)
    if stale and "--check" in sys.argv:
        sys.exit("stale router manifests: " + ", ".join(p.name for p in stale))


if __name__ == "__main__":
    main()
