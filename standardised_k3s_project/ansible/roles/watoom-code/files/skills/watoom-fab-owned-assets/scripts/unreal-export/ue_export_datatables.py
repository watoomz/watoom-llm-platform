"""Unreal-side DataTable dump (runs under UnrealEditor-Cmd -run=PythonScript, same sandbox as ue_export_assets.py).

For reading a Blueprint pack's tuning data (e.g. the Hyper Combat Framework's DT_Firearms/DT_Combat/DT_ApplyEffects)
as plain JSON, since those packs are content-source-only (owner decision on T-0063/T-0065: mine the numbers, do
not run their Blueprint code) and DataTable rows cannot be read any other way without opening the editor UI.

Reads /job/request.json: {"root": "/Game/<Folder>", "include": ["substring", ...] (optional), "exclude": [...] (optional)}.
Writes one JSON file per table under /job/exported/<relative asset path>.json (DataTableFunctionLibrary.export_data_table_to_json_string,
a list of row objects keyed by column) and /job/native-result.json with per-table row counts. Source is read-only.
"""
import json
import pathlib
import traceback

import unreal

JOB = pathlib.Path('/job')
OUT = JOB / 'exported'
r = {'status': 'FAIL', 'scope': 'Read-only JSON dump of DataTable rows; no Blueprint logic is run or exported.'}

try:
    req = json.loads((JOB / 'request.json').read_text())
    if req.get('probe'):
        names = [n for n in dir(unreal.DataTableFunctionLibrary) if not n.startswith('_')]
        r.update(status='PORTABLE_EXPORT_PASS', probe=names)
        (JOB / 'native-result.json').write_text(json.dumps(r, indent=2))
        raise SystemExit(0)
    root = req['root'].rstrip('/')
    include = req.get('include') or []
    exclude = req.get('exclude') or []
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous([root], True)
    rows = [{'path': str(x.package_name), 'class': str(x.asset_class_path.asset_name)} for x in registry.get_assets_by_path(root, True)]
    rows = [x for x in rows if x['class'] == 'DataTable' and not any(e in x['path'] for e in exclude) and (not include or any(i.lower() in x['path'].lower() for i in include))]
    if not rows:
        raise ValueError('No DataTable assets under ' + root)
    exported = []
    failed = []
    for row in sorted(rows, key=lambda x: x['path']):
        try:
            table = unreal.load_asset(row['path'])
            if table is None:
                raise ValueError('load failed')
            text = unreal.DataTableFunctionLibrary.export_data_table_to_json_string(table)
            if not text:
                raise ValueError('export_data_table_to_json_string returned nothing')
            data = json.loads(text)
            target = (OUT / pathlib.PurePosixPath(row['path']).relative_to(root)).with_suffix('.json')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(data, indent=1))
            exported.append({**row, 'file': str(target.relative_to(JOB)), 'rows': len(data) if isinstance(data, list) else None})
        except Exception as exc:
            failed.append({**row, 'error': str(exc)[:300]})
    r.update(status='PORTABLE_EXPORT_PASS' if exported and not failed else 'PARTIAL_EXPORT' if exported else 'FAIL',
              engine=unreal.SystemLibrary.get_engine_version(), root=root, exported=exported, failed=failed)
except Exception:
    r['error'] = traceback.format_exc()
(JOB / 'native-result.json').write_text(json.dumps(r, indent=2))
if r['status'] == 'FAIL':
    raise RuntimeError(r.get('error', 'export failed'))
