# Unreal Editor MCP (ue-mcp) over a restricted SSH route

Lets watoom-code drive the Unreal Editor that is open on the rig through **db-lyon/ue-mcp** (npm package `ue-mcp`, with its
`UE_MCP_Bridge` editor plugin): scenes, assets, materials, landscape terrain and paint layers, animation, PCG, foliage,
Blueprints, screenshots. It is the same route as `tools/rig-godot-mcp`, with its own account, port and policy.

```
watoom-code pod --ssh (key, pinned host key)--> uemcp@rig:2224
   forced command: run-ue-mcp.cmd -> ue-mcp-policy-wrapper.js -> node npx-cli.js -y ue-mcp@<pinned> <project>.uproject
   ue-mcp --WebSocket (127.0.0.1, in the editor)--> UE_MCP_Bridge plugin
```

Nothing is exposed on the rig beyond one SSH port reachable from the lab only. This is **separate from the older Nwiro route**
in `tools/rig-unreal-mcp` (reverse tunnel + HTTP proxy for the Nwiro AI Integration Kit), which is left as it is and stays off.
Both can exist; pick the one whose plugin is installed in the project.

**Status (2026-11-14): everything on the lab side is built and tested; nothing has been run on the rig.** The two PowerShell
scripts here could not be executed from the lab, the wrapper was tested only against a stand-in server, and ue-mcp itself has
not been run against the rig's Unreal 5.8 editor. Treat the first rig session as verification, the way the Godot route was
(`tools/rig-godot-mcp/README.md`, "Rig-side behaviour verified"): the Windows OpenSSH findings there apply here unchanged
(profile-less account, `AuthorizedKeysFile` under ProgramData, launcher `.cmd`, `node npx-cli.js`).

## Why ue-mcp, and what it changes

* It exposes 31 category tools and 3,714 actions (Epic's own UE 5.8+ toolsets wrapped inside them) and is released often (1.4.13
  on 2026-11-10, 1.4.14 on the rig since 2026-11-19). Supports UE 5.4 to 5.9; the rig runs 5.8.
* Default context strategy is **micro**: one `tools` gateway (`guide`, `search`, `list_categories`, `describe`, `call`), about 240
  tokens, instead of 32k (lean) or 90k (full) tokens of tool schemas. The launcher pins `UE_MCP_CONTEXT_STRATEGY=micro`.
* Every action declares an **effect** (`read`, `mutate`, `unknown`). `unknown` marks the escape hatches (`execute_command`,
  `invoke_*`, `epic.call_tool`). The language-knowledge product `ue-mcp` carries one card per action with that effect.
* Landscape support is unusually complete for our terrain work: `plan_real_world`, `create`, `import_heightmap` (16-bit only),
  paint layers (`add_layer`, `set_layer_weight_region`), slope maps, erosion, splines.

## Policy (`ue-mcp-policy.reviewed.json`)

Decisions are made by the wrapper **on the rig, before ue-mcp sees the call**, on `category.method` (micro: `tools` +
`action:"call"`; lean/full: the category tool + `action`). `allow` and `deny` hold `category.method`, `category.*` or `*`;
**deny always wins**; a missing or invalid policy file falls back to a discovery-only baseline, never to allow-all. Discovery calls
(`guide`, `search`, `list_categories`, `describe`) are always answered. The live file is `C:\ProgramData\watoom\ue-mcp-policy.json`
and is re-read on every request (no restart).

**Opened by the owner on 2026-11-14: all 31 categories plus the `flow` tool are allowed and nothing is denied** (all 3,714 actions and flows), including the
escape hatches (`editor.execute_python`, `execute_command`, console), builds, C++ writes, plugins, Fab, flows, feedback and source
control. The file lists `<category>.*` per category rather than `*`, so a category added by a later ue-mcp release stays blocked until
the generator is re-run. The generator, `tools/language-knowledge/extract/ue_mcp_entries.py`, also writes the cards, so the cards and
the policy cannot disagree; to close something put it in `DENY_CATEGORIES` / `DENY_ACTIONS` there and re-run `build`, or add it to
`deny` in the live file for an immediate effect. Good first candidates to close if ever needed: `flow`, `feedback`, `plugins`, `fab`,
`source_control`, `editor.execute_python`, `editor.execute_command`, `project.build`. ue-mcp's own guards (`ue-mcp.yml` in the project)
are separate from this file and still apply.

