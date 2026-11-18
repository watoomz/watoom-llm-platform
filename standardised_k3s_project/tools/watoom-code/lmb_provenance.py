"""Read-only metadata fingerprints, raw native input provenance and receipt identity.
No engine invocation, request submission or historical receipt mutation.
"""
import argparse, datetime, hashlib, json, os, pathlib, stat, subprocess
ALGORITHM = 'metadata-manifest-sha256-json-utf8-size-mtimeNs-cache-mount-v1'
NATIVE_ALGORITHM = 'raw-sha256-path-manifest-v1'
IDENTITY_FIELDS = ('request_id', 'job', 'operation', 'source_fingerprint')

def digest(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def native_input_files(source):
    """Entire declared purchased pack, not an OS trace of files opened by Unreal."""
    source = pathlib.Path(source)
    if source.resolve() != source or source.is_symlink():
        raise ValueError('Canonical native source required')
    rows = []
    for root, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            if (pathlib.Path(root) / name).is_symlink():
                raise ValueError('Native input symlink refused')
        for name in files:
            path = pathlib.Path(root) / name
            before = path.stat()
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('Native input must be regular')
            raw = digest(path)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise ValueError('Native input changed during hashing')
            rows.append(dict(path=str(path), relative_path=path.relative_to(source).as_posix(),
                             size=before.st_size, mtime_ns=str(before.st_mtime_ns),
                             mtime_utc=datetime.datetime.fromtimestamp(before.st_mtime, datetime.timezone.utc).isoformat(),
                             file_type=path.suffix, sha256=raw, coordinator_fingerprint_included=False))
    if not rows:
        raise ValueError('Native source empty or unavailable')
    return sorted(rows, key=lambda row: row['relative_path'].encode('utf-8'))

def native_input_sha256(rows):
    """Raw content identity; sizes and timestamps are intentionally not hashed."""
    pairs = sorted([[r['relative_path'], r['sha256']] for r in rows], key=lambda row: row[0].encode('utf-8'))
    if len({row[0] for row in pairs}) != len(pairs):
        raise ValueError('Duplicate native input')
    return hashlib.sha256(json.dumps(pairs, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

def compare_native_inputs(before, after):
    old = {r['relative_path']: r['sha256'] for r in before}
    new = {r['relative_path']: r['sha256'] for r in after}
    return dict(missing=sorted(old.keys() - new.keys()), added=sorted(new.keys() - old.keys()),
                changed=sorted(k for k in old.keys() & new.keys() if old[k] != new[k]))

def receipt_report(receipt, request, current_native=None):
    """Missing historical fields are warnings; explicit mismatches always fail."""
    errors, warnings = [], []
    for key in IDENTITY_FIELDS:
        if key not in receipt:
            warnings.append('Historical receipt missing ' + key)
        elif receipt[key] != request.get(key):
            errors.append('Receipt identity mismatch: ' + key)
    if 'project' in receipt and receipt['project'] != request.get('project'):
        errors.append('Receipt identity mismatch: project')
    rows = receipt.get('native_input_files')
    if rows is None:
        warnings.append('Historical receipt has no declared native input provenance')
    else:
        try:
            if not rows or native_input_sha256(rows) != receipt.get('native_input_sha256'):
                errors.append('Native input manifest digest mismatch or empty manifest')
            if current_native is None:
                warnings.append('Current external inputs not checked')
            else:
                changes = compare_native_inputs(rows, current_native)
                if any(changes.values()):
                    errors.append('External native input missing/changed/added: ' + json.dumps(changes))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append('Malformed native provenance: ' + str(exc))
    return dict(status='FAIL' if errors else 'WARNING' if warnings else 'PASS', errors=errors, warnings=warnings)

def coordinator_manifest(project, guard):
    """Execute the real JS function; never approximate it using Python JSON."""
    code = r'''import {readFile} from 'node:fs/promises';
import {readdir,stat,lstat,realpath} from 'node:fs/promises';
import {posix} from 'node:path';import {createHash} from 'node:crypto';
const source=await readFile(process.argv[1],'utf8');
const start=source.includes('export async function gameSourceManifest(')?source.indexOf('export async function gameSourceManifest('):source.indexOf('export async function gameSourceFingerprint(');
const end=source.indexOf('export function validateGameWorkerInput(');
if(start<0 || end<start)throw Error('Unrecognized coordinator module');
let f=source.slice(start,end);
if(f.startsWith('export async function gameSourceManifest(')) {
 f=f.slice(0,f.indexOf('export async function gameSourceFingerprint('));
 f=f.replace('export async function','async function');
 eval(f+';globalThis.rows=await gameSourceManifest('+JSON.stringify(process.argv[2])+');');
} else {
 const marker='return createHash("sha256").update(JSON.stringify(rows)).digest("hex");';
 if(!f.includes(marker))throw Error('Unrecognized deployed fingerprint; audit required');
 f=f.replace('export async function','async function').replace(marker,'return rows;');
 const fn=new Function('readdir','stat','lstat','posix','createHash',f+';return gameSourceFingerprint;')(readdir,stat,lstat,posix,createHash);
 globalThis.rows=await fn(process.argv[2]);
}
console.log(JSON.stringify({fingerprint:createHash('sha256').update(JSON.stringify(rows)).digest('hex'),rows,serialized:JSON.stringify(rows)}));'''
    # Use an async function constructor for both module versions, so no eval scope ambiguity.
    code = code.replace("eval(f+';globalThis.rows=await gameSourceManifest('+JSON.stringify(process.argv[2])+');');", "const fn=new Function('readdir','stat','lstat','realpath','posix','createHash',f+';return gameSourceManifest;')(readdir,stat,lstat,realpath,posix,createHash);globalThis.rows=await fn(process.argv[2]);")
    return json.loads(subprocess.check_output(['node', '--input-type=module', '-e', code, str(guard), str(project)], text=True))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', required=True, type=pathlib.Path)
    p.add_argument('--guard', required=True, type=pathlib.Path, help='Exact repository or deployed index.js to audit')
    p.add_argument('--native-source', required=True, type=pathlib.Path)
    p.add_argument('--request', type=pathlib.Path)
    p.add_argument('--receipt', type=pathlib.Path)
    p.add_argument('--output', required=True, type=pathlib.Path)
    a = p.parse_args()
    manifest = coordinator_manifest(a.project, a.guard)
    native = native_input_files(a.native_source)
    result = dict(source_fingerprint_algorithm=ALGORITHM, coordinator=manifest,
                  native_input_algorithm=NATIVE_ALGORITHM, native_input_files=native,
                  native_input_sha256=native_input_sha256(native),
                  provenance_scope='Declared purchased source pack; engine dependencies and actual file opens are not traced')
    if a.request:
        request = json.loads(a.request.read_text())
        result['request'] = request
        result['coordinator_matches_request'] = manifest['fingerprint'] == request.get('source_fingerprint')
        if a.receipt:
            result['receipt_verification'] = receipt_report(json.loads(a.receipt.read_text()), request, native)
    elif a.receipt:
        p.error('--receipt requires --request')
    # Exclusive private report; no source or historical evidence writes.
    with open(a.output, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(dict(report=str(a.output), source_fingerprint=manifest['fingerprint'],
                          source_file_count=len(manifest['rows']) - 1,
                          receipt_verification=result.get('receipt_verification'))))
    return 1 if result.get('receipt_verification', {}).get('status') == 'FAIL' else 0

if __name__ == '__main__':
    raise SystemExit(main())
