---
name: rust
description: Use for Rust crates, Cargo dependencies, compiler errors, tests, clippy, ownership-safe refactors, and Rust services/tools.
---

# Rust

- Inspect `Cargo.toml` and workspace layout first.
- Preserve ownership/lifetime intent; avoid unnecessary clones to silence the compiler.
- Prefer typed errors consistent with the project.
- Run `cargo fmt --check`, targeted tests, and `cargo clippy` when configured.
- Keep dependency additions minimal.
