# Qualified RIG capture backend

Normal model requests use native watoom_asset_capture in the authorized image project. Same stable native identity and root bridge proof; six modes, all fixed pose helpers, PNG/MP4, Action loops and external asset dependencies. Arbitrary asset-builder scripts remain outside the capture contract.

Windows pinned Blender 5.2.1, RTX2080SUPER OptiX or explicit CPU, 8GiB Windows Job Object, four render threads, one slot and 900-second capture deadline. Component scripts separately have a 300-second ceiling. No inference GPU use and no VRAM hard-cap claim.

Restricted persistent NDJSON SSH is control only. Separate locked, chrooted internal-SFTP account transfers read-only SHA-addressed snapshots and returned artifacts on /data. SFTP reget/reput support transfer resumption; host and client verify SHA-256. No passwords, shell, forwarding or broad host access. Preserve source files. Execution helper/script/profile hashes invalidate fetch adoption; interrupted/expired render claims never re-render automatically. The default worker claims native jobs only, preserving paused/manual requests.

Build Windows adapters with build_runtime.py from the authoritative source and verify renderer-provenance.json output hashes. Install-StageWorker.ps1 persists both SSH identities, SFTP, FFmpeg and native-only settings. Private keys stay on RIG. Activate backend/skills with activate.py under the existing native admission fence, then start the Windows task. Rollback disables the feature flag; previously admitted workstation jobs retain their route and must reconcile, not migrate.

Qualification 2026-10-26: component suite 50 pass/0 fail/0 skip, plus four explicit OptiX render/bake tests; capture inspect, still, turntable, animation, pose-inspect, auto/recipe/rig-adapter/TS4 preparation, MP4 and glTF/linked-library dependencies. SFTP upload/download resume, read-only input denial and chroot escape denial passed. Root receipt copy was checked in an isolated operator fixture, not a forged production admission. Visual acceptance always requires actual pixel review. Quin TS4 subset retains static limbs.

## OptiX capture efficiency

The generated Windows renderer enables Cycles persistent data for multi-frame OptiX animation/turntable captures and uses OptiX GPU denoising. Explicit CPU captures retain OpenImageDenoise on CPU and do not enable persistent data. Source assets, capture manifests, the 8GiB Job Object, four render threads and 900-second capture deadline are unchanged.

Each rendered job includes render-timings.json with per-frame elapsed time, observed Job Object peak memory and actual cache/denoising settings. The normal worker hashes and uploads this report with other outputs. Runtime receipts record render_settings and pinned renderer/helper hashes. Maintain this behavior in build_runtime.py; do not edit generated production renderers independently.

Qualification evidence: /data/ai/helper-scripts/workstation-render-optimization-20261026. The completed original clip is preserved; optimization validation uses separate derived outputs.
