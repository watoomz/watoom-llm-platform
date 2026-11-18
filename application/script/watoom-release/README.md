# WatooM Code Linux development validation package

This package contains the native CLI/backend and embedded web frontend. It is a development validation build. Full release acceptance remains open for authenticated skill approval administration, native AgentMemory delivery/restart acceptance, generic specialist runtime admission, optional component controls, and visual UI acceptance. Do not use it for production cutover.

Run `sh install.sh --prefix /absolute/user/chosen/path --profiles minimal,developer`. The installer verifies checksums, keeps versioned executables, installs profile configuration using the native CLI, and atomically publishes `bin/watoom-code`. Docker, configured immutable CPU images, external services, and GPU authority are prerequisites rather than bundled workloads. No production database is migrated by packaging.

Start an isolated backend with `bin/watoom-code serve --hostname 127.0.0.1 --port <unused-port>` in a disposable HOME/XDG environment first. Foreground startup prints a private pairing credential; keep its output private. The same executable serves its embedded frontend.

Upgrade: use the same prefix and explicitly selected profiles. Preserve the profile transaction receipt under `releases/<release-id>/profile-install.json`. Configuration remains in the native user configuration location; installation preserves unrelated JSONC fields.

Rollback: stop only your disposable development process. Read the transaction from the receipt and run `bin/watoom-code profiles rollback --scope user --transaction <transaction>`. Rollback refuses later configuration edits. If `previous-executable.txt` exists, verify its path points to a retained release under your prefix and repoint the executable symlink to that retained file. Restart your development process. Existing production processes are outside this installer.

`provenance.json` records the source commit, build command and outstanding acceptance gates. `SHA256SUMS` covers every packaged payload file except itself. Keep source and IaC evidence separately; development backup directories are never packaged.
