# Glance skill editor

Web page at `https://glance.internal.homelab.example/skills/` (linked from Glance → LLM Lab)
for editing the `SKILL.md` text of the repository-managed WatooM-Code skills.

## How a save works

1. The UI pod (`glance/skill-editor`, uid 1010, read-only root, no Git) authenticates
   the owner (password in `/data/ai/private/skill-editor/password`, user `admin`),
   checks Origin and CSRF, and forwards the request over a Unix socket.
2. The root broker (`watoom-skill-editor-broker.service`) accepts only uid 1010 and:
   - refuses unless the canonical checkout is on `main`, the skill's committed blob is
     the one the editor loaded (no lost updates) and the working copy is clean;
   - requires the front matter to keep its existing `name:` and a `description:`;
   - writes the file and runs `git commit --only -- <that SKILL.md>` as
     `Agent Export`, so unrelated staged or dirty files are never included;
   - copies the committed text to the live tree
     (`/data/ai/watoom-code/config/skills/<skill>/SKILL.md`, 1001:1001 0644).

Because the edit is committed to the source the skills playbook deploys from, later
`watoom-native-skills.yml` runs keep it. Scripts and other skill files are not editable.

## Not automatic

- Commits are **not pushed** to GitHub; the page shows how many commits are unpushed.
- Editor commits land on canonical `main`. Before fast-forwarding canonical `main`
  from an agent branch, merge canonical `main` into that branch first.

## Deploy and test

```
ansible-playbook -i ansible/inventories/homelab/hosts.yml ansible/playbooks/skill-editor.yml --connection local --limit homelab-host
python3 -m unittest test_skill_editor   # from tools/skill-editor
```
