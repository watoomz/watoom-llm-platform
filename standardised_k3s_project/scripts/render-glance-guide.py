#!/usr/bin/env python3
"""Render docs/guide/*.md into the multi-page Glance operations guide.

Requires markdown-it-py (/data/ai/toolchains/docs-render/bin/python). Every page shares one
shell, sidebar and theme (assets/site.css, assets/site.js). Internal links and anchors are
validated; a broken link fails the render. --check reports drift without writing.
This does not deploy anything: the guide is served by hostPath from the operator checkout.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/guide"
GUIDE = ROOT / "config/glance/guide"
# Sidebar order. index.md is the overview served at /guide/.
PAGES = ["index", "operator-manual", "software-design", "services", "network", "platform", "media", "games", "voice-companion", "artex", "ai",
         "watoom-code", "monitoring", "security", "operations", "tickets", "recovery", "disaster-recovery", "troubleshooting",
         "llm-user-guide", "llm-api", "llm-project", "llm-extensions", "animation-library", "llm-publication",
         "server-catalogue", "server-scripts", "server-playbooks", "server-roles", "server-tools"]
# Downloadable documentation references; source stays under docs/llm-platform.
DOCUMENT_ASSETS = {
    "assets/server-catalogue.json": ROOT / "docs/server-catalogue.json",
    'assets/llm-platform/OPENCODE-LICENSE.txt': ROOT / 'docs/llm-platform/api/OPENCODE-LICENSE.txt',
    'assets/llm-platform/watoom-code.openapi.json': ROOT / 'docs/llm-platform/api/watoom-code.openapi.json',
    'assets/llm-platform/router.openapi.json': ROOT / 'docs/llm-platform/api/router.openapi.json',
    'assets/llm-platform/watoom_client.py': ROOT / 'docs/llm-platform/examples/watoom_client.py',
    'assets/llm-platform/watoom_client.mjs': ROOT / 'docs/llm-platform/examples/watoom_client.mjs',
    'assets/llm-platform/verification.json': ROOT / 'docs/llm-platform/verification.json',
}
TOOLS = [("/guide/job-reference.html", "Job reference"),
         ("/guide/pipeline-prompts.html", "Pipeline prompts"),
         ("/guide/padkontrol-v18.html", "padKONTROL v18"),
         ("/", "Glance dashboard")]
TOOLS = [(href, label) for href, label in TOOLS if not href.startswith("/guide/") or (GUIDE / href.removeprefix("/guide/")).exists()]
CALLOUTS = {"NOTE": "Note", "RULE": "Rule", "WARNING": "Warning"}
# Old page addresses that forward to the page that now covers them.
REDIRECTS = {
    "ansible-iac.html": "operations.html",
    "llm-documentation.html": "llm-api.html",
    "llm-requirements.html": "llm-api.html",
    "llm-design.html": "llm-api.html",
    "llm-specification.html": "llm-api.html",
    "llm-operations.html": "llm-api.html",
}

# Sidebar grouping: every page in PAGES belongs to exactly one labelled group, in
# this order. Keeps the primary flow short and the LLM platform set together.
GROUPS = [
    ("Overview", ["index"]),
    ("Architecture", ["software-design"]),
    ("Platform", ["platform", "network", "security"]),
    ("Services", ["services", "media", "games", "voice-companion", "artex", "monitoring"]),
    ("LLM platform", ["ai", "watoom-code", "llm-project", "llm-extensions", "animation-library", "llm-user-guide", "llm-api", "llm-publication"]),
    ("Source reference", ["server-catalogue", "server-scripts", "server-playbooks", "server-roles", "server-tools"]),
    ("Operations", ["operator-manual", "operations", "tickets", "recovery", "disaster-recovery", "troubleshooting"]),
]
# A scoped export (the public LLM platform source) omits some pages. Keep the sidebar to the pages that exist.
PAGES = [name for name in PAGES if (SOURCE / (name + ".md")).exists()]
GROUPS = [(label, [name for name in names if name in PAGES]) for label, names in GROUPS]
GROUPS = [(label, names) for label, names in GROUPS if names]


def url(page, fragment=""):
    base = "/guide/" if page == "index" else "/guide/" + page + ".html"
    return base + ("#" + fragment if fragment else "")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def front_matter(text, name):
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, name + ": missing front matter"
    meta = dict(line.split(": ", 1) for line in match[1].splitlines())
    assert {"title", "nav", "summary"} <= set(meta), name + ": front matter needs title, nav, summary"
    return meta, text[match.end():]


def engine():
    md = MarkdownIt("commonmark", {"html": False, "typographer": False}).enable("table")
    md.add_render_rule("fence", lambda renderer, tokens, i, options, env: (
        '<div class="code-wrap"><button class="copy-btn" type="button">Copy</button><pre><code'
        + (' class="language-' + html.escape(tokens[i].info.split()[0]) + '"' if tokens[i].info.strip() else "")
        + ">" + html.escape(tokens[i].content) + "</code></pre></div>\n"))
    md.add_render_rule("table_open", lambda *a: '<div class="table-scroll"><table>\n')
    md.add_render_rule("table_close", lambda *a: "</table></div>\n")
    return md


def parse(name):
    meta, body = front_matter((SOURCE / (name + ".md")).read_text(), name)
    md = engine()
    tokens = md.parse(body)
    headings, used, links = [], set(), []
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            assert token.tag in ("h2", "h3", "h4"), name + ": use ## and below; the page title is the h1"
            text = tokens[index + 1].content
            ident = slug(text)
            while ident in used:
                ident += "-2"
            used.add(ident)
            token.attrSet("id", ident)
            headings.append((token.tag, ident, text))
        elif token.type == "blockquote_open":
            inline = next(t for t in tokens[index:] if t.type == "inline")
            marker = re.match(r"\[!([A-Z]+)\]\s*", inline.content)
            if marker:
                kind = marker[1]
                assert kind in CALLOUTS, name + ": unknown callout " + kind
                token.attrSet("class", "callout callout-" + kind.lower())
                token.attrSet("data-kind", CALLOUTS[kind])
                inline.content = inline.content[marker.end():]
                inline.children[0].content = re.sub(r"^\[![A-Z]+\]\s*", "", inline.children[0].content)
                while inline.children and (inline.children[0].type == "softbreak"
                                           or inline.children[0].type == "text" and not inline.children[0].content):
                    inline.children.pop(0)
        for child in token.children or []:
            if child.type != "link_open":
                continue
            href = child.attrGet("href")
            if re.match(r"^[a-z][a-z0-9+.-]*:", href):
                child.attrSet("rel", "noopener")
                continue
            path, _, fragment = href.partition("#")
            if path.endswith(".md"):
                target = path[:-3]
                assert target in PAGES, name + ": link to unknown page " + href
                child.attrSet("href", url(target, fragment))
                links.append((target, fragment))
            elif not path:
                links.append((name, fragment))
            elif path.startswith("/guide/"):
                target = path.removeprefix("/guide/")
                assert ((target in DOCUMENT_ASSETS and DOCUMENT_ASSETS[target].is_file()) or (GUIDE / target).exists()), name + ": missing guide file " + href
    return {"name": name, "meta": meta, "html": md.renderer.render(tokens, md.options, {}),
            "headings": headings, "anchors": used, "links": links, "tokens": tokens}


def search_entries(page):
    """One entry per h2/h3 section: title plus the first ~360 characters of its text."""
    entries, current, text = [], (page["meta"]["title"], ""), []

    def flush():
        body = re.sub(r"\s+", " ", " ".join(text)).strip()
        entries.append({"page": page["meta"]["nav"], "title": current[0],
                        "url": url(page["name"], current[1]), "text": body[:360]})

    for index, token in enumerate(page["tokens"]):
        if token.type == "heading_open" and token.tag in ("h2", "h3"):
            flush()
            current, text = (page["tokens"][index + 1].content, token.attrGet("id")), []
        elif token.type == "inline" and not (index and page["tokens"][index - 1].type == "heading_open"):
            text.append(token.content)
        elif token.type == "fence":
            text.append(token.content)
    flush()
    return [e for e in entries if e["text"] or e["url"].count("#")]


def sidebar(pages, current):
    by_name = {p["name"]: p for p in pages}
    grouped = {name for _, names in GROUPS for name in names}
    assert grouped == set(by_name), (
        "GROUPS must cover PAGES exactly; missing="
        + ", ".join(sorted(set(by_name) - grouped))
        + " extra=" + ", ".join(sorted(grouped - set(by_name))))
    items = []
    for label, names in GROUPS:
        items.append('<p class="nav-label">' + html.escape(label) + "</p>")
        for name in names:
            page = by_name[name]
            active = name == current["name"]
            items.append('<a class="nav-link' + (' active" aria-current="page' if active else "") + '" href="'
                         + url(name) + '">' + html.escape(page["meta"]["nav"]) + "</a>")
            if active:
                toc = "".join('<a class="toc-link" href="#' + ident + '">' + html.escape(text) + "</a>"
                              for tag, ident, text in current["headings"] if tag == "h2")
                if toc:
                    items.append('<div class="toc">' + toc + "</div>")
    tools = "".join('<a class="nav-link tool" href="' + href + '">' + html.escape(label) + "</a>" for href, label in TOOLS)
    return ('<nav class="nav" aria-label="Guide pages">' + "".join(items)
            + '<p class="nav-label">Tools</p>' + tools + "</nav>")


LIVE = ('<section class="live" aria-label="Live status"><div class="live-grid">'
        '<div class="live-card"><span>Applications</span><b id="live-apps">—</b><small id="live-apps-sub"></small></div>'
        '<div class="live-card"><span>Pods</span><b id="live-pods">—</b><small id="live-pods-sub"></small></div>'
        '<div class="live-card"><span>Memory</span><b id="live-mem">—</b><small>host RAM in use</small></div>'
        '<div class="live-card"><span>Disk</span><b id="live-disk">—</b><small>cluster filesystems</small></div>'
        '</div><div id="live-problems" class="live-problems"></div></section>'
        '<section class="flows" aria-label="Request flows"><div class="flow-tabs" role="tablist">'
        + "".join('<button class="flow-tab' + (" active" if key == "local" else "") + '" type="button" data-flow="'
                  + key + '">' + label + "</button>"
                  for key, label in [("local", "Internal web"), ("media", "Media"), ("stream", "Stream"),
                                     ("llm", "AI inference"), ("public", "Public web")])
        + '</div><div class="flow-board"><svg id="flow-svg" viewBox="0 70 1000 144" role="img" '
        'aria-label="Request flow diagram"></svg></div><p id="flow-explain" class="flow-explain"></p></section>')


def shell(pages, page):
    meta = page["meta"]
    title = meta["title"] if page["name"] == "index" else meta["title"] + " · Agent Export"
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="dark">'
            "<title>" + html.escape(title) + "</title>"
            '<meta name="description" content="' + html.escape(meta["summary"], quote=True) + '">'
            '<link rel="stylesheet" href="/guide/assets/site.css">\n</head>\n<body>\n'
            '<a class="skip" href="#content">Skip to content</a>'
            '<div class="shell">\n<aside class="sidebar">'
            '<a class="brand" href="/guide/"><span class="brand-mark" aria-hidden="true"></span>WATOOM<span>//ops</span></a>'
            '<button class="menu-toggle" type="button" aria-expanded="false" aria-controls="sidebar-nav">Menu</button>'
            '<div class="sidebar-body" id="sidebar-nav">'
            '<label class="search-wrap"><span class="sr-only">Search the guide</span>'
            '<input id="site-search" class="search" type="search" placeholder="Search guide  /" autocomplete="off"></label>'
            '<div id="search-results" class="search-results" hidden></div>'
            + sidebar(pages, page) + "</div></aside>\n"
            '<main class="main" id="content">\n<header class="hero"><p class="eyebrow">'
            + html.escape(meta["nav"]) + "</p><h1>" + html.escape(meta["title"]) + '</h1><p class="lede">'
            + html.escape(meta["summary"]) + "</p></header>\n"
            + (LIVE if page["name"] == "index" else "")
            + '<div class="content">\n' + page["html"] + "</div>\n"
            '<footer class="page-foot"><span>Source <code>docs/guide/' + page["name"] + '.md</code></span>'
            '<span>Rendered by <code>scripts/render-glance-guide.py</code></span></footer>\n'
            '</main>\n</div>\n<script src="/guide/assets/site.js"></script>\n</body>\n</html>\n')


def redirect(target):
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="refresh" content="0; url=' + url(target.removesuffix(".html")) + '">'
            "<title>Moved</title></head><body><p>This page moved to <a href=\"" + url(target.removesuffix(".html"))
            + '">' + target + "</a>.</p></body></html>\n")


def build():
    unknown = sorted(p.stem for p in SOURCE.glob("*.md") if p.stem not in PAGES)
    assert not unknown, "docs/guide pages missing from PAGES: " + ", ".join(unknown)
    pages = [parse(name) for name in PAGES]
    anchors = {page["name"]: page["anchors"] for page in pages}
    for page in pages:
        for target, fragment in page["links"]:
            assert not fragment or fragment in anchors[target], \
                page["name"] + ": link to missing anchor " + target + "#" + fragment
    outputs = {("index.html" if p["name"] == "index" else p["name"] + ".html"): shell(pages, p) for p in pages}
    outputs.update({name: redirect(target) for name, target in REDIRECTS.items()})
    index = [entry for page in pages for entry in search_entries(page)]
    outputs["assets/search-index.json"] = json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n"
    outputs.update({name: source.read_text() for name, source in DOCUMENT_ASSETS.items()})
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift; do not write")
    args = parser.parse_args()
    drift = []
    for name, content in build().items():
        path = GUIDE / name
        if not path.exists() or path.read_text() != content:
            drift.append(name)
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + ".tmp")
                temporary.write_text(content)
                temporary.replace(path)
        print(("DRIFT " if args.check and name in drift else "PASS  ") + name)
    return 1 if args.check and drift else 0


if __name__ == "__main__":
    sys.exit(main())
