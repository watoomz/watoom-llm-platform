# Python rules
- Inspect pyproject.toml/setup.cfg/tox.ini/requirements and existing tests before choosing tools.
- Use the existing environment/dependency workflow and detect the actual test framework; never assume pytest.
- Preserve typing, packaging, import, formatter and linter conventions.
- Do not add dependencies without a task-backed reason or restructure modules unnecessarily.
- Run the smallest focused test first.
