# Model manager

The CPU page inspects fixed-origin Hugging Face metadata, exact immutable file
selections, revisions and dependencies. It queues verified downloads, managed
zero-replica enrollment, generation validation and scoped removal. Source text
is never executed. GGUF, SDXL pipelines/checkpoints and SDXL LoRAs are distinct.
An SDXL adapter/checkpoint requires an explicitly selected installed base.

The latest owner default is 100000 context / 4096 output for language models,
with q4_0/q4_0 KV and a lower documented or GGUF-header limit enforced.
Architecture-specific MTP/vision capabilities remain opt-in and unverified
features are blocked. Image profiles have no language-model context settings.
Settings precedence is saved override, explicit applicable recommendation,
then the safe baseline. Safe reset persists; published reset clears overrides.

## Build and isolated staging

From a clean reviewed checkout, as an administrator:

    python3 tools/model-manager/manage.py build --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE
    python3 tools/model-manager/manage.py build-sdxl --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE
    python3 tools/model-manager/manage.py stage --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE
    python3 tools/model-manager/manage.py validate --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE

Staging uses a separate namespace/catalog/service and disables production
registration and GPU generation. It downloads no example model weights.
The SDXL image build installs software only and uses no GPU. Published image
digests identify exact artifacts; a build/pull/rollout alone is not acceptance.

The normal Ansible entry point is ansible/playbooks/model-manager.yml.
Root broker code is installed under /app/model-manager/releases; application
state and model data remain under /data/ai. No historical recovery overlay,
private skill, or retained Unreal experiment is a build dependency.

## Approval-gated production integration

Prepare a fresh private snapshot and exact source plan:

    python3 tools/model-manager/cutover.py prepare --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE

Review that plan, source commit, staging results and rollback before approving
a maintenance window. The activation command requires both the exact prepared
commit and an explicit administrative-quiet assertion. It refuses active native
work or actual inference and retains durable fencing during controller/router
changes. It never scales directly, rewrites legacy cutover proofs or changes
admission/RBAC to a wildcard writer.

The approved command is:

    python3 tools/model-manager/cutover.py activate --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE --approve EXACT_PREPARED_COMMIT --i-approve --administrative-quiet

The intended page is https://glance.internal.homelab.example/model-manager/ from
Glance's existing LLM Lab page. Do not call that URL deployed until activation,
served-page checks and real backend generation have passed.

Installation credentials are in the operator-private model-manager directory.
Never put them in URLs, browser storage, Git or a report. Optional Hub tokens
are read from private files and never sent with third-party CDN redirects.

## Runtime and removal

A registration transaction creates only manager-owned replicas=0 resources,
validates Kubernetes identities and enrolls never-started models through the
existing fenced controller. Enrollment is separate from legacy cutover proof.
The router consumes the root-derived catalog and managed requests hold durable
inference leases, including streaming completion. Actual slots/status must be
idle before switching. Native job admission is held for explicit generation;
uncertain completion retains recovery fences rather than killing work.

Changing settings creates an immutable replacement deployment/identity.
Verified shared files are reused; full diffusion directory closures use tracked
hard links. Existing deployment spec hashes are never edited behind the
controller. The previous version remains available until explicitly removed.

Remove defaults to keeping files and always requires a fresh identity-scoped
confirmation. Deletion moves only verified unshared owned files to quarantine,
with a durable recovery receipt; it does not claim reclaimed bytes. There is no
automatic purge. Shared bases, protected recovery models and active work block
unsafe removal. Failed or interrupted jobs retain receipts and partial data.

## Rollback and acceptance

    python3 tools/model-manager/manage.py rollback-stage --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE
    python3 tools/model-manager/cutover.py prepare-rollback --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE
    python3 tools/model-manager/cutover.py rollback --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE --approve EXACT_ROLLBACK_RELEASE_COMMIT --i-approve --administrative-quiet

Production rollback refuses active work, registered managed models and
independent edits. It reconciles durable before/after mutation intents, including a failure before
late success receipts exist, and removes only release-labelled resource UIDs. After an approved source upgrade,
prepare-rollback records the current maintained controller hashes and exact
manager resource identities without overwriting original before snapshots.
Any later independent spec, UID or metadata change blocks that prepared rollback.
It preserves model files. Recover or remove managed registrations through the controller first.
A retained maintenance record is intentional and requires operator review.

Offline fixtures and browser tests do not establish real GPU generation.
Keep downloaded, configured, registered and tested states separate. Remaining
acceptance is recorded in the private implementation-report.json, including
actual LLM and SDXL outputs or explicit BLOCKED/NOT TESTED results.

Production integration is not accepted by software imports or a staging rollout.
The staged CPU application and fixture removal were exercised; new controller
enrollment, GPU generation and production rollback still require authorized live
validation. The current package supports GGUF text generation and SDXL image
pipelines/checkpoints/LoRAs, not arbitrary Hugging Face architectures, SD3/Flux,
pickle-only pipelines or automatic remote-code execution.

After source review, promote this branch into the authoritative repository using
the normal review process; do not replace unrelated main-branch configuration.
Run prepare again from that clean promoted checkout, then approve its exact commit.
The private snapshots are operational rollback inputs, not build dependencies.
An activation exception does not imply that all production changes were reverted:
use the recorded transaction and gated rollback; uncertain ownership or unrelated
edits must be reconciled rather than forced. Data-preserving rollback is never
permission to unload an active model or overwrite independently changed state.

## SDXL software placement

The immutable software payload is published under
/data/ai/toolchains/model-manager-sdxl; GPU pods mount its root-owned Conda
runtime read-only at /app/runtime. Only the small pinned runner image enters
node image storage. Do not deploy the large software-source image as a pod.

    python3 tools/model-manager/manage.py publish-sdxl-runtime --evidence /data/ai/helper-scripts/model-manager-builds/CHANGE/sdxl-runtime

The publisher verifies the unpacker checksum, payload manifest and CPU imports,
then records a runner image with exact source and payload labels. Persist that
artifact and runtime descriptor in config/llm/model-manager/runtime.json before
the normal model-manager.yml deployment. GPU admission additionally checks root
disk headroom and node DiskPressure before draining the primary. Neither a
software import nor an image rollout proves generation.

## Repeatable production browser acceptance

Install the pinned test dependency with npm ci --ignore-scripts in
tools/model-manager, then install its headless Chromium into
/data/ai/toolchains/model-manager-browser using PLAYWRIGHT_BROWSERS_PATH and
npx playwright install chromium --only-shell.

    sudo python3 tools/model-manager/browser-test.py --evidence /data/ai/builds/model-manager-browser-NEW_RUN

This uses a new UID1009 browser profile with only the existing homelab public CA
trusted in that profile. TLS verification remains enabled; global machine trust,
networking and GPU ownership are untouched. Login, the real Glance link, live
LoRA metadata, exact sizes and dependency/settings controls are checked without
starting a download or generation. The example base must already be installed.
