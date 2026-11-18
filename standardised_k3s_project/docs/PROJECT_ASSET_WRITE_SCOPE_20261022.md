# Project asset write scope

Observed UID1001 permission failure copying selected nature assets: worker-owned assets/m7/env directories had a read-only ACL mask. Added only assets/m7/env to the explicit maintained candidate editable trees and reconciled with project_access.py, retaining ownership, default ACLs and original purchased sources. Verified a temporary create/write/delete as UID1001. No generation or asset copy was replayed by the operator.
