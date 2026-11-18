# Model Manager

Open Glance > LLM Lab > Model Manager:
https://glance.internal.homelab.example/model-manager/

Paste a Hugging Face URL, select an immutable revision and variant, review exact
download bytes and setting sources, then choose Download & set up.

GGUF language models default to 100000 context and 4096 output with q4_0 K/V.
Lower documented or GGUF context limits take precedence. Saved overrides,
published recommendations and safe defaults remain distinct.

SDXL pipelines, checkpoints and LoRAs are image backends. A LoRA needs an
explicitly selected compatible installed base. The 3D-animation example requires
stabilityai/stable-diffusion-xl-base-1.0.

Downloaded, configured, registered and tested are separate states. Generation
uses the existing exclusive GPU controller and restores the primary afterward.
Active work and unknown outcomes block unsafe changes.

Removal defaults to unregistering while retaining files. Confirmed removal
quarantines only verified unshared files; it does not immediately reclaim space.
Shared dependencies and existing recovery models remain protected.

The authenticated production page and served Glance link are verified.
Real GGUF generation and SDXL checkpoint generation at 1024×1024 passed.
Full SDXL LoRA generation at normal 30-step, 1024×1024 settings passed,
including primary restoration. The neutral cube output was visually checked. Production browser automation passed with certificate verification
and isolated trust for the existing internal CA. No system trust was weakened.

Automated checks: 67 manager tests and 122 GPU-controller tests passed. Live
unregister-with-files-retained and shared-base protection passed. Isolated staging
rollback and the earlier partial production rollback passed; rollback of the final
registered production installation has not been exercised. Unregister managed
installations while keeping files before using the guarded production rollback.

Unsupported architectures and arbitrary remote model code are not enabled. Image
model quality depends on the chosen checkpoint, adapter and sampling settings;
a successful generation is not a claim of prompt fidelity.

Login reminder: the server-local password file is
/data/github/watoom-standardised-homelab/standardised_k3s_project/.private/llm-passwords.json.
It is locally excluded from Git and is never part of a commit or image.
The maintained login screens show this path, never its contents.
