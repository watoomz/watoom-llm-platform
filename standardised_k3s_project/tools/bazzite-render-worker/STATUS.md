# Bazzite worker integration status (2026-10-26)

Completed and verified:
- Official Blender5.2.1 LTS build9e2066aef7ef, SHA-verified portable archive; existing Flatpak preserved.
- Real CPU render as watoom in root-owned sleep inhibitor and systemd cgroup:10GiB max,8GiB high,6 CPU quota; process/runtime bounded.
- Resumable SFTP output receiver: partial files, SHA256/size verification, atomic receipt, stable acknowledgment, per-delivery lock. Five fault-injection tests and real resumed SFTP transfer + persisted ACK passed; no render replay.
- Generic capture-scene operation deployed to main native application and its bounded CPU worker. Cross-project fixture rendered. Godot scene launches in the application are blocked, including headless/Xvfb wrappers; discovery and parser-only checks remain usable.
- Staged routing/resource policy stored in routing-policy.json.

Outstanding: connect the Bazzite consumer and capability-aware Bazzite-first/RIG-fallback scheduler to the existing native queue. Policy activation remains qualification-required; the existing RIG route is preserved. Do not claim Bazzite-first routing is live.
Godot graphics qualification failed under the isolated launcher because no usable Wayland/X11 display was available; headless import/regression passed earlier. GPU capture must route only to a qualified backend. No network/display settings were changed.

Resume from authoritative tools/bazzite-render-worker and tools/rig-async-stage. Reuse the existing broker ownership/token, source freezing, native proof and completion outbox rather than introducing a parallel scheduler. Never fall back/replay a job whose remote execution may have started.
