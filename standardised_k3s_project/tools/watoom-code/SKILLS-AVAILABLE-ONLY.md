# Skills page approved catalogue view

The native registry contains 116 usable skills. The catalogue separately contains 198 discovered records, 89 structurally valid entries and six approved entries. The page default previously requested approvedOnly=false and displayed the unapproved catalogue in Available. Self-learning snapshots were not in the native registry.

Source commit 25df038aa2b74a294000f6d166996f969253e0c3 changes Available to approvedOnly=true and reports its approved count. Installed still shows native skills; Pending Review preserves discovered candidates. No learning artifacts or catalogue entries were deleted or promoted.

Reproducible change: skills-available-only.patch against the previous application source. Candidate image: 127.0.0.1:5000/watoom-code@sha256:a7dfb0c680ac45aa4a7a8859e496bd09aeb8fd64a306ef044db648e1de220be0. Build and isolated acceptance evidence: /data/ai/projects/llm/watoom-code/skills-available-20261023. Router/selector tests, authenticated API/GUI, memory persistence, deployment fencing and rollback passed. Targeted real-browser verification confirms exactly six approved Available entries and a working Pending Review tab; available.png and pending.png are retained there under skills-ui.

Production deployment is pending the existing idle-admission gate because Magpie is running. Use the existing tools/watoom-code/deploy-platform.py with candidate-acceptance.json; do not interrupt active work or bypass the gate. The existing deployer preserves current config and updates only the image/source fields for a normal app release. Previous image for automatic rollback: 127.0.0.1:5000/watoom-code@sha256:028d291333f054e2b292a63ede2de6689e335eb92fc72b49e7fb13bc4297fb23.
