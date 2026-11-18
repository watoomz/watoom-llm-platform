#!/usr/bin/env python3
"""Generate the ue-mcp language-knowledge cards, the effects table and the reviewed rig policy.

Two manual products (same contract as every manuals/<product>/, verified by manual_extract.py):
  ue-mcp           one card per documented ue-mcp action (3.7k, from the generated tool reference) plus concept and
                   workflow cards. Each action card carries its declared effect (read / mutate / unknown), where that
                   effect came from, and whether the WatooM rig policy lets the model call it.
  watoom-ue-route  the reviewed policy and the route's own rules (sourced from tools/rig-ue-mcp/).

Effects are read statically from the published npm package (never executed): own actions declare
`specBp("read"|"mutate"|"unknown", ...)` in dist/tools/<category>.js; the Epic-wrapped `epic_*` actions take their effect from
dist/tools/epic/effects.js, keyed by Epic tool name; anything neither table names is "unclassified" and is treated as
`mutate`, which is ue-mcp's own default for an undeclared action.

  derive:  python3 extract/ue_mcp_entries.py derive --package <unpacked npm package dir> --manuals-root manuals
           (npm pack ue-mcp@<version>; tar -xzf; never npm install / run it)
  build:   python3 extract/ue_mcp_entries.py build --manuals-root manuals --policy-out ../rig-ue-mcp/ue-mcp-policy.reviewed.json
"""
import argparse
import collections
import json
import pathlib
import re

PRODUCT, ROUTE = "ue-mcp", "watoom-ue-route"
ROW = re.compile(r"^\| (`([a-z0-9_]+)\((.*?)\)`) \| (.*)$", re.M)
EPIC = re.compile(r"^\[Epic ([A-Za-z0-9_.]+)\]")
OWN = re.compile(r"^    ([a-z0-9_]+): (?:\{\s*\.\.\.)?[A-Za-z]+\(\"(read|mutate|unknown)\"", re.M)
DESTRUCTIVE = ("delete", "remove", "clear", "discard", "revert", "reset", "purge", "wipe", "destroy", "drop", "overwrite", "replace", "restore", "uninstall")

# Opened by the owner on 2026-11-14 ("i want all tools available"): every category is allowed and nothing is denied by default.
# Entries are per category (`<category>.*`), not `*`, so a category added by a later ue-mcp release stays blocked until the
# generator is re-run and the diff reviewed. To close something, add it to DENY_CATEGORIES / DENY_ACTIONS and re-run `build`:
# the policy, the cards and the route cards all follow. Ideas for what to close first if ever needed: flow, feedback, plugins,
# fab, source_control, editor.execute_python, editor.execute_command, project.build.
DENY_CATEGORIES = {}
DENY_ACTIONS = ()
# Tools that sit beside the 31 category tools but have no section in the generated tool reference (so the effects table cannot
# list them): `flow` runs multi-step YAML workflows. They are allowed like everything else.
EXTRA_TOOLS = ("flow",)


def sections(ref):
    cats, cur = collections.OrderedDict(), None
    for line in ref.split("\n"):
        m = re.match(r"^## ([a-z_]+)$", line)
        if m:
            cur = m.group(1)
            cats[cur] = []
            continue
        m = ROW.match(line)
        if cur and m:
            cats[cur].append((m.group(1), m.group(2), m.group(3), m.group(4)))
    return cats


