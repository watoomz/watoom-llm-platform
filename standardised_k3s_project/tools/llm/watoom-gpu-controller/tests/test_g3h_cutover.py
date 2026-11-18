"""Deterministic storage CAS/admission model; timing alone is never the fence."""
import unittest


class Store:
    def __init__(self):
        self.version=1
        self.replicas=0
        self.legacy_allowed=True

    def prepare_legacy(self):
        if not self.legacy_allowed:
            raise PermissionError('admission denied')
        return self.version

    def commit_legacy(self, expected):
        if expected!=self.version:
            # Kubernetes GuaranteedUpdate reevaluates updateValidation on retry.
            return self.commit_legacy(self.prepare_legacy())
        self.version+=1
        self.replicas=1

    def barrier(self):
        self.version+=1


class CutoverTests(unittest.TestCase):
    def test_legacy_admitted_before_policy_finishes_before_barrier(self):
        storage=Store();pending=storage.prepare_legacy()
        storage.legacy_allowed=False
        storage.commit_legacy(pending)
        storage.barrier()
        # Snapshot after barrier reveals the old write; cutover must fail health.
        self.assertEqual(storage.replicas,1)

    def test_late_admitted_write_after_barrier_cannot_retry(self):
        storage=Store();pending=storage.prepare_legacy()
        storage.legacy_allowed=False
        storage.barrier()
        with self.assertRaises(PermissionError):storage.commit_legacy(pending)
        self.assertEqual(storage.replicas,0)

    def test_rbac_only_positive_control_is_unsafe(self):
        storage=Store();pending=storage.prepare_legacy()
        # Revoking authorization does not change an already authorized retry.
        storage.barrier();storage.commit_legacy(pending)
        self.assertEqual(storage.replicas,1)

    def test_policy_without_barrier_positive_control_is_unsafe(self):
        storage=Store();pending=storage.prepare_legacy()
        storage.legacy_allowed=False;storage.commit_legacy(pending)
        self.assertEqual(storage.replicas,1)


if __name__=='__main__':unittest.main()
