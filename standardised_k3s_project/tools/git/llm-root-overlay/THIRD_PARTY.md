# Upstream and third-party components

| Component | Source/notice | Distribution treatment |
|---|---|---|
| OpenCode application | `application/LICENSE`, package metadata, upstream `https://github.com/anomalyco/opencode` | Pinned customised source snapshot; original notices retained |
| Application packages/dependencies | Workspace `package.json` files and `bun.lock` | Source and lockfiles retained; dependency caches excluded |
| Native skills and bundled bridge dependencies | Role payloads and their `LICENSE`, package metadata or skill notices | Preserve original notices; imported content is not claimed as WatooM-authored |
| llama.cpp / llamAmpere | Deployment/build references in the platform | External runtime/build input; weights and compiled binaries are not bundled |
| AgentMemory | Independent image pin and configuration in the WatooM role and `ansible/vars/watoom-code.yml` | Image source must be resolved separately for a clean build; not claimed to be the OpenCode source |
| Blender / Godot / Unreal | Owning worker recipes and version/hash checks | External engine/toolchain prerequisites; engine source and acquired assets excluded |
| Language/API reference manuals | `standardised_k3s_project/tools/language-knowledge/manuals/*/source.json` | Third-party documentation excerpts retained with their source notices; not claimed as WatooM-authored. Check each source's terms before redistributing |
| Purchased/Fab assets | Source/library paths referenced by worker contracts | Not redistributed |

See `publication/provenance.json` for the exact application source commit and source export limits. The full application includes upstream functionality not selected by the active WatooM configuration. Preserve applicable notices when changing the distribution. This list is a source/notice map, not a legal compatibility certification.
