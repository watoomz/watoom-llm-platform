#!/usr/bin/env python3
"""Render copyable pipeline prompts; no execution, credentials, inference or deployment."""

import argparse, html, json, pathlib, re
from project_groups import groups, stale_roots

ROOT = pathlib.Path(__file__).resolve().parents[1]
AVAILABILITY = {"available", "capability-gated", "host workflow", "inspection first", "validation required"}


def render():
    data = json.loads((ROOT / "config/glance/pipeline-prompts.json").read_text())
    ids = [x["id"] for x in data["templates"]]
    assert len(ids) == len(set(ids)) and data["version"] == 1
    allowed = groups()
    common = data["common"]
    assert (
        common.count("[PROJECT_PATH]") == 1 and common.count("[PROJECT_GROUPS]") == 1
    ), "common must name [PROJECT_PATH] and [PROJECT_GROUPS] once"
    common = common.replace("[PROJECT_GROUPS]", ", ".join(allowed[:-1]) + " or " + allowed[-1])
    for item in data["templates"]:
        assert re.fullmatch("[a-z0-9-]+", item["id"]) and item["title"] and item["category"] and item["prompt"], (
            "incomplete template " + item["id"]
        )
        assert item["availability"] in AVAILABILITY, "unknown availability for " + item["id"]
    # Prompts must only name live project groups; a retired root (development/, pipelines/) fails the render.
    stale = stale_roots(common + "".join(x["prompt"] for x in data["templates"]), allowed)
    assert not stale, "prompts name non-group project roots: " + ", ".join(stale)
    cards = []
    for item in data["templates"]:
        prompt = common + item["prompt"]
        cards.append(
            '<article class="prompt-card" id="'
            + html.escape(item["id"], quote=True)
            + '" data-category="'
            + html.escape(item["category"], quote=True)
            + '"><h2>'
            + html.escape(item["title"])
            + '</h2><p class="meta">'
            + html.escape(item["category"] + " · " + item["availability"])
            + '</p><details><summary>Preview prompt</summary><textarea readonly aria-label="'
            + html.escape(item["title"], quote=True)
            + ' prompt">'
            + html.escape(prompt)
            + '</textarea></details><button type="button" class="copy">Copy prompt</button></article>'
        )
    return (
        """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pipeline prompt templates · WatooM</title><link rel="stylesheet" href="/guide/assets/site.css"><link rel="stylesheet" href="/guide/assets/pipeline-prompts.css"><script src="/guide/assets/pipeline-prompts.js" defer></script></head><body><main class="prompts"><header><a href="/guide/job-reference.html">Job reference · all skills</a> · <a href="/">Glance</a> · <a href="/llm-lab">LLM Lab</a> · <a href="/guide/watoom-code.html">WatooM Code guide</a><h1>Pipeline prompt templates</h1><p>Choose a template, copy it into WatooM Code and replace the square-bracket fields. Copying never starts a job.</p><p>Available means a maintained route exists; each requested output still needs validation. Capability-gated and host workflows may require operator access or an installed feature. Exact-map reconstruction, effects conversion and online multiplayer are not implied by static asset acceptance.</p></header><div class="controls"><label>Find a pipeline<input type="search" id="search" placeholder="Dungeon, character, image, Kali…" autocomplete="off"></label><label>Project path (optional)<input id="project" placeholder="/data/ai/projects/games/my-project" autocomplete="off" data-groups='"""
        + html.escape(" ".join(allowed), quote=True)
        + """'></label></div><p id="count"></p><p id="feedback" role="status" aria-live="polite"></p><div class="cards">"""
        + "".join(cards)
        + """</div><p id="empty" hidden>No matching templates.</p><footer>Prompts preserve project containment, current handoff rules, stable job IDs and GPU ownership. Edit scope before running. <a href="https://watoom-code.internal.homelab.example">Open WatooM Code</a></footer></main></body></html>"""
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    page = ROOT / "config/glance/guide/pipeline-prompts.html"
    value = render()
    if args.check:
        assert page.read_text() == value, "Prompt page drift; rerun without --check"
    else:
        temporary = page.with_suffix(".html.tmp")
        temporary.write_text(value)
        temporary.replace(page)
    print("PASS pipeline-prompts.html")


if __name__ == "__main__":
    main()