def derive(package, manuals_root):
    pk = pathlib.Path(package) / "dist" / "tools"
    ref = (manuals_root / PRODUCT / "sources" / "tool-reference.md").read_text(encoding="utf-8")
    epic = dict(re.findall(r'^\s+"([A-Za-z0-9_.]+)": "(read|mutate|unknown)"', (pk / "epic" / "effects.js").read_text(encoding="utf-8"), re.M))
    epic_norm = {k.lower().replace("_", ""): v for k, v in epic.items()}
    out, stats = {}, collections.Counter()
    for cat, rows in sections(ref).items():
        f = pk / (cat + ".js")
        own = dict(OWN.findall(f.read_text(encoding="utf-8"))) if f.exists() else {}
        for _raw, act, _sig, desc in rows:
            e = EPIC.match(desc.strip().replace("\\|", "|"))
            if act in own:
                eff, src = own[act], "declared"
            elif e and act.startswith("epic_") and (e.group(1) + "." + act[5:]).lower().replace("_", "") in epic_norm:
                eff, src = epic_norm[(e.group(1) + "." + act[5:]).lower().replace("_", "")], "epic-table"
            else:
                eff, src = "mutate", "unclassified"
            out[cat + "." + act] = {"effect": eff, "source": src}
            stats[src] += 1
    pkg = json.loads((pathlib.Path(package) / "package.json").read_text(encoding="utf-8"))
    doc = {"package": pkg["name"] + "@" + pkg["version"], "note": "effects read statically from the package source; unclassified is treated as mutate (ue-mcp's own default)", "actions": out}
    (manuals_root / PRODUCT / "effects.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("effects.json:", len(out), "actions", dict(stats), "from", doc["package"])


def policy(effects):
    cats = sorted({k.split(".")[0] for k in effects})
    deny = sorted({k for k in effects if k.split(".")[0] in DENY_CATEGORIES} | set(DENY_ACTIONS))
    cats = sorted(set(cats) | set(EXTRA_TOOLS))
    return {"allow": ["%s.*" % c for c in cats if c not in DENY_CATEGORIES], "deny": ["%s.*" % c for c in sorted(DENY_CATEGORIES)] + [d for d in deny if d.split(".")[0] not in DENY_CATEGORIES]}


def matches(lst, ident):
    return any(e == "*" or e == ident or (e.endswith(".*") and ident.startswith(e[:-1])) for e in lst)


def allowed(pol, ident):
    return matches(pol["allow"], ident) and not matches(pol["deny"], ident)


def params_from(sig):
    out, depth, cur = [], 0, ""
    for ch in sig + ",":
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            p = cur.strip()
            cur = ""
            if p:
                name, _, typ = p.partition(":")
                out.append({"name": name.rstrip("?").strip(), "type": typ or "string", "default": None, "doc": "optional" if name.rstrip().endswith("?") else "required"})
        else:
            cur += ch
    return out


def action_entries(ref, effects, pol):
    entries = []
    for cat, rows in sections(ref).items():
        for raw, act, sig, desc in rows:
            ident = cat + "." + act
            eff = effects[ident]
            leading = act[5:] if act.startswith("epic_") else act
            destructive = eff["effect"] != "read" and leading.split("_")[0] in DESTRUCTIVE
            ok = allowed(pol, ident)
            cons = ["Effect: %s (%s)." % (eff["effect"], {"declared": "declared in ue-mcp's source", "epic-table": "from Epic's own accessMode table", "unclassified": "no declaration found; treated as a change, ue-mcp's own default"}[eff["source"]])]
            if destructive:
                cons.append("Destructive by name: removes or overwrites something it may not be able to give back. Prefer the dry-run/preview form where one exists.")
            if eff["effect"] == "unknown":
                cons.append("Effect depends on its parameters (an escape hatch such as running Python or a console command): use a dedicated action instead.")
            cons.append("Call it as tools(action=\"call\", category=\"%s\", method=\"%s\", args={...}); describe it first for the exact parameters." % (cat, act))
            cons.append("WatooM route: ALLOWED (reviewed rig policy)." if ok else
                        "WatooM route: NOT reachable (the reviewed rig policy denies it). Say so in your handoff for the operator; do not retry it or substitute another action to get around the policy.")
            desc_clean = re.sub(r"\s*Params: `[^`]*`\s*\|?\s*$", "", desc.replace("\\|", "|")).strip().rstrip("|").strip()
            entries.append({
                "symbol": ident, "kind": "mcp_action", "signature": "%s(%s)" % (act, sig.replace("\\|", "|")), "summary": desc_clean[:300],
                "params": params_from(sig.replace("\\|", "|")), "constraints": cons, "aliases": [ident.replace(".", "_"), "ue:" + ident],
                "meta": {"category": cat, "effect": eff["effect"], "effect_source": eff["source"], "destructive": destructive, "watoom_route_allowed": ok},
                "source_file": "tool-reference.md", "source_span": raw,
            })
    return entries


def concept(symbol, sig, summary, f, span, cons, kind="concept"):
    return {"symbol": symbol, "kind": kind, "signature": sig, "summary": summary, "source_file": f, "source_span": span, "constraints": cons}


def vendor_concepts(ref):
    return [
        concept("ue-mcp-context-strategies", "micro (default, ~240 tokens) | lean (~32k) | full (~90k)",
                "ue-mcp advertises either one gateway tool (micro) or its 31 category tools (lean, full); the strategy trades context cost against discovery round trips.",
                "configuration.md", "| **`micro`** (default) |",
                ["On WatooM the route runs micro: guide -> search -> describe -> call.", "In micro, call tools(action=\"guide\") first, then search/describe before calling an action you have not used."]),
        concept("ue-mcp-call-shapes", "tools(action=\"call\", category, method, args) | <category>(action, args)",
                "Every action is reached through the micro gateway (tools with action call, category, method, args) or, in lean/full, as the category tool with an action and an args object; parameters may also sit flat beside action.",
                "configuration.md", "Every category tool takes `action` and `args`:",
                ["The WatooM policy wrapper reads both shapes and decides on category.method.", "A wrong parameter type is refused with an Input validation error; describe the action to see the schema."]),
        concept("ue-mcp-effects-and-read-only", "effect: read | mutate | unknown; session access read-only -> WRITE_BLOCKED",
                "Every action declares its effect. Under a read-only session a mutate or unknown action is refused with WRITE_BLOCKED before it runs; unknown covers escape hatches such as execute_python and execute_command.",
                "configuration.md", "In `read-only` mode a call whose action is declared `mutate` or `unknown`",
                ["The read-only session mode is a daemon feature; the WatooM rig policy is the control that applies to this route."]),
        concept("ue-mcp-guards", "guards: scope all | mutations | writes | reads | unknown",
                "ue-mcp guards gate every bridge call from the project's ue-mcp.yml; scopes are read from each action's declared effect, and the unknown scope covers the escape hatches.",
                "guards.md", "A guard gates every bridge call.", ["Guards live in the project's ue-mcp.yml on the rig; they are separate from the WatooM policy file."]),
        concept("ue-mcp-dialogs-block-the-editor", "dialogBlocking: true -> refused until the dialog is answered",
                "A modal dialog blocks Unreal's game thread; while one is up every action is refused with dialogBlocking and the dialog's title, message and buttons.",
                "tool-reference.md", "A modal dialog blocks Unreal's game thread.",
                ["Read the refusal's dialogTitle/dialogMessage/buttons; do not retry blindly.", "Dialog handling modes are interactive / auto / defer; the default never answers for you."]),
        concept("ue-mcp-first-call", "project(action=\"get_status\") then level(get_outliner) / asset(list)",
                "The first call in any session is project get_status to check the editor connection; then explore with the outliner or an asset listing.",
                "tool-reference.md", "Start with `project(action=\"get_status\")` to check the connection",
                ["If get_status shows no editor, the Unreal Editor on the rig is not open: say so, do not retry in a loop."]),
        concept("ue-mcp-select-omit-timeout", "select, omit, timeoutMs beside action",
                "Every action accepts select and omit (dotted paths) to narrow the answer and timeoutMs (1 to 3,600,000 ms) to bound one call.",
                "tool-reference.md", "| `select` | string or string list | Keep only these result fields. |",
                ["Use select on big results (actor lists, graph reads) to keep your context small."]),
        concept("ue-landscape-real-world-terrain", "landscape: plan_real_world -> create -> import_heightmap -> analyze_terrain",
                "To reproduce a real heightmap at true scale: plan_real_world turns extent and elevation range into the exact create and import_heightmap parameters (landscape vertex counts are constrained), create makes the flat landscape, import_heightmap writes a 16-bit PNG or raw16 into it.",
                "tool-reference.md", "Turn a real-world extent plus a heightmap file into the exact landscape(create) and landscape(import_heightmap) parameters",
                ["import_heightmap refuses 8-bit images (a 256-step heightmap terraces): feed it a 16-bit PNG or raw16.", "minHeight/maxHeight remap 0..65535 onto a world Z band.",
                 "watoom-texture-layering/scripts/unreal_landscape_export.py makes the 16-bit PNG from the terrain builder's EXR and prints the plan_real_world parameters.",
                 "Composed from the documented action descriptions; not run end-to-end on the WatooM rig."], kind="workflow"),
        concept("ue-landscape-paint-layers", "landscape: add_layer / create_layer_info -> set_layer_weight_region -> get_layer_weight_region",
                "Paint layers are registered with add_layer (which creates the LayerInfo asset) and written with set_layer_weight_region as one uint8 per vertex (base64), a number per vertex, or a single 0..1 fraction; the engine no longer renormalises the other layers, so write every layer explicitly if they must sum to 1.",
                "tool-reference.md", "Weights are written as given: the engine no longer renormalises the other layers for you",
                ["The landscape material must declare the layer names (a layer-blend in the material) or reads refuse with the registered layers.", "Describe set_layer_weight_region for the exact region object before the first write.",
                 "Write all layers for a region, then read one back to verify; weights across layers should sum to 255.", "Composed from the documented action descriptions; not run end-to-end on the WatooM rig."], kind="workflow"),
        concept("ue-landscape-slope-analysis", "landscape: get_slope_map, analyze_terrain, get_slope_at_point",
                "Slope and terrain analysis are read-only: get_slope_map gives per-vertex slope with a fixed ten-degree histogram, analyze_terrain gives height and slope distribution plus the largest flat area; use them to check that slope-driven layers (rock, scree) cover the right ground.",
                "tool-reference.md", "Per-vertex slope in degrees over a rectangle, plus min/max/mean and a fixed nine-bucket ten-degree histogram.",
                ["Compare against the layer_report.json coverage from layer_masks.py: both should agree on how much of the terrain is steep."], kind="workflow"),
    ]


def route_entries(pol):
    closed = pol["deny"]
    return [
        concept("watoom-ue-allowed-categories", "allow = every ue-mcp category (%d), deny = %s" % (len(pol["allow"]), ", ".join(closed) if closed else "nothing"),
                "The rig policy allows every ue-mcp category plus the flow tool and denies nothing: all 3,714 actions and flows are reachable, including the escape hatches (execute_python, execute_command, console, invoke_*), builds, C++ writes, plugins, Fab, flows, feedback and source control. The owner opened it on 2026-11-14.",
                "ue-mcp-policy.reviewed.json", '"allow": [',
                ["Decisions are on category.method; deny always wins.", "The live copy is C:\\ProgramData\\watoom\\ue-mcp-policy.json on the rig, re-read on every request.",
                 "A category added by a later ue-mcp release is not allowed until the policy is regenerated and reviewed.",
                 "Allowed does not mean harmless: prefer the dedicated action over an escape hatch, read before you change, and do not run builds, plugin installs or source-control actions unless the task asks for them."], kind="config"),
        concept("watoom-ue-nothing-denied", "deny = []",
                "No action is denied by the WatooM policy, so a refusal does not come from it. A refusal then comes from ue-mcp itself (its guards in the project's ue-mcp.yml, a read-only session mode, a modal dialog blocking the editor, or an Input validation error).",
                "ue-mcp-policy.reviewed.json", '"deny": []',
                ["Read the refusal text: dialogBlocking, WRITE_BLOCKED, a guard name or a validation message each have a different fix.", "Do not retry a refused call unchanged."]),
        concept("watoom-ue-route-ask-for-action", "refused -> report the exact text, do not work around",
                "If a call is refused, report the category.method and the exact refusal text in the handoff; do not retry in a loop, rename the call, or use another route to reach the editor.",
                "ue-mcp-policy.reviewed.json", '"allow": [', ["Opening or closing an action is an operator decision on the rig."]),
    ]


def write(path, entries):
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
    print("%s: %d entries" % (path, len(entries)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["derive", "build"])
    ap.add_argument("--manuals-root", required=True, type=pathlib.Path)
    ap.add_argument("--package", type=pathlib.Path)
    ap.add_argument("--policy-out", type=pathlib.Path)
    a = ap.parse_args()
    root = a.manuals_root
    if a.mode == "derive":
        derive(a.package, root)
        return
    ref = (root / PRODUCT / "sources" / "tool-reference.md").read_text(encoding="utf-8")
    effects = json.loads((root / PRODUCT / "effects.json").read_text(encoding="utf-8"))["actions"]
    pol = policy(effects)
    if a.policy_out:
        a.policy_out.write_text(json.dumps(pol, indent=1) + "\n", encoding="utf-8")
        print("policy:", len(pol["allow"]), "allow,", len(pol["deny"]), "deny ->", a.policy_out)
    write(root / PRODUCT / "entries.jsonl", action_entries(ref, effects, pol) + vendor_concepts(ref))
    if (root / ROUTE / "sources" / "ue-mcp-policy.reviewed.json").exists():
        write(root / ROUTE / "entries.jsonl", route_entries(pol))


if __name__ == "__main__":
    main()
