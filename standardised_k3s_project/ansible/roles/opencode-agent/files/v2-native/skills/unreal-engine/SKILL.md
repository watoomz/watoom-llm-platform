---
name: unreal-engine
description: Use for Unreal Engine projects, including C++ and Blueprints, .uproject/.uplugin structure, assets, maps, gameplay frameworks, Enhanced Input, physics, animation, materials, Niagara, lighting, Lumen, Nanite, plugins, automation, builds, packaging, profiling, and version-aware Unreal APIs.
---

# Unreal Engine

Use this skill for Unreal Engine projects.

Do not assume an Unreal Engine major or minor version.

Determine the project's actual engine association, build metadata and available
engine installation before using version-specific APIs, command-line flags,
plugins or migration advice.

## Core operating rule

Inspect the existing project before changing it.

Do not recreate a project merely because its current structure is unfamiliar,
incomplete, broken, or difficult to build.

Reuse the project's existing assets, code, Blueprints, maps, configuration,
plugins and conventions wherever practical.

When the assignment is to improve an existing game, improve that game rather
than creating a substitute demonstration project.

## Establish engine and project identity

Start with the project's actual evidence.

Inspect as applicable:

- `*.uproject`;
- `Config/DefaultEngine.ini`;
- `Config/DefaultGame.ini`;
- `Config/DefaultInput.ini`;
- `Source/`;
- `Content/`;
- `Plugins/`;
- `Build/`;
- `Platforms/`;
- target files;
- module `.Build.cs` files;
- plugin `.uplugin` descriptors.

Read `EngineAssociation` from the `.uproject` when present.

Do not infer the exact Unreal version solely from directory names,
documentation remembered by the model, or an asset's advertised compatibility.

If an engine binary is available, query the installed engine/version rather
than guessing.

Report version uncertainty explicitly when exact evidence is unavailable.

## Source of truth

Treat these as authoritative project inputs when present:

- `.uproject`;
- `.uplugin`;
- `Source/`;
- `Content/`;
- `Config/`;
- `Plugins/`;
- `Build/`;
- project-specific scripts and automation;
- project-specific tests.

Do not treat generated state as authoritative source.

Typical generated or disposable state includes:

- `Binaries/`;
- `DerivedDataCache/`;
- `Intermediate/`;
- `Saved/`;
- IDE-generated project metadata.

Do not delete generated directories merely because they are normally
re-creatable. Destructive cleanup requires a concrete reason and authorization.

## Asset-first workflow

Before creating replacement content, inventory the assets already available to
the project.

Look for relevant:

- Static Meshes;
- Skeletal Meshes;
- textures;
- materials and material instances;
- animations;
- animation Blueprints;
- sounds;
- Niagara systems;
- foliage;
- landscapes;
- data assets;
- UI assets;
- maps;
- imported marketplace or external asset packs.

Prefer adapting existing suitable assets over synthesizing crude substitutes.

Do not assume an asset is unused merely because there is no obvious source-code
reference. Unreal assets may be referenced through Blueprints, maps, soft
references, data assets, Asset Manager rules or editor configuration.

## Unreal binary assets

Treat `.uasset` and `.umap` files as structured Unreal binary assets.

Do not:

- edit them as text;
- perform search/replace over their binary contents;
- fabricate binary asset contents;
- claim to have modified a Blueprint graph without an engine/editor-capable
  mechanism that actually performed the modification.

When a required binary asset change cannot be performed in the available
environment, distinguish clearly between:

1. source/config work completed;
2. engine/editor work still required.

Never report hypothetical editor operations as completed work.

## C++ architecture

Before modifying C++, inspect:

- module boundaries;
- `.Build.cs`;
- target files;
- existing include conventions;
- UObject/UClass/USTRUCT/UENUM declarations;
- reflection macros;
- generated-header placement;
- ownership and lifetime;
- existing gameplay framework.

Preserve Unreal Header Tool requirements.

Do not casually rename reflected classes, properties or functions when existing
Blueprints or serialized assets may reference them.

Consider compatibility implications for:

- `UCLASS`;
- `USTRUCT`;
- `UENUM`;
- `UPROPERTY`;
- `UFUNCTION`;
- Blueprint-exposed names;
- class paths;
- asset references;
- config properties.

Do not treat successful standalone C++ compilation as sufficient Unreal
validation.

## Gameplay framework

Determine the architecture actually in use before introducing another one.

Inspect relevant existing:

