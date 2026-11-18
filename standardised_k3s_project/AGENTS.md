# WatooM Standardised K3s Project

This directory contains the active homelab IaC project.

Important areas:

- `ansible/` — roles, playbooks, inventories, group vars
- `manifests/` — Kubernetes manifests and generated deployment material
- `config/` — source configuration and render inputs
- `scripts/` — maintained helper and operational scripts

## Working method

1. Inspect the current source of truth and nearby conventions.
2. Identify whether a file is authoritative or generated before editing it.
3. Prefer persistent source changes over live-only fixes.
4. Keep changes narrowly scoped.
5. Validate before deployment.
6. Deploy only the affected component.
7. Verify the live result.
8. Check that the Git index was not changed unexpectedly.

## Existing infrastructure

- k3s and Docker already exist; do not reinstall them.
- Use existing Ansible roles/playbooks when they manage the component.
- Use existing package-management/helper scripts rather than introducing parallel installers.
- Keep environment-specific values in existing vars/config mechanisms rather than scattering literals through tasks or scripts.

## Boundaries

Do not modify unrelated services, networking, secrets, authentication, authorization, or security policy unless the task explicitly requires it.

## Publishing fixes

Who publishes where:

- **WatooM-Code/OpenCode models** commit to their agent branch and integrate only into `dev` after validation. They never modify, merge or push `main`.
- **The owner's operator assistant (Claude Code)**, after validating a requested fix, commits and pushes its explicitly reviewed paths to `main`. This is the owner's standing preference.

Both: preserve unrelated dirty changes and the existing index; never use broad staging or rewrite branch history. Keep staged-only capabilities distinguished from live activation, and report any deployment blocker honestly.

## Model GPU placement preference

Prefer full GPU residency for model weights (including the MTP head and vision projector) whenever the complete model, KV context, compute buffers and a safety margin fit in available VRAM. Do not configure CPU expert/FFN offload as an arbitrary default. Retain CPU offload only as a documented, qualified capacity fallback. Do not silently change quantization, context size or KV precision to claim full residency. Validate a candidate through the existing GPU ownership controller with rollback before changing a running job. The CyberTiel IQ4_XS 128K/Q4 KV profile currently retains its eight-layer CPU MoE fallback; its recorded full-residency estimate leaves no safe headroom on the 20 GiB GPU.
