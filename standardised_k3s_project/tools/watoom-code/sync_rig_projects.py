#!/usr/bin/env python3
"""Keep the rig stage's project enrollment (/etc/watoom-rig-async-stage.json) in sync with the main game
worker's project list (/etc/watoom-game-worker.json), so a project enrolled for the main Bazzite/local worker
is automatically rig-eligible too (owner policy 2026-11-09: any job may use the rig if it needs to).

Additive and one-directional only: this NEVER removes a project already enrolled on the rig (the fixture
project stays enrolled even though it is not in the main list), and it never touches the rig stage's own code,
operations list, activation_ms or application block -- only merges into the projects array. The rig's live
dispatcher reads this config fresh on every poll tick, so no restart is needed for a change here to take effect.

This script is intentionally NOT part of the rig-async-stage release bundle (tools/rig-async-stage/), which is
deployed as an immutable, hash-pinned release through its own careful install-runtime.py procedure -- this is
a separate, ordinary host script that only ever edits the (unpinned) JSON config, never the pinned runner code.
"""
import json
import os
import pathlib
import sys

MAIN_CONFIG = pathlib.Path('/etc/watoom-game-worker.json')
RIG_CONFIG = pathlib.Path('/etc/watoom-rig-async-stage.json')


def sync(main_config=MAIN_CONFIG, rig_config=RIG_CONFIG):
    if not rig_config.is_file():
        return None  # rig stage not provisioned on this host; nothing to do
    main = json.loads(main_config.read_text())
    rig = json.loads(rig_config.read_text())
    before = set(rig.get('projects', []))
    after = before | set(main.get('projects', []))
    if after == before:
        return False
    rig['projects'] = sorted(after)
    tmp = rig_config.with_suffix('.tmp')
    tmp.write_text(json.dumps(rig, indent=2) + '\n')
    os.chmod(tmp, 0o644)
    os.replace(tmp, rig_config)
    return sorted(after - before)


if __name__ == '__main__':
    added = sync()
    if added is None:
        print('rig stage not provisioned on this host; nothing to do')
    elif added is False:
        print('already in sync; no change')
    else:
        print('added to rig enrollment: ' + ', '.join(added))
    sys.exit(0)