- `UGameInstance`;
- `AGameModeBase` / `AGameMode`;
- `AGameStateBase` / `AGameState`;
- `APlayerController`;
- `APlayerState`;
- `APawn`;
- `ACharacter`;
- `UActorComponent`;
- subsystems;
- interfaces;
- gameplay tags;
- Gameplay Ability System;
- Blueprint framework.

Do not introduce GAS, Mass, CommonUI or another large framework solely because
it could solve a local problem.

Use the project's existing abstractions unless the task explicitly calls for an
architectural change.

## Blueprints

Blueprints are first-class project implementation.

Do not assume C++ is preferable simply because it is easier for a text agent to
edit.

Before replacing Blueprint functionality with C++, establish why the change is
necessary.

Preserve Blueprint-callable and Blueprint-implementable contracts when existing
assets depend on them.

For mixed C++/Blueprint systems, keep responsibilities explicit.

## Input

Determine the actual input architecture.

Common possibilities include:

- Enhanced Input;
- legacy Action/Axis mappings;
- custom input abstraction;
- platform-specific input.

For Enhanced Input inspect:

- Input Actions;
- Input Mapping Contexts;
- where contexts are added/removed;
- trigger/modifier behavior;
- possession/controller lifecycle.

Do not replace the input architecture as part of an unrelated gameplay change.

## Physics and movement

Identify whether movement is driven by:

- Character Movement Component;
- physics simulation;
- root motion;
- custom Pawn movement;
- vehicle systems;
- direct transforms;
- another project-specific system.

Preserve collision channels, object types, profiles and response settings.

Avoid changing global physics settings to solve a local gameplay issue unless
evidence demonstrates that the global setting is the cause.

Keep tick-rate and frame-rate assumptions explicit.

## World, maps and levels

Before world changes inspect:

- project default maps;
- game default maps;
- World Partition usage;
- streaming configuration;
- Data Layers;
- Level Instances;
- landscape;
- foliage;
- navigation;
- collision;
- spawn points;
- world settings.

Do not create a new map merely to avoid understanding the existing one.

Do not overwrite a production map for an experiment.

Use a bounded test map or copy only when the task genuinely requires isolation.

## Rendering

Determine the actual renderer/project settings before changing visual systems.

Inspect relevant configuration for:

- rendering feature level;
- RHI;
- DirectX/Vulkan choice;
- Forward vs Deferred rendering;
- Lumen;
- Nanite;
- Virtual Shadow Maps;
- ray tracing;
- TSR;
- post processing;
- exposure;
- scalability;
- texture streaming;
- virtual textures.

Do not enable expensive rendering features merely because the engine supports
them.

Do not assume an imported asset is Nanite-ready or that its material is
compatible with every rendering path.

## Materials and textures

Preserve existing master-material and material-instance architecture.

Prefer parameterized material instances over duplicating near-identical
materials when that matches the project.

Inspect:

- texture resolutions;
- compression;
- sRGB intent;
- normal-map settings;
- material domain;
- blend mode;
- shading model;
- instance hierarchy.

Avoid broad material conversion without visual validation.

## Lighting and atmosphere

For visual improvement inspect the existing scene before adding systems.

Relevant components may include:

- Directional Light;
- Sky Light;
- Sky Atmosphere;
- Volumetric Clouds;
- Exponential Height Fog;
- post-process volumes;
- local lights;
- reflection/capture strategy;
- Lumen settings.

Avoid stacking duplicate environment systems because the existing configuration
was not inspected.

Visual changes require visual evidence when the environment supports rendering.

## Nanite

Use Nanite deliberately.

Consider:

- engine version;
- target platform;
- mesh type;
- material compatibility;
- deformation requirements;
- foliage behavior;
- performance evidence.

Do not globally enable Nanite on every mesh as an optimization shortcut.

## Lumen

Use Lumen only when supported by the project's engine version, renderer,
platform and performance target.

Inspect existing GI/reflection settings first.

Do not claim Lumen is faster or visually preferable for a particular project
without project-specific evidence.

## Niagara and effects

Reuse existing Niagara systems where appropriate.

Before changing effects inspect:

- system and emitter structure;
- user parameters;
- material dependencies;
- collision;
- scalability;
- bounds;
- spawn rates;
- GPU versus CPU simulation.

Avoid unbounded particle counts and effects with uncontrolled lifetime.

## Animation

Inspect the actual animation architecture before changing character behavior.

Relevant systems include:

- Animation Blueprints;
- state machines;
- montages;
- blend spaces;
- Control Rig;
- IK Rig;
- IK Retargeter;
- root motion;
- motion matching where adopted.

