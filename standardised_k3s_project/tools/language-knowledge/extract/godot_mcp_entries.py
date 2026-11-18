#!/usr/bin/env python3
"""Generate manuals/godot-mcp-toolkit/entries.jsonl and manuals/watoom-godot-route/entries.jsonl.

Same "manual product" contract as every other manuals/<product>/ (see manual_extract.py): each entry names a
source_file under sources/ and a source_span that must appear verbatim there, so manual_extract.py remains the
integrity gate. This script only saves hand-typing one entry per tool: it parses the toolkit's generated tool
reference (sources/tool-reference.md) and takes each tool's description, access label, tier and parameters from it,
then adds the WatooM route fact (whether the rig policy lets the model call it) from watoom-godot-route's own source.

Re-run after re-downloading the sources or after changing the rig allow-list default:
  python3 extract/godot_mcp_entries.py --manuals-root manuals
then verify with manual_extract.py --product godot-mcp-toolkit / watoom-godot-route (build.sh does this for the registry).
"""
import argparse
import json
import pathlib
import re

BLOCK = re.compile(r"<!-- tool:([a-z0-9_]+) -->\n### `([a-z0-9_]+)`\n\n(.+?)\n\n(\*\*eager\*\*|on-demand \(group: `([a-z0-9_]+)`\))([^\n]*)\n", re.S)
ROW = re.compile(r"^\| `([^`]+)` \| ([^|]+?) \| (yes|no) \| ([^|]*?) \|$", re.M)
OPERATIONS = re.compile(r"^_(\d+) operations?\._$", re.M)

# The tools upstream labels as risky, from security-recommendations.md ("These six tools").
HIGH_RISK = {"execute_code", "node_call_method", "save_write", "save_delete", "save_read", "save_list"}
# Meta tools are registered outside the generated catalogue (tool-reference.md says so).
META = ("discover_tools", "extensions_refresh")


def allowed_names(route_dir):
    """allow_names from the reviewed policy (Setup-RigAccount.ps1 installs it as C:\\ProgramData\\watoom\\godot-mcp-policy.json)."""
    policy = json.loads((route_dir / "sources" / "godot-mcp-policy.reviewed.json").read_text(encoding="utf-8"))
    if policy.get("allow_prefixes"):
        raise SystemExit("prefix rules are not modelled by the cards; use explicit allow_names")
    return [n for n in policy["allow_names"] if n not in policy.get("deny_names", [])]


def tool_entries(ref_text, allowed):
    entries, seen = [], set()
    for m in BLOCK.finditer(ref_text):
        name, heading, desc, tier_raw, group, flags = m.groups()
        if name != heading or name in seen:
            raise SystemExit("tool block mismatch or duplicate: %s" % name)
        seen.add(name)
        tail = ref_text[m.end(): m.end() + 1800].split("<!-- tool:")[0]
        ops = OPERATIONS.search(tail)
        params = [{"name": n, "type": t.strip(), "default": None,
                   "doc": ("required" if req == "yes" else "optional") + ((" — " + d.strip()) if d.strip() else "")}
                  for n, t, req, d in ROW.findall(tail)]
        labels = [x.strip() for x in flags.replace("·", " ").split() if x.strip() in ("read-only", "destructive", "idempotent")]
        access = "read-only" if "read-only" in labels else "destructive" if "destructive" in labels else "unlabelled"
        eager = tier_raw == "**eager**"
        sig = "%s(%s)" % (name, ", ".join(("%s%s: %s" % (p["name"], "" if p["doc"].startswith("required") else "?", p["type"])) for p in params))
        route_ok = name in allowed
        constraints = [
            "Upstream access label: %s%s." % (access, " + idempotent" if "idempotent" in labels and access != "unlabelled" else ""),
            ("Always registered (eager)." if eager else
             "On-demand: not in the initial tool list. Call discover_tools to activate group '%s' first, and only if the client handles tools/list_changed." % group),
        ]
        if access == "unlabelled":
            constraints.append("No read-only label upstream: treat as able to change the project, the editor or the running game.")
        if access == "destructive":
            constraints.append("Destructive upstream: changes or removes project/editor/game state. Many support Undo in the editor but do not rely on it.")
        if name in HIGH_RISK:
            constraints.append("One of upstream's six high-risk tools (arbitrary code, method calls or user:// storage): block unless the task needs it.")
        constraints.append(
            "WatooM route: ALLOWED (the reviewed rig policy names this tool)." if route_ok else
            "WatooM route: NOT reachable (the reviewed rig policy does not name it). If you need it, say so in your handoff for the operator; "
            "do not retry it or substitute a different tool to get around the policy.")
        entries.append({
            "symbol": name, "kind": "mcp_tool", "signature": sig, "summary": desc.replace("\n", " ")[:300],
            "params": params, "constraints": constraints,
            "aliases": ["mcp__godot__" + name, "watoom-godot_" + name],
            "meta": {"access": access, "tier": "eager" if eager else "on-demand", "group": group or "startup",
                     "operations": int(ops.group(1)) if ops else 1, "watoom_route_allowed": route_ok},
            "source_file": "tool-reference.md",
            "source_span": "### `%s`\n\n%s" % (name, desc),
        })
    return entries


