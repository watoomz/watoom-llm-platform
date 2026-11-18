"""Owner project groups, read from the watoom-code role defaults (the mounted source of truth)."""
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "ansible/roles/watoom-code/defaults/main.yml"
PROJECT_PATH = re.compile(r"/data/ai/projects/([A-Za-z0-9_-]+)")


def groups():
    """Group names mounted read-write into the app: the generic groups plus the image root."""
    data = yaml.safe_load(DEFAULTS.read_text())
    root = data["watoom_code_project_groups_root"]
    images = Path(data["watoom_code_image_projects_root"])
    assert images.parent == Path(root), "image projects root must be a direct project group"
    return [*data["watoom_code_project_groups"], images.name]


def stale_roots(text, allowed):
    """Return /data/ai/projects/<name> roots mentioned in text that are not project groups."""
    return sorted({name for name in PROJECT_PATH.findall(text) if name not in allowed})
