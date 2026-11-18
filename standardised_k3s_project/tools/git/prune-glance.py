#!/usr/bin/env python3
"""Trim the Glance dashboard source to the AI platform for the public export.

Removes pages and tiles that name services outside the AI platform scope (media, games, DNS/VPN,
password manager, tunnels) from config/glance/glance.yml, and the helper routes that only served them from
config/glance/helper.py. Run on an export tree; the ConfigMap manifest is regenerated afterwards by
scripts/render-glance-configmaps.py. Usage: prune-glance.py <standardised_k3s_project dir>
"""
import ast
import re
import sys
from pathlib import Path

import yaml

OUT_OF_SCOPE = re.compile(
    r'\b(arma|armareforger|dayz|cs2|valheim|enshrouded|minecraft|vaultwarden|pi-?hole|wireguard|wg-easy|jellyfin|'
    r'sonarr|radarr|prowlarr|bazarr|qbittorrent|azuracast|dispatcharr|flaresolverr|cloudflare|plex|immich|'
    r'audiobookshelf|lidarr|sabnzbd|seerr|overseerr|steam|steamdb|epic|psytrance|padkontrol|traktor)\b', re.I)
DROP_PAGES = {'Games', 'DJ', 'Media', 'Info & News'}


def text(node):
    return yaml.serialize(node)


def hits(node):
    return bool(OUT_OF_SCOPE.search(text(node)))


def span(node):
    return node.start_mark.line, node.end_mark.line


def collect_drops(root):
    """Return (start, end) line ranges (0-based, end exclusive) of YAML sequence items to delete."""
    drops = []
    pages = next(v for k, v in root.value if k.value == 'pages')
    for page in pages.value:
        name = next((v.value for k, v in page.value if k.value == 'name'), '')
        if name in DROP_PAGES:
            drops.append(span(page))
            continue
        columns = next((v for k, v in page.value if k.value == 'columns'), None)
        for column in (columns.value if columns else []):
            widgets = next((v for k, v in column.value if k.value == 'widgets'), None)
            for widget in (widgets.value if widgets else []):
                prune_widget(widget, drops)
    return drops


def prune_widget(widget, drops):
    fields = {k.value: v for k, v in widget.value}
    kind = fields.get('type').value if fields.get('type') else ''
    if kind == 'monitor' and 'sites' in fields:
        sites = fields['sites'].value
        bad = [s for s in sites if hits(s)]
        if len(bad) == len(sites):
            drops.append(span(widget))
        else:
            drops.extend(span(s) for s in bad)
    elif kind == 'bookmarks' and 'groups' in fields:
        groups = fields['groups'].value
        gone = 0
        for group in groups:
            links = next((v for k, v in group.value if k.value == 'links'), None)
            if links is None:
                continue
            bad = [l for l in links.value if hits(l)]
            if len(bad) == len(links.value):
                drops.append(span(group)); gone += 1
            else:
                drops.extend(span(l) for l in bad)
        if gone == len(groups):
            drops.append(span(widget))
    elif kind == 'split-column' and 'widgets' in fields:
        inner = fields['widgets'].value
        bad = [w for w in inner if hits(w)]
        if len(bad) == len(inner):
            drops.append(span(widget))
        else:
            for w in inner:
                prune_widget(w, drops)
    elif hits(widget):
        drops.append(span(widget))


def prune_config(path):
    raw = path.read_text()
    root = yaml.compose(raw)
    drops = collect_drops(root)
    # Drop nested ranges contained in a larger drop.
    drops = sorted(set(drops))
    merged = []
    for start, end in drops:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    lines = raw.splitlines(keepends=True)
    for start, end in reversed(merged):
        del lines[start:end]
    new = ''.join(lines)
    # Style rules for removed widgets (steam/cs2/game cards) live in the document head.
    new = re.sub(r'\.(?:cs2|steam|watoom-game)[^{}]*\{[^{}]*\}', '', new)
    data = yaml.safe_load(new)
    head = data.get('document', {}).get('head', '')
    if head.count('{') != head.count('}'):
        raise SystemExit('CSS pruning unbalanced the document head')
    left = [m for m in OUT_OF_SCOPE.findall(yaml.dump(data))]
    path.write_text(new)
    return len(merged), sorted(set(x.lower() for x in left)), [p.get('name') for p in data['pages']]


DROP_ROUTES = {'/media', '/calendar', '/media-summary', '/game-summary', '/steam-sales', '/steam-profile',
               '/steamdb-free', '/epic-free', '/astro', '/news', '/markets-dashboard', '/reddit-cards', '/padkontrol-live'}
