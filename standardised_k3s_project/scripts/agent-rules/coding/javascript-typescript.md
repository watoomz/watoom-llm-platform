# JavaScript / TypeScript rules
- Detect the package manager from metadata/lockfiles; do not switch npm/pnpm/yarn.
- Use existing package scripts and inspect package.json, tsconfig, lint/format/test configuration first.
- Do not regenerate lockfiles unless dependency state legitimately changes or add dependencies for preference.
- Preserve module-system/TypeScript conventions and detect the actual test framework.
