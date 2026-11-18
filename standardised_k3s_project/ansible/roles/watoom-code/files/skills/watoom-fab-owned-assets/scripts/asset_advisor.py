#!/usr/bin/env python3
"""Offline asset classification and pipeline advice (Python stdlib only).

Examples:
  python3 tools/fab/asset_advisor.py build --facts /path/to/facts.json
  python3 tools/fab/asset_advisor.py advise "German Shepherd" --json
  python3 tools/fab/asset_advisor.py classify --category terrain

Facts JSON is an object keyed by asset id (or source:id to disambiguate).
Supported facts: category/listing_category, tags, formats, has_skeletal_mesh,
has_static_mesh, has_mesh, rigged, animated, anim_count, unrigged, static.
Only explicit facts establish rig/animation state; title matches are hypotheses.
This module never downloads assets, launches engines or writes source catalogues.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys


CATALOG = Path('/data/ai/assets/catalog')
OUTPUT = CATALOG  # default destination of `build`; the operator runs it (the catalogue is root-owned)
PIPELINES = Path(__file__).with_name('asset_pipelines.json')
APPROVAL = ('Any additional Fab download requires explicit per-asset owner approval '
            'through watoom-fab-owned-assets. Ownership, project approval and this '
            'advice are not download approval; reconcile existing sources/receipts first.')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_taxonomy(path=PIPELINES):
    return read_json(path)


def string_list(value):
    """Accept a single listing label or a list of labels, never stringify objects."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return value
    raise ValueError('formats/tags must be a string or a list of strings')


def keyword_category(text, taxonomy):
    for entry in taxonomy['categories']:
        if entry.get('pattern'):
            match = re.search(entry['pattern'], text, re.IGNORECASE)
            if match:
                return entry['id'], match.group(0)
    return 'uncategorised', None


def classify(item, facts=None, taxonomy=None, catalogue=None):
    """Return an enriched copy; never mutate catalogue records or assume rigging."""
    taxonomy = taxonomy or load_taxonomy()
    facts = facts or {}
    if not isinstance(facts, dict):
        raise ValueError('facts for each asset must be an object')
    result = dict(item)
    result['id'] = str(item['id'])
    result['catalogue'] = catalogue or ('animpic' if item.get('source') == 'animpic' else 'fab')
    result['source'] = item.get('source', result['catalogue'])
    result['formats'] = string_list(facts.get('formats', item.get('formats', [])))
    result['facts'] = facts
    evidence = []
    category = None
    confidence = 0.0
    ids = {x['id'] for x in taxonomy['categories']}
    # Explicit listing metadata outranks the title, including a valid unknown label.
    label = facts.get('category', facts.get('listing_category'))
    if label is not None:
        labels = string_list(label)
        category = next((x for x in labels if x in ids), None)
        if category is None:
            category, _ = keyword_category(' '.join(labels), taxonomy)
        evidence.append('facts listing category: ' + ', '.join(labels))
        confidence = 1.0 if category != 'uncategorised' else 0.0
    if category in (None, 'uncategorised') and facts.get('tags'):
        tags = string_list(facts['tags'])
        tagged, term = keyword_category(' '.join(tags), taxonomy)
        if term:
            category, confidence = tagged, 0.95
            evidence.append('facts tags matched: ' + term)
    if category is None:
        kind = item.get('type', '')
        types = {'CODE_PLUGIN': 'code_plugins', 'METAHUMAN': 'metahuman'}
        if kind in types:
            category, confidence = types[kind], 1.0
            evidence.append('catalogue type: ' + kind)
        else:
            category, term = keyword_category(item.get('title', ''), taxonomy)
            confidence = 0.65 if term else 0.0
            evidence.append('title keyword: ' + term if term else 'no recognised content keyword')
            if category == 'uncategorised' and kind == 'COMPLETE_PROJECT':
                category, confidence = 'complete_projects', 1.0
                evidence.append('catalogue type: ' + kind)
    if (label is None and facts.get('anim_count', 0) > 0 and
            facts.get('has_mesh') is False):
        category, confidence = 'animations', 0.98
        evidence.append('facts anim_count>0 and has_mesh=false override title')
    # A scan can resolve unknown titles, but cannot identify animal vs humanoid.
    if category == 'uncategorised':
        if facts.get('has_skeletal_mesh') is True:
            category, confidence = 'characters', 0.95
            evidence.append('facts has_skeletal_mesh=true (subtype unknown)')
        elif facts.get('anim_count', 0) > 0 and facts.get('has_mesh') is False:
            category, confidence = 'animations', 0.98
            evidence.append('facts anim_count>0 and has_mesh=false')
        elif facts.get('has_static_mesh') is True:
            category, confidence = 'environment', 0.9
            evidence.append('facts has_static_mesh=true (content subtype unknown)')
    for key in ('has_skeletal_mesh', 'has_static_mesh', 'has_mesh', 'rigged',
                'animated', 'anim_count', 'unrigged', 'static'):
        if key in facts:
            evidence.append('facts ' + key + '=' + json.dumps(facts[key]))
    if 'formats' in facts or item.get('formats'):
        evidence.append(('facts' if 'formats' in facts else 'catalogue') +
                        ' formats: ' + ', '.join(result['formats']))
    # Preserve unknown separately from explicit false; no title-derived rig facts.
    result['rigged'] = facts.get('rigged', facts.get('has_skeletal_mesh'))
    result['animated'] = facts.get('animated',
                                   facts['anim_count'] > 0 if 'anim_count' in facts else None)
    result.update(category=category, confidence=confidence, evidence=evidence)
    result['pipeline_ids'] = select_pipelines(result, taxonomy)
    result['requires_owner_approval'] = result['catalogue'] == 'fab'
    result['approval_reminder'] = APPROVAL if result['catalogue'] == 'fab' else None
    return result