Preserve skeleton and retargeting compatibility.

Do not silently replace skeletons or animation assets.

## UI

Determine whether the project uses:

- UMG;
- CommonUI;
- Slate;
- another UI layer.

Preserve existing viewport ownership, input modes, focus behavior and controller
navigation.

Do not introduce CommonUI solely for a small HUD change.

## Plugins

Treat project plugins as part of the compatibility surface.

Inspect:

- `.uproject` plugin declarations;
- `Plugins/`;
- `.uplugin` descriptors;
- module loading phases;
- platform restrictions;
- engine-version constraints.

Do not upgrade, disable or replace unrelated plugins.

Do not assume a marketplace/plugin release is compatible with the project's
exact engine version.

## Asset migration and external packs

When integrating Unreal-targeted asset packs:

1. identify the pack's supported engine versions;
2. inspect dependencies and required plugins;
3. preserve the project's existing content organization where practical;
4. avoid filename/path collisions;
5. preserve material and skeleton dependencies;
6. validate migrated references;
7. avoid copying generated cache/build state.

Do not flatten a structured Unreal asset pack into arbitrary directories.

When source assets such as FBX, GLTF, textures or audio are available, preserve
them according to the project's existing source-art convention.

## Performance

Measure before broad optimization.

Inspect evidence such as:

- `stat unit`;
- `stat game`;
- `stat gpu`;
- Unreal Insights;
- render/GPU profiling;
- memory reports;
- asset sizes;
- shader complexity;
- draw calls;
- actor/component counts;
- tick cost;
- Blueprint hot paths;
- texture streaming;
- shader compilation;
- loading behavior.

Potential optimization techniques are not evidence that they are needed.

Do not perform broad optimization passes without first identifying a measured
bottleneck.

## Tick discipline

Avoid adding per-frame Tick work when event-driven or timer-based behavior is
sufficient.

For existing ticking objects inspect:

- whether Tick is enabled;
- tick interval;
- tick group;
- dependencies;
- work performed per frame.

Do not disable Tick globally to solve a local performance issue.

## Memory and references

Understand Unreal ownership and garbage collection.

Be deliberate with:

- UObject references;
- weak references;
- soft references;
- asset references;
- delegates;
- spawned actors/components;
- async loads.

Avoid converting soft references into hard references casually, especially when
that expands startup memory or packaging dependencies.

## Async and threading

Do not assume arbitrary UObject or engine operations are thread-safe.

Keep game-thread requirements explicit.

When using asynchronous loading, tasks or worker threads, preserve object
lifetime and synchronization semantics.

Do not move engine calls off the game thread solely as an optimization attempt.

## Networking

When the project is networked, establish authority and replication architecture
before changing gameplay.

Inspect:

- server/client authority;
- replicated properties;
- RPCs;
- relevancy;
- ownership;
- prediction;
- dormancy;
- replicated components;
- dedicated-server requirements.

Do not fix a replication issue by duplicating authoritative gameplay state on
clients.

## Configuration safety

Treat Unreal `.ini` files as structured configuration.

Prefer narrow changes.

Preserve existing sections and project overrides.

Do not replace complete configuration files for a one-line setting change.

Remember that configuration may be layered across engine, project, platform and
user-generated state.

## Build system

Use the project's actual build mechanism.

Depending on environment this may involve:

- UnrealBuildTool;
- AutomationTool / `RunUAT`;
- editor commandlets;
- project-specific scripts;
- IDE-generated build integration.

Discover actual engine paths before invoking them.

Do not invent paths such as `/opt/UnrealEngine` or assume Epic Launcher layout.

Do not install or download an Unreal Engine version unless explicitly
authorized.

## Linux/headless environments

A Linux OpenCode environment does not imply that Unreal Editor or a compatible
engine build is installed.

Check first.

Useful evidence includes commands such as:

    find /opt /usr/local /data /app -maxdepth 4 \
      -type f \
      \( -name UnrealEditor -o -name UnrealEditor-Cmd \) \
      2>/dev/null

and project-local scripts/configuration.

Do not run an unbounded filesystem search.

If Unreal Editor is unavailable, perform the strongest source-level validation
available and report engine-level validation as BLOCKED rather than pretending
it passed.

## Commandlets and unattended execution

Prefer commandlets or project automation for operations that can safely be run
without an interactive editor.

Use the project's exact engine binary and project file.

Bound long-running commands with sensible timeouts where appropriate.

Capture stdout/stderr and exit status.

