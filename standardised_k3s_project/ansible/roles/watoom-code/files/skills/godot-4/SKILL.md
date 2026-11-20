---
name: godot-4
description: Use for Godot 4.x projects, including modern GDScript, Node3D and CharacterBody APIs, scenes, resources, rendering, UI, physics, plugins, exports, and Godot-4-specific behavior.
---

# Godot 4

Use this skill only for Godot 4.x projects.

Determine the exact Godot 4 minor version before relying on version-specific
APIs or engine behavior.

## Version boundary

Do not mix Godot 3 APIs into Godot 4 code unless performing an explicit
migration.

Typical Godot 4 concepts include:

- `Node3D`;
- `CharacterBody2D`;
- `CharacterBody3D`;
- `PackedScene.instantiate()`;
- `await`;
- `PackedByteArray` and other Packed arrays;
- `Callable`;
- `@export`;
- `@onready`;
- `@tool`.

## Inspect first

Before editing inspect:

- `project.godot`;
- representative `.gd`;
- `.tscn`;
- `.tres`;
- addons/plugins;
- renderer configuration;
- physics configuration;
- input map;
- autoloads.

Use the project's actual engine version and conventions.

## GDScript

Preserve the project's typing level and style.

Keep:

- lifecycle callbacks correct;
- signal connections deliberate;
- async behavior explicit;
- node ownership/path behavior intact.

Do not weaken types merely to suppress errors.

## Scenes and resources

Avoid broad textual rewrites.

Preserve:

- node ownership;
- node paths;
- resource IDs;
- signal connections;
- project settings;
- input actions;
- layers and masks.

Do not treat `.godot/` generated state as source.

## Character movement

For CharacterBody controllers inspect:

- `velocity`;
- `move_and_slide()`;
- physics processing;
- floor/wall/ceiling state;
- collision layers/masks;
- gravity ownership.

Do not blindly port Godot 3 movement code.

## Rendering

Determine the active renderer before changing:

- shaders;
- materials;
- environment;
- post-processing;
- renderer-specific features.

Do not assume Forward+, Mobile, and Compatibility capabilities are identical.

## Godot 3 migration

For an explicit migration:

1. inventory Godot 3 APIs actually used;
2. make bounded mechanical changes;
3. handle behavioral changes separately;
4. validate scenes/scripts after each stage;
5. avoid unrelated refactoring during migration.

## Validation

Prefer:

1. exact engine version;
2. project/headless parse when supported;
3. project tests;
4. smallest relevant scene;
5. engine errors/warnings;
6. export validation only when required.
