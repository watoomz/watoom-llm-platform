---
name: godot-3
description: Use for Godot 3.x projects, including GDScript, scenes, nodes, UI, physics, resources, editor tooling, exports, and Godot-3-specific APIs.
---

# Godot 3

Use this skill only for Godot 3.x projects.

Determine the exact engine version from the project/environment before making
version-sensitive changes.

## Version boundary

Never silently use Godot 4 APIs in Godot 3 code.

Typical Godot 3 concepts include:

- `Spatial`;
- `KinematicBody` / `KinematicBody2D`;
- `PackedScene.instance()`;
- `yield()`;
- `PoolByteArray` and other Pool arrays;
- Godot 3 signal connection forms;
- Godot 3 `export`, `onready`, and `tool` syntax.

Do not replace these with Godot 4 equivalents unless performing an explicitly
requested migration.

## Inspect first

Before editing inspect:

- `project.godot`;
- representative `.gd` files;
- representative `.tscn` files;
- addons/plugins;
- autoloads;
- input actions;
- collision layers/masks.

Preserve existing project conventions.

## GDScript

Use Godot 3-compatible syntax.

Do not introduce Godot 4-only:

- `@export`;
- `@onready`;
- `@tool`;
- `await`;
- `Node3D`;
- `CharacterBody2D`;
- `CharacterBody3D`.

Preserve engine callback names exactly.

## Scenes and resources

Treat these as structured engine data:

- `.tscn`;
- `.tres`;
- `.res`;
- `project.godot`.

Avoid rewriting complete scene files for small changes.

Preserve:

- node paths;
- ownership;
- resource references;
- groups;
- signals;
- collision configuration.

## Physics

Inspect existing:

- `move_and_slide()`;
- `move_and_collide()`;
- physics process usage;
- floor/up direction;
- collision layers and masks.

Do not copy Godot 4 CharacterBody examples directly into Godot 3.

## Validation

Prefer:

1. determine exact Godot version;
2. parse/load project;
3. run project-specific tests if present;
4. run the smallest affected scene;
5. inspect engine errors/warnings.

Do not upgrade a Godot 3 project to Godot 4 unless explicitly requested.