Do not assume every editor operation has a safe commandlet equivalent.

## Testing and validation

Validate from cheapest/most targeted to broader checks.

Prefer:

1. inspect exact engine/project version;
2. validate descriptors and configuration;
3. compile affected C++ module when engine tooling exists;
4. run project automation tests when present;
5. load the smallest relevant map/test;
6. run commandlet validation where appropriate;
7. perform bounded runtime test;
8. capture actual visual evidence for visual changes;
9. package/build only when required.

A successful source parse or standalone compiler run is not proof that Unreal
reflection, Blueprints, assets or maps are valid.

## Visual validation

When the task changes appearance, level layout, materials, lighting, characters,
camera or UI, visual evidence is part of validation when rendering capability is
available.

Use the actual project and actual affected map.

Do not:

- substitute a mock scene;
- fabricate screenshots;
- describe an imagined render as evidence;
- claim visual correctness from compilation alone.

When automated capture is supported, capture a real viewport/game/render output.

Record:

- project;
- map;
- engine version;
- renderer/RHI when known;
- resolution;
- capture path;
- relevant log output;
- PASS/FAIL and limitations.

## Logs and crashes

For a failing project inspect the current run's evidence.

Useful sources may include:

- `Saved/Logs/`;
- crash context;
- AutomationTool output;
- UnrealBuildTool output;
- editor commandlet output;
- system/GPU errors where relevant.

Do not diagnose a current crash solely from stale logs.

Identify the timestamp/run corresponding to the failure.

## Build and packaging

Determine actual target platform and configuration first.

Do not alter unrelated packaging settings.

Preserve:

- target definitions;
- platform-specific configuration;
- required maps;
- cook rules;
- plugin dependencies;
- staging requirements.

A Development Editor build is not equivalent to a packaged-game validation.

## Engine upgrades

Do not upgrade Unreal Engine as part of an unrelated task.

For an explicitly requested upgrade:

1. establish exact starting version;
2. identify target version;
3. inspect plugin compatibility;
4. preserve a reproducible baseline;
5. distinguish generated upgrade changes from intentional refactors;
6. compile C++ modules;
7. inspect Blueprint/compiler errors;
8. inspect materials/rendering;
9. validate important maps;
10. run project tests;
11. validate packaging when relevant.

Do not silently resave every asset as part of an unrelated change.

## Git and generated files

Respect the repository's existing ignore policy.

Do not use destructive broad cleanup commands.

Do not use:

- `git reset --hard`;
- `git clean -fd`;
- `git checkout .`;
- broad `git restore`.

Do not stage unrelated changes.

Preserve existing dirty work unless the assignment explicitly owns it.

## Agent workflow

For non-trivial Unreal work use this sequence:

1. inspect;
2. identify exact engine/project constraints;
3. inventory reusable assets;
4. identify the smallest implementation surface;
5. collect missing evidence before guessing;
6. make bounded changes;
7. run source/config validation;
8. run engine validation when available;
9. run the smallest meaningful gameplay test;
10. capture actual visual evidence for visual work;
11. inspect logs;
12. repair only evidence-backed failures;
13. rerun affected validation;
14. report exact changed files and proof.

Do not repeatedly rewrite the implementation without new evidence.

## WatooM evidence rule

Never guess a missing engine path, project version, asset location, map name,
plugin state, build command or runtime capability.

When required evidence is missing, gather it read-only first.

Current runtime evidence overrides stale conversation context.

Do not install dependencies, engine versions or plugins merely because a
validation capability is unavailable.

## Completion

Before finishing Unreal work report:

- detected Unreal Engine version or why it remains unknown;
- `.uproject` used;
- relevant modules/plugins;
- relevant existing assets reused;
- files changed;
- source/config validation;
- engine/editor validation;
- gameplay/runtime validation;
- visual evidence when applicable;
- packaging/build validation when applicable;
- blocked validation and its exact reason;
- remaining risks.

Never report a validation stage as passed when it was not actually executed.

<!-- WATOOM-UNREAL-RUNTIME-BEGIN -->

## WatooM Unreal runtime

For the WatooM homelab OpenCode deployment, use these runtime facts unless
fresh runtime evidence contradicts them.

### Paths

Inside OpenCode:

- Unreal Engine: `/unreal-engine`
- Unreal Engine installation is read-only.
- Game workspace: `/workspace/games`
- Wombat Australia project: `/workspace/games/wombat-australia`
- Project descriptor: `/workspace/games/wombat-australia/WombatAustralia.uproject`

