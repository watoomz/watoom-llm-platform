# WatooM Configuration Rules

These rules apply under `standardised_k3s_project/config/`.

## Source configuration

- Treat this area as source input for rendered/deployed configuration where the existing project does so.
- Inspect nearby helper/render code before editing generated manifests directly.
- Preserve established schema, key ordering conventions, and naming where practical.
- Keep environment-specific values in the established config/vars mechanism.
- Do not duplicate the same setting in multiple sources unless the existing renderer requires it.

## Validation

After changing configuration:

1. run the existing renderer/helper if one exists;
2. inspect the generated diff;
3. run any existing syntax/schema validation;
4. deploy through the owning role/playbook;
5. verify the live consumer actually loaded the new configuration.

If a pod mounts a ConfigMap/Secret with `subPath`, remember that a rollout/restart may be required after the ConfigMap/Secret is updated.

## Boundaries

- Do not put secrets into ordinary config files.
- Do not alter unrelated generated outputs.
- Do not bypass an established renderer merely because editing the generated file is faster.
