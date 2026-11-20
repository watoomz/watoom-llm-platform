#!/usr/bin/env python3
"""Project existing reference metadata into a dedicated Glance bookmarks page; no scraping or execution."""

import argparse, pathlib, sqlite3, json, re, urllib.parse, collections, hashlib
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
START = "# WATOOM_KNOWLEDGE_PAGE_BEGIN\n"
END = "# WATOOM_KNOWLEDGE_PAGE_END\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True, type=pathlib.Path)
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    source = ROOT / "config/glance/glance.yml"
    before = source.read_text()
    config = yaml.safe_load(before)
    if START not in before:
        assert all(page["name"] != "Knowledge" for page in config["pages"])
    names = collections.defaultdict(list)
    links = collections.defaultdict(list)
    seen = set()
    rejected = 0

    def placeholder(parts):
        # Documentation examples harvested from skill text: reserved domains (RFC 2606) and fake or joke video IDs.
        host = parts.hostname.lower()
        if re.search(r"(?:^|\.)example\.(?:com|net|org)$|\.(?:example|test|invalid|localhost)$", host):
            return True
        video = (
            parts.path.strip("/")
            if host == "youtu.be"
            else (
                dict(urllib.parse.parse_qsl(parts.query)).get("v")
                if host.endswith("youtube.com") and parts.path == "/watch"
                else None
            )
        )
        return video is not None and (not re.fullmatch(r"[A-Za-z0-9_-]{11}", video) or video == "dQw4w9WgXcQ")

    def safe(url):
        parts = urllib.parse.urlsplit(url)
        return (
            parts.scheme == "https"
            and parts.hostname
            and not placeholder(parts)
            and parts.hostname
            and re.fullmatch(r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", parts.hostname)
            and not parts.username
            and not parts.password
            and not any(
                re.search("token|password|secret|api.?key|authorization", key, re.I)
                for key, _ in urllib.parse.parse_qsl(parts.query)
            )
        )

    def title(text):
        return re.sub("[-_]+", " ", text).strip().title()

    with sqlite3.connect("file:" + str(a.catalog.resolve()) + "?mode=ro", uri=True) as db:
        rows = db.execute(
            "SELECT s.repo,s.path,s.name,src.commit_sha FROM skills s JOIN sources src ON src.repo=s.repo WHERE s.validation!='valid' ORDER BY s.repo,s.name"
        ).fetchall()
        for repo, path, name, revision in rows:
            if (
                not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
                or not re.fullmatch("[a-f0-9]{40}", revision)
                or path.startswith("/")
                or ".." in pathlib.PurePosixPath(path).parts
            ):
                rejected += 1
                continue
            file = "SKILL.md" if path == "." else path if path.endswith("SKILL.md") else path + "/SKILL.md"
            url = "https://github.com/" + repo + "/blob/" + revision + "/" + urllib.parse.quote(file, safe="/")
            if url in seen:
                continue
            seen.add(url)
            readable = pathlib.PurePosixPath(path).name if re.search(r"[\u3400-\u9fff]", name) else name
            names[repo].append({"title": title(readable), "url": url})
        references = db.execute("SELECT url,discovered_in FROM external_links ORDER BY url").fetchall()
        for url, discovered in references:
            if not safe(url):
                rejected += 1
                continue
            if url in seen:
                continue
            seen.add(url)
            parts = urllib.parse.urlsplit(url)
            label = urllib.parse.unquote(parts.path.strip("/").split("/")[-1]) or parts.hostname
            links[parts.hostname].append({"title": title(label)[:110], "url": url})
    page = {
        "name": "Knowledge",
        "width": "wide",
        "columns": [
            {
                "size": "full",
                "widgets": [
                    {
                        "type": "bookmarks",
                        "title": "Source reading · not installed skills",
                        "groups": [{"title": repo, "links": items} for repo, items in sorted(names.items())],
                    }
                ],
            },
            {
                "size": "full",
                "widgets": [
                    {
                        "type": "bookmarks",
                        "title": "Collected reference links",
                        "groups": [{"title": host, "links": items} for host, items in sorted(links.items())],
                    }
                ],
            },
        ],
    }
    block = START + yaml.safe_dump([page], sort_keys=False, width=1000, allow_unicode=True) + END
    if START in before:
        prefix, rest = before.split(START, 1)
        _, suffix = rest.split(END, 1)
        after = prefix + block + suffix
    else:
        roots = list(re.finditer(r"(?m)^[A-Za-z][A-Za-z0-9_-]*:", before))
        page = next(index for index, match in enumerate(roots) if match.group() == "pages:")
        position = roots[page + 1].start() if page + 1 < len(roots) else len(before)
        after = before[:position].rstrip() + "\n" + block + before[position:]
    parsed = yaml.safe_load(after)
    assert parsed["pages"][-1]["name"] == "Knowledge"
    report = {
        "source_reading": sum(map(len, names.values())),
        "external_links": sum(map(len, links.values())),
        "deduplicated_total": len(seen),
        "rejected_unsafe_or_unpinned": rejected,
        "catalog_sha256": hashlib.sha256(a.catalog.read_bytes()).hexdigest(),
        "changed": after != before,
    }
    if a.check:
        assert after == before, "Glance knowledge projection differs"
    else:
        source.write_text(after)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