Use the container-visible paths above for OpenCode work.

### Installed engine

The installed source-built engine is Unreal Engine 5.8.3.

Expected executables:

- `/unreal-engine/Engine/Binaries/Linux/UnrealEditor`
- `/unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd`

The engine installation must not be edited, rebuilt, patched, cleaned, checked
out, or used as a destination for project-generated content during ordinary
game-development tasks.

Do not run Epic setup/build/update operations unless the user explicitly asks
for engine maintenance.

### Runtime identity

OpenCode runs as UID/GID `1009:1009`.

Never run UnrealEditor or UnrealEditor-Cmd as root.

A previous root probe was invalid because Unreal explicitly reported:

    Refusing to run with the root privileges.

Do not treat that root refusal as evidence that the engine is broken.

Run Unreal validation through the normal non-root OpenCode runtime.

### Known engine capabilities

This installation has confirmed engine-side support for:

- Runtime Landscape
- LandscapeEditor
- PythonScriptPlugin
- EditorScriptingUtilities

Availability in the engine installation does not automatically mean every
plugin is enabled in a particular project. Inspect the current `.uproject` and
configuration before relying on a plugin.

### Wombat Australia assets

The existing project contains imported content directories corresponding to:

- `/Game/Wildwood`
- `/Game/Oni_Project`
- `/Game/Creatures`

Do not invent Unreal object paths from filenames.

Confirm exact object paths through Unreal or Asset Registry evidence before
referencing assets in automation.

Do not move, rename, mass-edit, or duplicate imported Marketplace content
without an explicit requirement.

### Unreal asset safety

Never hand-author binary `.uasset` or `.umap` data.

Create and save Unreal assets through Unreal itself using supported editor
scripting, Python editor APIs, C++ editor tooling, commandlets, or another
verified engine mechanism.

Project text source/configuration such as `.uproject`, `.ini`, `.Build.cs`,
`.Target.cs`, C++, and project-local Python scripts may be edited when required.

### UE 5.8 API evidence rule

Do not guess Unreal Python, Landscape, World Partition, Editor Utility,
asset-creation, or map-saving APIs from memory or examples for other Unreal
releases.

Before using version-sensitive editor APIs:

1. inspect the current project;
2. inspect UE 5.8.3 installed engine/plugin source or reflected Python API;
3. identify the exact callable/property present in this installation;
4. implement the smallest reproducible automation;
5. run Unreal to create/save the actual assets;
6. verify generated assets through Unreal or Asset Registry evidence.

For Landscape work, inspect the installed UE 5.8.3 Landscape and
LandscapeEditor implementation before choosing the automation path.

### Headless qualification

Use the actual project and the non-root runtime. A suitable minimal probe is:

    timeout --signal=TERM --kill-after=15s 300s \
      /unreal-engine/Engine/Binaries/Linux/UnrealEditor-Cmd \
      /workspace/games/wombat-australia/WombatAustralia.uproject \
      -NullRHI \
      -Unattended \
      -NoSplash \
      -NoSound \
      -NoAssetRegistryCache \
      -ddc=NoZenLocalFallback \
      -LocalDataCachePath=/home/opencode/.cache/UnrealEngine/DerivedDataCache \
      -stdout \
      -FullStdOutLogOutput \
      -ExecCmds="QUIT_EDITOR"

Do not claim command-line automation is qualified merely because binaries
exist. Report the actual return code and relevant Unreal log evidence.

Do not repeatedly rerun a crashing editor invocation without new evidence.

### World-building workflow

For requests to create terrain or a first playable world:

1. inspect `.uproject`, Config, Content, Source, Plugins, and existing maps;
2. preserve existing project state;
3. determine the exact UE 5.8.3 automation surface;
4. create a real Unreal Landscape rather than substituting a scaled cube or
   static plane unless the user explicitly requests a placeholder;
5. use simple deterministic terrain first;
6. add only the minimum lighting, sky, fog, and Player Start;
7. save assets through Unreal;
8. validate the resulting map through Unreal;
9. render/capture only after runtime/rendering capability is proven.

Prefer reproducible project-local automation over undocumented manual GUI-only
steps.

### Failure classification

Distinguish:

- project permission failure
- engine mount/visibility failure
- missing shared-library/runtime dependency
- Unreal project/plugin/configuration failure
- Unreal API/automation failure
- rendering/GPU/display failure

Do not collapse these into a generic Unreal failure.

<!-- WATOOM-UNREAL-RUNTIME-END -->
