"""Crash-resistant single-host state store for offline GPU controller tests.

This implements atomic persistence, not distributed mutual exclusion. Caller must
hold the controller's external GPU lock before doing any read-modify-write.
"""
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from controller import State


class DurableStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self):
        if not self.path.exists():
            return State()
        doc = json.loads(self.path.read_text(encoding='utf-8'))
        if set(doc) != {'phase','owner','generation','uncertain'}:
            raise ValueError('GPU state schema mismatch; refusing unsafe default')
        if not isinstance(doc['generation'], int) or isinstance(doc['generation'], bool) or doc['generation'] < 0:
            raise ValueError('Invalid generation')
        if not isinstance(doc['phase'], str) or not isinstance(doc['uncertain'], bool):
            raise ValueError('Invalid GPU state')
        if doc['owner'] is not None and not isinstance(doc['owner'],str):
            raise ValueError('Invalid owner')
        return State(**doc)

    def save(self, state):
        if not isinstance(state, State):
            raise TypeError('State required')
        parent = self.path.parent
        tmp_name = None
        try:
            with tempfile.NamedTemporaryFile('w', dir=parent, prefix='.gpu-state-', suffix='.tmp', encoding='utf-8', delete=False) as handle:
                tmp_name = handle.name
                os.chmod(tmp_name,0o600)
                json.dump(asdict(state), handle, sort_keys=True)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name,self.path)
            fd=os.open(parent,os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        finally:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
