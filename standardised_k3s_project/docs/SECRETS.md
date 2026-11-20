# Secrets Workflow

Do not commit live secret values.

Ignored local inputs:

- `secrets/.env.local`
- generated secret manifests under `manifests/05-secrets/*-generated.yml`

Encrypted Git input:

- `secrets-vault/env.local.vault`

The encrypted vault file is committed for rebuilds. The vault password is not
committed. On the current server it is stored at:

```bash
/data/secrets/homelab-host/ansible-vault-password.txt
```

Recommended permissions:

```bash
sudo chgrp -R wheel /data/secrets/homelab-host
sudo chmod 0750 /data/secrets/homelab-host
sudo chmod 0640 /data/secrets/homelab-host/ansible-vault-password.txt
```

Store that vault password in your password manager. On a fresh rebuild, restore
the password file first, then run:

```bash
scripts/restore-vault-secrets.sh
```

Then render and apply Kubernetes secrets:

```bash
scripts/render-secrets.sh
kubectl apply -f manifests/05-secrets/
scripts/check-required-secrets.sh
```

## Secret names required by source workflows

| Namespace | Secret | Purpose |
|---|---|---|
| `monitoring` | `grafana-secrets` | Grafana admin credentials |
| `glance` | `glance-secrets` | Glance private config values |

## Later Improvement

Optional generated secrets are created when their matching env vars are set, for example `MKTXP_CREDENTIALS_YML`.

Longer term, SOPS + age or External Secrets would make secret rotation and
multi-machine recovery cleaner.
