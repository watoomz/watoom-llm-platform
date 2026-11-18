#!/usr/bin/env python3
import sys, yaml
from pathlib import Path
root = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
errors = 0
for p in sorted(root.rglob('*.yml')) + sorted(root.rglob('*.yaml')):
    try:
        docs = list(yaml.safe_load_all(p.read_text(errors='ignore')))
        count = sum(1 for d in docs if d)
        print(f'OK {p} docs={count}')
    except Exception as e:
        errors += 1
        print(f'ERR {p}: {e}')
print(f'errors={errors}')
sys.exit(1 if errors else 0)
