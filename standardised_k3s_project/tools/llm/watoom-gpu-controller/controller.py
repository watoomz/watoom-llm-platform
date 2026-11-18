"""Offline reference for WatooM GPU controller. NO Kubernetes client / live entrypoint.

All scale operations must be mediated by this single writer; this module alone
cannot revoke legacy API permissions or fence previously admitted legacy writes.
"""
from dataclasses import dataclass
from threading import RLock
from typing import Protocol

class Conflict(RuntimeError): pass
class Unsafe(RuntimeError): pass

@dataclass(frozen=True)
class State:
    phase: str = 'qwen-ready'
    owner: str | None = None
    generation: int = 0
    uncertain: bool = False

class Store(Protocol):
    def load(self) -> State: ...
    def save(self, state: State) -> None: ...

class Actuator(Protocol):
    def scale(self, deployment: str, replicas: int, generation: int) -> None: ...
    def stopped(self, deployment: str) -> bool: ...
    def healthy(self, deployment: str) -> bool: ...
    def fence_and_reconcile(self, generation: int) -> bool: ...

class Controller:
    """Reference state machine; storage durability and auth are integration gates."""
    def __init__(self, store: Store, actuator: Actuator, primary: str, mesh: str):
        self.store, self.actuator, self.primary, self.mesh = store, actuator, primary, mesh
        self.lock = RLock()

    def begin_specialist(self, job: str):
        with self.lock:
            s = self.store.load()
            if s.phase != 'qwen-ready' or s.owner or s.uncertain:
                raise Conflict('GPU busy or outcome unknown')
            s = State('acquiring', job, s.generation + 1)
            self.store.save(s)  # durable BEFORE any scale request
            return s.generation

    def switch_to_mesh(self, job: str, generation: int):
        with self.lock:
            s = self._require(job, generation, 'acquiring')
            self.store.save(State('stopping-qwen', job, generation))
            try:
                self.actuator.scale(self.primary, 0, generation)
                if not self.actuator.stopped(self.primary):
                    raise Unsafe('Qwen still active')
                self.store.save(State('starting-mesh', job, generation))
                self.actuator.scale(self.mesh, 1, generation)
                if not self.actuator.healthy(self.mesh):
                    raise Unsafe('Mesh not healthy')
                self.store.save(State('mesh-active', job, generation))
            except BaseException:
                self.store.save(State('recovery-required', job, generation, True))
                raise

    def begin_restore(self, job: str, generation: int):
        with self.lock:
            s = self._require(job, generation, 'mesh-active')
            self.store.save(State('restoring', job, generation))
            self._restore(job, generation)

    def recover(self, job: str, generation: int, owner_confirmed_ended: bool):
        with self.lock:
            s = self.store.load()
            if s.owner != job or s.generation != generation:
                raise Conflict('stale recovery token')
            if not owner_confirmed_ended:
                raise Unsafe('live ownership cannot be seized')
            if s.phase not in ('recovery-required','restoring','stopping-qwen','starting-mesh','acquiring'):
                raise Conflict('recovery not permitted from phase ' + s.phase)
            self.store.save(State('recovery-required', job, generation, True))
            self._restore(job, generation)

    def _restore(self, job: str, generation: int):
        # Critical: an unacknowledged/late write must be fenced and reconciled
        # before restoration starts. Reconciliation must itself be API-enforced.
        if not self.actuator.fence_and_reconcile(generation):
            self.store.save(State('recovery-required', job, generation, True))
            raise Unsafe('outstanding write could arrive after restoration')
        try:
            self.actuator.scale(self.mesh, 0, generation)
            if not self.actuator.stopped(self.mesh):
                raise Unsafe('Mesh still active')
            self.actuator.scale(self.primary, 1, generation)
            if not self.actuator.healthy(self.primary):
                raise Unsafe('Qwen inference health check failed')
        except BaseException:
            self.store.save(State('recovery-required', job, generation, True))
            raise
        self.store.save(State('qwen-ready', None, generation))

    def request_qwen(self):
        with self.lock:
            s = self.store.load()
            if s.phase != 'qwen-ready' or s.owner or s.uncertain:
                raise Conflict('specialist owns GPU')
            return True

    def _require(self, job, generation, phase):
        s = self.store.load()
        if (s.owner, s.generation, s.phase, s.uncertain) != (job, generation, phase, False):
            raise Conflict('invalid or stale ownership transition')
        return s
