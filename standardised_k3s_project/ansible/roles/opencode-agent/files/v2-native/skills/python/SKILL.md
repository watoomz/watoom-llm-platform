---
name: python
description: Use for Python implementation, scripts, tests, packaging, type-aware refactors, and project-local Python dependency work.
---

<!-- WATOOM-PYTHON-ENV-GATE-BEGIN -->

## Existing-environment hard gate

This gate runs before dependency installation, virtual-environment creation, or
interpreter substitution.

Before executing any command equivalent to:

- `pip install`
- `pip3 install`
- `python -m pip install`
- `python3 -m pip install`
- `python -m venv`
- `python3 -m venv`
- `virtualenv`
- `uv venv`
- `poetry env`
- `conda create`

first determine whether the project already defines an authoritative Python
environment.

Use this precedence:

1. explicit assignment instructions;
2. project-local environment such as `.venv-opencode`, `.venv`, or `venv`;
3. repository/AGENTS instructions;
4. `pyproject.toml`, requirements files, lockfiles, and toolchain configuration.

If the assignment names an interpreter such as:

`.venv-opencode/bin/python`

that exact project environment is authoritative.

Before considering installation, first test the required import or command with
the authoritative project interpreter.

Do not create another virtual environment merely because:

- system `pip` is blocked by PEP 668;
- system Python reports `externally-managed-environment`;
- `python3` resolves to the system interpreter;
- activation does not persist between shell calls;
- an import failed under a different or incorrect interpreter.

PEP 668 protects the system Python. It is not an instruction to create another
project environment.

Activation is not required when the interpreter can be called directly. Prefer:

`.venv-opencode/bin/python ...`

over relying on `source .../bin/activate`.

If an existing project environment is present, do not replace, recreate,
upgrade, or shadow it unless the assignment explicitly requests that operation.

If the assignment prohibits installs or environment creation, an import or
dependency failure must be reported as an environment finding or blocker. It
does not authorize `pip install` or creation of another venv.

Never create a sibling or parent-directory venv as a workaround for a valid
project-local environment.

<!-- WATOOM-PYTHON-ENV-GATE-END -->

# Python

- Inspect `pyproject.toml`/requirements/test layout before adding dependencies.
- Preserve project formatter/linter/test conventions.
- Prefer explicit exceptions and deterministic cleanup.
- Avoid global/system package installation for project dependencies.
- Add focused tests for behavior changes.
- Run the narrowest tests first, then the project-required validation.

<!-- WATOOM_PROJECT_VENV_POLICY_START -->
## Existing project virtual-environment policy

When an existing project virtual environment is present, its interpreter is
authoritative for project execution, imports and validation.

For `.venv-opencode`, use:

`.venv-opencode/bin/python`

Verify it before testing:

`test -x .venv-opencode/bin/python`

Then verify the actual interpreter:

`.venv-opencode/bin/python -c 'import sys; print("PYTHON_EXECUTABLE =", sys.executable); print("VENV_PREFIX =", sys.prefix); print("BASE_PREFIX =", sys.base_prefix); assert sys.prefix != sys.base_prefix; print("PROJECT_VENV=PASS")'`

Use the explicit interpreter for project commands:

`.venv-opencode/bin/python -m py_compile main.py`

`.venv-opencode/bin/python -m pytest`

`.venv-opencode/bin/python -m pip list`

`.venv-opencode/bin/python -m pip show PACKAGE`

Do not use bare `python`, `python3`, `pip`, `pip3` or `pytest` for project
validation when an authoritative project venv exists.

Do not rely on shell activation persisting across tool calls.

Do not silently:

- recreate the venv;
- replace the venv;
- upgrade the venv;
- install missing packages;
- fall back to system Python.

Temporary diagnostic, rendering and screenshot scripts must also execute with
the project interpreter.

A successful system-Python test does not count as project validation.
<!-- WATOOM_PROJECT_VENV_POLICY_END -->
