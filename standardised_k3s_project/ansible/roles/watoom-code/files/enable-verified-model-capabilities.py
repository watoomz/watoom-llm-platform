"""Apply only explicitly qualified capability metadata; budgets and routing stay unchanged."""

import json, os, sys
from pathlib import Path


def update(document, profiles):
    models = document.get("providers", {}).get("watoom", {}).get("models", {})
    for name, capabilities in profiles.items():
        if name not in models:
            continue
        if (
            set(capabilities) != {"tools", "input", "output"}
            or type(capabilities["tools"]) is not bool
            or capabilities["input"] not in (["text"], ["text", "image"])
            or capabilities["output"] != ["text"]
        ):
            raise ValueError("Unsupported verified capability profile")
        models[name]["capabilities"] = capabilities
    return document


def main():
    path = Path(sys.argv[1])
    before = json.loads(path.read_text())
    document = update(json.loads(path.read_text()), json.loads(Path(sys.argv[2]).read_text()))
    if before == document:
        print("UNCHANGED")
        return
    stat = path.stat()
    temporary = path.with_name(path.name + ".capabilities-new")
    with temporary.open("w") as stream:
        json.dump(document, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, stat.st_mode & 0o777)
    os.chown(temporary, stat.st_uid, stat.st_gid)
    os.replace(temporary, path)
    print("UPDATED")


if __name__ == "__main__":
    main()
