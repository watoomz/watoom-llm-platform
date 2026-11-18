#!/usr/bin/env python3
"""Verified local procedures, never official reference data.

JSONL entries are immutable revision events. `supersedes` marks the prior
revision without rewriting history. Only the latest revision of an id is valid.
Runtime may be a tool->exact-version object or a string naming exact versions;
fingerprints use canonical JSON, without fuzzy/compatible version matching.
With runtime=None, list_valid returns latest revisions for all runtimes; callers
selecting for an environment must pass its runtime. Commands are never executed.
"""
import argparse
from collections import Counter
from datetime import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

FIELDS = set('procedure_id project runtime command_template preconditions verification source_card_ids created_at last_verified_at trust'.split())
VERSION = re.compile(r'(?<![\w.])\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?(?![\w.])')
SECRET = re.compile(
    r'(?i)(?:\b(?:password|passwd|pwd|token|api[_-]?key|secret|access[_-]?key|client[_-]?secret)\b[\s\"\x27]*[:=]|'
    r'\bbearer\s+\S+|-----BEGIN[^\n]*PRIVATE KEY-----|'
    r'\b(?:sk[-_][A-Za-z0-9_-]{8,}|(?:AKIA|ASIA)[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9_]{10,}))')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def scan(value, path=()):
    if isinstance(value, str):
        if len(value) > 2000:
            raise ValueError('field exceeds transcript limit')
        # Only the validated receipt digest is exempt from entropy detection.
        if path == ('verification', 'receipt_sha256'):
            return
        if SECRET.search(value):
            raise ValueError('possible credential in record')
        for token in re.findall(r'[A-Za-z0-9_+/=\-]{32,}', value):
            counts = Counter(token)
            entropy = -sum(n / len(token) * math.log2(n / len(token)) for n in counts.values())
            if entropy >= 4.0 or (len(token) >= 40 and re.fullmatch('[0-9a-fA-F]+', token) and entropy >= 3.5):
                raise ValueError('possible high-entropy credential')
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('object keys must be strings')
            scan(key)
            if re.fullmatch(r'(?i)(password|passwd|pwd|token|api[_-]?key|secret|access[_-]?key|client[_-]?secret)', key):
                raise ValueError('credential field')
            scan(item, path + (key,))
    elif isinstance(value, list):
        for item in value:
            scan(item, path + ('[]',))
    elif value is not None and not isinstance(value, (int, float, bool)):
        raise ValueError('record must contain JSON values')


def runtime_fingerprint(runtime):
    if isinstance(runtime, dict) and runtime:
        if not all(isinstance(k, str) and k.strip() and isinstance(v, str) and VERSION.fullmatch(v) for k, v in runtime.items()):
            raise ValueError('runtime requires tool names and exact versions')
    elif isinstance(runtime, str) and runtime.strip():
        # Each tool/version pair must be complete, not a mixed exact/range string.
        if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*\s+' + VERSION.pattern, part.strip()) for part in re.split('[,;]', runtime)):
            raise ValueError('runtime tool lacks exact version')
    else:
        raise ValueError('runtime requires exact versions')
    return digest(runtime)