# Exact blocks inside stats() that only describe media/download apps. The tool fails closed if the source changes.
STATS_EDITS = [
    (r'''  radarr, radarr_err = try_json(f"{RADARR}/api/v3/movie", arr_headers(env("RADARR_API_KEY")))
  sonarr, sonarr_err = try_json(f"{SONARR}/api/v3/series", arr_headers(env("SONARR_API_KEY")))
  lidarr, lidarr_err = try_json(f"{LIDARR}/api/v1/artist", arr_headers(env("LIDARR_API_KEY")))
  prowlarr, prowlarr_err = try_json(f"{PROWLARR}/api/v1/indexer", arr_headers(env("PROWLARR_API_KEY")))
  sab, sab_err = try_json(f"{SAB}/api?mode=queue&output=json&apikey={env('SABNZBD_API_KEY')}")
  jf, jf_err = try_json(f"{JELLYFIN}/System/Info/Public")
  seerr, seerr_err = try_json(f"{SEERR}/api/v1/status", {"X-Api-Key": env("SEERR_API_KEY")})
''', ''),
    (r'''  qbit, qbit_err = qbit_stats()

  qbit_down=(qbit or {}).get('dl_info_speed', 0)
  qbit_up=(qbit or {}).get('up_info_speed', 0)
  sab_queue=(sab or {}).get("queue", {})

''', ''),
]


TOPOLOGY_EDITS = [
    ('  ("media", "Media", ["jellyfin", "radarr", "sonarr", "lidarr", "prowlarr", "sabnzbd",\n                      "qbittorrent", "seerr", "dispatcharr"]),\n', ''),
    ('["glance", "platform-workers", "vaultwarden", "pihole"]', '["glance", "platform-workers"]'),
    ('("ingress", "media"), ', ''),
    ('("media", "observability"),\n            ', ''),
]


def prune_helper(path):
    src = path.read_text()
    for old_text, new_text in TOPOLOGY_EDITS:
        if src.count(old_text) != 1:
            raise SystemExit('helper.py topology changed; update TOPOLOGY_EDITS in prune-glance.py')
        src = src.replace(old_text, new_text)
    # 1. stats(): drop the media/download app summaries.
    for old, new in STATS_EDITS:
        if src.count(old) != 1:
            raise SystemExit('helper.py stats() changed; update STATS_EDITS in prune-glance.py')
        src = src.replace(old, new)
    lines = src.splitlines(keepends=True)
    out, skip = [], False
    in_apps = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('apps = ['):
            in_apps = True
            out.append(line); continue
        if in_apps:
            if stripped == ']':
                in_apps = False
                out.append(line); continue
            if not stripped.startswith('app_summary("Grafana"'):
                continue
        out.append(line)
    src = ''.join(out)
    for block in (
        '      "media": {\n        "movies": len(radarr or []),\n        "series": len(sonarr or []),\n        "artists": len(lidarr or []),\n        "indexers": len(prowlarr or []),\n      },\n',
        '      "downloads": {\n        "sab_status": sab_queue.get("status", "API error" if sab_err else "unknown"),\n        "sab_speed": sab_queue.get("speed", ""),\n        "qbit_down": fmt_bytes(qbit_down) + "/s",\n        "qbit_up": fmt_bytes(qbit_up) + "/s",\n      }\n',
    ):
        if src.count(block) != 1:
            raise SystemExit('helper.py stats() summary changed; update prune-glance.py')
        src = src.replace(block, '')
    src = src.replace('"issues": issues[:6],\n      \n    },', '"issues": issues[:6],\n    },')
    # 2. do_GET: drop the routes for removed pages.
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    cut = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) \
                and node.test.left.id == 'p' and len(node.test.comparators) == 1 \
                and isinstance(node.test.comparators[0], ast.Constant) and node.test.comparators[0].value in DROP_ROUTES:
            cut.append((node.lineno - 1, node.body[-1].end_lineno))
    for a, b in sorted(cut, reverse=True):
        del lines[a:b]
    src = ''.join(lines)
    # 3. Remove top-level functions and constants nothing references any more, until stable.
    removed = []
    while True:
        tree = ast.parse(src)
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        lines = src.splitlines(keepends=True)
        victims = []
        for n in tree.body:
            if isinstance(n, ast.FunctionDef) and n.name not in used and not n.decorator_list:
                victims.append((n.lineno - 1, n.end_lineno, n.name))
            elif isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                    and n.targets[0].id not in used and n.targets[0].id.isupper():
                victims.append((n.lineno - 1, n.end_lineno, n.targets[0].id))
        if not victims:
            break
        for a, b, name in sorted(victims, reverse=True):
            del lines[a:b]
            removed.append(name)
        src = ''.join(lines)
    compile(src, str(path), 'exec')
    path.write_text(src)
    left = sorted(set(m.lower() for m in OUT_OF_SCOPE.findall(src)))
    return removed, [], left


def main():
    project = Path(sys.argv[1])
    dropped, left, pages = prune_config(project / 'config/glance/glance.yml')
    print('glance.yml: dropped ranges', dropped, 'pages kept', pages, 'residual terms', left)
    removed, missing, residual = prune_helper(project / 'config/glance/helper.py')
    print('helper.py: removed', len(removed), 'unreferenced names; residual terms', residual)
    if left or residual:
        sys.exit('Glance pruning left out-of-scope terms or dangling references')


if __name__ == '__main__':
    main()
