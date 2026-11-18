---
name: ursina
description: Use for Python projects built with Ursina Engine, including Entities, update/input loops, UI, collisions, prefabs, assets, Panda3D integration, and Ursina-specific game architecture.
---

<!-- WATOOM-URSINA-PYTHON-ENV-GATE-BEGIN -->

## Python environment prerequisite

Apply the Python skill's existing-environment hard gate before any dependency or
virtual-environment operation.

When `.venv-opencode/bin/python` exists or the assignment names it, use it
directly for Ursina/Panda3D imports, compilation, runtime checks, and headless
capture.

Do not:

- try system `pip` first;
- create another venv after a PEP 668 error;
- substitute `python3` for the project interpreter;
- install Ursina/Panda3D merely because they were not tested yet.

First test imports with the authoritative interpreter.

For a task that prohibits dependency changes, a genuine missing dependency is a
BLOCKED validation result, not authorization to install it.

<!-- WATOOM-URSINA-PYTHON-ENV-GATE-END -->

# Ursina Engine

Use this skill for Ursina projects together with the general `python` skill.

Determine the actual Python and Ursina versions from the project environment
before using version-specific behavior.

## Python environment

Inspect:

- `pyproject.toml`;
- requirements files;
- lockfiles;
- virtual environments;
- existing scripts/tests.

Keep dependencies project-local.

Do not install Python packages globally.

## Ursina application structure

Prefer the project's existing Ursina architecture.

Common concepts include:

- `Ursina`;
- `Entity`;
- `Text`;
- `Button`;
- camera;
- `update()`;
- `input(key)`;
- held keys;
- prefabs;
- invoke/sequences;
- scene/entity hierarchy.

Do not create a second game loop around Ursina.

## Entities

Before changing entities inspect:

- parent/child relationships;
- local versus world transforms;
- enabled/visible state;
- model;
- texture;
- material;
- shader;
- collider;
- attached custom behavior.

Avoid unnecessary per-frame Entity creation.

## Input

Distinguish:

- discrete `input(key)` events;
- held-key polling;
- UI input;
- gameplay input.

Do not duplicate input handling across several mechanisms without a reason.

## Timing

Do not hardcode assumed frame rates.

Use the project's existing timing approach and appropriate Ursina/Panda3D
timing facilities.

Keep frame-rate-independent movement deliberate.

## Collision and physics

Determine whether the project uses:

- Ursina colliders;
- raycasts;
- custom movement;
- Panda3D physics;
- another physics integration.

Do not assume an Entity collider provides a full rigid-body simulation.

## Assets

Preserve project asset conventions.

Inspect how the project loads:

- models;
- textures;
- shaders;
- audio;
- fonts.

Use portable paths and avoid assumptions about the process working directory.

## Panda3D boundary

Ursina is built on Panda3D.

Use direct Panda3D APIs only when:

1. Ursina does not expose the required feature; or
2. the existing project already uses Panda3D directly.

Make that boundary explicit.

## Performance

Inspect before optimizing.

Watch for:

- excessive Entity creation/destruction;
- unnecessary work in `update()`;
- repeated asset loading;
- expensive collision/raycast loops;
- per-frame Python allocations.

Prefer reuse/pooling when the project needs it.

## Validation

Prefer:

1. Python syntax/import validation;
2. existing unit tests;
3. targeted Entity/component tests;
4. smallest relevant game scene;
5. runtime console output.

In headless environments, do not assume window/render creation is available.

Use the `python` skill for general Python packaging, testing, typing, and
dependency practices.

## Headless graphical smoke testing

When Mesa and Xvfb are available in the OpenCode container, use
software-rendered headless graphical smoke tests for Ursina projects.

Use the project-local interpreter explicitly. Do not rely on virtualenv
activation.

Compile and import validation:

    .venv-opencode/bin/python -m py_compile main.py
    .venv-opencode/bin/python -c 'import ursina, panda3d; print("imports OK")'

OpenGL validation:

    LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a glxinfo -B

Bounded graphical startup test:

    LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a timeout --signal=TERM --kill-after=2s 10s .venv-opencode/bin/python main.py