def select_pipelines(asset, taxonomy):
    """Conditional routing keeps titles, known source facts and execution gaps distinct."""
    category = asset['category']
    formats = ' '.join(asset['formats']).casefold()
    facts = asset['facts']
    blockers = {'CODE_PLUGIN': 'no-godot-plugin', 'COMPLETE_PROJECT': 'no-godot-project',
                'METAHUMAN': 'metahuman-pipeline'}
    if asset.get('type') in blockers:
        return [blockers[asset['type']]]
    if re.search(r'\bgodot\b', formats):
        return ['native-godot']
    if category in ('characters', 'animals', 'creatures'):
        unrigged = (facts.get('unrigged') is True or facts.get('static') is True or
                    asset['rigged'] is False)
        # Explicit "static models"/"unrigged" in a title is a cautious route hint.
        title_static = re.search(r'\bunrigged\b|\bstatic (?:models?|meshes?|characters?|animals?|birds?)\b',
                                 asset.get('title', ''), re.IGNORECASE)
        if unrigged or (title_static and asset['rigged'] is not True):
            return ['rigify-static-character']
        if re.search(r'\b(?:glb|gltf|fbx|blender)\b', formats):
            return ['portable-character']
        if asset['source'] == 'ue-library' or re.search(r'\bunreal\b', formats):
            return ['unreal-skeletal-to-godot']
        return ['inspect-unknown']
    if category == 'environment' and re.search(r'\b(?:glb|gltf|fbx|blender)\b', formats):
        return ['portable-static']
    return [p['id'] for p in taxonomy['pipelines'] if category in p['applies_to']]


def load_assets(catalog_dir=CATALOG, facts=None, taxonomy=None):
    taxonomy = taxonomy or load_taxonomy()
    facts = facts or {}
    if not isinstance(facts, dict):
        raise ValueError('facts JSON must be an object keyed by asset id')
    assets, inventories = [], {}
    for name in ('fab', 'animpic'):
        document = read_json(Path(catalog_dir) / (name + '-owned.json'))
        inventories[name] = {'refreshed_at': document.get('refreshed_at'),
                             'count': len(document['assets'])}
        for item in document['assets']:
            asset_id = str(item['id'])
            override = facts.get(name + ':' + asset_id,
                                 facts.get(item.get('source', name) + ':' + asset_id,
                                           facts.get(asset_id, {})))
            assets.append(classify(item, override, taxonomy, name))
    return assets, inventories


def advise(query, assets, taxonomy=None, category=None, limit=5):
    taxonomy = taxonomy or load_taxonomy()
    definitions = {p['id']: p for p in taxonomy['pipelines']}
    query = query.casefold().strip()
    tokens = re.findall(r'\w+', query)
    matches = []
    for asset in assets:
        if category and asset['category'] != category:
            continue
        title = asset.get('title', '').casefold()
        exact = query in (asset['id'].casefold(),
                          (asset['source'] + ':' + asset['id']).casefold(),
                          (asset['catalogue'] + ':' + asset['id']).casefold())
        score = 10000 if exact else (100 if query and query in title else 0)
        score += sum(1 for t in tokens if t in title)
        if not query or (not exact and not score):
            continue
        row = dict(asset)
        # Approval applies to this acquisition source, not every future pipeline use.
        row['pipelines'] = [dict(definitions[p],
                                 requires_owner_approval=asset['requires_owner_approval'])
                            for p in asset['pipeline_ids']]
        matches.append((score, row))
    matches.sort(key=lambda pair: (-pair[0], pair[1].get('title', '').casefold(),
                                    pair[1]['source'], pair[1]['id']))
    return {'schema': 1, 'query': query, 'category_filter': category,
            'total_matches': len(matches), 'matches': [a for _, a in matches[:limit]],
            'notice': 'Offline advice; candidates are not qualified integrations until validated. '
                      'A QUALIFIED pipeline has only the scope described in qualification_scope.'}