def concept(symbol, signature, summary, source_file, span, constraints):
    return {"symbol": symbol, "kind": "concept", "signature": signature, "summary": summary,
            "source_file": source_file, "source_span": span, "constraints": constraints}


def workflow(symbol, signature, summary, first_tool, ref_entries, steps):
    first = next(e for e in ref_entries if e["symbol"] == first_tool)
    return {"symbol": symbol, "kind": "workflow", "signature": signature, "summary": summary,
            "source_file": "tool-reference.md", "source_span": first["source_span"],
            "constraints": steps + ["Composed from the documented tool descriptions; not run end-to-end on the WatooM rig. "
                                    "Check each step's 'WatooM route' line on its own card before relying on it."]}


def vendor_concepts(tools):
    return [
        concept("godot-mcp-on-demand-tools", "discover_tools({group}) -> activates an on-demand tool group",
                "Only the 34 eager tools plus two meta tools are in the first tool list; the rest are on-demand and appear after discover_tools, if the client handles tools/list_changed.",
                "tool-reference.md", "Registered up front — always in the initial `tools/list`.",
                ["A tool missing from the list may simply be on-demand: check its card's tier before concluding it does not exist.",
                 "Tools activated mid-session appear only if the MCP client handles the tools/list_changed notification."]),
        concept("godot-mcp-pagination", "has_more / total_* / returned / next_* / hint",
                "Capped reads (script_read in lines, save_read in bytes) page with one contract: loop while has_more is true, passing next_start_line / next_offset back.",
                "advanced-configuration.md", "**The loop is always the same:** call the tool; if `has_more` is `true`, pass the",
                ["script_read takes start_line/end_line (1-based); resume with next_start_line.",
                 "A response with has_more=false is complete; never assume a single call returned a whole large file."]),
        concept("godot-mcp-read-only-mode", "GODOT_MCP_READ_ONLY=1",
                "Built-in mode that hides tools carrying destructiveHint; the tool list is fixed at connect time. It does not hide read-only tools such as save_read and save_list.",
                "security-recommendations.md", "`GODOT_MCP_READ_ONLY=1` is the simplest option.",
                ["Separate from the WatooM rig policy, which is an explicit allow-list enforced before the bridge.",
                 "Upstream's two pages word the scope slightly differently (every mutating tool vs destructiveHint tools): do not assume a non-destructive writer is hidden."]),
        concept("godot-mcp-high-risk-tools", "execute_code, node_call_method, save_write, save_delete, save_read, save_list",
                "Upstream's six tools that warrant per-tool blocking: arbitrary GDScript execution, arbitrary method calls and user:// storage access.",
                "security-recommendations.md", "These six tools warrant consideration for per-tool blocking depending on",
                ["In the editor execute_code bypasses the file guard and can reach the update installer and the .mcp.json server pin."]),
        concept("godot-mcp-filesystem-sandbox", "res:// only; PATH_DENIED; FOLDER_PROTECTED",
                "File tools are limited to res://: traversal (..), absolute OS paths and the toolkit's own folders are refused, and delete tools refuse dot-folders, project.godot and override.cfg.",
                "readme.md", "**Filesystem sandbox.** All file operations are restricted to `res://` by default.",
                ["Use project-relative res:// paths in every call.", "A PATH_DENIED answer is the guard working: do not try other spellings of the path."]),
        concept("godot-mcp-runtime-channel", "game_start({wait_for_runtime:true}) -> runtime_* tools",
                "Playtest tools talk to a second WebSocket server inside the running game; it exists only while a debug-build playtest runs, so runtime tools need game_start first and fail otherwise.",
                "readme.md", "During playtests, the plugin injects an autoload that opens a second WebSocket server",
                ["Start the game, wait for the runtime, inspect, then game_stop; do not leave a playtest running.",
                 "Runtime tools exist only in debug builds; exported games carry none of the addon code."]),
        concept("godot-mcp-ports", "editor 6550-6560, runtime 6570-6585, LSP 6005",
                "Editor channel scans 6550-6560 and the runtime channel 6570-6585 by default; both bind 127.0.0.1 only. The GDScript language server defaults to 6005.",
                "advanced-configuration.md", "| `GODOT_MCP_EDITOR_PORT_MIN` / `_MAX` | Editor channel | **Relocate** the scan band (inclusive) | `6550` / `6560` |",
                ["On the WatooM route the bridge runs on the rig over SSH; these ports never leave the rig's loopback."]),
        concept("godot-mcp-headless-mode", "godot --headless --editor",
                "Most file, scene, node, script, ClassDB and project tools work headless; screenshots and anything needing a running game degrade with clear errors.",
                "readme.md", "Most tools work under `godot --headless --editor`",
                ["Do not expect a screenshot from a headless editor."]),
        workflow("godot-mcp-workflow-inspect-before-edit", "scene_get_tree -> scene_query -> node_get_property_list",
                 "Read the open scene's structure and the properties of the nodes you will touch before proposing any change.",
                 "scene_get_tree", tools,
                 ["1) scene_get_tree for the node hierarchy; 2) scene_query to find nodes by class/group/name; 3) node_get_property_list for property names and types.",
                  "Quote what you read in your handoff so the next agent need not re-inspect."]),
        workflow("godot-mcp-workflow-check-a-script", "script_read -> script_check",
                 "Read a script (paged) and validate GDScript offline before concluding it is correct.",
                 "script_read", tools,
                 ["1) script_read, looping while has_more is true; 2) script_check for offline validation; 3) editor_get_console / debugger_get_log for runtime errors."]),
        workflow("godot-mcp-workflow-visual-evidence", "game_start -> runtime_screenshot -> game_stop",
                 "A visual claim needs a real rendered image: start a playtest, capture the running game window, stop the playtest.",
                 "runtime_screenshot", tools,
                 ["The repo rule is no visual PASS without an actual rendered image; describe what the screenshot shows, not what the code should do.",
                  "game_start and game_stop change editor state: only use them where the route allows."]),
    ]


