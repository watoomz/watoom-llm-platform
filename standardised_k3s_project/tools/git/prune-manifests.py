#!/usr/bin/env python3
"""Remove out-of-scope service entries from shared manifests, inventories and scripts in the public export.

Usage: prune-manifests.py <standardised_k3s_project dir>. Fails closed: every rule must match something,
so a source change that moves a block is noticed instead of silently leaving it in.
"""
import re
import sys
from pathlib import Path

import yaml

SERVICES = (r'arma-reforger|arma|dayz|cs2|valheim|enshrouded|minecraft(?:-pixel|-zom)?|vaultwarden|pihole|wireguard|jellyfin|'
            r'sonarr|radarr|prowlarr|bazarr|qbittorrent|azuracast|dispatcharr|flaresolverr|cloudflare|plex|immich|'
            r'audiobookshelf|lidarr|sabnzbd|seerr|homeassistant|kali')
SERVICE_RE = re.compile(r'\b(?:' + SERVICES + r')\b', re.I)


class Literal(str):
    pass


yaml.add_representer(Literal, lambda d, v: d.represent_scalar('tag:yaml.org,2002:str', v, style='|'), Dumper=yaml.SafeDumper)


def literalise(value):
    if isinstance(value, dict):
        return {k: literalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [literalise(v) for v in value]
    if isinstance(value, str) and '\n' in value:
        return Literal(value)
    return value


def prune_platform_workers(path):
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d]
    kept, dropped = [], 0
    for doc in docs:
        name = doc.get('metadata', {}).get('name', '')
        if re.search(r'cs2', name, re.I):
            dropped += 1
            continue
        if doc.get('kind') == 'Deployment':
            spec = doc['spec']['template']['spec']
            spec['containers'] = [c for c in spec['containers'] if not re.search(r'cs2', c['name'], re.I)]
            spec['volumes'] = [v for v in spec.get('volumes', []) if not re.search(r'cs2', yaml.dump(v), re.I)]
            for c in spec['containers']:
                c['volumeMounts'] = [m for m in c.get('volumeMounts', []) if not re.search(r'cs2', yaml.dump(m), re.I)]
                if not c['volumeMounts']:
                    c.pop('volumeMounts')
        kept.append(doc)
    if not dropped:
        raise SystemExit('platform-workers.yml: no cs2 documents found; update prune-manifests.py')
    text = '---\n'.join(yaml.safe_dump(literalise(d), sort_keys=False, width=1000) for d in kept)
    if SERVICE_RE.search(text):
        raise SystemExit('platform-workers.yml still names out-of-scope services: ' + ', '.join(sorted(set(m.lower() for m in SERVICE_RE.findall(text)))))
    path.write_text('---\n' + text)
    return dropped


def drop_list_items(path, pattern):
    """Delete YAML list items (dash line plus its indented continuation) whose text matches pattern."""
    lines = path.read_text().splitlines(keepends=True)
    regex = re.compile(pattern, re.I)
    out, i, dropped = [], 0, 0
    while i < len(lines):
        m = re.match(r'^(\s*)- ', lines[i])
        if m:
            indent = len(m[1])
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > indent):
                j += 1
            block = ''.join(lines[i:j])
            if regex.search(block):
                dropped += 1
                i = j
                continue
        out.append(lines[i])
        i += 1
    if not dropped:
        raise SystemExit(str(path) + ': no list items matched ' + pattern)
    path.write_text(''.join(out))
    return dropped


def drop_service_lines(path):
    """group_vars lists host paths (- /app/<svc>/...) and per-service keys; drop those of out-of-scope services."""
    lines = path.read_text().splitlines(keepends=True)
    path_item = re.compile(r'^\s*- /app/(?:' + SERVICES + r')(?:/\S*)?\s*$', re.I)
    key = re.compile(r'^(\s*)(?:' + SERVICES + r'|[\w-]*(?:' + SERVICES + r')[\w-]*):\s*$', re.I)
    out, i, dropped = [], 0, 0
    while i < len(lines):
        if path_item.match(lines[i]):
            dropped += 1; i += 1; continue
        m = key.match(lines[i])
        if m:
            indent = len(m[1]); j = i + 1
            while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > indent):
                j += 1
            dropped += 1; i = j; continue
        out.append(lines[i]); i += 1
    path.write_text(''.join(out))
    return dropped


def drop_path_tokens(path):
    """create-hostpaths.sh lists host directories; remove the ones that belong to out-of-scope services."""
    token = re.compile(r'(?<=\s)/app/(?:' + SERVICES + r')(?:/\S*)?', re.I)
    lines = path.read_text().splitlines(keepends=True)
    out, changed = [], 0
    for line in lines:
        new = token.sub('', line)
        if new != line:
            changed += 1
            if not new.strip():
                continue
        out.append(new if new.strip() else line)
    if not changed:
        raise SystemExit(str(path) + ': nothing to prune')
    path.write_text(''.join(out))
    return changed


def main():
    project = Path(sys.argv[1])
    print('platform-workers: dropped', prune_platform_workers(project / 'manifests/10-infrastructure/platform-workers/platform-workers.yml'), 'cs2 documents')
    ns = r'(?:namespace:\s*|name:\s*)[\w-]*(?:' + SERVICES + r')[\w-]*'
    for rel in ('ansible/inventories/homelab/group_vars/all.yml', 'ansible/roles/validation/defaults/main.yml'):
        print(rel, 'dropped', drop_list_items(project / rel, ns), 'items')
    print('group_vars service lines dropped', drop_service_lines(project / 'ansible/inventories/homelab/group_vars/all.yml'))
    print('create-hostpaths.sh lines changed', drop_path_tokens(project / 'scripts/create-hostpaths.sh'))


if __name__ == '__main__':
    main()
