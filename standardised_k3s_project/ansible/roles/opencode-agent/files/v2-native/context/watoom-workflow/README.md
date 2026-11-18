# WatooM Workflow

This is a purpose-built WatooM workflow for the local OpenCode/Swift stack.

It adopts ideas, not installers/config trees, from:

- Agentic: phased Research -> Plan -> Execute -> Review and persisted context
  artifacts.
  Source: https://github.com/Cluster444/agentic
  Build-time source commit: 3a3915310d3d03d4a45114b7b0c0a17c34bf0e8b

- OpenAgentsControl: minimum-viable-information context discipline, explicit
  task acceptance criteria, resumable progress and bounded specialist roles.
  Source: https://github.com/darrenhinde/OpenAgentsControl
  Build-time source commit: 37ca233fa5597a5abb90cba73165deafffe0344f

Both upstream projects are MIT licensed at the time this integration was
designed.

WatooM deliberately omits upstream commit automation and interactive approval
gates because this homelab uses unattended bounded execution with explicit hard
Git/privilege restrictions.
