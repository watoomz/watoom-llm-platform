"""Explicit-opt-in Kubernetes actuator adapter; NEVER auto-start or acquire credentials.
Preconditions: only controller may patch deployments, legacy router writer fenced,
quiescence externally established. Unsafe to serve before production cutover.
"""
from pathlib import Path
from kubernetes_api import DeploymentAPI
from kubernetes_actuator import KubernetesActuator, IntentJournal

class LiveAdapterError(RuntimeError):
    pass

class LiveActuator(KubernetesActuator):
    def __init__(self, *, base_url, namespace, token, ca_file, primary, mesh,
                 journal_root, generation, legacy_fenced=False, quiesced=False):
        if legacy_fenced is not True or quiesced is not True:
            raise LiveAdapterError('legacy writer fencing AND in-flight quiescence are mandatory')
        if not isinstance(generation,int) or generation < 1:
            raise LiveAdapterError('valid generation required')
        if primary == mesh:
            raise LiveAdapterError('deployment identities overlap')
        api = DeploymentAPI(base_url=base_url, namespace=namespace,
                            token=token, ca_file=ca_file,
                            allowed=(primary,mesh))
        super().__init__(api, IntentJournal(Path(journal_root)),
                         allowed=(primary,mesh),owner_generation=generation)
        self.primary=primary
        self.mesh=mesh