def validate_record(record):
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError('procedure fields must match schema')
    canonical(record)  # also rejects NaN and non-JSON values
    scan(record)
    for value in record.values():
        if isinstance(value, (dict, list)) and len(canonical(value)) > 2000:
            raise ValueError('field exceeds transcript limit')
    for key in ('procedure_id', 'project', 'command_template', 'created_at', 'last_verified_at'):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError('invalid ' + key)
    pid = record['procedure_id']
    if pid.startswith('verified:'):
        pid = pid[len('verified:'):]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', pid) or '..' in pid:
        raise ValueError('procedure id must belong to verified namespace and be path safe')
    if record['trust'] != 'verified_local':
        raise ValueError('trust must be verified_local')
    if not isinstance(record['preconditions'], list) or not all(isinstance(x, str) for x in record['preconditions']):
        raise ValueError('invalid preconditions')
    if not isinstance(record['source_card_ids'], list) or not all(isinstance(x, str) and x.strip() for x in record['source_card_ids']):
        raise ValueError('invalid source_card_ids')
    verification = record['verification']
    if not isinstance(verification, dict) or set(verification) != {'command', 'result', 'receipt_sha256'}:
        raise ValueError('invalid verification')
    if verification['result'] != 'PASS' or not isinstance(verification['command'], str) or not verification['command'].strip():
        raise ValueError('successful verification is required')
    if not isinstance(verification['receipt_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', verification['receipt_sha256']):
        raise ValueError('invalid receipt sha256')
    dates = []
    for key in ('created_at', 'last_verified_at'):
        date = datetime.fromisoformat(record[key].replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError('timestamps must have a timezone')
        dates.append(date)
    if dates[1] < dates[0]:
        raise ValueError('verification predates creation')
    return 'verified:' + pid, runtime_fingerprint(record['runtime'])


def no_symlinks(path):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_symlink():
        raise ValueError('symlink path refused')
    return path


def read_entries(file):
    entries = []
    for line in file:
        if not line.strip():
            continue
        entry = json.loads(line)
        namespace, fingerprint = validate_record(entry['record'])
        if entry['namespace'] != namespace or entry['content_sha256'] != digest(entry['record']) or entry['runtime_fingerprint'] != fingerprint:
            raise ValueError('store integrity mismatch')
        prior = [e for e in entries if e['namespace'] == namespace]
        last = prior[-1] if prior else None
        if entry['revision'] != len(prior) + 1 or entry['supersedes'] != (last['content_sha256'] if last else None):
            raise ValueError('invalid revision chain')
        entries.append(entry)
    return entries


def add(record, receipts_dir, store_path, cards=None):
    """Validate evidence before append. Optional cards is a cards.jsonl path.

    Returns the existing/new event. `supersedes` is an append-only tombstone for
    the older content hash, not a modification of the older JSONL line.
    """
    namespace, fingerprint = validate_record(record)
    receipt_dir = no_symlinks(receipts_dir)
    receipt = no_symlinks(receipt_dir / record['verification']['receipt_sha256'])
    fd = os.open(receipt, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as file:
        sha = hashlib.sha256()
        for block in iter(lambda: file.read(65536), b''):
            sha.update(block)
    if sha.hexdigest() != record['verification']['receipt_sha256']:
        raise ValueError('receipt hash mismatch')
    if cards is not None:
        try:
            from .wlk import checked
        except ImportError:
            from wlk import checked
        source_cards, _ = checked(no_symlinks(cards).read_bytes())
        ids = {c['id'] for c in source_cards}
        if set(record['source_card_ids']) - ids:
            raise ValueError('unknown source card id')
    path = no_symlinks(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+', encoding='utf-8') as store:
        fcntl.flock(store, fcntl.LOCK_EX)
        entries = read_entries(store)
        content_hash = digest(record)
        prior = [e for e in entries if e['namespace'] == namespace]
        for entry in prior:
            if entry['content_sha256'] == content_hash:
                return entry
        store.seek(0, os.SEEK_END)
        if store.tell():
            store.seek(store.tell() - 1)
            if store.read(1) != '\n':
                raise ValueError('store has an incomplete final line')
        entry = {'namespace': namespace, 'record': json.loads(canonical(record)),
                 'content_sha256': content_hash, 'runtime_fingerprint': fingerprint,
                 'revision': len(prior) + 1,
                 'supersedes': prior[-1]['content_sha256'] if prior else None}
        store.write(canonical(entry) + '\n')
        store.flush()
        os.fsync(store.fileno())
        return entry


def list_valid(store_path, runtime=None):
    """Return latest procedure records, optionally pinned to exact runtime."""
    fingerprint = runtime_fingerprint(runtime) if runtime is not None else None
    path = no_symlinks(store_path)
    if not path.exists():
        return []
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding='utf-8') as store:
        fcntl.flock(store, fcntl.LOCK_SH)
        entries = read_entries(store)
    latest = {e['namespace']: e for e in entries}
    return [e['record'] for e in latest.values() if fingerprint is None or e['runtime_fingerprint'] == fingerprint]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    add_parser = sub.add_parser('add')
    add_parser.add_argument('record', help='JSON record file')
    add_parser.add_argument('--receipts-dir', required=True)
    add_parser.add_argument('--store', required=True)
    add_parser.add_argument('--cards')
    listing = sub.add_parser('list')
    listing.add_argument('--store', required=True)
    listing.add_argument('--runtime', help='JSON exact-runtime object or JSON string')
    args = parser.parse_args(argv)
    try:
        if args.command == 'add':
            result = add(json.loads(Path(args.record).read_text()), args.receipts_dir, args.store, args.cards)
        else:
            result = list_valid(args.store, json.loads(args.runtime) if args.runtime else None)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        # Never echo rejected content or parser messages containing secrets.
        print('procedures: validation or storage failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