def build(assets, inventories, taxonomy=None, output_dir=OUTPUT):
    taxonomy = taxonomy or load_taxonomy()
    output_dir = Path(output_dir)
    counts = Counter(a['category'] for a in assets)
    document = {'schema': 1, 'basis': taxonomy['basis'], 'inventories': inventories,
                'category_counts': dict(sorted(counts.items())),
                'categories': taxonomy['categories'], 'pipelines': taxonomy['pipelines'],
                'assets': assets}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'asset-index.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    lines = ['# Owned asset index', '', taxonomy['basis'], '', APPROVAL, '',
             'Candidates require exact-source import/runtime and visual validation. '
             'QUALIFIED describes a scoped recipe, not an accepted asset.', '',
             'For full steps/tools/pitfalls run `python3 tools/fab/asset_advisor.py '
             'advise "<asset id>"` from the maintained checkout, or resolve the '
             'pipeline IDs below in `asset-index.json`.', '']
    for category in taxonomy['categories']:
        rows = [a for a in assets if a['category'] == category['id']]
        if not rows:
            continue
        lines += ['## ' + category['label'] + ' (' + str(len(rows)) + ')', '']
        for asset in sorted(rows, key=lambda a: (a.get('title', '').casefold(), a['id'])):
            title = asset.get('title', '').replace('\n', ' ').replace('\r', ' ')
            lines.append('- ' + title + ' — `' + asset['catalogue'] + ':' + asset['id'] +
                         '`; ' + asset['source'] + '; formats: ' +
                         (', '.join(asset['formats']) or 'unknown') + '; ' +
                         ', '.join(asset['pipeline_ids']) + '; confidence ' + str(asset['confidence']))
        lines.append('')
    (output_dir / 'asset-index.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    categories = [c['id'] for c in load_taxonomy()['categories']]
    for command in ('classify', 'build', 'advise'):
        child = sub.add_parser(command)
        child.add_argument('--catalog-dir', type=Path, default=CATALOG)
        child.add_argument('--facts', type=Path, help='JSON object keyed by asset id or source:id')
        if command == 'build':
            child.add_argument('--output-dir', type=Path, default=OUTPUT)
        else:
            child.add_argument('--category', choices=categories)
        if command == 'advise':
            child.add_argument('query')
            child.add_argument('--json', action='store_true')
            child.add_argument('--limit', type=int, default=5)
    args = parser.parse_args(argv)
    try:
        taxonomy = load_taxonomy()
        # Operator-collected listing facts (tools/fab/fab_listing_facts.ts) sit beside the catalogues and apply
        # automatically; an explicit --facts file takes precedence.
        facts_path = args.facts or (args.catalog_dir / 'fab-listing-facts.json'
                                    if (args.catalog_dir / 'fab-listing-facts.json').is_file() else None)
        assets, inventories = load_assets(args.catalog_dir,
                                          read_json(facts_path) if facts_path else None, taxonomy)
        if args.command == 'build':
            doc = build(assets, inventories, taxonomy, args.output_dir)
            print(json.dumps({'output': str(args.output_dir), 'counts': doc['category_counts'],
                              'total': len(assets)}, indent=2))
        elif args.command == 'classify':
            print(json.dumps([a for a in assets if not args.category or a['category'] == args.category], indent=2))
        else:
            if args.limit < 1:
                raise ValueError('--limit must be positive')
            result = advise(args.query, assets, taxonomy, args.category, args.limit)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(result['notice'])
                if not result['matches']:
                    print('No matching assets.')
                for asset in result['matches']:
                    print('\n' + asset['title'] + ' [' + asset['source'] + ':' + asset['id'] + ']')
                    print('Category: ' + asset['category'] + '; confidence: ' + str(asset['confidence']) +
                          '; source: ' + asset['source'] + '; formats: ' +
                          (', '.join(asset['formats']) or 'unknown'))
                    print('Evidence: ' + '; '.join(asset['evidence']))
                    for pipeline in asset['pipelines']:
                        print('Pipeline: ' + pipeline['id'] + ' (' + pipeline['status'] + ')')
                        print('Scope: ' + pipeline['qualification_scope'])
                        for n, step in enumerate(pipeline['steps'], 1):
                            print('  ' + str(n) + '. ' + step)
                        print('Tools: ' + ', '.join(pipeline['tools']))
                        for pitfall in pipeline['pitfalls']:
                            print('Pitfall: ' + pitfall)
                    if asset['approval_reminder']:
                        print(asset['approval_reminder'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, 'asset_advisor: ' + str(error) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