def route_entries(allowed):
    return [
        {"symbol": "watoom-godot-allowed-tools", "kind": "config",
         "signature": "allow_names = [%d tool names]; deny_names = []" % len(allowed),
         "summary": "The reviewed rig policy names every tool in the toolkit's reference (%d, including discover_tools and extensions_refresh); the wrapper refuses any other name before it reaches the editor." % len(allowed),
         "source_file": "godot-mcp-policy.reviewed.json",
         "source_span": '"allow_prefixes": [],',
         "constraints": ["Opened to all tools by the owner on 2026-11-13; before that only script_read, project_get_settings, editor_get_console, debugger_get_log and signal_list were allowed.",
                         "The live copy is C:\\ProgramData\\watoom\\godot-mcp-policy.json on the rig and is re-read on every request; to close one tool the operator adds its name to deny_names (deny wins).",
                         "A tool added by a later toolkit update is NOT allowed until its name is added to the policy.",
                         "With everything open, apply the access labels in the godot-mcp-toolkit cards: prefer read-only tools, keep destructive and unlabelled ones to what the task needs, and run execute_code or node_call_method only when no dedicated tool does the job."]},
        {"symbol": "watoom-godot-route-ask-for-tool", "kind": "concept", "signature": "tool not in allow_names -> hand off, do not work around",
         "summary": "If a Godot MCP tool is refused by the policy, the model reports the tool name and why in its handoff; it must not retry in a loop, try other names, or use another route to reach the editor.",
         "source_file": "rig-godot-mcp-README.md",
         "source_span": "To open a specific tool, edit `%ProgramData%\\watoom\\godot-mcp-policy.json` on the rig",
         "constraints": ["Opening or closing a tool is an operator decision on the rig; execute_code-style tools carry the highest risk."]},
        {"symbol": "watoom-godot-route-names-not-prefixes", "kind": "concept", "signature": "tool names put the verb mid-name",
         "summary": "The bridge's tool names put the verb mid-name (scene_get_tree, script_read), so verb-prefix allow rules match nothing; the policy is an explicit name list.",
         "source_file": "rig-godot-mcp-README.md",
         "source_span": "The bridge's tool\n  names put the verb mid-name (`scene_get_tree`, `script_read`, `project_get_settings`)",
         "constraints": ["Re-check names after toolkit updates: the registered tool set can change (36 -> 35 was observed)."]},
        {"symbol": "watoom-godot-route-script-read-paths", "kind": "concept", "signature": "script_read(file_path: res://...)",
         "summary": "script_read accepts only project-relative res:// paths; absolute OS paths and .. are rejected by the toolkit.",
         "source_file": "rig-godot-mcp-README.md",
         "source_span": "`script_read` only accepts project-relative `res://` paths",
         "constraints": ["Use res:// paths copied from scene_get_tree/scene output, or from the project layout."]},
    ]


def write(path, entries):
    path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
    print("%s: %d entries" % (path, len(entries)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manuals-root", required=True, type=pathlib.Path)
    root = ap.parse_args().manuals_root
    route_dir, tk_dir = root / "watoom-godot-route", root / "godot-mcp-toolkit"
    allowed = allowed_names(route_dir)
    ref = (tk_dir / "sources" / "tool-reference.md").read_text(encoding="utf-8")
    tools = tool_entries(ref, allowed)
    if len(tools) < 100:
        raise SystemExit("expected ~113 tools, parsed %d" % len(tools))
    write(tk_dir / "entries.jsonl", tools + vendor_concepts(tools))
    write(route_dir / "entries.jsonl", route_entries(allowed))


if __name__ == "__main__":
    main()
