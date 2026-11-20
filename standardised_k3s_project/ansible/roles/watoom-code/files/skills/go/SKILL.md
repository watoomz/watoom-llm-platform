---
name: go
description: Use for Go modules, packages, tests, formatting, static analysis, and Go service implementation.
---

# Go

- Inspect `go.mod` and package boundaries first.
- Prefer standard-library solutions when adequate.
- Preserve context cancellation and error propagation.
- Use `gofmt` on changed Go files.
- Run targeted `go test` first, then broader tests as required.
- Do not introduce hidden goroutine/process leaks.
