# Go rules
- Preserve module/package structure; gofmt changed Go files when applicable.
- Test affected packages first and use go vet when configured/appropriate.
- Do not run go get or add modules casually; avoid unnecessary interfaces/abstractions.
- Preserve project error-handling/context conventions.