For a normal persistent game loop, timeout status 124 after successful startup
is expected and counts as a successful bounded smoke test.

A Python traceback, import error, display/OpenGL initialization failure, or
another non-timeout non-zero exit is a failure.

Do not claim visual correctness from Xvfb. It validates graphical
initialization and bounded runtime, not appearance.

<!-- WATOOM_URSINA_HEADLESS_VALIDATION_START -->
## Project venv and headless Ursina validation

For an existing Ursina project containing `.venv-opencode`, all project
Python inspection, execution and validation must use:

`.venv-opencode/bin/python`

Do not silently fall back to system Python.

### Project venv

Verify:

`test -x .venv-opencode/bin/python`

Then:

`.venv-opencode/bin/python -c 'import sys; print("PYTHON_EXECUTABLE =", sys.executable); print("VENV_PREFIX =", sys.prefix); print("BASE_PREFIX =", sys.base_prefix); assert sys.prefix != sys.base_prefix; print("PROJECT_VENV=PASS")'`

Verify Ursina and Panda3D from the same interpreter:

`.venv-opencode/bin/python -c 'import sys, ursina, panda3d; print("PYTHON_EXECUTABLE =", sys.executable); print("URSINA_IMPORT=PASS"); print("PANDA3D_IMPORT=PASS")'`

Compile with:

`.venv-opencode/bin/python -m py_compile main.py`

### Headless graphics

Never infer graphics availability solely from conversation history, compacted
context or the fact that the environment is headless.

Check the current runtime:

`command -v Xvfb`

`command -v xvfb-run`

`command -v glxinfo`

Verify software OpenGL:

`LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a -s "-screen 0 1280x720x24" glxinfo -B`

Mesa llvmpipe is a valid software OpenGL renderer for headless graphical
testing.

### Bounded real-game test

Use the actual project venv:

`LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a -s "-screen 0 1280x720x24" timeout --signal=TERM --kill-after=2s 10s .venv-opencode/bin/python main.py`

For this bounded test:

- return code `124` after successful initialization means PASS;
- traceback means FAIL;
- import failure means FAIL;
- Panda3D/OpenGL initialization failure means FAIL;
- OpenAL NullAudioManager fallback is acceptable;
- PNG iCCP warnings are non-fatal.

A successful bounded startup verifies graphical initialization and continued
execution. It does not verify visual appearance.

### Actual framebuffer screenshot

When visual evidence is requested, capture an actual framebuffer image from
the real running Panda3D/Ursina application.

Do not merely print a hypothetical command.

Do not recreate a simplified substitute scene.

Before creating a harness, inspect the installed Ursina/Panda3D APIs using
`.venv-opencode/bin/python` or installed package source.

Do not guess the screenshot API.

A temporary screenshot harness must still run using:

`.venv-opencode/bin/python`

Keep temporary validation harnesses inside the active project/worktree. Prefer:

- `.opencode/validation/` for temporary Python validation harnesses;
- `.opencode/captures/` for framebuffer captures and related evidence.

Do not place Ursina validation harnesses or captures under `/tmp`, `/var/tmp`,
the user's home directory, or another external directory.

If needed, set `PYTHONPATH` to the project root so the project-local temporary
harness can import project code.

When validation requires the project interpreter, attempt the actual native
shell call. Do not infer a permission failure from the absence of a
command-specific `python3` pattern. Report BLOCKED only after an actual tool
call is denied or otherwise cannot execute.

The harness must:

1. use the existing game implementation;
2. initialize the actual scene;
3. allow several frames to render;
4. capture the actual Panda3D/Ursina framebuffer;
5. save the PNG;
6. terminate cleanly.

Verify that the output:

- exists;
- is non-empty;
- is a valid image;
- has expected dimensions.

Report:

- Python executable;
- venv status;
- OpenGL vendor;
- OpenGL renderer;
- OpenGL version;
- actual screenshot API used;
- PNG path;
- dimensions;
- file size;
- relevant rendering output;
- PASS or FAIL.

Current runtime evidence overrides stale session summaries.
<!-- WATOOM_URSINA_HEADLESS_VALIDATION_END -->