The effect of 320 of the 3,714 actions could not be found in the package source and is treated as `mutate` (ue-mcp's own default
for an undeclared action); the cards say so per action.

## Install

1. **Rig, the Unreal project folder, editor CLOSED, as your own user:** `npx ue-mcp@1.4.14 init`. It installs
   `Plugins\UE_MCP_Bridge`, enables `UE_MCP_Bridge` and `PythonScriptPlugin` in the `.uproject` and writes `ue-mcp.yml`. Open the
   editor (a source build compiles the plugin on first launch) and check the Output Log for `LogMCPBridge`.
2. **router** (management VLAN): open exactly one port, 2224, from the lab to the rig, the same narrow exception as the Godot
   route's 2223. This is a router change and is not done by any script here.
3. **Rig, Administrator PowerShell:** copy this folder to the rig, then `.\Setup-RigAccount.ps1` (OpenSSH Server, restricted
   `uemcp` account, wrapper in `C:\watoom\rig-ue-mcp\`, the reviewed policy, sshd `Match User uemcp` block on port 2224, Windows
   Firewall rule for the lab address only).
4. **Lab, root, from `ansible/`:** `ansible-playbook -i inventories/homelab/hosts.yml playbooks/ue-mcp-ssh.yml`. It generates the lab key
   at `/data/ai/ue-mcp-ssh/`, prints the public key, and (once the rig's sshd answers) pins the rig's host key and stages the
   credentials in `/data/ai/watoom-code/config/watoom-tools/ue-mcp-credentials/`.
5. **Rig:** `.\Add-RigAuthorizedKey.ps1 -PublicKey '<printed key>' -UProject <full path>\MyGame.uproject` (writes the launcher and
   the forced-command key line; `-Version` defaults to the pinned 1.4.14, never `@latest`).
6. **Lab:** re-run step 4 so the host key is pinned, then test the route directly, holding the session open for a few seconds:
   ```bash
   ( printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
     '{"jsonrpc":"2.0","method":"notifications/initialized"}' ; sleep 8; \
     printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"tools","arguments":{"action":"call","category":"project","method":"get_status","args":{}}}}' ; sleep 6 ) | \
   ssh -i /data/ai/ue-mcp-ssh/key -o UserKnownHostsFile=/data/ai/ue-mcp-ssh/known_hosts -p 2224 uemcp@10.99.1.44
   ```
   Expect the `tools` gateway in `tools/list`, and the status of the open editor from `get_status`. A call refused by policy (only if you have closed something) comes back as `not allowed by the proxy policy`.
7. **Enable it in watoom-code (restarts the pod):** set `watoom_code_ue_mcp_enabled: true` in `ansible/vars/watoom-code.yml`, run
   `ansible-playbook playbooks/watoom-code-ue-mcp.yml` from `ansible/`, then `kubectl rollout restart deploy/watoom-code -n watoom-code`.
   The `opencode.json` template is seed-only, so `roles/watoom-code/tasks/ue_mcp.yml` (`files/enable-ue-mcp.py`) merges the `watoom-ue`
   entry (execution timeout 600 s: erosion and large imports are slow).

**Do not apply `manifests/10-infrastructure/opencode/watoom-code-ue-mcp-egress.yml` on its own.** The namespace has no
NetworkPolicies today; one egress policy selecting the pod turns the rest of its egress into default-deny (DNS, inference). Apply it only
together with the policies that keep the pod's other egress, and only once everything above works.

## Things to check on the first rig session

* **Bridge session token (found 2026-11-14).** The editor bridge refuses clients without a token it writes at startup, by default under
  the editor user's home, which `uemcp` cannot read (`requires a session token, and there is none at ...\.ue-mcp\bridge\63053.token`).
  `Add-RigAuthorizedKey.ps1` creates `C:\ProgramData\watoom\ue-mcp-bridge-tokens` (editor user modify, `uemcp` read only) and sets
  `UE_MCP_BRIDGE_TOKEN_DIR` in the launcher; the **editor must be started with the same variable**: `setx UE_MCP_BRIDGE_TOKEN_DIR
  "C:\ProgramData\watoom\ue-mcp-bridge-tokens"` as the editor's user, then close and restart the editor.

* `uemcp` can read the project and write what ue-mcp needs. The script grants read on the project and modify on `Saved\` only; if
  ue-mcp wants to write elsewhere (for example a `.ue-mcp` state folder) the launcher shows a permission error.
* ue-mcp keeps state under the user's home; the launcher points `HOME`/`USERPROFILE` at `C:\ProgramData\watoom\ue-mcp-home`.
* The editor-side bridge accepts the connection from a different Windows account (it listens on loopback only).
* A modal dialog in the editor blocks every action until answered (`dialogBlocking: true`); the models are told to report it.
* `region` objects for the landscape actions: use `tools(action="describe", category="landscape", method="set_layer_weight_region")`
  for the exact shape before the first write.

## Cutting access

Remove or rename `C:\ProgramData\ssh\uemcp_authorized_keys` on the rig, or `Disable-LocalUser -Name uemcp`, or stop sshd. To remove the
entry from watoom-code, set `watoom_code_ue_mcp_enabled: false`, re-run `playbooks/watoom-code-ue-mcp.yml` and restart the pod.

## Tests

`node test-ue-mcp-policy-wrapper.js` in this folder (Node; 15 tests against a stand-in server: micro and lean call shapes, the `flow`
bypass, unclassifiable calls, batches, list filtering). The reviewed policy and the cards are generated and verified by
`tools/language-knowledge/extract/ue_mcp_entries.py` and `manual_extract.py`.

## Asset check and fix (2026-11-17)

A bad asset used to surface late: a cut-off `.uasset` the editor skips, a name that stops scp half way, a manifest with scale 0 that places
an empty actor. Two offline tools (stdlib only, no rig, no editor) catch these first:

* `python3 ue_asset_check.py --pack PACKDIR [--dest F:/.../Content/] | --sources DIR | --manifest m.json | --layout village.json | --heights h.png`
  is read-only and prints one JSON report (`ok`, `summary`, and per asset a `severity` of error / warning / info with `code`, `message`,
  `fixable`). Exit 0 = no errors, 1 = errors (`--strict`: warnings too), 2 = bad command line. The checks and the reason for each are listed
  at the top of the script: packs (missing or empty Content, empty or cut-off packages, names Unreal or Windows refuse, case collisions,
  links, path length under `--dest`, packs that merge with different bytes), loose FBX / GLB / glTF / OBJ files (file tags, cut-off GLB,
  missing buffers / textures / mtllib, zero or NaN scale and bounds, formats with no import step, unsafe names), `ue_place_assets.py`
  manifests, `ue_village_build.py` layouts, and heights PNGs (16-bit greyscale, complete, one size).
* **Gate.** `rig_copy_pack.py` (packs, with `--dest`), `ue_place_assets.py` (manifest + heights) and `ue_village_build.py` (layout + both
  heights) run the check first, dry run included. On an error they print the findings on stderr and exit 1 before anything is copied, sent to
  the editor or saved; `--force-save` does not skip it. Only `rig_copy_pack.py` has an override, `--no-asset-check`.
* `python3 ue_asset_fix.py pack|sources|manifest SOURCE --out NEW [--apply]` repairs what the report marks `fixable`, in a copy. Dry run is
  the default; `--apply` writes the new folder (a full copy of the pack) or manifest plus a change log (`asset_fix_log.json` with the sha256
  of every file, or `<new>.fixlog.json`), never touches the original and refuses an `--out` that exists. Repairs: OS clutter left out, unsafe
  names of mesh source files and of non-package pack files sanitised, manifest asset paths / labels / kind normalised. Everything else is
  refused and reported, and then nothing is written: a `.uasset`, `.umap` or folder is never renamed (the package path is stored in the file
  and in every reference: rename it in the editor), a texture / `.mtl` / `.bin` is never renamed (the mesh finds it by name), and empty or
  cut-off files, case collisions, duplicate labels, zero / NaN scale and 8-bit heightmaps need a person. The checker later verifies a fixed
  copy against its log (`hash_mismatch`).

Not checked offline: what is inside a `.uasset` (its references, materials, textures), the inside of an FBX, and whether a `/Game/...` path
exists in the live project (only against a `--pack` given on the command line). Tests: `python3 -m unittest test_ue_asset_check test_ue_asset_fix`.

## Editor auto-start and the maintenance account (2026-11-14)

* **Start the editor without anyone opening it.** `editor.start_editor` on this route launches the editor through the rig's `WatooM-UeEditorStart`
  task (the `UeEditorTaskShim` described in `UE-route-verification.md` on the rig), but it gives up after about 150 s with a false "the editor
  process is gone - it exited during startup" while the editor is still booting; a cold start took 12 minutes. `python3 tools/rig-ue-mcp/ue_route.py ensure --max-wait 1200`
  (unit tests: `python3 -m unittest tools/rig-ue-mcp/test_ue_route.py`) calls `project.get_status`, starts the editor once if `editorConnected` is not
  true, ignores the false failure and polls until the bridge answers. Models do the same by hand: `project.get_status`, `editor.start_editor`, poll.
  Worker jobs (MetaHuman skin and similar, `unreal_runner.py`) start their own editor or commandlet and never needed this.
* **Maintenance account.** `Add-RigMaintenanceAccount.ps1 -PublicKey "<key.pub>" -Admin` (elevated PowerShell on the rig) creates the key-only local account
  `migrate` for the lab operator to fix workers, Unreal and Godot: password login disabled, accepted only from the lab server (10.99.20.225),
  no TCP forwarding, no expiry unless `-Hours N`; `-Remove` deletes it. The private key stays on the lab server in `/data/ai/rig-migrate-ssh/` (not in git).
  Connect with `ssh -i /data/ai/rig-migrate-ssh/key -o UserKnownHostsFile=/data/ai/ue-mcp-ssh/known_hosts -p 2224 migrate@10.99.1.44`; its default shell is cmd,
  so run PowerShell as `powershell -NoProfile -EncodedCommand ...` or upload a script. It is a full administrator on the rig: use it only for the owner's tasks.
  If every `migrate` login is reset during authentication while uemcp still works, the account is disabled (an earlier `-Hours` expiry ran
  `Disable-LocalUser`): `Get-LocalUser migrate` shows `Enabled False`. `Enable-LocalUser migrate` fixes it; the script re-enables it on a rerun since 2026-11-18.
* **Epic vault moved to F:.** `C:\ProgramData\Epic\EpicGamesLauncher\VaultCache` is a junction to `F:\UnrealData\VaultCache` (41 GB, 30,948 files, verified
  identical before the C: copy was deleted). A plain rename of that folder failed even as administrator because something held a directory handle on it; moving its
  children aside and converting the emptied folder to a junction in place (FSCTL_SET_REPARSE_POINT) worked.

## Water, lake and berm tools (2026-11-18, T-0049)

The procedures and the reasons are in the skill doc `watoom-texture-layering/references/unreal-scene.md` (sections "Lakes as WaterBodyLake, and
repairing a lake bed" and "Berms along creeks and around lakes"); each tool's docstring has its exact command line and each has a `test_*.py`.

* `ue_lake_as_waterbody.py` places or reuses a round `WaterBodyLake` and carves its bank. Modes for an existing lake: `--carve-only` (bed only),
  `--clear-water-first` (neutral the carve rectangle's Water layer first), `--materials-only` (materials and properties only, plus `--old-label` /
  `--delete-old`), `--recreate`. `ue_lake_as_river.py` is now only the shared lake library (its own river recipe floods and is refused).
* `ue_lake_check.py --lakes FILE` (read-only) reports a broken lake bed: sea_clamp, water_outside_ring, seam, dry_inside, missing_actor.
* `ue_water_fetch.py --out water.json` (read-only) writes every creek (spline, water level, `RiverWidth`), lake and the sea level; it feeds
  `scripts/unreal_water_berms.py`, which plans berms along creeks and around lakes so no water shows past its shape.
* `ue_run_phases.py` applies every height calls json and subtracts the lake beds' Water-layer offset; never apply height calls another way.
* `ue_heights_fetch.py` writes the merged (visible) heights: on this map the `editLayer:"Layer"` read is wrong along x=126 and y=126.
* `ue_creek_foliage.py` refits foliage after a carve or berm: receipt first (`--out-removed`), re-adds in batches (`--add-batch`, a 2031-instance
  call crashed the editor). `ue_foliage_buried.py` writes its receipt before each removal.
* `ue_viewport_shot.py --around X Y Z R` captures the owner's view unmoved, then seven views around the subject, and puts the camera back; the
  image comes back inline over the normal route (the `migrate` scp pull is only a fallback).

## Look check (2026-11-18, T-0027)

`ue_look_check.py` (read-only) compares the level's look settings with the recipe that worked and exits 1 on any drift: the star dome's
`MI_Star_Nebula_*` override (a dome on its black base material makes auto exposure wash the scene out), sun and sky light, post-process values
*and* their `bOverride_*` flags (a value without its flag is ignored), and the leaf `Contrast` / `SS Power`. Run it after an editor crash,
restart or `level.load`, and before judging colour work. `--checks FILE` takes the same checks as JSON for another level.

Since the atmosphere pass (2026-11-18) the default checks also cover the locked exposure (Min = Max 0.45 with override flags), the nebula
`Power` (an exponent, higher is dimmer), the SkyAtmosphere distance-haze scale, the cloud material and layer, cloud coverage and the height fog
(29 checks). The settings themselves come from the skill script `unreal_atmosphere.py` (apply with `ue_run_phases.py`).

**Any game:** `ue_look_check.py --from-calls atmo.json` builds the checks from whatever calls file the pipeline applied and resolves actors
by label, so it needs no per-game check list. `ue_look_probe.py --out-dir DIR [--sweep-exposure 0.3 0.45 0.6 --post-process LABEL]` measures
ground brightness over the owner's view and four horizon views (per exposure value), restores the exposure and camera, and names the
value closest to `--target`; put it in the profile's `exposure` for `unreal_atmosphere.py`.

## Building a C++ code plugin for the rig project (2026-11-18, T-0063)

The rig project is Blueprint-only and its ue-mcp bridge is a **binary-only** plugin (`"Installed": true`, no `Source/`). So a project-level
build (`project.build`, or putting plugin source in `Plugins/`) always fails before compiling anything:
`Could not find definition for module 'UE_MCP_BridgeStatus'` (RulesError). A source plugin left in `Plugins/` also stops the next editor start
at "missing modules". Build the plugin on its own instead and install the binaries, exactly the way the bridge is installed:

1. Lint: stage the source outside `Plugins/` (`rig_copy_pack.py --plugin --apply <plugin> --dest "<project>/Saved/"`), then
   `project.lint_cpp_header {"path": "<project>/Saved/<P>/Source/<P>/Public/X.h", "buildCsPath": ".../<P>.Build.cs"}` per header. The
   result's list is `findings` (not `issues`). Known false positive: `FTransform` -> "Chaos/Transform.h" + module `Experimental`; ignore it.
2. Build (migrate account, editor may keep running; ~2.5 min):
   `RunUAT.bat BuildPlugin -Plugin="<project>\Saved\<P>\<P>.uplugin" -Package="<project>\Saved\<P>Pkg" -TargetPlatforms=Win64 -Rocket`
   Needs MSVC (`project.check_install` -> `toolchain.present`) AND the .NET Framework 4.8 SDK, which the VCTools workload leaves out:
   UAT then fails with `Could not find NetFxSDK install dir` (RulesError). Add it with the VS installer
   (`setup.exe modify --installPath "...\2022\BuildTools" --add Microsoft.Net.Component.4.8.SDK --add Microsoft.Net.Component.4.8.TargetingPack --quiet --norestart`;
   `setup.exe` has no `--wait`, exit 87 means a bad option, so wait on the process). A BuildPlugin build treats the module like an engine
   module: every exposed UPROPERTY needs an explicit `Category` (UHT error otherwise).
3. Install with the editor STOPPED: copy the package (without `Intermediate/`) to `<project>/Plugins/<P>` (its .uplugin has
   `"Installed": true`), start the editor, then check the log for `InternalLoadLibrary: '<P>'` and read a class default, e.g.
   `editor.get_property {"objectPath": "/Script/<P>.Default__<Class>", "propertyName": "..."}`. `editor.start_editor` may report
   "exited during startup" while the editor is still coming up: poll `project.get_status` for `editorConnected`.
4. After a source change: rebuild into a fresh `<P>Pkg` and replace `Plugins/<P>` with the editor stopped.
5. All of the above in one tested command: `rig_build_plugin.py <plugin dir> [--install --check-class /Script/<M>.Default__<C>
   --check-prop <prop>]`. It never copies while this project's editor process exists (matched by command line), installs nothing
   after a failed build, and prints the compiler/UHT error lines.

## Checking Niagara effects (`ue_fx_check.py`)
`ue_fx_check.py --from-calls fx_calls.json` validates each system made by unreal_niagara_fx.py, places it on a temporary actor,
reactivates it and reads the sim cache: particles, colour range and spread per emitter; exit 1 on an invalid system or an
emitter with no particles. Emitters with Lifetime Max < 0.25 s are SKIP (they die between reactivate and capture). Screenshots
cannot judge bursts; this can.

## Importing an FBX character or creature (`rig_import_fbx_character.py`)
`rig_import_fbx_character.py --name N --dest /Game/.../N --mesh skinned.fbx --anim Walk=walk.fbx [--anim Run=run.fbx]
[--textures-from DIR] --apply` copies the files (and their textures) to `<project>/Saved/Import/N/` with the maintenance account,
imports SK_N with its own skeleton and physics asset, and each clip as A_N_<Clip> on that skeleton. Without --apply it prints the
plan. A clip FBX that carries the skin (`*_withSkin.fbx`) is a good --mesh: the skeleton is then the one the clips were made on.
Next: `ue_mesh_body.py` for the body, then a combat spec (anim_set + character; `Wander.bEnabled` for roaming).

## Parameter schemas (`ue_route.py describe cat.method`)
The one-line tool reference does not document nested params (e.g. a stackInputRef object). `ue_route.py describe
niagara.set_module_input` asks the gateway for the full schema (describe is always answered; only calls are policy-filtered).
It also tells you an action is missing on the rig's ue-mcp version (the reply lists the actions that exist).

## Unsaved work and the plugin install (2026-11-19)
`rig_build_plugin.py --install` lists the editor's dirty packages (`editor.list_dirty_packages`) and refuses BEFORE stopping it
when project content is unsaved: the stop opens a modal "Save Content" dialog, dialog mode "defer" means only a person can
answer it, and ending the editor loses the work. `asset.import_animation` and `asset.import_static_mesh` do not save:
`rig_import_fbx_character.py` (also `--static` for statues/props) saves what it imported plus any dirty package under its
destination. `ue_stray_check.py --underground-prefixes` (profile `underground_label_prefixes`) leaves a dungeon alone.

## Long reads survive a daemon restart (`ue_route.call_read`)
The ue-mcp daemon on the rig can restart mid-call (JSON-RPC -32001 "daemon stopped while this call was in flight"); a 15-minute
foliage scan died that way with nothing done. `ue_route.call_read(t, cat, method, args)` retries such a READ (never a write,
whose outcome is then unknown); ue_stray_check.py's paged foliage reads use it.

## Project plugin switches as code (`rig_project_plugins.py`)
`project_plugins.json` lists the plugins whose on/off state matters, each with the reason; `rig_project_plugins.py` shows the
difference to the rig's .uproject and `--apply` writes it (editor stopped, backup kept). Only the named plugins are touched.
`MeshPartitionWater` is OFF: enabled, every foliage add crashed the editor (T-0061, bisected 2026-11-19).

## Upgrading ue-mcp (2026-11-19, 1.4.13 -> 1.4.14)
1. Lab: `npm pack ue-mcp@V` and unpack it (never install or run it); fetch docs/tool-reference.md, configuration.md and guards.md
   at tag vV into `tools/language-knowledge/manuals/ue-mcp/sources/`; `extract/ue_mcp_entries.py derive --package <unpacked>`
   then `build --policy-out ue-mcp-policy.reviewed.json`; review the policy diff (a new category stays blocked until reviewed);
   `manual_extract.py --product ue-mcp` must report 0 failures. Bump the pins (Add-RigAuthorizedKey.ps1 default, this README,
   docs/guide/watoom-code.md, source.json).
2. Rig: copy `<unpacked>/plugin/ue_mcp_bridge` to a folder named `UE_MCP_Bridge` and build it:
   `rig_build_plugin.py <dir>/UE_MCP_Bridge` (~45 min, editor untouched). Then, after a note on T-0049,
   `rig_build_plugin.py <dir>/UE_MCP_Bridge --install --reuse-build --ue-mcp-version V`: one editor stop, the bridge binaries and
   the uemcp launcher pin change together, editor start. A stop reply whose log already says `exiting` is waited out.
3. Check: `project.get_status` connected; the plugin's VersionName and `findstr ue-mcp@ run-ue-mcp.cmd` show V.
The `epic_*` actions of a category (e.g. niagara.epic_set_stack_input_data) exist only when that engine toolset plugin is enabled
in the project (NiagaraToolsets, ...: `epic.list_toolsets` lists the live ones). On 1.4.13 and 1.4.14 alike they were "Unknown
action" until NiagaraToolsets went into project_plugins.json; `rig_build_plugin.py --install --project-plugins` applies that file
in the same editor restart as a plugin install.

## Checking combat in PIE (`ue_combat_check.py`)
`ue_combat_check.py --from-calls combat_calls.json [--net]` replays the combat slice checks from the generated calls: melee on
the first dummy, every spell (aimed from the real camera), consumable pickups, and with --net a listen server + client run
(client hit applied on the server, teammates immune). It restores the editor throttle and play settings afterwards.

## Character bodies for any skeleton (`ue_mesh_body.py`)
`ue_mesh_body.py --out bodies.json /Game/.../SK_Mesh ...` measures how a skeletal mesh sits in a Character capsule: facing (toes vs
ankles, else head vs pelvis/root, snapped to an axis), capsule radius (sideways reach of the leg bones, >= 0.18 x height), half
height and the mesh offset/rotation. Works for bipeds, quadrupeds, dragons. `unreal_combat.py` reads the file (`bodies_file`).
Measured: Manny r 32 hh 90 (-90 cm, yaw -90, the Unreal convention); Wildwood-free dragon r 328 hh 438, facing from its head.
